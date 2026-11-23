"""Benchmark orchestration: run identity, matrix expansion, resume, budget guard.

One :class:`RunSpec` is one comparable run: a profile, a rule configuration, a prior, an
attempt limit, a strategy and a labelled answer set. Its key is the benchmark plan's
§2 tuple, so two runs with the same key are the same experiment and a resumed matrix
never silently re-runs one.

A run that plays an *exact* policy built over an answer subset is played against that
subset as its own answer universe: the policy's candidate masks are only as wide as the
answers it was solved for, so pretending it covers the full list would fail the first
lookup. Every other run plays the full profile with a prefix of answers.

The budget guard is a refusal, not a truncation. A run that would exceed its wall-clock
budget is still finished and stored with ``status = budget_exceeded``, then raises: a
truncated answer set would silently change the denominator, which is the defect the
plan forbids.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from .. import __version__
from ..engine.prior import normalised_weights, parse_prior_id
from ..errors import BudgetExceeded, WordleError
from ..lexicon.profile import TABLE_NAME, load_profile
from ..lexicon.source import sha256_file
from ..sim.parallel import run_profile_parallel
from ..sim.runner import GameRecord
from ..solver.policy import answer_set_digest, load_policy, subset_profile
from ..strategy import get_strategy
from ..types import Profile, RuleMode
from .metrics import RunResult, summarise

#: The run key records the package version, so it must come from the one place that
#: defines it rather than from a copy that drifts.
PACKAGE_VERSION = __version__


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def config_digest(path: Path | str | None) -> str:
    if path is None or not Path(path).exists():
        return ""
    return sha256_file(Path(path))


def peak_rss_mib() -> float | None:
    """Peak resident set of this process, or ``None`` where the OS cannot report it."""

    try:  # POSIX
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        scale = 1024.0 if sys.platform != "darwin" else 1024.0 * 1024.0
        return usage / scale
    except ImportError:  # pragma: no cover - Windows
        pass
    try:
        from ctypes import wintypes

        class _Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        # GetCurrentProcess returns a handle; without restype ctypes truncates it to a
        # 32-bit int on 64-bit Windows and the query fails with an invalid handle.
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_Counters),
            wintypes.DWORD,
        ]
        counters = _Counters()
        counters.cb = ctypes.sizeof(_Counters)
        if not psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            return None
        return counters.PeakWorkingSetSize / (1024.0 * 1024.0)
    except Exception:  # pragma: no cover - best effort only
        return None


@dataclass(frozen=True)
class RunSpec:
    """One comparable benchmark run."""

    profile_id: str
    profile_dir: Path
    strategy: str
    mode: RuleMode = RuleMode.NORMAL
    prior: str = "uniform"
    attempts: int = 6
    answers: tuple[str, ...] | None = None
    workers: int = 1
    seed: int | None = None
    policy_path: Path | None = None

    @property
    def table_path(self) -> Path | None:
        candidate = self.profile_dir / TABLE_NAME
        return candidate if candidate.exists() else None


@dataclass(frozen=True)
class PreparedRun:
    """A spec resolved against its profile: the answer universe and the run key."""

    spec: RunSpec
    profile: Profile
    universe: Profile
    answers: tuple[str, ...]
    answer_set_id: str
    run_key: str
    subset_size: int | None
    exhaustive: bool
    strategy_kwargs: dict


def run_key(
    *,
    profile_id: str,
    manifest_sha256: str,
    mode: RuleMode,
    prior: str,
    attempts: int,
    strategy: str,
    answer_set_id: str,
    seed: int | None,
    package_version: str,
    config_sha256: str,
) -> str:
    """The §2 run identity: the same tuple always hashes to the same key."""

    payload = {
        "profile_id": profile_id,
        "manifest_sha256": manifest_sha256,
        "rules": mode.value,
        "prior": prior,
        "attempts": attempts,
        "strategy": strategy,
        "answer_set_id": answer_set_id,
        "seed": seed,
        "package_version": package_version,
        "config_sha256": config_sha256,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _policy_subset_size(path: Path, profile: Profile) -> int | None:
    """Answer-universe size the policy was solved for, when it is a subset."""

    header = load_policy(path)
    size = header.get("answer_set_size")
    if not isinstance(size, int) or size < 1:
        raise WordleError(f"{path}: policy has no usable answer_set_size", code="artifact_mismatch")
    if size > len(profile.answers):
        raise WordleError(
            f"{path}: policy covers {size} answers but {profile.profile_id} has "
            f"{len(profile.answers)}",
            code="artifact_mismatch",
        )
    return None if size == len(profile.answers) else size


def prepare(
    spec: RunSpec,
    *,
    package_version: str = PACKAGE_VERSION,
    config_sha256: str = "",
) -> PreparedRun:
    """Resolve a spec: load the profile, the policy's answer universe and the run key."""

    profile = load_profile(Path(spec.profile_dir))
    if spec.profile_id != profile.profile_id:
        raise WordleError(
            f"the spec names profile {spec.profile_id!r} but {spec.profile_dir} holds "
            f"{profile.profile_id!r}",
            code="profile_mismatch",
        )
    subset_size = (
        _policy_subset_size(spec.policy_path, profile)
        if spec.policy_path is not None
        else None
    )
    universe = subset_profile(profile, subset_size)
    answers = tuple(universe.answers if spec.answers is None else spec.answers)
    if not answers:
        raise WordleError("a run needs at least one answer", code="empty_answer_set")
    unknown = [word for word in answers if word not in universe.answer_index]
    if unknown:
        raise WordleError(
            f"{len(unknown)} answer(s) are outside the {len(universe.answers)}-answer "
            f"universe of this run (first: {unknown[0]!r})",
            code="answer_set_mismatch",
        )
    # A run is exhaustive when it plays the whole answer universe it is defined over:
    # the full profile, or the subset an exact policy was solved for. Anything smaller
    # is a labelled subset, never silently an "all answers" run.
    exhaustive = len(answers) == len(universe.answers)
    digest = answer_set_digest(universe)[:12]
    answer_set_id = (
        f"{universe.profile_id}.all.{digest}"
        if exhaustive
        else f"{universe.profile_id}.first{len(answers)}.{digest}"
    )

    if spec.strategy == "exact":
        if spec.policy_path is None:
            raise WordleError(
                "the exact strategy needs --policy <artifact>; build one with "
                "`wordle-ai policy build`",
                code="missing_policy",
            )
        policy = load_policy(
            spec.policy_path, profile=universe, mode=spec.mode, attempts=spec.attempts
        )
        if policy.get("prior") != spec.prior:
            raise WordleError(
                f"policy {spec.policy_path} was built under prior {policy.get('prior')!r}, "
                f"not {spec.prior!r}",
                code="artifact_mismatch",
            )
        strategy_kwargs = {"policy": policy}
    else:
        if spec.policy_path is not None:
            raise WordleError(
                f"--policy was given for strategy {spec.strategy!r}; only 'exact' reads one",
                code="unexpected_policy",
            )
        # The prior reweights every objective, not just the prior-aware ones, because
        # ``expected_remaining`` is already ``sum_r p_r |S_r|``. A uniform prior adds
        # no weights at all, which keeps uniform runs bit-identical to Phase 4.
        prior_object = parse_prior_id(spec.prior)
        strategy_kwargs = (
            {}
            if spec.prior.strip() in ("", "uniform")
            else {"prior_weights": normalised_weights(prior_object, universe)}
        )

    return PreparedRun(
        spec=spec,
        profile=profile,
        universe=universe,
        answers=answers,
        answer_set_id=answer_set_id,
        run_key=run_key(
            profile_id=universe.profile_id,
            manifest_sha256=universe.manifest_sha256,
            mode=spec.mode,
            prior=spec.prior,
            attempts=spec.attempts,
            strategy=spec.strategy,
            answer_set_id=answer_set_id,
            seed=spec.seed,
            package_version=package_version,
            config_sha256=config_sha256,
        ),
        subset_size=subset_size,
        exhaustive=exhaustive,
        strategy_kwargs=strategy_kwargs,
    )


