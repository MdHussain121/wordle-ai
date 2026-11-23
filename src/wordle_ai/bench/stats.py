"""Paired statistics for benchmark comparisons (benchmark plan §4.5).

Implemented with numpy and ``math`` only: no scipy, no statsmodels. Each test is
small enough to read and is checked against a hand-computed fixture.

The rules the plan fixes, and which this module enforces in its return values:

* paired by answer word, never by aggregate;
* a 10,000-resample bootstrap interval on the mean difference, seeded;
* McNemar's exact test for solve/fail differences;
* Wilcoxon signed-rank for guess-count differences, with the effect size reported;
* a difference is not an improvement if its bootstrap interval includes zero.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from ..sim.runner import GameRecord


def _normal_cdf(value: float) -> float:
    return 0.5 * math.erfc(-value / math.sqrt(2.0))


def _average_ranks(values: np.ndarray) -> np.ndarray:
    """Ranks with ties receiving their average rank (1-based)."""

    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=np.float64)
    sorted_values = values[order]
    start = 0
    while start < len(values):
        stop = start + 1
        while stop < len(values) and sorted_values[stop] == sorted_values[start]:
            stop += 1
        ranks[order[start:stop]] = (start + stop + 1) / 2.0
        start = stop
    return ranks


def bootstrap_mean_difference(
    a: Sequence[float],
    b: Sequence[float],
    *,
    samples: int = 10_000,
    seed: int = 20261119,
    confidence: float = 0.95,
) -> dict:
    """Bootstrap interval for ``mean(a - b)`` over paired observations."""

    if len(a) != len(b):
        raise ValueError("paired samples must have the same length")
    if not a:
        raise ValueError("cannot bootstrap an empty sample")
    differences = np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(differences), size=(samples, len(differences)))
    means = differences[indices].mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    low, high = np.percentile(means, [100 * alpha, 100 * (1 - alpha)])
    return {
        "mean_difference": float(differences.mean()),
        "ci_low": float(low),
        "ci_high": float(high),
        "confidence": confidence,
        "samples": samples,
        "significant": bool(low > 0.0 or high < 0.0),
    }


def mcnemar(solved_a: Sequence[bool], solved_b: Sequence[bool]) -> dict:
    """Exact two-sided McNemar test on paired solve/fail outcomes."""

    if len(solved_a) != len(solved_b):
        raise ValueError("paired samples must have the same length")
    only_a = sum(1 for x, y in zip(solved_a, solved_b) if x and not y)
    only_b = sum(1 for x, y in zip(solved_a, solved_b) if y and not x)
    discordant = only_a + only_b
    if discordant == 0:
        return {"only_a": 0, "only_b": 0, "p_value": 1.0}
    tail = sum(math.comb(discordant, k) for k in range(min(only_a, only_b) + 1))
    p_value = min(1.0, 2.0 * tail / (2.0**discordant))
    return {"only_a": only_a, "only_b": only_b, "p_value": p_value}


def wilcoxon_signed_rank(
    a: Sequence[float], b: Sequence[float], *, z_epsilon: float = 1e-12
) -> dict:
    """Two-sided Wilcoxon signed-rank test using the normal approximation.

    Zero differences are dropped, ties get average ranks, and the variance carries the
    standard tie correction. With fewer than 6 non-zero pairs the normal approximation
    is unreliable, so ``approximate`` is reported as ``False`` for the caller to see.
    """

    if len(a) != len(b):
        raise ValueError("paired samples must have the same length")
    differences = np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    differences = differences[np.abs(differences) > z_epsilon]
    n = int(differences.size)
    if n == 0:
        return {
            "n": 0,
            "statistic": 0.0,
            "p_value": 1.0,
            "rank_biserial": 0.0,
            "approximate": False,
        }

    ranks = _average_ranks(np.abs(differences))
    positive = float(ranks[differences > 0].sum())
    negative = float(ranks[differences < 0].sum())
    total = positive + negative
    rank_biserial = (positive - negative) / total if total else 0.0

    mean = n * (n + 1) / 4.0
    variance = n * (n + 1) * (2 * n + 1) / 24.0
    _, counts = np.unique(np.abs(differences), return_counts=True)
    variance -= float(((counts.astype(np.float64) ** 3) - counts).sum()) / 48.0
    if variance <= 0:
        p_value = 1.0
    else:
        z = (positive - mean) / math.sqrt(variance)
        p_value = min(1.0, 2.0 * (1.0 - _normal_cdf(abs(z))))
    return {
        "n": n,
        "statistic": positive,
        "p_value": p_value,
        "rank_biserial": rank_biserial,
        "approximate": n >= 6,
    }


def _charged_turns(records: Sequence[GameRecord], max_attempts: int) -> list[float]:
    """Guess counts with failures charged ``K + 1`` (the §4.1 convention)."""

    return [
        float(record.turns) if record.solved else float(max_attempts + 1) for record in records
    ]


def paired_comparison(
    a: Sequence[GameRecord],
    b: Sequence[GameRecord],
    *,
    max_attempts: int = 6,
    samples: int = 10_000,
    seed: int = 20261119,
) -> dict:
    """Compare two runs answer by answer; refuses mismatched answer sets."""

    index_b = {record.answer: record for record in b}
    if len(index_b) != len(b):
        raise ValueError("run B contains a duplicate answer")
    missing = [record.answer for record in a if record.answer not in index_b]
    if missing:
        raise ValueError(
            f"answer sets differ: {len(missing)} answer(s) of run A are absent from run B "
            f"(first: {missing[0]!r})"
        )
    if len(a) != len(b):
        raise ValueError(
            f"answer sets differ in size: {len(a)} vs {len(b)}; a paired test needs equal sets"
        )

    turns_a = _charged_turns(a, max_attempts)
    turns_b = [float(index_b[record.answer].turns) if index_b[record.answer].solved
               else float(max_attempts + 1) for record in a]
    solved_a = [record.solved for record in a]
    solved_b = [index_b[record.answer].solved for record in a]
    differences = [x - y for x, y in zip(turns_a, turns_b)]
    return {
        "answers": len(a),
        "mean_a": sum(turns_a) / len(a),
        "mean_b": sum(turns_b) / len(b),
        "median_difference": float(np.median(differences)),
        "bootstrap": bootstrap_mean_difference(turns_a, turns_b, samples=samples, seed=seed),
        "mcnemar": mcnemar(solved_a, solved_b),
        "wilcoxon": wilcoxon_signed_rank(turns_a, turns_b),
    }
