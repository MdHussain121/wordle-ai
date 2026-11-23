"""Reports: provenance block, tables, failures and CSV export (benchmark plan §10).

The Markdown report is the document a reviewer reads, so it never shows an aggregate
without the answer set and the exhaustive/sampled label, and it prints failures in
their own section rather than hiding them inside an average. The CSV export is the
artifact a reviewer recomputes from: it carries one row per game, and
``aggregates_from_csv`` proves the two agree.
"""

from __future__ import annotations

import csv
import dataclasses
import io
from typing import Iterable, Mapping, Sequence

from .metrics import RunResult

CSV_COLUMNS = (
    "run_id",
    "answer",
    "guesses",
    "n_guesses",
    "solved",
    "elapsed_ms",
    "final_candidates",
    "opener",
)

PUBLISHED_TARGETS: tuple[dict, ...] = (
    {
        "profile_id": "classic.en.5",
        "strategy": "exact",
        "mode": "normal",
        "guess_set": "all",
        "answers": 2315,
        "attempts": 6,
        "expected": 3.4212,
        "max_guesses": 5,
        "opener": "salet",
        "tolerance": 0.0005,
        "source": "Selby 2022; Bertsimas & Paskov 2025",
    },
    {
        "profile_id": "classic.en.5",
        "strategy": "entropy",
        "mode": "normal",
        "guess_set": "all",
        "answers": 2315,
        "attempts": 6,
        "expected": 3.476,
        "max_guesses": 6,
        "opener": "soare",
        "tolerance": None,
        "source": "Luebeck, as tabulated",
    },
    {
        "profile_id": "classic.en.5",
        "strategy": "entropy_candidates",
        "mode": "normal",
        "guess_set": "candidates",
        "answers": 2315,
        "attempts": 6,
        "expected": 3.4955,
        "max_guesses": 6,
        "opener": None,
        "tolerance": None,
        "source": "Greenberg 2024",
    },
    {
        "profile_id": "classic.en.5",
        "strategy": "expected_remaining_candidates",
        "mode": "normal",
        "guess_set": "candidates",
        "answers": 2315,
        "attempts": 6,
        "expected": 3.4600,
        "max_guesses": 6,
        "opener": None,
        "tolerance": None,
        "source": "Greenberg 2024 (bin-count)",
    },
)


def format_table(runs: Sequence[RunResult], *, max_attempts: int = 6) -> str:
    turns = list(range(1, max_attempts + 1))
    header = [
        "strategy",
        "avg_solved",
        "avg_all",
        "median",
        "max",
        "success%",
        "p95_ms",
        *map(str, turns),
        "failed",
    ]
    rows = []
    for run in runs:
        avg = "n/a" if run.avg_guesses_solved is None else f"{run.avg_guesses_solved:.4f}"
        rows.append(
            [
                run.strategy,
                avg,
                f"{run.avg_guesses_all:.4f}",
                "n/a" if run.median_guesses is None else f"{run.median_guesses:g}",
                "-" if run.worst_case is None else str(run.worst_case),
                f"{run.success_rate * 100:.2f}",
                f"{run.decision_p95_ms:.2f}",
                *[str(run.distribution.get(turn, 0)) for turn in turns],
                str(run.failed),
            ]
        )

    widths = [max(len(header[i]), *(len(row[i]) for row in rows)) for i in range(len(header))]
    lines = ["  ".join(value.ljust(widths[i]) for i, value in enumerate(header)).rstrip()]
    lines.append("  ".join("-" * widths[i] for i in range(len(header))))
    for row in rows:
        lines.append("  ".join(value.ljust(widths[i]) for i, value in enumerate(row)).rstrip())
    return "\n".join(lines)


def distribution_table(runs: Sequence[RunResult]) -> str:
    """Distribution rows keyed by run, so two worker counts are not two blank rows."""

    max_attempts = runs[0].max_attempts if runs else 6
    turns = list(range(1, max_attempts + 1))
    header = ["run", "strategy", *map(str, turns), "failed"]
    lines = ["  ".join(header), "  ".join("-" * len(column) for column in header)]
    for run in runs:
        cells = [str(run.distribution.get(turn, 0)) for turn in turns]
        lines.append(
            "  ".join([run.run_key[:12] or "-", run.strategy, *cells, str(run.failed)])
        )
    return "\n".join(lines)


def failures_section(runs: Sequence[RunResult]) -> str:
    lines: list[str] = []
    for run in runs:
        if not run.failed:
            lines.append(f"{run.strategy}: none")
            continue
        shown = ", ".join(run.failed_answers[:10])
        more = "" if run.failed <= 10 else f" (+{run.failed - 10} more)"
        lines.append(f"{run.strategy}: {run.failed} unsolved — {shown}{more}")
    return "\n".join(lines)