def execute(
    spec: RunSpec,
    *,
    store=None,
    package_version: str = PACKAGE_VERSION,
    config_sha256: str = "",
    time_budget_s: float | None = None,
    feedback_source: str = "table",
    strict_legality: bool = False,
) -> RunResult:
    """Run one spec and return its measured result (stored when a store is given)."""

    prepared = prepare(spec, package_version=package_version, config_sha256=config_sha256)
    profile = prepared.universe
    started_utc = utc_now()
    started = time.perf_counter()
    records, elapsed = run_profile_parallel(
        profile_dir=Path(spec.profile_dir),
        subset_size=prepared.subset_size,
        table_path=spec.table_path,
        strategy_name=spec.strategy,
        strategy_kwargs=prepared.strategy_kwargs,
        answers=prepared.answers,
        workers=spec.workers,
        mode=spec.mode,
        max_attempts=spec.attempts,
        feedback_source=feedback_source,
        strict_legality=strict_legality,
    )
    result = summarise(
        records,
        profile_id=profile.profile_id,
        profile_manifest_sha256=profile.manifest_sha256,
        strategy=spec.strategy,
        objective=get_strategy(spec.strategy).objective,
        mode=spec.mode,
        max_attempts=spec.attempts,
        total_s=elapsed,
        guess_index=profile.guess_index,
        exhaustive=prepared.exhaustive,
        answer_set_id=prepared.answer_set_id,
        seed=spec.seed,
        workers=spec.workers,
        run_key=prepared.run_key,
    )

    provenance = {
        "run_key": prepared.run_key,
        "package_version": package_version,
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "hostname": socket.gethostname(),
        "started_utc": started_utc,
        "finished_utc": utc_now(),
        "wall_s": round(time.perf_counter() - started, 3),
        "peak_rss_mib": peak_rss_mib(),
        "profile_id": profile.profile_id,
        "manifest_sha256": profile.manifest_sha256,
        "rules": spec.mode.value,
        "prior": spec.prior,
        "attempts": spec.attempts,
        "strategy": spec.strategy,
        "workers": spec.workers,
        "seed": spec.seed,
        "answer_set_id": prepared.answer_set_id,
        "answers": len(prepared.answers),
        "answer_set_total": len(profile.answers),
        "exhaustive": result.exhaustive,
        "feedback_source": feedback_source,
        "table_sha256": sha256_file(spec.table_path) if spec.table_path else None,
        "policy_sha256": _policy_digest(spec.policy_path),
        "config_sha256": config_sha256,
    }

    status = "succeeded"
    if time_budget_s is not None and elapsed > time_budget_s:
        status = "budget_exceeded"
    if store is not None:
        store.save(result, records, provenance=provenance, status=status)
    if status != "succeeded":
        raise BudgetExceeded(
            f"{spec.strategy} on {profile.profile_id} took {elapsed:.1f}s, above the "
            f"{time_budget_s:.0f}s budget; the run is stored with status budget_exceeded "
            "and its averages describe the full answer set, not a truncated one",
            run=prepared.run_key,
            elapsed_s=round(elapsed, 3),
        )
    return result


