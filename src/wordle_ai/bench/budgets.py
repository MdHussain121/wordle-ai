"""Performance budgets from technical specification §17, with pass/fail evaluation.

The table is data so a measurement script and a test assert against the same numbers.
Seconds are the unit; ``value`` is the measured quantity in the unit named by ``unit``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Budget:
    key: str
    description: str
    limit: float
    unit: str


BUDGETS: tuple[Budget, ...] = (
    Budget("feedback_single", "single feedback (Python)", 2e-6, "s"),
    Budget("feedback_vectorised", "single feedback (vectorised, per pair)", 200e-9, "s"),
    Budget("candidate_filter", "candidate filter, 2,315 answers", 100e-6, "s"),
    Budget("decision_full", "one-step decision, S=2,315, all guesses", 250e-3, "s"),
    Budget("decision_shortlist", "one-step decision, S<=50", 5e-3, "s"),
    Budget("lookahead_two_ply", "two-ply, S=50, top 12", 2.0, "s"),
    Budget("exact_lookup", "exact policy lookup", 1e-3, "s"),
    Budget("profile_load", "profile load (classic)", 1.0, "s"),
    Budget("table_build", "table build (classic)", 60.0, "s"),
)

BUDGET_BY_KEY: dict[str, Budget] = {budget.key: budget for budget in BUDGETS}


def evaluate(key: str, seconds: float | None) -> dict:
    """Compare a measurement to its budget.

    ``seconds is None`` means the operation does not exist in this build (the two-ply
    lookahead, for example); it is reported as ``not_applicable`` rather than passed or
    failed by omission.
    """

    budget = BUDGET_BY_KEY[key]
    if seconds is None:
        return {
            "key": key,
            "description": budget.description,
            "budget": budget.limit,
            "unit": budget.unit,
            "measured": None,
            "status": "not_applicable",
            "ratio": None,
        }
    ratio = seconds / budget.limit
    return {
        "key": key,
        "description": budget.description,
        "budget": budget.limit,
        "unit": budget.unit,
        "measured": seconds,
        "status": "met" if seconds <= budget.limit else "missed",
        "ratio": ratio,
    }


def evaluate_all(measurements: dict[str, float | None]) -> list[dict]:
    return [evaluate(key, measurements.get(key)) for key in BUDGET_BY_KEY]


def summarise(results: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for row in results:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "met": counts.get("met", 0),
        "missed": counts.get("missed", 0),
        "not_applicable": counts.get("not_applicable", 0),
        "total": len(results),
    }


__all__ = [
    "BUDGETS",
    "BUDGET_BY_KEY",
    "Budget",
    "evaluate",
    "evaluate_all",
    "summarise",
]