def correctness_table(runs: Sequence[RunResult]) -> str:
    header = [
        "strategy",
        "invalid_guesses",
        "mode_violations",
        "answers_eliminated",
        "det_hash",
    ]
    lines = ["  ".join(header), "  ".join("-" * len(column) for column in header)]
    for run in runs:
        lines.append(
            "  ".join(
                [
                    run.strategy,
                    str(run.invalid_guess_count),
                    str(run.mode_violation_count),
                    str(run.answer_eliminated_count),
                    run.determinism_sha256[:16],
                ]
            )
        )
    return "\n".join(lines)


def efficiency_table(runs: Sequence[RunResult]) -> str:
    header = ["strategy", "reduction_mean", "reduction_geomean", "gain_bits", "decisions_p50_ms"]
    lines = ["  ".join(header), "  ".join("-" * len(column) for column in header)]
    for run in runs:
        lines.append(
            "  ".join(
                [
                    run.strategy,
                    f"{run.candidate_reduction_mean:.4f}",
                    f"{run.candidate_reduction_geomean:.4f}",
                    f"{run.information_gain_bits:.4f}",
                    f"{run.decision_p50_ms:.3f}",
                ]
            )
        )
    return "\n".join(lines)


def compare_to_published(run: RunResult, *, guess_set: str | None = None) -> list[dict]:
    """Published figures for this (profile, strategy, mode), with the observed delta."""

    out: list[dict] = []
    for target in PUBLISHED_TARGETS:
        if target["profile_id"] != run.profile_id:
            continue
        if target["strategy"] != run.strategy:
            continue
        if target["mode"] != run.mode:
            continue
        # A published figure describes one configuration. A run with a different
        # attempt limit, answer count or a non-exhaustive set is not that experiment,
        # so it gets no published comparison at all rather than a misleading delta.
        if not run.exhaustive:
            continue
        if run.max_attempts != target["attempts"] or run.answers != target["answers"]:
            continue
        if guess_set is not None and target["guess_set"] != guess_set:
            continue
        observed = run.avg_guesses_solved
        delta = None if observed is None else observed - target["expected"]
        status = "not measured"
        if delta is not None:
            if target["tolerance"] is not None and abs(delta) <= target["tolerance"]:
                status = "reproduced"
            elif target["tolerance"] is not None:
                status = "not reproduced"
            else:
                status = "reference comparison"
        out.append(
            {
                "strategy": run.strategy,
                "published": target["expected"],
                "observed": observed,
                "delta": delta,
                "status": status,
                "max_published": target["max_guesses"],
                "max_observed": run.worst_case,
                "source": target["source"],
            }
        )
    return out


