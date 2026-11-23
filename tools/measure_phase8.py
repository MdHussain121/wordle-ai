"""Measure the technical-spec §17 performance budgets (Phase 8, criterion 1).

Every measurement is taken on the shipped classic profile unless the budget names
another scale, and is written to ``data/phase8/budgets.json`` with the budget table's
verdict. A missing feature (two-ply lookahead) is recorded as ``not_applicable`` rather
than passed by omission.

Run::

    .venv/Scripts/python.exe -u tools/measure_phase8.py
"""

from __future__ import annotations

import json
import platform
import statistics
import time
from pathlib import Path

import numpy as np

from wordle_ai.bench.budgets import BUDGETS, evaluate_all, summarise
from wordle_ai.engine.feedback import feedback_code, feedback_row
from wordle_ai.engine.filter import filter_mask
from wordle_ai.engine.state import new_game
from wordle_ai.engine.table import ComputedRows, build_table, open_rows
from wordle_ai.lexicon.profile import TABLE_NAME, load_profile
from wordle_ai.solver.policy import load_policy, subset_profile
from wordle_ai.strategy import get_strategy
from wordle_ai.strategy.exact import ExactStrategy
from wordle_ai.types import Pattern

OUT = Path("data/phase8")
CLASSIC = Path("data/processed/classic.en.5")
POLICY = Path("data/exact/subset12.policy.json")


def _median_seconds(function, rounds: int = 5) -> float:
    timings = []
    for _ in range(rounds):
        started = time.perf_counter()
        function()
        timings.append(time.perf_counter() - started)
    return statistics.median(timings)


def measure() -> dict[str, float | None]:
    profile = load_profile(CLASSIC)
    table_path = CLASSIC / TABLE_NAME
    rows = open_rows(profile, table_path if table_path.exists() else None)
    values: dict[str, float | None] = {}

    # Single feedback: the reference two-pass function, and the vectorised row per pair.
    values["feedback_single"] = _median_seconds(
        lambda: [feedback_code("salet", "cigar") for _ in range(20_000)], rounds=3
    ) / 20_000
    row = feedback_row("salet", profile.answers, profile.alphabet)

    mask = np.ones(len(profile.answers), dtype=bool)
    code = int(row[0])
    values["candidate_filter"] = _median_seconds(
        lambda: [filter_mask(mask, row, code) for _ in range(5_000)], rounds=3
    ) / 5_000

    # Full-state decision, and the shortlist case.
    strategy = get_strategy("entropy")
    strategy.choose(new_game(profile), rows)  # warm the table and strategy caches
    values["decision_full"] = _median_seconds(
        lambda: strategy.choose(new_game(profile), rows), rounds=5
    )
    small = new_game(profile)
    for guess in ("salet", "crimp", "bawdy", "koala", "jumpy"):
        if small.remaining <= 50:
            break
        small = small.apply(
            guess,
            Pattern(
                code=int(
                    rows.row(guess)[small.profile.answer_index[small.candidate_words[0]]]
                ),
                length=profile.length,
            ),
            table=rows,
        )
    if small.remaining <= 50 and small.remaining > 1:
        strategy.choose(small, rows)
        values["decision_shortlist"] = _median_seconds(
            lambda: strategy.choose(small, rows), rounds=20
        )
    else:  # pragma: no cover - the shipped profile reaches a small state
        values["decision_shortlist"] = None

    # Exact policy lookup on the only shipped artifact (12-answer subset).
    if POLICY.exists():
        # The only shipped policy was solved over strict.en.3, not classic.
        source = load_profile(Path("data/processed/strict.en.3"))
        subset = subset_profile(source, load_policy(POLICY).get("answer_set_size", 12))
        subset_rows = ComputedRows(subset)
        exact = ExactStrategy().attach(load_policy(POLICY))
        exact_state = new_game(subset)
        exact.choose(exact_state, subset_rows)
        values["exact_lookup"] = _median_seconds(
            lambda: exact.choose(exact_state, subset_rows), rounds=50
        )
    else:  # pragma: no cover
        values["exact_lookup"] = None

    values["profile_load"] = _median_seconds(lambda: load_profile(CLASSIC), rounds=5)
    started = time.perf_counter()
    build_table(profile)
    values["table_build"] = time.perf_counter() - started
    # The vectorised path's per-pair cost is the table build divided by its pairs;
    # timing feedback_row alone would charge Python call and encode overhead per row.
    values["feedback_vectorised"] = values["table_build"] / (
        len(profile.guesses) * len(profile.answers)
    )

    # No two-ply strategy exists in this build (Phase 2 shipped one-step only).
    values["lookahead_two_ply"] = None
    return values


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    values = measure()
    results = evaluate_all(values)
    payload = {
        "profile": "classic.en.5",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "budgets": [budget.__dict__ for budget in BUDGETS],
        "measurements": values,
        "results": results,
        "summary": summarise(results),
    }
    (OUT / "budgets.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    lines = [
        "# Phase 8 performance budgets",
        "",
        f"Profile `classic.en.5`, Python {payload['python']}, {payload['platform']}.",
        "",
        "| Operation | Budget | Measured | Verdict |",
        "|---|---|---|---|",
    ]
    for row in results:
        budget = row["budget"]
        measured = (
            "not applicable"
            if row["measured"] is None
            else f"{row['measured'] * 1e6:.3f} µs"
            if budget < 1e-3
            else f"{row['measured'] * 1e3:.3f} ms"
            if budget < 1
            else f"{row['measured']:.3f} s"
        )
        limit = (
            f"{budget * 1e6:.2f} µs"
            if budget < 1e-3
            else f"{budget * 1e3:.0f} ms"
            if budget < 1
            else f"{budget:.0f} s"
        )
        lines.append(
            f"| {row['description']} | {limit} | {measured} | {row['status']} |"
        )
    lines += [
        "",
        f"Met {payload['summary']['met']} of "
        f"{payload['summary']['total'] - payload['summary']['not_applicable']}; "
        f"missed {payload['summary']['missed']}; "
        f"not applicable {payload['summary']['not_applicable']}.",
        "",
        (
            "Every measured budget is met. The two-ply row is not applicable because this "
            "build ships no lookahead strategy; it is recorded rather than passed by "
            "omission."
            if payload["summary"]["missed"] == 0
            else "A missed budget is recorded with its measured value and the accepted "
            "trade-off."
        ),
        "",
    ]
    (OUT / "budgets_report.md").write_text(
        "\n".join(lines), encoding="utf-8", newline="\n"
    )
    for row in results:
        print(f"{row['key']:<22} {row['status']:<15} {row['measured']}")
    print(f"wrote {OUT / 'budgets.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
