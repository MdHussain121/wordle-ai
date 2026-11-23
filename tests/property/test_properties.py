"""Properties that must hold for every input, not just the sampled ones."""

from __future__ import annotations

from collections import Counter

import pytest
from hypothesis import given, settings as hyp_settings, strategies as st

from wordle_ai.engine.feedback import encode_tiles, feedback_code, feedback_tiles
from wordle_ai.engine.state import new_game
from wordle_ai.types import Pattern, Profile, Tile

ALPHABET = "abc"
WORDS = tuple(a + b + c for a in ALPHABET for b in ALPHABET for c in ALPHABET)

PROFILE = Profile(
    profile_id="all.abc.3",
    language="abc",
    dialect=None,
    length=3,
    alphabet=ALPHABET,
    answers=WORDS,
    guesses=WORDS,
    manifest_sha256="0" * 64,
    answer_index={w: i for i, w in enumerate(WORDS)},
    guess_index={w: i for i, w in enumerate(WORDS)},
)

words = st.sampled_from(WORDS)


@given(guess=words, answer=words)
@hyp_settings(max_examples=300, deadline=None)
def test_green_count_equals_exact_matches(guess, answer):
    tiles = feedback_tiles(guess, answer)
    assert sum(1 for t in tiles if t == Tile.GREEN) == sum(
        1 for g, a in zip(guess, answer) if g == a
    )


@given(guess=words, answer=words)
@hyp_settings(max_examples=300, deadline=None)
def test_non_gray_tiles_never_exceed_letter_multisets(guess, answer):
    tiles = feedback_tiles(guess, answer)
    guess_counts = Counter(guess)
    answer_counts = Counter(answer)
    marked = Counter(g for g, t in zip(guess, tiles) if t != Tile.GRAY)
    for letter, count in marked.items():
        assert count <= min(guess_counts[letter], answer_counts[letter])


@given(guess=words, answer=words)
@hyp_settings(max_examples=300, deadline=None)
def test_absent_letters_are_always_gray(guess, answer):
    tiles = feedback_tiles(guess, answer)
    for g, t in zip(guess, tiles):
        if g not in answer:
            assert t == Tile.GRAY


@given(guess=words, answer=words)
@hyp_settings(max_examples=300, deadline=None)
def test_feedback_is_deterministic(guess, answer):
    assert feedback_code(guess, answer) == feedback_code(guess, answer)


@given(guess=words, answer=words)
@hyp_settings(max_examples=300, deadline=None)
def test_pattern_codec_roundtrips(guess, answer):
    tiles = feedback_tiles(guess, answer)
    encoded = encode_tiles(tiles)
    assert Pattern(code=encoded, length=3).tiles() == tiles


@given(guess=words, answer=words)
@hyp_settings(max_examples=200, deadline=None)
def test_true_answer_always_survives_filtering(guess, answer):
    state = new_game(PROFILE, max_attempts=1)
    nxt = state.apply(guess, Pattern(code=feedback_code(guess, answer), length=3))
    assert answer in nxt.candidate_words
    assert nxt.remaining >= 1
    assert nxt.posterior.sum() == pytest.approx(1.0)
