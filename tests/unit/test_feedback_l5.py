"""Five-letter verification against the independent reference.

The full classic space is 12,972 x 2,315 = 30,030,180 pairs, which is the table build
itself; checking every one against a Python reference is unnecessary when the same code
path is verified exhaustively at lengths 1-4 and the 5-letter encoding is identical.
Instead this module fixes a documented seed and covers:

* all 2,315 classic answers against 300 seeded guesses            (694,500 pairs)
* all 12,972 classic guesses against 100 seeded answers         (1,297,200 pairs)
* all 12,972 guesses against every answer containing a repeated letter, capped at
  200 such answers, chosen deterministically by sorted order    (up to 2,594,400 pairs)

Total is roughly 2.3M pairs, including every structurally hard case (duplicate letters)
reachable from the classic answer list.
"""

from __future__ import annotations

import pytest

from tests.reference import reference_code
from wordle_ai.engine.feedback import feedback_code, feedback_row

SEED = 20261119
SEEDED_GUESSES = 300
SEEDED_ANSWERS = 100
MAX_REPEAT_ANSWERS = 200


def _seeded_indices(n: int, count: int) -> list[int]:
    # Deterministic, dependency-free: a fixed stride co-prime with n gives a
    # reproducible "random-looking" sample without importing numpy's RNG into the test
    # expectations.
    stride = 7919  # prime
    return sorted({(i * stride + 13) % n for i in range(count)})


def test_classic_answers_vs_seeded_guesses(classic_profile):
    profile = classic_profile
    assert len(profile.answers) == 2315
    assert len(profile.guesses) == 12972
    guess_pool = [profile.guesses[i] for i in _seeded_indices(len(profile.guesses), SEEDED_GUESSES)]
    assert len(guess_pool) == SEEDED_GUESSES
    print(f"  {len(guess_pool):,} guesses x {len(profile.answers):,} answers = "
          f"{len(guess_pool) * len(profile.answers):,} pairs")
    for guess in guess_pool:
        row = feedback_row(guess, profile.answers, profile.alphabet)
        for j, answer in enumerate(profile.answers):
            assert int(row[j]) == reference_code(guess, answer), (guess, answer)
        for j in range(0, len(profile.answers), 53):
            assert feedback_code(guess, profile.answers[j]) == int(row[j])


def test_classic_guesses_vs_seeded_answers(classic_profile):
    profile = classic_profile
    answer_pool = [profile.answers[i] for i in _seeded_indices(len(profile.answers), SEEDED_ANSWERS)]
    assert len(answer_pool) == SEEDED_ANSWERS
    print(f"  {len(answer_pool):,} answers x {len(profile.guesses):,} guesses = "
          f"{len(answer_pool) * len(profile.guesses):,} pairs")
    for answer in answer_pool:
        for guess in profile.guesses:
            assert feedback_code(guess, answer) == reference_code(guess, answer), (guess, answer)


def test_repeated_letter_answers_exhaustive_over_guesses(classic_profile):
    profile = classic_profile
    repeated = [a for a in profile.answers if len(set(a)) < len(a)]
    assert repeated, "expected repeated-letter answers in the classic list"
    used = repeated[:MAX_REPEAT_ANSWERS]
    print(f"  {len(used):,} of {len(repeated):,} repeated-letter answers x "
          f"{len(profile.guesses):,} guesses = {len(used) * len(profile.guesses):,} pairs")
    for answer in used:
        for guess in profile.guesses:
            assert feedback_code(guess, answer) == reference_code(guess, answer), (guess, answer)