def _policy_digest(path: Path | None) -> str | None:
    return sha256_file(Path(path)) if path is not None and Path(path).exists() else None


def expand_matrix(
    *,
    profiles: Sequence[tuple[str, Path]],
    strategies: Sequence[str],
    modes: Sequence[RuleMode] = (RuleMode.NORMAL,),
    attempts: Sequence[int] = (6,),
    priors: Sequence[str] = ("uniform",),
    workers: Sequence[int] = (1,),
    answers: tuple[str, ...] | None = None,
    seed: int | None = None,
    policy_path: Path | None = None,
) -> list[RunSpec]:
    """Every cell of the requested matrix, in a fixed order."""

    specs: list[RunSpec] = []
    for profile_id, profile_dir in profiles:
        for mode in modes:
            for attempt in attempts:
                for prior in priors:
                    for strategy in strategies:
                        for worker in workers:
                            specs.append(
                                RunSpec(
                                    profile_id=profile_id,
                                    profile_dir=Path(profile_dir),
                                    strategy=strategy,
                                    mode=mode,
                                    prior=prior,
                                    attempts=attempt,
                                    answers=answers,
                                    workers=worker,
                                    seed=seed,
                                    policy_path=policy_path if strategy == "exact" else None,
                                )
                            )
    return specs


def run_matrix(
    specs: Iterable[RunSpec],
    *,
    store=None,
    package_version: str = PACKAGE_VERSION,
    config_sha256: str = "",
    resume: bool = True,
    time_budget_s: float | None = None,
    feedback_source: str = "table",
    strict_legality: bool = False,
) -> tuple[list[RunResult], list[str]]:
    """Execute specs sequentially, skipping completed runs; return (results, skipped)."""

    results: list[RunResult] = []
    skipped: list[str] = []
    for spec in specs:
        prepared = prepare(
            spec, package_version=package_version, config_sha256=config_sha256
        )
        if resume and store is not None and store.has_completed(prepared.run_key):
            skipped.append(prepared.run_key)
            continue
        results.append(
            execute(
                spec,
                store=store,
                package_version=package_version,
                config_sha256=config_sha256,
                time_budget_s=time_budget_s,
                feedback_source=feedback_source,
                strict_legality=strict_legality,
            )
        )
    return results, skipped


def records_from_store(rows: Sequence[dict]) -> list[GameRecord]:
    """Rebuild game records from persisted rows (used by ``bench compare``)."""

    out: list[GameRecord] = []
    for row in rows:
        candidates = json.loads(row["candidates_json"]) if row.get("candidates_json") else {}
        out.append(
            GameRecord(
                answer=str(row["answer"]),
                guesses=tuple(json.loads(row["guesses_json"])),
                solved=bool(row["solved"]),
                candidates_before=tuple(candidates.get("before", ())),
                candidates_after=tuple(candidates.get("after", ())),
            )
        )
    return out


__all__ = [
    "PACKAGE_VERSION",
    "PreparedRun",
    "RunSpec",
    "config_digest",
    "execute",
    "expand_matrix",
    "peak_rss_mib",
    "prepare",
    "records_from_store",
    "run_key",
    "run_matrix",
    "utc_now",
]
