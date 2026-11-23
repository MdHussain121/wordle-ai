"""Run aggregation and every metric in the benchmark plan §4.

Each formula is implemented once, from the plan's definition, and tested against a
hand-computed fixture. Failures stay in the denominator: ``avg_guesses_all`` charges
``K + 1`` for an unsolved game, and ``failure_rate`` is reported next to it so a
strategy cannot look good by giving up.

The calibration helpers (§4.4) are pure functions over a predicted distribution and
its target, so Phase 5's priors and Phase 6's rankers can be scored with the same code
and the same tests.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

import numpy as np

from ..sim.runner import GameRecord
from ..types import RuleMode


def determinism_hash(records: Sequence[GameRecord]) -> str:
    """Hash of every answer and its full guess sequence (benchmark plan §2)."""

    lines = sorted(
        f"{record.answer}\t{record.turns}\t{','.join(record.guesses)}" for record in records
    )
    payload = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class RunResult:
    profile_id: str
    profile_manifest_sha256: str
    strategy: str
    objective: str
    mode: str
    max_attempts: int
    answers: int
    solved: int
    failed: int
    distribution: dict[int, int]
    avg_guesses_solved: float | None
    avg_guesses_all: float
    median_guesses: float | None
    worst_case: int | None
    worst_case_answer: str | None
    determinism_sha256: str
    total_s: float
    decision_p50_ms: float
    decision_p95_ms: float
    decision_max_ms: float
    failed_answers: tuple[str, ...] = field(repr=False, default=())
    exhaustive: bool = True
    answer_set_id: str = "all"
    seed: int | None = None
    workers: int = 1
    run_key: str = ""
    pct_solved_in_k: dict[int, float] = field(default_factory=dict)
    candidate_reduction_mean: float = 0.0
    candidate_reduction_geomean: float = 0.0
    information_gain_bits: float = 0.0
    information_gain_weighted: float = 0.0
    per_round_reduction: dict[int, float] = field(default_factory=dict)
    invalid_guess_count: int = 0
    mode_violation_count: int = 0
    answer_eliminated_count: int = 0

    @property
    def failure_rate(self) -> float:
        return self.failed / self.answers if self.answers else 0.0

    @property
    def success_rate(self) -> float:
        return self.solved / self.answers if self.answers else 0.0

    @property
    def total_guesses(self) -> int:
        """Sum of guesses over solved games (the published 7,920 for exact play)."""

        return int(round((self.avg_guesses_solved or 0.0) * self.solved))

    def to_dict(self) -> dict:
        return {
            "run_key": self.run_key,
            "profile_id": self.profile_id,
            "profile_manifest_sha256": self.profile_manifest_sha256,
            "strategy": self.strategy,
            "objective": self.objective,
            "mode": self.mode,
            "max_attempts": self.max_attempts,
            "answers": self.answers,
            "answer_set_id": self.answer_set_id,
            "exhaustive": self.exhaustive,
            "seed": self.seed,
            "workers": self.workers,
            "solved": self.solved,
            "failed": self.failed,
            "failure_rate": self.failure_rate,
            "success_rate": self.success_rate,
            "distribution": {str(k): v for k, v in sorted(self.distribution.items())},
            "pct_solved_in_k": {str(k): v for k, v in sorted(self.pct_solved_in_k.items())},
            "avg_guesses_solved": self.avg_guesses_solved,
            "avg_guesses_all": self.avg_guesses_all,
            "total_guesses": self.total_guesses,
            "median_guesses": self.median_guesses,
            "worst_case": self.worst_case,
            "worst_case_answer": self.worst_case_answer,
            "failed_answers": list(self.failed_answers),
            "determinism_sha256": self.determinism_sha256,
            "total_s": round(self.total_s, 3),
            "decision_p50_ms": round(self.decision_p50_ms, 3),
            "decision_p95_ms": round(self.decision_p95_ms, 3),
            "decision_max_ms": round(self.decision_max_ms, 3),
            "candidate_reduction_mean": self.candidate_reduction_mean,
            "candidate_reduction_geomean": self.candidate_reduction_geomean,
            "information_gain_bits": self.information_gain_bits,
            "information_gain_weighted": self.information_gain_weighted,
            "per_round_reduction": {
                str(k): v for k, v in sorted(self.per_round_reduction.items())
            },
            "invalid_guess_count": self.invalid_guess_count,
            "mode_violation_count": self.mode_violation_count,
            "answer_eliminated_count": self.answer_eliminated_count,
        }


def _efficiency(records: Sequence[GameRecord]) -> dict:
    """Candidate reduction, information gain and their per-round breakdown (§4.2)."""

    ratios: list[float] = []
    bits: list[float] = []
    by_round: dict[int, list[float]] = {}
    for record in records:
        for turn, (before, after) in enumerate(
            zip(record.candidates_before, record.candidates_after), 1
        ):
            if before <= 0 or after <= 0:
                continue
            ratio = after / before
            ratios.append(ratio)
            bits.append(math.log2(before) - math.log2(after))
            by_round.setdefault(turn, []).append(ratio)
    if not ratios:
        return {
            "candidate_reduction_mean": 0.0,
            "candidate_reduction_geomean": 0.0,
            "information_gain_bits": 0.0,
            "information_gain_weighted": 0.0,
            "per_round_reduction": {},
        }
    geomean = math.exp(sum(math.log(ratio) for ratio in ratios) / len(ratios))
    gain = sum(bits) / len(bits)
    return {
        "candidate_reduction_mean": sum(ratios) / len(ratios),
        "candidate_reduction_geomean": geomean,
        "information_gain_bits": gain,
        # Under the uniform prior the weighted gain is the same quantity; Phase 5 adds
        # a non-uniform prior and reports the two separately.
        "information_gain_weighted": gain,
        "per_round_reduction": {
            turn: sum(values) / len(values) for turn, values in by_round.items() if values
        },
    }


def summarise(
    records: Sequence[GameRecord],
    *,
    profile_id: str,
    profile_manifest_sha256: str,
    strategy: str,
    objective: str,
    mode: RuleMode,
    max_attempts: int,
    total_s: float,
    guess_index: Mapping[str, int] | None = None,
    exhaustive: bool = True,
    answer_set_id: str = "all",
    seed: int | None = None,
    workers: int = 1,
    run_key: str = "",
) -> RunResult:
    if not records:
        raise ValueError("cannot summarise an empty run")
    answers = len(records)
    solved_records = [record for record in records if record.solved]
    solved = len(solved_records)
    failed = answers - solved

    distribution = {turn: 0 for turn in range(1, max_attempts + 1)}
    for record in solved_records:
        distribution[record.turns] += 1
    if sum(distribution.values()) != solved:  # pragma: no cover - defensive
        raise AssertionError("distribution does not sum to the solved count")

    turns = [record.turns for record in solved_records]
    avg_solved = sum(turns) / solved if solved else None
    charged = sum(turns) + failed * (max_attempts + 1)
    avg_all = charged / answers
    worst = max(turns) if turns else None
    worst_answer = None
    if worst is not None:
        worst_answer = next(record.answer for record in solved_records if record.turns == worst)

    pct_solved_in_k = {
        k: sum(1 for record in solved_records if record.turns <= k) / answers
        for k in range(1, max_attempts + 1)
    }

    decision_ms = [ms for record in records for ms in record.decision_ms]
    if decision_ms:
        array = np.asarray(decision_ms, dtype=np.float64)
        p50 = float(np.percentile(array, 50))
        p95 = float(np.percentile(array, 95))
        max_ms = float(array.max())
    else:  # pragma: no cover - every game records decisions
        p50 = p95 = max_ms = 0.0

    invalid = 0
    if guess_index is not None:
        invalid = sum(
            1 for record in records for guess in record.guesses if guess not in guess_index
        )

    return RunResult(
        profile_id=profile_id,
        profile_manifest_sha256=profile_manifest_sha256,
        strategy=strategy,
        objective=objective,
        mode=mode.value,
        max_attempts=max_attempts,
        answers=answers,
        solved=solved,
        failed=failed,
        distribution=distribution,
        avg_guesses_solved=avg_solved,
        avg_guesses_all=avg_all,
        median_guesses=float(np.median(turns)) if turns else None,
        worst_case=worst,
        worst_case_answer=worst_answer,
        determinism_sha256=determinism_hash(records),
        total_s=total_s,
        decision_p50_ms=p50,
        decision_p95_ms=p95,
        decision_max_ms=max_ms,
        failed_answers=tuple(record.answer for record in records if not record.solved),
        exhaustive=exhaustive,
        answer_set_id=answer_set_id,
        seed=seed,
        workers=workers,
        run_key=run_key,
        pct_solved_in_k=pct_solved_in_k,
        invalid_guess_count=invalid,
        mode_violation_count=sum(1 for record in records if record.mode_violation),
        answer_eliminated_count=sum(1 for record in records if record.answer_eliminated),
        **_efficiency(records),
    )


# ---- calibration metrics (§4.4) ------------------------------------------------


def log_loss(probabilities: Sequence[Sequence[float]], targets: Sequence[int]) -> float:
    """Mean negative log probability assigned to the target."""

    if len(probabilities) != len(targets):
        raise ValueError("probabilities and targets must have the same length")
    if not targets:
        raise ValueError("cannot compute log loss over zero samples")
    total = 0.0
    for row, target in zip(probabilities, targets):
        value = float(row[target])
        if value <= 0.0:
            return math.inf
        total -= math.log(value)
    return total / len(targets)


def brier(probabilities: Sequence[Sequence[float]], targets: Sequence[int]) -> float:
    """Mean squared error of the whole predicted distribution."""

    if len(probabilities) != len(targets):
        raise ValueError("probabilities and targets must have the same length")
    if not targets:
        raise ValueError("cannot compute Brier score over zero samples")
    total = 0.0
    for row, target in zip(probabilities, targets):
        total += sum(
            (float(value) - (1.0 if index == target else 0.0)) ** 2
            for index, value in enumerate(row)
        )
    return total / len(targets)


def reliability_curve(
    confidence: Sequence[float], correct: Sequence[bool], *, bins: int = 10
) -> list[dict]:
    """Equal-width bins of predicted confidence against observed accuracy."""

    if len(confidence) != len(correct):
        raise ValueError("confidence and correctness must have the same length")
    edges = np.linspace(0.0, 1.0, bins + 1)
    values = np.asarray(confidence, dtype=np.float64)
    hits = np.asarray(correct, dtype=np.float64)
    # Assign by bin index rather than by comparing to floating-point edges: a value
    # like 0.6 sits on an edge that is stored as 0.6000000000000001 and would fall into
    # the wrong bin. The epsilon keeps exact multiples of 1/bins in the upper bin.
    indices = np.clip(np.floor(values * bins + 1e-9).astype(int), 0, bins - 1)
    out: list[dict] = []
    for index in range(bins):
        low, high = float(edges[index]), float(edges[index + 1])
        mask = indices == index
        count = int(mask.sum())
        out.append(
            {
                "bin": index,
                "low": round(low, 6),
                "high": round(high, 6),
                "count": count,
                "confidence": float(values[mask].mean()) if count else None,
                "accuracy": float(hits[mask].mean()) if count else None,
            }
        )
    return out


def ece(confidence: Sequence[float], correct: Sequence[bool], *, bins: int = 10) -> float:
    """Expected calibration error over the reliability curve, weighted by bin mass."""

    if not len(confidence):
        raise ValueError("cannot compute ECE over zero samples")
    curve = reliability_curve(confidence, correct, bins=bins)
    total = len(confidence)
    return sum(
        entry["count"] / total * abs(entry["confidence"] - entry["accuracy"])
        for entry in curve
        if entry["count"]
    )


def top_k_hit_rate(
    rankings: Iterable[Sequence[int]], targets: Sequence[int], *, ks: Sequence[int] = (1, 10, 100)
) -> dict[int, float]:
    """Fraction of samples whose target appears in the first ``k`` ranked indices."""

    rows = list(rankings)
    if len(rows) != len(targets):
        raise ValueError("rankings and targets must have the same length")
    if not targets:
        raise ValueError("cannot compute top-k hit rate over zero samples")
    out: dict[int, float] = {}
    for k in ks:
        hits = sum(1 for row, target in zip(rows, targets) if target in list(row)[:k])
        out[k] = hits / len(targets)
    return out
