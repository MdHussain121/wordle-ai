"""Strategy layer: registry, objectives, determinism and scoring correctness (§6).

These tests pin the two properties the plan depends on: a strategy's choice is a pure
function of the state (the same inputs give the same word, every time), and the
partition statistics every objective reads are the brute-force values, not something
that merely looks plausible.
"""

from __future__ import annotations

import math
from collections import Counter

import numpy as np
import pytest

from wordle_ai.engine.feedback import feedback_row
from wordle_ai.engine.state import new_game
from wordle_ai.engine.table import ComputedRows, build_table, FeedbackTable, save_table
from wordle_ai.strategy import STRATEGY_NAMES, describe, get_strategy
from wordle_ai.strategy.base import PartitionStats
from wordle_ai.types import Profile

REQUIRED = {
    "entropy",
    "entropy_candidates",
    "expected_remaining",
    "expected_remaining_candidates",
    "first_candidate",
    "letter_frequency",
    "minimax",
    "positional_frequency",
}

WORDS_2 = ("aa", "ab", "ba", "bb")


def tiny_profile() -> Profile:
    return Profile(
        profile_id="tiny.ab.2",
        language="ab",
        dialect=None,
        length=2,
        alphabet="ab",
        answers=WORDS_2,
        guesses=WORDS_2,
        manifest_sha256="0" * 64,
        answer_index={word: i for i, word in enumerate(WORDS_2)},
        guess_index={word: i for i, word in enumerate(WORDS_2)},
    )


def test_every_required_strategy_is_registered_with_an_objective():
    assert REQUIRED <= set(STRATEGY_NAMES)
    entries = describe()
    assert [entry["name"] for entry in entries] == list(STRATEGY_NAMES)
    for entry in entries:
        assert entry["objective"].strip()
        assert isinstance(entry["candidate_only"], bool)
    assert sum(1 for entry in entries if entry["candidate_only"]) >= 3


def test_unknown_strategy_name_is_rejected():
    with pytest.raises(KeyError) as excinfo:
        get_strategy("nope")
    assert "entropy" in str(excinfo.value)


@pytest.mark.parametrize("name", sorted(REQUIRED))
def test_choice_is_deterministic_for_identical_inputs(name, strict_profiles):
    profile = strict_profiles["strict.en.2"]
    rows = ComputedRows(profile)
    strategy = get_strategy(name)
    state = new_game(profile)
    first = strategy.choose(state, rows)
    second = strategy.choose(new_game(profile), rows)
    assert first.guess == second.guess
    assert first.score == second.score
    assert first.candidates_before == second.candidates_before == len(profile.answers)
    assert first.guess in profile.guess_index


def test_opener_falls_out_of_the_profile_not_a_constant(strict_profiles):
    rows_2 = ComputedRows(strict_profiles["strict.en.2"])
    rows_3 = ComputedRows(strict_profiles["strict.en.3"])
    openers = {}
    for length, rows in ((2, rows_2), (3, rows_3)):
        profile = strict_profiles[f"strict.en.{length}"]
        decision = get_strategy("entropy").choose(new_game(profile), rows)
        assert decision.guess in profile.guess_index
        openers[length] = decision.guess
    assert openers[2] != openers[3]


def test_entropy_opener_equals_bruteforce_argmax(strict_profiles):
    """Recompute the entropy of every opener from the reference feedback path."""

    profile = strict_profiles["strict.en.2"]
    rows = ComputedRows(profile)
    n = len(profile.answers)

    def score(word: str) -> tuple[float, float]:
        counts = Counter(feedback_row(word, profile.answers, profile.alphabet).tolist())
        entropy = -sum((c / n) * math.log2(c / n) for c in counts.values())
        expected = sum(c * c for c in counts.values()) / n
        return entropy, expected

    ranked = sorted(
        ((word, *score(word)) for word in profile.guesses),
        key=lambda item: (-round(item[1], 12), round(item[2], 12), profile.guess_index[item[0]]),
    )
    decision = get_strategy("entropy").choose(new_game(profile), rows)
    assert decision.guess == ranked[0][0]
    assert decision.breakdown["entropy"] == pytest.approx(ranked[0][1], abs=1e-9)


