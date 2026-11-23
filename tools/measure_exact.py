"""Measure the exact solver's feasibility boundary (Phase 3).

Each case is solved with a wall-clock budget and the outcome recorded verbatim:
``solved`` (value, worst case, nodes, seconds), ``infeasible`` (no guarantee within the
attempt limit) or ``budget`` (the budget expired with the node count reached). The
table is written to ``data/exact/feasibility.json`` and printed.

Run::

    python tools/measure_exact.py [--budget-seconds 120]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from wordle_ai.engine.table import ComputedRows, FeedbackTable
from wordle_ai.errors import BudgetExceeded
from wordle_ai.lexicon.profile import TABLE_NAME, load_profile
from wordle_ai.solver.dp import ExactSolver

CASES = [
    # (profile id, attempts, guess set, answer subset or None)
    ("strict.en.2", 6, "all", None),
    ("strict.en.3", 6, "all", 12),
    ("strict.en.3", 6, "all", 40),
    ("strict.en.3", 6, "candidates", None),
    ("strict.en.3", 6, "all", None),
    ("classic.en.5", 6, "all", None),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget-seconds", type=float, default=120.0)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--out", default="data/exact/feasibility.json")
    args = parser.parse_args()

    root = Path(args.data_dir) / "processed"
    rows_out: list[dict] = []
    for profile_id, attempts, guess_set, subset in CASES:
        profile = load_profile(root / profile_id)
        table_path = root / profile_id / TABLE_NAME
        rows = (
            FeedbackTable(table_path, profile)
            if table_path.exists()
            else ComputedRows(profile)
        )
        mask = None
        label = profile_id
        if subset is not None:
            mask = np.zeros(len(profile.answers), dtype=bool)
            mask[:subset] = True
            label = f"{profile_id}@{subset}"
        solver = ExactSolver(
            profile,
            rows,
            max_attempts=attempts,
            guess_set=guess_set,
            time_budget_s=args.budget_seconds,
        )
        started = time.perf_counter()
        record: dict = {
            "case": label,
            "answers": int(mask.sum()) if mask is not None else len(profile.answers),
            "guesses": len(profile.guesses),
            "attempts": attempts,
            "guess_set": guess_set,
            "budget_s": args.budget_seconds,
        }
        try:
            solution = solver.solve(mask)
            record.update(
                status="solved",
                expected_guesses=round(solution.value, 6),
                max_guesses=solution.max_guesses,
                opener=solution.root_guess,
                nodes=solution.nodes,
                guess_evaluations=solution.guess_evaluations,
                elapsed_s=round(solution.elapsed_s, 3),
                nodes_per_s=round(solution.nodes / max(solution.elapsed_s, 1e-9), 1),
            )
        except BudgetExceeded as exc:
            infeasible = "no strategy can guarantee" in exc.message
            record.update(
                status="infeasible" if infeasible else "budget",
                nodes=solver._nodes,
                guess_evaluations=solver._evaluations,
                elapsed_s=round(time.perf_counter() - started, 3),
                message=exc.message,
            )
        rows_out.append(record)
        print(json.dumps(record, sort_keys=True))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows_out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
