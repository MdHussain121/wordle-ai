"""Hard- and superhard-mode legality, derived from recorded feedback (§6.3).

The constraint is not a hand-coded letter rule: it is read off the same feedback
function that produced the history. For one turn:

* every green pins a letter to a position and accounts for one matched copy;
* every yellow accounts for one further matched copy and forbids that position;
* a gray for a letter proves the answer contains exactly as many copies as were
  matched in that turn, because any unmatched copy would have been yellow.

Across turns that yields a minimum multiplicity (the answer always satisfies it), an
optional maximum (only when a gray was seen) and a set of forbidden positions. The
bounds are ranges where the feedback is underdetermined; a letter may therefore be
reused freely when it was only ever green, which is exactly the NYT rule.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from ..types import RuleMode, Tile, Turn


@dataclass(frozen=True)
class LetterConstraint:
    """What the history proves about the answer's letters."""

    length: int
    fixed: dict[int, str] = field(default_factory=dict)
    forbidden: dict[str, frozenset[int]] = field(default_factory=dict)
    min_count: dict[str, int] = field(default_factory=dict)
    max_count: dict[str, int | None] = field(default_factory=dict)

    def legal(self, word: str) -> bool:
        if len(word) != self.length:
            return False
        for position, letter in self.fixed.items():
            if word[position] != letter:
                return False
        counts = Counter(word)
        for letter, low in self.min_count.items():
            if counts[letter] < low:
                return False
        for letter, high in self.max_count.items():
            if high is not None and counts[letter] > high:
                return False
        for letter, positions in self.forbidden.items():
            for position in positions:
                if word[position] == letter:
                    return False
        return True


def derive_constraint(length: int, history: Sequence[Turn]) -> LetterConstraint:
    """Build the constraint implied by ``history`` using the feedback definition."""

    fixed: dict[int, str] = {}
    forbidden: dict[str, set[int]] = {}
    min_count: dict[str, int] = {}
    max_count: dict[str, int | None] = {}

    for turn in history:
        guess = turn.guess
        guess_counts = Counter(guess)
        greens: Counter[str] = Counter()
        yellows: Counter[str] = Counter()
        for position, tile in enumerate(turn.pattern.tiles()):
            letter = guess[position]
            if tile is Tile.GREEN:
                greens[letter] += 1
                fixed[position] = letter
            elif tile is Tile.YELLOW:
                yellows[letter] += 1
                forbidden.setdefault(letter, set()).add(position)

        for letter, in_guess in guess_counts.items():
            matched = greens[letter] + yellows[letter]
            min_count[letter] = max(min_count.get(letter, 0), matched)
            if matched < in_guess:
                previous = max_count.get(letter)
                max_count[letter] = matched if previous is None else min(previous, matched)

    return LetterConstraint(
        length=length,
        fixed=dict(sorted(fixed.items())),
        forbidden={
            letter: frozenset(sorted(positions)) for letter, positions in forbidden.items()
        },
        min_count=dict(sorted(min_count.items())),
        max_count=dict(sorted(max_count.items())),
    )


def is_legal(
    word: str,
    *,
    profile_guesses: set[str] | dict[str, int],
    constraint: LetterConstraint | None,
    mode: RuleMode,
    candidates: set[str] | None = None,
) -> bool:
    """Whether ``word`` is a legal guess in ``mode`` for the given history."""

    if word not in profile_guesses:
        return False
    if mode is RuleMode.NORMAL:
        return True
    if constraint is None:  # pragma: no cover - defensive
        raise ValueError("a constraint is required outside normal mode")
    if not constraint.legal(word):
        return False
    if mode is RuleMode.SUPERHARD:
        return candidates is not None and word in candidates
    return True


def legal_mask(
    guesses: Sequence[str],
    *,
    constraint: LetterConstraint | None,
    mode: RuleMode,
    candidates: set[str] | None = None,
) -> np.ndarray:
    """Boolean mask of the guesses that satisfy the mode's constraints."""

    if mode is RuleMode.NORMAL:
        return np.ones(len(guesses), dtype=bool)
    if constraint is None:  # pragma: no cover - defensive
        raise ValueError("a constraint is required outside normal mode")
    return np.fromiter(
        (
            constraint.legal(word)
            and (mode is not RuleMode.SUPERHARD or (candidates is not None and word in candidates))
            for word in guesses
        ),
        dtype=bool,
        count=len(guesses),
    )


def constraint_for(state) -> LetterConstraint | None:
    """Constraint for a state, or ``None`` in normal mode."""

    if state.mode is RuleMode.NORMAL:
        return None
    return derive_constraint(state.profile.length, state.history)