def test_score_returns_a_breakdown_for_every_legal_guess(strict_profiles):
    profile = strict_profiles["strict.en.2"]
    rows = ComputedRows(profile)
    scores = get_strategy("entropy").score(new_game(profile), rows)
    assert len(scores) == len(profile.guesses)
    assert {entry.guess for entry in scores} == set(profile.guesses)
    assert all(entry.breakdown for entry in scores)


def test_uniform_prior_matches_no_prior(strict_profiles):
    profile = strict_profiles["strict.en.2"]
    rows = ComputedRows(profile)
    strategy = get_strategy("expected_remaining")
    state = new_game(profile)
    without = strategy.choose(state, rows)
    with_uniform = strategy.choose(state, rows, prior=np.ones(len(profile.answers)))
    assert without.guess == with_uniform.guess
    assert without.breakdown["expected_remaining"] == pytest.approx(
        with_uniform.breakdown["expected_remaining"], abs=1e-12
    )


def test_partition_statistics_match_bruteforce():
    profile = tiny_profile()
    rows = build_table(profile)
    stats = PartitionStats(rows, profile.pattern_count).compute(np.ones(4, dtype=bool))
    n = len(profile.answers)
    for index, word in enumerate(profile.guesses):
        counts = np.bincount(rows[index], minlength=profile.pattern_count).astype(np.float64)
        probabilities = counts / n
        entropy = -sum(p * math.log2(p) for p in probabilities if p > 0)
        assert stats["expected_remaining"][index] == pytest.approx(float((counts ** 2).sum()) / n)
        assert stats["entropy"][index] == pytest.approx(entropy)
        assert stats["worst_case"][index] == float(counts.max())
        assert stats["p_solve_now"][index] == pytest.approx(
            1.0 / n if word in profile.answer_index else 0.0
        )


def test_partition_statistics_honour_a_prior():
    profile = tiny_profile()
    rows = build_table(profile)
    weights = np.array([0.7, 0.1, 0.1, 0.1])
    stats = PartitionStats(rows, profile.pattern_count).compute(
        np.ones(4, dtype=bool), weights
    )
    index = profile.guess_index_of("aa")
    counts = np.bincount(rows[index], minlength=profile.pattern_count).astype(np.float64)
    weighted = np.zeros_like(counts)
    for column, code in enumerate(rows[index]):
        weighted[code] += weights[column]
    assert stats["expected_remaining"][index] == pytest.approx(
        float((weighted * counts).sum())
    )


def test_dense_and_sparse_paths_agree(strict_profiles):
    """The sparse endgame path and the dense pattern-space path are the same maths."""

    profile = strict_profiles["strict.en.3"]
    rows = np.stack([feedback_row(w, profile.answers, profile.alphabet) for w in profile.guesses])
    for size in (1, 2, 5, 40):
        mask = np.zeros(len(profile.answers), dtype=bool)
        mask[:size] = True
        stats = PartitionStats(rows, profile.pattern_count).compute(mask)
        for index in (0, 7, len(profile.guesses) - 1):
            counts = np.bincount(rows[index][mask], minlength=profile.pattern_count).astype(float)
            probabilities = counts / size
            entropy = -sum(p * math.log2(p) for p in probabilities if p > 0)
            assert stats["expected_remaining"][index] == pytest.approx(float((counts ** 2).sum()) / size)
            assert stats["entropy"][index] == pytest.approx(entropy, abs=1e-9)


def test_objectives_disagree_on_at_least_one_real_state(strict_profiles):
    """Entropy and expected-remaining are different objectives, not aliases."""

    profile = strict_profiles["strict.en.3"]
    rows = ComputedRows(profile)
    entropy = get_strategy("entropy")
    expected = get_strategy("expected_remaining")
    state = new_game(profile)
    disagreements = 0
    for answer in profile.answers[:6]:
        current = state
        for _ in range(2):
            left = entropy.choose(current, rows).guess
            right = expected.choose(current, rows).guess
            if left != right:
                disagreements += 1
                break
            from wordle_ai.engine.feedback import feedback_pattern

            pattern = feedback_pattern(left, answer)
            if left == answer:
                break
            current = current.apply(left, pattern)
    assert disagreements > 0


def test_first_candidate_picks_the_alphabetically_first_candidate():
    profile = tiny_profile()
    rows = ComputedRows(profile)
    decision = get_strategy("first_candidate").choose(new_game(profile), rows)
    assert decision.guess == profile.answers[0]
    assert decision.breakdown["branch"] in {"first_candidate", "endgame_candidate"}
