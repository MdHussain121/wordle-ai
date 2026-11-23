"""Feedback correctness: golden duplicate cases, exhaustive equality, codec round-trips."""

from __future__ import annotations

import numpy as np
import pytest

from tests.reference import reference_code, reference_tiles
from wordle_ai.engine.feedback import (
    encode_tiles,
    encode_words,
    feedback_code,
    feedback_pattern,
    feedback_row,
    feedback_row_codes,
    feedback_tiles,
)
from wordle_ai.errors import InvalidPattern
from wordle_ai.types import Pattern, Tile


# (guess, answer, expected tiles). Expectations were produced by the independent
# reference in tests/reference.py and then checked by hand (six of them re-derived
# manually) before being frozen here, so the table is not a snapshot of the engine.
GOLDEN = [
    ("sassy", "assay", (1, 1, 2, 0, 2)),
    ("eerie", "eagle", (2, 0, 0, 0, 2)),
    ("allee", "apple", (2, 1, 0, 0, 2)),
    ("llama", "lolly", (2, 1, 0, 0, 0)),
    ("abbey", "babes", (1, 1, 2, 2, 0)),
    ("speed", "abide", (0, 0, 1, 0, 1)),
    ("array", "radar", (1, 1, 1, 2, 0)),
    ("tepee", "epees", (0, 1, 1, 2, 1)),
    ("mamma", "mamma", (2, 2, 2, 2, 2)),
    ("aaaaa", "aaaab", (2, 2, 2, 2, 0)),
    ("baaaa", "aaaab", (1, 2, 2, 2, 1)),
    ("xxyxx", "yxxxx", (1, 2, 1, 2, 2)),
]


@pytest.mark.parametrize("guess,answer,expected", GOLDEN)
def test_golden_duplicate_cases(guess, answer, expected):
    assert feedback_tiles(guess, answer) == tuple(Tile(t) for t in expected)
    assert feedback_tiles(guess, answer) == reference_tiles(guess, answer)


def test_repeated_letter_cannot_exceed_answer_multiset():
    # "broke" has one 'e'; "eerie" guesses three. Only the green survives; the other
    # two copies must be gray, and the leftover 'r' is the single yellow.
    assert feedback_tiles("eerie", "broke") == (
        Tile.GRAY, Tile.GRAY, Tile.YELLOW, Tile.GRAY, Tile.GREEN,
    )

    # Two 's' in the guess, one in the answer: the later copy has no copy left.
    tiles = feedback_tiles("sassy", "shaft")
    assert tiles[0] == Tile.GREEN
    assert tiles[2] == Tile.GRAY
    assert sum(1 for t in tiles if t != Tile.GRAY) == 2


def test_gray_only_letter_never_yellow():
    tiles = feedback_tiles("zzzzz", "apple")
    assert all(t == Tile.GRAY for t in tiles)


def test_pattern_codec_roundtrip():
    for tiles in [(2, 1, 0), (0, 0, 0), (2, 2, 2), (1, 1, 1)]:
        code = encode_tiles(tiles)
        assert Pattern(code=code, length=len(tiles)).tiles() == tuple(Tile(t) for t in tiles)


def test_pattern_parse_forms():
    assert Pattern.parse("GYBBG").code == Pattern.from_tiles([2, 1, 0, 0, 2]).code
    assert Pattern.parse("21002").code == Pattern.parse("GYBBG").code
    assert Pattern.parse("🟩🟨⬛⬛🟩").code == Pattern.parse("GYBBG").code
    assert Pattern.parse(" G Y B B G ").render() == "GYBBG"


@pytest.mark.parametrize("text", ["", "GGX", "GGB?", "🟩🟨🟥"])
def test_pattern_parse_rejects_malformed(text):
    # Length is a property of the profile, not of the text: ``Pattern.parse`` infers
    # it, and ``Profile.validate_pattern`` rejects a mismatch. Only bad characters and
    # empty input are malformed here.
    with pytest.raises(InvalidPattern):
        Pattern.parse(text)


def test_code_range_enforced():
    with pytest.raises(InvalidPattern):
        Pattern(code=3 ** 5, length=5)
    with pytest.raises(InvalidPattern):
        Pattern(code=-1, length=5)


def test_feedback_pattern_matches_code():
    pattern = feedback_pattern("crane", "slate")
    assert pattern.length == 5
    assert pattern.code == feedback_code("crane", "slate")


def _check_exhaustive(profile) -> int:
    """Compare the production row path with the reference for every pair.

    Answer and guess encodings are computed once (they are inputs to the table build
    too); the scalar path is spot-checked against each row so both implementations are
    covered without a third full pass. Returns the number of pairs compared.
    """

    answer_codes = encode_words(profile.answers, profile.alphabet)
    guess_codes = encode_words(profile.guesses, profile.alphabet)
    n_letters = len(profile.alphabet)
    pairs = 0
    for index, guess in enumerate(profile.guesses):
        row = feedback_row_codes(guess_codes[index], answer_codes, n_letters)
        for j, answer in enumerate(profile.answers):
            expected = reference_code(guess, answer)
            if int(row[j]) != expected:
                pytest.fail(
                    f"{profile.profile_id}: guess={guess!r} answer={answer!r} "
                    f"row={int(row[j])} reference={expected}"
                )
            pairs += 1
        for j in range(0, len(profile.answers), 97):
            assert feedback_code(guess, profile.answers[j]) == int(row[j])
    print(f"  {profile.profile_id}: {pairs:,} pairs matched the reference")
    return pairs


def test_exhaustive_l1(strict_profiles):
    profile = strict_profiles["strict.en.1"]
    assert _check_exhaustive(profile) == 2 * 2


def test_exhaustive_l2(strict_profiles):
    profile = strict_profiles["strict.en.2"]
    assert len(profile.guesses) == 65
    assert _check_exhaustive(profile) == 65 * 65


def test_exhaustive_l3(strict_profiles):
    profile = strict_profiles["strict.en.3"]
    assert len(profile.guesses) == 588
    assert _check_exhaustive(profile) == 588 * 588


def test_exhaustive_l4(strict_profiles):
    """The Phase 1 gate: every (guess, answer) pair at length 4.

    2,303 x 2,303 = 5,303,809 pairs, each compared with the independent brute-force
    reference.
    """

    profile = strict_profiles["strict.en.4"]
    assert len(profile.guesses) == 2303
    assert _check_exhaustive(profile) == 2303 * 2303


def test_feedback_row_wrapper_matches_codes(strict_profiles):
    profile = strict_profiles["strict.en.3"]
    for guess in (profile.guesses[0], profile.guesses[123], profile.guesses[-1]):
        row = feedback_row(guess, profile.answers, profile.alphabet)
        for j in range(0, len(profile.answers), 41):
            assert int(row[j]) == feedback_code(guess, profile.answers[j])


def test_row_matches_scalar_random_sample(strict_profiles):
    profile = strict_profiles["strict.en.5"]
    rng = np.random.default_rng(20261119)
    for guess_index in rng.integers(0, len(profile.guesses), size=40):
        guess = profile.guesses[int(guess_index)]
        row = feedback_row(guess, profile.answers, profile.alphabet)
        for answer_index in rng.integers(0, len(profile.answers), size=40):
            assert int(row[int(answer_index)]) == feedback_code(guess, profile.answers[int(answer_index)])


def test_row_codes_requires_uint8_space():
    with pytest.raises(ValueError):
        feedback_row_codes(
            np.zeros(6, dtype=np.uint8), np.zeros((2, 6), dtype=np.uint8), 26
        )
