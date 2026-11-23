"""Measure the Phase 4 benchmark matrix and write the gate evidence.

Runs the required benchmark set on the shipped classic profile (plus an exact-policy
proxy, because the Phase 3 gate cannot solve classic), stores every run in SQLite and
writes Markdown, CSV and JSON artifacts under ``data/bench/phase4``.

``--report-only`` re-renders those artifacts from the measurements already recorded, so
a report-format change does not require replaying 7,000 games.

Run::

    .venv/Scripts/python.exe -u tools/measure_phase4.py [--workers 16] [--limit N]
    .venv/Scripts/python.exe -u tools/measure_phase4.py --report-only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from wordle_ai.bench.report import (
    compare_to_published,
    csv_rows,
    csv_text,
    markdown,
    result_from_dict,
)
from wordle_ai.bench.runner import (
    PACKAGE_VERSION,
    RunSpec,
    config_digest,
    execute,
    peak_rss_mib,
)
from wordle_ai.config import load_config
from wordle_ai.errors import BudgetExceeded
from wordle_ai.lexicon.profile import load_profile
from wordle_ai.store.sqlite import RunStore

OUT = Path("data/bench/phase4")


def _games(store: RunStore, run_key: str) -> list[dict]:
    return [
        {
            "answer": row["answer"],
            "guesses": json.loads(row["guesses_json"]),
            "n_guesses": row["n_guesses"],
            "solved": bool(row["solved"]),
            "elapsed_ms": row["elapsed_ms"],
            "final_candidates": row["final_candidates"],
            "opener": row["opener"],
        }
        for row in store.games(run_key)
    ]


def _row(label: str, result, wall: float) -> dict:
    return {
        "label": label,
        "run_key": result.run_key,
        "strategy": result.strategy,
        "answers": result.answers,
        "answer_set_id": result.answer_set_id,
        "exhaustive": result.exhaustive,
        "workers": result.workers,
        "avg_guesses_solved": result.avg_guesses_solved,
        "avg_guesses_all": result.avg_guesses_all,
        "worst_case": result.worst_case,
        "failed": result.failed,
        "success_rate": result.success_rate,
        "determinism_sha256": result.determinism_sha256,
        "total_s": round(result.total_s, 3),
        "wall_s": round(wall, 3),
        "peak_rss_mib": round(peak_rss_mib() or 0.0, 1),
    }


def _write_reports(
    out_dir: Path,
    runs: list,
    rows: list[dict],
    guard: dict,
    store: RunStore,
    digest: str,
    determinism_match: bool,
) -> dict:
    comparisons = [row for result in runs for row in compare_to_published(result)]
    provenance = store.get(runs[0].run_key).provenance
    (out_dir / "phase4_report.md").write_text(
        markdown(
            runs,
            provenance=provenance,
            comparisons=comparisons,
            # The date comes from the measurement itself, so a re-render cannot
            # claim a date the runs were not made on.
            title=f"Phase 4 benchmark matrix (measured {provenance['started_utc'][:10]})",
        ),
        encoding="utf-8",
        newline="\n",
    )

    entropy_csv = next(
        result
        for result in runs
        if result.strategy == "entropy" and result.max_attempts == 6
    )
    rows_csv = csv_rows(
        [entropy_csv], {entropy_csv.run_key: _games(store, entropy_csv.run_key)}
    )
    (out_dir / "b03_entropy_games.csv").write_text(
        csv_text(rows_csv), encoding="utf-8", newline="\n"
    )

    failure_run = next(result for result in runs if result.max_attempts == 3)
    (out_dir / "failures_report.md").write_text(
        markdown(
            [failure_run],
            provenance=store.get(failure_run.run_key).provenance,
            comparisons=compare_to_published(failure_run),
            title="Induced-failure run (attempt limit 3)",
        ),
        encoding="utf-8",
        newline="\n",
    )

    summary = {
        "package_version": PACKAGE_VERSION,
        "python": sys.version.split()[0],
        "config_sha256": digest,
        "rows": rows,
        "runs": [result.to_dict() for result in runs],
        "comparisons": comparisons,
        "budget_guard": guard,
        "determinism_match": determinism_match,
        "store": str(store.path),
        "csv_rows": len(rows_csv),
    }
    (out_dir / "measurements.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def _measure(args, store: RunStore, digest: str) -> tuple[list, list[dict], dict, bool]:
    settings = load_config(args.config)
    processed = Path(args.data_dir) / "processed"
    classic = processed / "classic.en.5"
    seed = settings.bench.seed
    classic_profile = load_profile(classic)
    answers = (
        tuple(classic_profile.answers[: args.limit]) if args.limit is not None else None
    )

    rows: list[dict] = []
    runs: list = []

    def go(label: str, spec: RunSpec):
        started = time.perf_counter()
        result = execute(spec, store=store, config_sha256=digest)
        wall = time.perf_counter() - started
        runs.append(result)
        rows.append(_row(label, result, wall))
        print(json.dumps(rows[-1], sort_keys=True), flush=True)
        return result

    # B-03: the three primary ablations AB-1, exhaustive over the classic list.
    for strategy in ("entropy", "expected_remaining", "minimax"):
        go(
            "B-03",
            RunSpec(
                profile_id="classic.en.5",
                profile_dir=classic,
                strategy=strategy,
                answers=answers,
                workers=args.workers,
                seed=seed,
            ),
        )

    # B-02 at the configured worker count, then the same run at one worker (B-12).
    b02 = go(
        "B-02",
        RunSpec(
            profile_id="classic.en.5",
            profile_dir=classic,
            strategy="hybrid.balanced",
            answers=answers,
            workers=args.workers,
            seed=seed,
        ),
    )
    b12 = go(
        "B-12 (1 worker)",
        RunSpec(
            profile_id="classic.en.5",
            profile_dir=classic,
            strategy="hybrid.balanced",
            answers=answers,
            workers=1,
            seed=seed,
        ),
    )
    determinism_match = b02.determinism_sha256 == b12.determinism_sha256
    print(
        json.dumps(
            {
                "determinism_match": determinism_match,
                "hash": b02.determinism_sha256,
                "workers": [b02.workers, b12.workers],
            },
            sort_keys=True,
        ),
        flush=True,
    )

    # B-01 proxy: the exact machinery, on the only policy the Phase 3 gate can build.
    policy = Path(args.data_dir) / "exact" / "subset12.policy.json"
    if policy.exists():
        go(
            "B-01 (subset proxy)",
            RunSpec(
                profile_id="strict.en.3",
                profile_dir=processed / "strict.en.3",
                strategy="exact",
                attempts=6,
                workers=1,
                policy_path=policy,
            ),
        )
    else:
        print(json.dumps({"skipped": f"{policy} is absent"}, sort_keys=True), flush=True)

    # An induced-failure run: attempt limit 3, so failures are real and reported.
    go(
        "failures (K=3)",
        RunSpec(
            profile_id="classic.en.5",
            profile_dir=classic,
            strategy="entropy",
            attempts=3,
            answers=answers,
            workers=args.workers,
            seed=seed,
        ),
    )

    # Budget guard: a run whose measured time exceeds a deliberately tiny budget.
    guard: dict = {"status": "not triggered"}
    try:
        execute(
            RunSpec(
                profile_id="strict.en.3",
                profile_dir=processed / "strict.en.3",
                strategy="entropy",
                answers=tuple(load_profile(processed / "strict.en.3").answers[:4]),
                workers=1,
                seed=seed,
            ),
            store=store,
            config_sha256=digest,
            time_budget_s=1e-6,
        )
    except BudgetExceeded as exc:
        guard = {
            "status": "refused",
            "code": exc.code,
            "message": exc.message,
            "stored_as_budget_exceeded": not store.has_completed(exc.context["run"]),
        }
    print(json.dumps(guard, sort_keys=True), flush=True)
    return runs, rows, guard, determinism_match


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--limit", type=int, default=None, help="Answer limit (measurement only)")
    parser.add_argument("--config", default="config/default.toml")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument(
        "--report-only", action="store_true", help="Re-render artifacts from measurements.json"
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = config_digest(args.config)
    store = RunStore(Path(args.data_dir) / "bench" / "runs.sqlite")
    try:
        if args.report_only:
            recorded = json.loads((out_dir / "measurements.json").read_text(encoding="utf-8"))
            runs = [result_from_dict(entry) for entry in recorded["runs"]]
            rows = recorded["rows"]
            guard = recorded["budget_guard"]
            determinism_match = bool(recorded["determinism_match"])
        else:
            runs, rows, guard, determinism_match = _measure(args, store, digest)
        summary = _write_reports(
            out_dir, runs, rows, guard, store, digest, determinism_match
        )
    finally:
        store.close()
    print(
        json.dumps(
            {
                "runs": len(summary["rows"]),
                "sum_run_s": round(sum(row["total_s"] for row in summary["rows"]), 1),
                "determinism_match": summary["determinism_match"],
                "wrote": str(out_dir),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
