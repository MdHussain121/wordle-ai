"""Hand-computed fixtures for the §4.5 paired statistics."""

from __future__ import annotations

import math

import pytest

from wordle_ai.bench.stats import (
    bootstrap_mean_difference,
    mcnemar,
    paired_comparison,
    wilcoxon_signed_rank,
)
from wordle_ai.sim.runner import GameRecord


def test_bootstrap_interval_is_seeded_and_signed():
    a = [1.0, 1.0, 2.0, 2.0, 1.0]
    b = [3.0, 3.0, 3.0, 3.0, 3.0]
    first = bootstrap_mean_difference(a, b, samples=500, seed=7)
    second = bootstrap_mean_difference(a, b, samples=500, seed=7)
    assert first == second
    # every paired difference is -2 or -1, so the mean is -1.6
    assert first["mean_difference"] == pytest.approx(-1.6)
    assert first["ci_high"] < 0.0
    assert first["significant"] is True


def test_bootstrap_is_insignificant_when_the_mean_is_zero():
    result = bootstrap_mean_difference([1.0, 2.0, 3.0], [3.0, 2.0, 1.0], samples=500, seed=1)
    assert result["mean_difference"] == pytest.approx(0.0)
    assert result["ci_low"] <= 0.0 <= result["ci_high"]
    assert result["significant"] is False


def test_mcnemar_exact_binomial():
    # 4 discordant pairs, all favouring A: p = 2 * C(4,0) / 2**4
    result = mcnemar([True] * 4 + [False] * 2, [False] * 4 + [False] * 2)
    assert (result["only_a"], result["only_b"]) == (4, 0)
    assert result["p_value"] == pytest.approx(2 / 16)


def test_mcnemar_with_no_discordant_pairs_is_uninformative():
    assert mcnemar([True, False], [True, False])["p_value"] == 1.0


def test_wilcoxon_normal_approximation_matches_hand_formula():
    # six positive differences of distinct size: W+ = 21, mu = 10.5,
    # sigma^2 = 6*7*13/24 = 22.75, z = 2.2016, two-sided p = 0.0277
    differences_b = [0.0] * 6
    differences_a = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    result = wilcoxon_signed_rank(differences_a, differences_b)
    expected_z = (21 - 10.5) / math.sqrt(22.75)
    expected_p = 2 * (1 - 0.5 * math.erfc(-expected_z / math.sqrt(2)))
    assert result["statistic"] == pytest.approx(21.0)
    assert result["p_value"] == pytest.approx(expected_p)
    assert result["rank_biserial"] == pytest.approx(1.0)
    assert result["approximate"] is True


def test_wilcoxon_with_zero_differences_excludes_them():
    result = wilcoxon_signed_rank([2.0, 2.0, 3.0], [2.0, 1.0, 1.0])
    assert result["n"] == 2
    assert result["approximate"] is False  # too few pairs for the normal approximation


def _game(answer: str, turns: int, solved: bool) -> GameRecord:
    return GameRecord(
        answer=answer,
        guesses=tuple(["aaaa"] * turns),
        solved=solved,
        decision_ms=tuple(1.0 for _ in range(turns)),
    )


def test_paired_comparison_charges_failures_and_refuses_mismatched_sets():
    a = [_game("aaaa", 3, True), _game("bbbb", 6, False)]
    b = [_game("aaaa", 4, True), _game("bbbb", 2, True)]
    result = paired_comparison(a, b, max_attempts=6, samples=200, seed=3)
    # charged turns: A = 3, 7; B = 4, 2 -> means 5.0 and 3.0
    assert result["mean_a"] == pytest.approx(5.0)
    assert result["mean_b"] == pytest.approx(3.0)
    assert result["mcnemar"] == {"only_a": 0, "only_b": 1, "p_value": 1.0}

    with pytest.raises(ValueError, match="answer sets differ"):
        paired_comparison(a, b[:1], max_attempts=6)

    with pytest.raises(ValueError, match="answer sets differ"):
        paired_comparison(a, [_game("zzzz", 1, True), b[1]], max_attempts=6)
