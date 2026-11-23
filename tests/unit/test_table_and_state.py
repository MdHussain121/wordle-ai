"""Feedback tables, candidate filtering and game-state replay (§5, §7)."""

from __future__ import annotations

import numpy as np
import pytest

from wordle_ai.engine.feedback import (
    encode_words,
    feedback_code,
    feedback_pattern,
    feedback_row,
)
from wordle_ai.engine.filter import filter_mask, from_bitset, popcount, to_bitset
from wordle_ai.engine.state import new_game, replay
from wordle_ai.engine.table import FeedbackTable, build_table, save_table, table_footprint
from wordle_ai.errors import InconsistentFeedback, ProfileIntegrityError
from wordle_ai.types import Pattern, Profile, RuleMode, Turn

WORDS = ("aa", "ab", "ba", "bb")


def tiny_profile() -> Profile:
    return Profile(
        profile_id="tiny.ab.2",
        language="ab",
        dialect=None,
        length=2,
        alphabet="ab",
        answers=WORDS,
        guesses=WORDS,
        manifest_sha256="0" * 64,
        answer_index={w: i for i, w in enumerate(WORDS)},
        guess_index={w: i for i, w in enumerate(WORDS)},
    )


def test_table_matches_feedback_row():
    profile = tiny_profile()
    table = build_table(profile)
    assert table.shape == (4, 4)
    assert table.dtype == np.uint8
    for i, guess in enumerate(profile.guesses):
        np.testing.assert_array_equal(table[i], feedback_row(guess, profile.answers, "ab"))


def test_table_footprint_and_budget():
    profile = tiny_profile()
    assert table_footprint(profile) == 16


def test_save_table_is_deterministic(tmp_path):
    profile = tiny_profile()
    table = build_table(profile)
    first, size_first = save_table(table, tmp_path / "a.npy")
    second, size_second = save_table(table, tmp_path / "b.npy")
    assert first == second
    assert size_first == size_second


def test_feedback_table_mmaps_and_caches(tmp_path):
    profile = tiny_profile()
    table = build_table(profile)
    save_table(table, tmp_path / "t.npy")
    loaded = FeedbackTable(tmp_path / "t.npy", profile, lru_rows=2)
    for i, guess in enumerate(profile.guesses):
        np.testing.assert_array_equal(loaded.row(guess), table[i])
    # Cache eviction must not change answers.
    np.testing.assert_array_equal(loaded.row("aa"), table[0])


def test_feedback_table_matrix_stays_memory_mapped(tmp_path):
    """Scoring reads the map in place; copying it would cost a table per worker."""

    profile = tiny_profile()
    save_table(build_table(profile), tmp_path / "t.npy")
    loaded = FeedbackTable(tmp_path / "t.npy", profile)
    matrix = loaded.matrix()
    assert isinstance(matrix, np.memmap)
    np.testing.assert_array_equal(matrix, build_table(profile))


def test_feedback_table_rejects_shape_mismatch(tmp_path):
    profile = tiny_profile()
    np.save(tmp_path / "t.npy", np.zeros((2, 2), dtype=np.uint8))
    with pytest.raises(ProfileIntegrityError):
        FeedbackTable(tmp_path / "t.npy", profile)


def test_filter_mask_is_monotonic():
    mask = np.ones(4, dtype=bool)
    row = feedback_row("aa", WORDS, "ab")
    code = int(row[0])
    narrowed = filter_mask(mask, row, code)
    assert narrowed.sum() <= mask.sum()
    assert np.all(narrowed <= mask)
    assert narrowed[0]


def test_filter_mask_rejects_impossible_pattern():
    mask = np.ones(4, dtype=bool)
    row = feedback_row("aa", WORDS, "ab")
    produced = {int(value) for value in row}
    impossible = next(code for code in range(9) if code not in produced)
    with pytest.raises(InconsistentFeedback):
        filter_mask(mask, row, impossible)


@pytest.mark.parametrize("size", [3, 64, 65, 200])
def test_bitset_roundtrip(size):
    rng = np.random.default_rng(size)
    mask = rng.integers(0, 2, size=size).astype(bool)
    packed = to_bitset(mask)
    restored = from_bitset(packed, size)
    assert popcount(restored) == popcount(mask)
    np.testing.assert_array_equal(restored, mask)


def test_state_starts_with_every_candidate():
    state = new_game(tiny_profile())
    assert state.remaining == 4
    assert state.candidate_words == list(WORDS)
    np.testing.assert_allclose(state.posterior.sum(), 1.0)


def test_state_apply_narrows_and_keeps_truth():
    profile = tiny_profile()
    state = new_game(profile)
    guess, answer = "ab", "ba"
    pattern = feedback_pattern(guess, answer)
    nxt = state.apply(guess, pattern)
    assert answer in nxt.candidate_words
    assert nxt.remaining < state.remaining
    assert nxt.history[-1].guess == guess


def test_state_replay_equals_sequential_apply(strict_profiles):
    profile = strict_profiles["strict.en.3"]
    answer = profile.answers[17]
    turns = []
    state = new_game(profile)
    for guess in (profile.guesses[100], profile.guesses[301]):
        pattern = feedback_pattern(guess, answer)
        turns.append(Turn(guess=guess, pattern=pattern))
        state = state.apply(guess, pattern)
    replayed = replay(profile, turns)
    assert replayed.candidate_words == state.candidate_words
    assert replayed.remaining == state.remaining
    assert answer in replayed.candidate_words


def test_solved_state_invariants():
    profile = tiny_profile()
    answer = "ba"
    state = new_game(profile).apply(answer, feedback_pattern(answer, answer))
    assert state.is_solved()
    assert state.remaining == 1
    assert state.candidate_words == [answer]
    index = profile.answer_index[answer]
    assert state.posterior[index] == pytest.approx(1.0)
    assert np.count_nonzero(state.posterior) == 1


def test_attempt_limit_is_enforced():
    profile = tiny_profile()
    state = new_game(profile, max_attempts=1).apply("aa", feedback_pattern("aa", "aa"))
    with pytest.raises(ProfileIntegrityError):
        state.apply("ab", feedback_pattern("ab", "aa"))


def test_inconsistent_history_is_rejected():
    profile = tiny_profile()
    with pytest.raises(InconsistentFeedback):
        new_game(profile).apply("aa", Pattern(code=1, length=2))


def test_mode_is_carried_through_apply():
    profile = tiny_profile()
    state = new_game(profile, mode=RuleMode.HARD)
    nxt = state.apply("ab", feedback_pattern("ab", "ba"))
    assert nxt.mode is RuleMode.HARD


def test_pattern_enum_code_agrees_with_scalar():
    for guess in WORDS:
        for answer in WORDS:
            assert feedback_pattern(guess, answer).code == feedback_code(guess, answer)