def markdown(
    runs: Sequence[RunResult],
    *,
    provenance: Mapping | None = None,
    comparisons: Sequence[dict] | None = None,
    title: str = "Benchmark report",
) -> str:
    """A self-contained Markdown report for one or more runs."""

    lines: list[str] = [f"# {title}", ""]
    lines.append("## Provenance")
    lines.append("")
    if provenance:
        lines.append("```")
        for key in (
            "run_key",
            "profile_id",
            "manifest_sha256",
            "rules",
            "prior",
            "attempts",
            "answer_set_id",
            "exhaustive",
            "workers",
            "seed",
            "package_version",
            "python",
            "numpy",
            "platform",
            "cpu_count",
            "wall_s",
            "peak_rss_mib",
            "table_sha256",
            "policy_sha256",
            "config_sha256",
            "started_utc",
            "finished_utc",
        ):
            if key in provenance:
                lines.append(f"{key}: {provenance[key]}")
        lines.append("```")
    else:
        lines.append("(no provenance recorded)")
    lines.append("")

    lines.append("## Results")
    lines.append("")
    lines.append(
        "| run | strategy | workers | answers | exhaustive | avg_solved | avg_all | median | "
        "worst | success | p95 ms |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for run in runs:
        avg = "n/a" if run.avg_guesses_solved is None else f"{run.avg_guesses_solved:.4f}"
        lines.append(
            "| {key} | {strategy} | {workers} | {answers} | {exhaustive} | {avg} | {all:.4f} | "
            "{median} | {worst} | {success:.2f}% | {p95:.2f} |".format(
                key=run.run_key[:12] or "-",
                strategy=run.strategy,
                workers=run.workers,
                answers=f"{run.answer_set_id} ({run.answers})"
                if run.answer_set_id
                else str(run.answers),
                exhaustive="exhaustive" if run.exhaustive else "sampled",
                avg=avg,
                all=run.avg_guesses_all,
                median="n/a" if run.median_guesses is None else f"{run.median_guesses:g}",
                worst="-" if run.worst_case is None else run.worst_case,
                success=run.success_rate * 100,
                p95=run.decision_p95_ms,
            )
        )
    lines.append("")

    lines.append("## Distribution (solved games)")
    lines.append("")
    lines.append("```")
    lines.append(distribution_table(runs))
    lines.append("```")
    lines.append("")

    lines.append("## Failures")
    lines.append("")
    lines.append("```")
    lines.append(failures_section(runs))
    lines.append("```")
    lines.append("")

    lines.append("## Correctness")
    lines.append("")
    lines.append("```")
    lines.append(correctness_table(runs))
    lines.append("```")
    lines.append("")

    lines.append("## Efficiency")
    lines.append("")
    lines.append("```")
    lines.append(efficiency_table(runs))
    lines.append("```")
    lines.append("")

    lines.append("## Comparison vs published")
    lines.append("")
    if comparisons:
        lines.append("| strategy | published | observed | delta | status | source |")
        lines.append("|---|---|---|---|---|---|")
        for row in comparisons:
            delta = "n/a" if row["delta"] is None else f"{row['delta']:+.4f}"
            observed = "n/a" if row["observed"] is None else f"{row['observed']:.4f}"
            lines.append(
                f"| {row['strategy']} | {row['published']:.4f} | {observed} | {delta} | "
                f"{row['status']} | {row['source']} |"
            )
    else:
        lines.append("No published figure applies to these runs.")
    lines.append("")
    return "\n".join(lines)


def csv_rows(runs: Sequence[RunResult], games_by_run: Mapping[str, Iterable[dict]]) -> list[dict]:
    """One row per game, in the plan's §10 column order."""

    rows: list[dict] = []
    for run in runs:
        for game in games_by_run.get(run.run_key, ()):
            guesses = game["guesses"]
            rows.append(
                {
                    "run_id": run.run_key,
                    "answer": game["answer"],
                    "guesses": " ".join(guesses) if isinstance(guesses, (list, tuple)) else str(guesses),
                    "n_guesses": game["n_guesses"],
                    "solved": int(game["solved"]),
                    "elapsed_ms": round(float(game["elapsed_ms"]), 3),
                    "final_candidates": game["final_candidates"],
                    "opener": game["opener"],
                }
            )
    return rows


def csv_text(rows: Sequence[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(CSV_COLUMNS), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in CSV_COLUMNS})
    return buffer.getvalue()


def parse_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict] = []
    for raw in reader:
        rows.append(
            {
                "run_id": raw["run_id"],
                "answer": raw["answer"],
                "guesses": raw["guesses"].split(),
                "n_guesses": int(raw["n_guesses"]),
                "solved": bool(int(raw["solved"])),
                "elapsed_ms": float(raw["elapsed_ms"]),
                "final_candidates": int(raw["final_candidates"]),
                "opener": raw["opener"],
            }
        )
    return rows


def aggregates_from_csv(rows: Sequence[dict], *, max_attempts: int) -> dict[str, dict]:
    """Recompute every aggregate from per-game CSV rows, per run id."""

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["run_id"], []).append(row)
    out: dict[str, dict] = {}
    for run_id, games in grouped.items():
        answers = len(games)
        solved_rows = [row for row in games if row["solved"]]
        solved = len(solved_rows)
        turns = [row["n_guesses"] for row in solved_rows]
        distribution = {str(turn): 0 for turn in range(1, max_attempts + 1)}
        for turn in turns:
            distribution[str(turn)] = distribution.get(str(turn), 0) + 1
        charged = sum(turns) + (answers - solved) * (max_attempts + 1)
        out[run_id] = {
            "answers": answers,
            "solved": solved,
            "failed": answers - solved,
            "avg_guesses_solved": (sum(turns) / solved) if solved else None,
            "avg_guesses_all": charged / answers,
            "median_guesses": _median(turns),
            "worst_case": max(turns) if turns else None,
            "distribution": distribution,
            "openers": sorted({row["opener"] for row in games}),
        }
    return out


def _median(values: Sequence[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def payload(runs: Sequence[RunResult], *, provenance: dict) -> dict:
    return {
        "provenance": provenance,
        "runs": [run.to_dict() for run in runs],
        "comparisons": [row for run in runs for row in compare_to_published(run)],
    }


def result_from_dict(data: Mapping) -> RunResult:
    """Rehydrate a stored run record into a :class:`RunResult` without guessing."""

    names = {field.name for field in dataclasses.fields(RunResult)}
    kwargs = {key: value for key, value in data.items() if key in names}
    kwargs["distribution"] = {
        int(key): int(value) for key, value in kwargs.get("distribution", {}).items()
    }
    kwargs["pct_solved_in_k"] = {
        int(key): float(value) for key, value in kwargs.get("pct_solved_in_k", {}).items()
    }
    kwargs["per_round_reduction"] = {
        int(key): float(value)
        for key, value in kwargs.get("per_round_reduction", {}).items()
    }
    kwargs["failed_answers"] = tuple(kwargs.get("failed_answers") or ())
    return RunResult(**kwargs)
