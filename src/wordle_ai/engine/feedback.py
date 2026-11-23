"""Wordle feedback: the single definition used by every component (§4).

Two-pass reservation, in this exact order:

1. Greens are claimed first, and the claimed letters are removed from the multiset of
   answer letters that remain available.
2. Yellows are then assigned only while unmatched copies of that letter remain.

A single pass that consumes letters left to right awards a yellow to a duplicated guess
letter the answer does not contain, which is the classic repeated-letter defect.

The scalar and vectorised implementations must agree on every pair; the test suite
compares both against an independent brute-force reference.
"""

from __future__ import annotations

from collections import Counter
from typing import Sequence

import numpy as np

from ..types import Pattern, Tile

GRAY, YELLOW, GREEN = 0, 1, 2


def feedback_tiles(guess: str, answer: str) -> tuple[Tile, ...]:
    """Return one ``Tile`` per position for a single (guess, answer) pair."""

    if len(guess) != len(answer):
        raise ValueError(f"length mismatch: guess {len(guess)}, answer {len(answer)}")
    length = len(guess)
    tiles = [GRAY] * length
    remaining: Counter[str] = Counter()

    for i in range(length):
        if guess[i] == answer[i]:
            tiles[i] = GREEN
        else:
            remaining[answer[i]] += 1

    for i in range(length):
        if tiles[i] == GREEN:
            continue
        letter = guess[i]
        if remaining[letter] > 0:
            tiles[i] = YELLOW
            remaining[letter] -= 1

    return tuple(Tile(t) for t in tiles)


def encode_tiles(tiles: Sequence[Tile | int]) -> int:
    """Base-3 encode tiles; position 0 is the least-significant trit."""

    code = 0
    for i, tile in enumerate(tiles):
        code += int(tile) * (3 ** i)
    return code


_POW3: dict[int, tuple[int, ...]] = {}


def _powers_of_three(length: int) -> tuple[int, ...]:
    powers = _POW3.get(length)
    if powers is None:
        powers = tuple(3**i for i in range(length))
        _POW3[length] = powers
    return powers


def feedback_code(guess: str, answer: str) -> int:
    """Encode one (guess, answer) pair without materialising tiles or a Counter.

    Same two-pass reservation as :func:`feedback_tiles`: greens are claimed first,
    their letters removed from the answer multiset, and yellows are then assigned
    while unmatched copies remain. The direct form exists because the §17 budget is
    per call (2 µs): building a tile tuple and a ``Counter`` costs more than the
    reservation arithmetic itself. The green positions are kept in an integer bit
    mask, and the answer multiset in a plain dict, so the function stays generic for
    any equal-length strings rather than assuming a 26-letter alphabet.
    """

    length = len(guess)
    if length != len(answer):
        raise ValueError(f"length mismatch: guess {length}, answer {len(answer)}")

    powers = _powers_of_three(length)
    greens = 0
    remaining: dict[str, int] = {}
    for i in range(length):
        g = guess[i]
        a = answer[i]
        if g == a:
            greens |= 1 << i
        else:
            remaining[a] = remaining.get(a, 0) + 1

    code = 0
    for i in range(length):
        if greens & (1 << i):
            code += 2 * powers[i]
    for i in range(length):
        if not greens & (1 << i):
            g = guess[i]
            left = remaining.get(g, 0)
            if left:
                remaining[g] = left - 1
                code += powers[i]
    return code


def feedback_pattern(guess: str, answer: str) -> Pattern:
    return Pattern(code=feedback_code(guess, answer), length=len(guess))


def encode_words(words: Sequence[str], alphabet: str) -> np.ndarray:
    """Encode words as an ``(N, L)`` uint8 array of alphabet indices."""

    index = {ch: i for i, ch in enumerate(alphabet)}
    width = len(words[0]) if words else 0
    out = np.empty((len(words), width), dtype=np.uint8)
    for row, word in enumerate(words):
        if len(word) != width:
            raise ValueError(f"ragged word list: {word!r} has length {len(word)}, expected {width}")
        try:
            out[row] = [index[ch] for ch in word]
        except KeyError as exc:  # pragma: no cover - guarded by profile construction
            raise ValueError(f"word {word!r} contains {exc.args[0]!r} outside the alphabet") from None
    return out


def feedback_row_codes(
    guess_codes: np.ndarray,
    answer_codes: np.ndarray,
    n_letters: int,
) -> np.ndarray:
    """Vectorised feedback for one guess against every encoded answer.

    ``guess_codes`` is ``(L,)`` and ``answer_codes`` is ``(N, L)``, both uint8 indices
    into the alphabet. Returns ``(N,)`` uint8 pattern codes. The algorithm is the same
    two-pass reservation as ``feedback_tiles``; only its expression is vectorised:

    * greens are marked first and never turned into yellows;
    * for each letter, ``available = count_in_answer - greens_of_that_letter``;
    * walking that letter's guess positions left to right, a position becomes yellow
      while at least one unmatched copy remains, and each yellow consumes one copy.
    """

    n_answers = answer_codes.shape[0]
    length = answer_codes.shape[1]
    if guess_codes.shape != (length,):
        raise ValueError("guess code shape does not match answer width")
    if 3 ** length > 256:
        raise ValueError(f"pattern space 3^{length} exceeds uint8; this build supports L <= 5")

    tiles = np.zeros((n_answers, length), dtype=np.uint8)
    green = answer_codes == guess_codes[np.newaxis, :]
    tiles[green] = GREEN

    avail = np.empty(n_answers, dtype=np.int16)
    for letter in range(n_letters):
        positions = np.nonzero(guess_codes == letter)[0]
        if positions.size == 0:
            continue
        count = (answer_codes == letter).sum(axis=1, dtype=np.int16)
        greens = green[:, positions].sum(axis=1, dtype=np.int16)
        avail[:] = count - greens
        for position in positions:
            not_green = ~green[:, position]
            yellow = not_green & (avail > 0)
            tiles[yellow, position] = YELLOW
            avail -= yellow.astype(np.int16)

    code = tiles[:, 0].astype(np.uint16)
    for i in range(1, length):
        code += tiles[:, i].astype(np.uint16) * (3 ** i)
    return code.astype(np.uint8)


def feedback_row(
    guess: str,
    answers: Sequence[str],
    alphabet: str,
) -> np.ndarray:
    """Convenience wrapper: string guess against a list of answers."""

    answer_codes = encode_words(answers, alphabet)
    guess_codes = encode_words([guess], alphabet)[0]
    return feedback_row_codes(guess_codes, answer_codes, len(alphabet))
