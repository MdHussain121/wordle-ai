"""Hand-computed fixtures for the §4 metric formulas.

Each expected value below is written out from the definition, not from the code: if a
formula drifts, the fixture stops matching for a reason the test names.
"""

from __future__ import annotations

import math

import pytest

from wordle_ai.bench.metrics import (
    brier,
    determinism_hash,
    ece,
    log_loss,
    reliability_curve,
    summarise,
    top_k_hit_rate,
)
from wordle_ai.sim.runner import GameRecord
from wordle_ai.types import RuleMode

K = 6


def game(answer: str, guesses: list[str], solved: bool, before, after) -> GameRecord:
    return GameRecord(
        answer=answer,
        guesses=tuple(guesses),
        solved=solved,
        decision_ms=tuple(1.0 for _ in guesses),
        candidates_before=tuple(before),
        candidates_after=tuple(after),
    )


@pytest.fixture()
def records() -> list[GameRecord]:
    return [
        game("aaaa", ["aaaa"], True, [2315], [1]),
        game("bbbb", ["cccc", "bbbb"], True, [2315, 10], [10, 1]),
        game("dddd", ["eeee", "ffff", "gggg", "dddd"], True, [2315, 30, 3, 1], [30, 3, 1, 1]),
        game("hhhh", ["iiii", "jjjj", "kkkk", "llll", "mmmm", "nnnn"], False,
             [2315, 100, 20, 5, 2, 2], [100, 20, 5, 2, 2, 2]),
    ]


def summarised(records, **overrides):
    payload = dict(
        profile_id="fixture.en.5",
        profile_manifest_sha256="0" * 64,
        strategy="fixture",
        objective="fixture",
        mode=RuleMode.NORMAL,
        max_attempts=K,
        total_s=1.0,
    )
    payload.update(overrides)
    return summarise(records, **payload)


def test_outcome_metrics_match_hand_arithmetic(records):
    result = summarised(records)

    assert (result.answers, result.solved, result.failed) == (4, 3, 1)
    # solved turns are 1, 2, 4 -> mean 7/3
    assert result.avg_guesses_solved == pytest.approx(7 / 3)
    # one failure is charged K+1 = 7 -> (7 + 7) / 4
    assert result.avg_guesses_all == pytest.approx(3.5)
    assert result.median_guesses == pytest.approx(2.0)
    assert (result.worst_case, result.worst_case_answer) == (4, "dddd")
    assert result.success_rate == pytest.approx(0.75)
    assert result.failure_rate == pytest.approx(0.25)
    assert result.distribution == {1: 1, 2: 1, 3: 0, 4: 1, 5: 0, 6: 0}
    assert sum(result.distribution.values()) == result.solved
    # pct_solved_in_k uses N, not the solved count, in the denominator
    assert result.pct_solved_in_k == {
        1: 0.25, 2: 0.5, 3: 0.5, 4: 0.75, 5: 0.75, 6: 0.75
    }
    assert result.total_guesses == 7


def test_efficiency_metrics_match_hand_arithmetic(records):
    result = summarised(records)

    ratios = [
        1 / 2315,
        10 / 2315, 1 / 10,
        30 / 2315, 3 / 30, 1 / 3, 1 / 1,
        100 / 2315, 20 / 100, 5 / 20, 2 / 5, 2 / 2, 2 / 2,
    ]
    assert result.candidate_reduction_mean == pytest.approx(sum(ratios) / len(ratios))
    assert result.candidate_reduction_geomean == pytest.approx(
        math.exp(sum(math.log(r) for r in ratios) / len(ratios))
    )
    bits = [
        math.log2(2315) - math.log2(1),
        math.log2(2315) - math.log2(10), math.log2(10) - math.log2(1),
        math.log2(2315) - math.log2(30), math.log2(30) - math.log2(3),
        math.log2(3) - math.log2(1), 0.0,
        math.log2(2315) - math.log2(100), math.log2(100) - math.log2(20),
        math.log2(20) - math.log2(5), math.log2(5) - math.log2(2), 0.0, 0.0,
    ]
    assert result.information_gain_bits == pytest.approx(sum(bits) / len(bits))
    # uniform prior: the weighted gain is the same number, reported separately in Phase 5
    assert result.information_gain_weighted == pytest.approx(result.information_gain_bits)
    # turn 1 always shrinks 2315 to one of 1, 10, 30, 100
    assert result.per_round_reduction[1] == pytest.approx(
        (1 / 2315 + 10 / 2315 + 30 / 2315 + 100 / 2315) / 4
    )


def test_correctness_counters_are_measured(records):
    result = summarised(records, guess_index={f"{letter}{letter}{letter}{letter}": 1 for letter in "abcdefgh"})
    # the fixture guesses are iii..nnn, none of which is in the a..h guess index
    assert result.invalid_guess_count == 6
    assert result.mode_violation_count == 0
    assert result.answer_eliminated_count == 0


def test_failed_run_reports_both_averages():
    failed = [game("aaaa", ["bbbb", "cccc"], False, [2315, 2], [2, 2])]
    result = summarised(failed)
    assert result.solved == 0
    assert result.avg_guesses_solved is None
    assert result.avg_guesses_all == pytest.approx(7.0)
    assert result.failed_answers == ("aaaa",)
    assert result.worst_case is None


def test_determinism_hash_ignores_order(records):
    assert determinism_hash(records) == determinism_hash(list(reversed(records)))
    assert determinism_hash(records) != determinism_hash(records[:-1])


def test_log_loss_and_brier_match_hand_arithmetic():
    probabilities = [[0.5, 0.5], [1.0, 0.0]]
    targets = [0, 0]
    assert log_loss(probabilities, targets) == pytest.approx(math.log(2) / 2)
    assert brier(probabilities, targets) == pytest.approx(0.25)


def test_log_loss_is_infinite_for_an_impossible_prediction():
    assert log_loss([[0.0, 1.0]], [0]) == math.inf


def test_reliability_curve_and_ece_match_hand_arithmetic():
    confidence = [0.9, 0.9, 0.6, 0.6]
    correct = [True, True, True, False]

    curve = {entry["bin"]: entry for entry in reliability_curve(confidence, correct, bins=10)}
    assert curve[9]["count"] == 2
    assert curve[9]["confidence"] == pytest.approx(0.9)
    assert curve[9]["accuracy"] == pytest.approx(1.0)
    assert curve[6]["count"] == 2
    assert curve[6]["confidence"] == pytest.approx(0.6)
    assert curve[6]["accuracy"] == pytest.approx(0.5)
    # 0.5 * |0.9 - 1.0| + 0.5 * |0.6 - 0.5|
    assert ece(confidence, correct, bins=10) == pytest.approx(0.1)


def test_top_k_hit_rate_matches_hand_arithmetic():
    rankings = [[0, 1, 2], [3, 4, 5]]
    targets = [1, 5]
    assert top_k_hit_rate(rankings, targets, ks=(1, 3)) == {1: 0.0, 3: 1.0}
