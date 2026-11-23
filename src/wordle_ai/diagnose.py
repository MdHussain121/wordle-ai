"""`diagnose`: a fail-closed health check for a built installation (Phase 8, task 5).

Each check answers one question with one of four statuses: ``ok``, ``warn``,
``fail`` or ``blocked``. A ``fail`` means the installation cannot be trusted for the
configuration it was pointed at; a ``warn`` means it works with a documented
degradation; ``blocked`` means the check cannot run here (no git repository, for
example), and the reason is recorded instead of being reported as a pass.

Messages are distinct per condition (missing table vs checksum mismatch vs profile
mismatch) so a failure names the thing that is wrong rather than "integrity error".
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .buildinfo import build_info
from .config import load_config
from .errors import WordleError
from .lexicon.profile import TABLE_NAME, load_profile, read_manifest
from .solver.policy import load_policy
from .types import Profile, RuleMode


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # ok | warn | fail | blocked
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "detail": self.detail,
        }


def _check_build() -> Check:
    info = build_info()
    return Check(
        "build",
        "ok",
        f"wordle-ai {info['version']} on python {info['python']} ({info['platform']})",
        info,
    )


def _check_config(config_path: Path) -> Check:
    try:
        settings = load_config(config_path)
    except WordleError as exc:
        return Check("config", "fail", f"configuration is invalid: {exc}", {"path": str(config_path)})
    return Check(
        "config",
        "ok",
        f"configuration loaded from {config_path}",
        {"path": str(config_path), "data_dir": settings.general.data_dir},
    )


def _check_profile(profile_dir: Path, expected_id: str) -> tuple[Check, Profile | None]:
    if not profile_dir.exists():
        return (
            Check(
                "profile",
                "fail",
                f"profile directory does not exist: {profile_dir}",
                {"path": str(profile_dir)},
            ),
            None,
        )
    try:
        profile = load_profile(profile_dir)
    except WordleError as exc:
        return (
            Check(
                "profile",
                "fail",
                f"profile is not loadable: {exc}",
                {"path": str(profile_dir)},
            ),
            None,
        )
    if profile.profile_id != expected_id:
        return (
            Check(
                "profile",
                "fail",
                f"profile mismatch: {profile_dir} holds {profile.profile_id!r}, "
                f"not the requested {expected_id!r}",
                {"expected": expected_id, "found": profile.profile_id},
            ),
            profile,
        )
    return (
        Check(
            "profile",
            "ok",
            f"{profile.profile_id}: {len(profile.answers):,} answers, "
            f"{len(profile.guesses):,} guesses, manifest verified",
            {
                "answers": len(profile.answers),
                "guesses": len(profile.guesses),
                "manifest_sha256": profile.manifest_sha256,
            },
        ),
        profile,
    )


def _check_table(profile_dir: Path, profile: Profile | None) -> Check:
    if profile is None:
        return Check("table", "warn", "table not checked because the profile failed to load")
    try:
        manifest = read_manifest(profile_dir)
    except WordleError as exc:
        return Check("table", "fail", f"table check cannot read the manifest: {exc}")
    recorded = manifest.outputs.feedback_table
    if not recorded:
        return Check(
            "table",
            "warn",
            "no feedback table is recorded; rows are computed on demand",
            {"path": None},
        )
    path = Path(recorded)
    if not path.is_absolute():
        # Manifests written by this project record project-relative paths.
        candidate = profile_dir / TABLE_NAME
        path = candidate if candidate.exists() else path
    if not path.exists():
        return Check(
            "table",
            "fail",
            f"feedback table is missing: {path}",
            {"path": str(path)},
        )
    from .lexicon.source import sha256_file

    actual = sha256_file(path)
    if actual != manifest.outputs.table_sha256:
        return Check(
            "table",
            "fail",
            f"table checksum mismatch: {path} has {actual[:16]}…, manifest records "
            f"{str(manifest.outputs.table_sha256)[:16]}…",
            {"path": str(path), "actual": actual, "expected": manifest.outputs.table_sha256},
        )
    try:
        array = np.load(path, mmap_mode="r", allow_pickle=False)
    except Exception as exc:  # pragma: no cover - corrupt file path
        return Check("table", "fail", f"table is unreadable: {path}: {exc}")
    expected_shape = (len(profile.guesses), len(profile.answers))
    if array.dtype != np.uint8:
        return Check(
            "table",
            "fail",
            f"table dtype is {array.dtype}, expected uint8",
            {"path": str(path)},
        )
    if tuple(array.shape) != expected_shape:
        return Check(
            "table",
            "fail",
            f"table shape {tuple(array.shape)} does not match the profile's {expected_shape}",
            {"path": str(path)},
        )
    return Check(
        "table",
        "ok",
        f"{path.name}: {expected_shape[0]:,}x{expected_shape[1]:,} uint8, checksum verified",
        {"path": str(path), "sha256": actual, "bytes": path.stat().st_size},
    )


def _check_policy(
    policy_path: Path | None,
    profile: Profile | None,
    *,
    mode: RuleMode,
    prior: str,
    attempts: int,
) -> Check:
    if policy_path is None:
        return Check("policy", "warn", "no policy artifact was given")
    if profile is None:
        return Check("policy", "warn", "policy not checked because the profile failed to load")
    try:
        payload = load_policy(
            policy_path,
            profile=profile,
            mode=mode,
            prior=prior,
            attempts=attempts,
        )
    except WordleError as exc:
        message = str(exc)
        if "checksum" in message:
            return Check(
                "policy",
                "fail",
                f"policy checksum mismatch (stale or tampered artifact): {policy_path}",
                {"path": str(policy_path), "error": message},
            )
        if "profile" in message or "answer" in message:
            return Check(
                "policy",
                "fail",
                f"policy profile mismatch: {message}",
                {"path": str(policy_path), "error": message},
            )
        return Check(
            "policy",
            "fail",
            f"policy rejected: {message}",
            {"path": str(policy_path), "error": message},
        )
    return Check(
        "policy",
        "ok",
        f"{policy_path.name}: {payload['profile_id']} {payload['rules']} "
        f"prior={payload['prior']} attempts={payload['attempts']}, checksum verified",
        {"path": str(policy_path), "sha256": payload["sha256"]},
    )


def _check_prior(data_dir: Path) -> Check:
    report = data_dir / "bench" / "phase5" / "calibration.json"
    if not report.exists():
        return Check(
            "prior",
            "warn",
            "no prior calibration report; uniform remains the default",
            {"path": str(report)},
        )
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Check("prior", "warn", f"calibration report is unreadable: {exc}")
    admitted = bool(payload.get("admitted"))
    return Check(
        "prior",
        "ok" if admitted else "warn",
        f"{payload.get('prior_id')} was {'admitted' if admitted else 'rejected'}: "
        f"{payload.get('reject_reason') or 'log loss and ECE within the gate'}",
        {"path": str(report), "admitted": admitted, "prior_id": payload.get("prior_id")},
    )


def _check_distribution(project_root: Path) -> Check:
    ignore = project_root / ".gitignore"
    if not ignore.exists():
        return Check("distribution", "fail", f"no .gitignore at {project_root}")
    lines = {
        line.strip()
        for line in ignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    missing = [entry for entry in ("data/", "policies/") if entry not in lines]
    if missing:
        return Check(
            "distribution",
            "fail",
            f".gitignore does not exclude: {', '.join(missing)}",
            {"missing": missing},
        )
    if not (project_root / ".git").exists():
        return Check(
            "distribution",
            "blocked",
            ".gitignore excludes data/ and policies/, but this workspace is not a git "
            "repository, so `git check-ignore` cannot be run here",
            {"gitignore": str(ignore)},
        )
    completed = subprocess.run(
        ["git", "check-ignore", "data/raw", "data/user", "data/processed"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return Check(
            "distribution",
            "fail",
            "git check-ignore did not confirm the data directories are ignored: "
            + (completed.stderr.strip() or completed.stdout.strip()),
        )
    return Check(
        "distribution",
        "ok",
        "git check-ignore confirms data/raw, data/user and data/processed are ignored",
    )


def run_diagnostics(
    *,
    config_path: Path = Path("config/default.toml"),
    data_dir: Path = Path("data"),
    profile_id: str = "classic.en.5",
    policy_path: Path | None = None,
    mode: RuleMode = RuleMode.NORMAL,
    prior: str = "uniform",
    attempts: int = 6,
    project_root: Path = Path("."),
) -> dict:
    """Run every check and return a machine-readable report."""

    checks: list[Check] = [_check_build(), _check_config(Path(config_path))]
    profile_check, profile = _check_profile(Path(data_dir) / "processed" / profile_id, profile_id)
    checks.append(profile_check)
    checks.append(_check_table(Path(data_dir) / "processed" / profile_id, profile))
    checks.append(
        _check_policy(
            Path(policy_path) if policy_path is not None else None,
            profile,
            mode=mode,
            prior=prior,
            attempts=attempts,
        )
    )
    checks.append(_check_prior(Path(data_dir)))
    checks.append(_check_distribution(Path(project_root)))

    counts: dict[str, int] = {}
    for check in checks:
        counts[check.status] = counts.get(check.status, 0) + 1
    return {
        "status": "fail" if counts.get("fail") else "ok",
        "summary": counts,
        "checks": [check.to_dict() for check in checks],
    }


__all__ = ["Check", "run_diagnostics"]
