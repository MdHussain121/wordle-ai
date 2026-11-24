"""Phase 8 `diagnose`: distinct messages for each integrity failure."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from wordle_ai.diagnose import run_diagnostics
from wordle_ai.lexicon.profile import load_profile


def _copy(profile_dir, tmp_path, profile_id="strict.en.2") -> Path:
    target = tmp_path / "data" / "processed" / profile_id
    shutil.copytree(profile_dir(profile_id), target)
    return target


def _report(tmp_path: Path, profile_id="strict.en.2", **kwargs) -> dict:
    return run_diagnostics(
        data_dir=tmp_path / "data",
        profile_id=profile_id,
        project_root=Path("."),
        **kwargs,
    )


def _checks(report: dict) -> dict:
    return {check["name"]: check for check in report["checks"]}


def _project_root(tmp_path: Path) -> Path:
    """A checkout-like directory with the distribution ignore rules, but no .git."""

    root = tmp_path / "project"
    root.mkdir()
    (root / ".gitignore").write_text("data/\npolicies/\n", encoding="utf-8")
    return root


def test_clean_installation_is_ok_with_warnings(profile_dir, tmp_path):
    _copy(profile_dir, tmp_path)
    report = run_diagnostics(
        data_dir=tmp_path / "data",
        profile_id="strict.en.2",
        project_root=_project_root(tmp_path),
    )
    checks = _checks(report)
    assert checks["profile"]["status"] == "ok"
    assert checks["table"]["status"] == "warn"  # profile was built without a table
    assert checks["policy"]["status"] == "warn"  # no policy requested
    assert checks["distribution"]["status"] == "blocked"  # no .git here
    assert report["status"] == "ok"


def test_distribution_check_passes_in_a_git_checkout(profile_dir, tmp_path):
    if shutil.which("git") is None:  # pragma: no cover - git is present in CI
        pytest.skip("git is not installed")
    _copy(profile_dir, tmp_path)
    root = _project_root(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    report = run_diagnostics(
        data_dir=tmp_path / "data",
        profile_id="strict.en.2",
        project_root=root,
    )
    distribution = _checks(report)["distribution"]
    assert distribution["status"] == "ok"
    assert "git check-ignore confirms" in distribution["message"]


def test_corrupt_table_is_reported_as_a_checksum_mismatch(profile_dir, tmp_path):
    target = _copy(profile_dir, tmp_path)
    profile = load_profile(target)
    table = target / "feedback.npy"
    np.save(table, np.zeros((len(profile.guesses), len(profile.answers)), dtype=np.uint8))
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["outputs"]["feedback_table"] = str(table)
    manifest["outputs"]["table_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = _report(tmp_path)
    table_check = _checks(report)["table"]
    assert table_check["status"] == "fail"
    assert "table checksum mismatch" in table_check["message"]
    assert report["status"] == "fail"


def test_profile_mismatch_is_named(profile_dir, tmp_path):
    target = _copy(profile_dir, tmp_path)
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["profile_id"] = "other.en.2"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = _report(tmp_path)
    profile_check = _checks(report)["profile"]
    assert profile_check["status"] == "fail"
    assert "profile mismatch" in profile_check["message"]
    assert "other.en.2" in profile_check["message"]


def test_tampered_policy_is_reported_as_stale(tmp_path):
    source = Path("data/exact/subset12.policy.json")
    if not source.exists():
        source = Path("policies/classic.en.5.normal.uniform.policy.json")
    target = tmp_path / "tampered.policy.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["tree"]["guess"] = "zzz"
    target.write_text(json.dumps(payload), encoding="utf-8")

    report = run_diagnostics(
        data_dir=Path("data"),
        profile_id="classic.en.5",
        policy_path=target,
        project_root=Path("."),
    )
    policy_check = _checks(report)["policy"]
    assert policy_check["status"] == "fail"
    assert "policy checksum mismatch" in policy_check["message"]


def test_missing_profile_directory_is_named(tmp_path):
    report = run_diagnostics(
        data_dir=tmp_path / "data",
        profile_id="nope.en.5",
        project_root=Path("."),
    )
    check = _checks(report)["profile"]
    assert check["status"] == "fail"
    assert "does not exist" in check["message"]
