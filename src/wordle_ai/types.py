"""Core value types: tiles, patterns, profiles (technical specification §3).

The feedback alphabet is fixed at three states per position, so a pattern is a
base-3 integer in ``[0, 3**L)``. Position 0 is the least-significant trit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Iterable, Sequence

from .errors import InvalidGuess, InvalidPattern, ProfileIntegrityError

_TILE_FROM_TEXT = {
    "G": 2, "Y": 1, "B": 0,
    "2": 2, "1": 1, "0": 0,
    "\U0001F7E9": 2,  # green square
    "\U0001F7E8": 1,  # yellow square
    "\u2B1B": 0,      # black large square
    "\u2B1C": 0,      # white large square (common paste variant)
}
_RENDER = ("B", "Y", "G")


class Tile(IntEnum):
    GRAY = 0
    YELLOW = 1
    GREEN = 2


class RuleMode(str, Enum):
    NORMAL = "normal"
    HARD = "hard"
    SUPERHARD = "superhard"


class PriorKind(str, Enum):
    UNIFORM = "uniform"
    ZIPF = "zipf"
    EMPIRICAL = "empirical"


@dataclass(frozen=True, order=True)
class Pattern:
    """One feedback outcome, encoded as a base-3 integer."""

    code: int
    length: int

    def __post_init__(self) -> None:
        if self.length < 1:
            raise InvalidPattern(f"pattern length must be >= 1, got {self.length}")
        if not (0 <= self.code < 3 ** self.length):
            raise InvalidPattern(
                f"pattern code {self.code} outside [0, {3 ** self.length}) for length {self.length}"
            )

    def tiles(self) -> tuple[Tile, ...]:
        code, out = self.code, []
        for _ in range(self.length):
            out.append(Tile(code % 3))
            code //= 3
        return tuple(out)

    @classmethod
    def from_tiles(cls, tiles: Sequence[Tile | int]) -> "Pattern":
        code = 0
        for i, tile in enumerate(tiles):
            value = int(tile)
            if value not in (0, 1, 2):
                raise InvalidPattern(f"tile value {value} is not 0, 1 or 2")
            code += value * (3 ** i)
        return cls(code=code, length=len(tiles))

    @classmethod
    def parse(cls, text: str, alphabet: str | None = None) -> "Pattern":
        """Parse ``GYBBG`` / ``21001`` / emoji feedback.

        ``alphabet`` is accepted for signature compatibility with the specification
        and validates that the profile alphabet could have produced the pattern; it
        does not change the encoding, because patterns contain no letters.
        """

        if alphabet is not None and len(set(alphabet)) < 2:
            raise InvalidPattern("alphabet must contain at least two distinct symbols")
        stripped = "".join(text.split())
        if not stripped:
            raise InvalidPattern("empty pattern")
        tiles: list[int] = []
        for ch in stripped:
            if ch not in _TILE_FROM_TEXT:
                raise InvalidPattern(f"invalid pattern character {ch!r}")
            tiles.append(_TILE_FROM_TEXT[ch])
        return cls.from_tiles(tiles)

    def render(self) -> str:
        return "".join(_RENDER[t] for t in self.tiles())

    def count(self, tile: Tile) -> int:
        return self.render().count(_RENDER[int(tile)])


@dataclass(frozen=True)
class Turn:
    guess: str
    pattern: Pattern


@dataclass(frozen=True)
class Profile:
    """An immutable lexicon profile.

    Construction validates every invariant in the technical specification §3.2 and
    raises ``ProfileIntegrityError`` rather than warning.
    """

    profile_id: str
    language: str
    dialect: str | None
    length: int
    alphabet: str
    answers: tuple[str, ...]
    guesses: tuple[str, ...]
    manifest_sha256: str
    source_ids: tuple[str, ...] = ()
    answer_index: dict[str, int] = field(default_factory=dict, repr=False, compare=False)
    guess_index: dict[str, int] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not (1 <= self.length <= 5):
            raise ProfileIntegrityError(
                f"length {self.length} is outside the supported range 1..5"
            )
        if not self.alphabet or len(set(self.alphabet)) != len(self.alphabet):
            raise ProfileIntegrityError("alphabet must be a non-empty string of distinct symbols")
        word_re = re.compile(rf"^[{re.escape(self.alphabet)}]{{{self.length}}}$")

        for name, words in (("answers", self.answers), ("guesses", self.guesses)):
            if len(set(words)) != len(words):
                raise ProfileIntegrityError(f"{name} contains duplicate words")
            if list(words) != sorted(words):
                raise ProfileIntegrityError(f"{name} is not sorted")
            bad = [w for w in words if not word_re.match(w)]
            if bad:
                raise ProfileIntegrityError(
                    f"{name} contains entries that are not {self.length}-character "
                    f"words over the alphabet: {bad[:5]}"
                )
        extra = set(self.answers) - set(self.guesses)
        if extra:
            raise ProfileIntegrityError(
                f"answers are not a subset of guesses: {sorted(extra)[:5]}"
            )

    @property
    def pattern_count(self) -> int:
        return 3 ** self.length

    def __len__(self) -> int:
        return len(self.guesses)

    def answer_index_of(self, word: str) -> int:
        try:
            return self.answer_index[word]
        except KeyError:  # pragma: no cover - defensive
            raise ProfileIntegrityError(f"{word!r} is not in the answer set") from None

    def guess_index_of(self, word: str) -> int:
        try:
            return self.guess_index[word]
        except KeyError:  # pragma: no cover - defensive
            raise ProfileIntegrityError(f"{word!r} is not in the guess set") from None

    def validate_guess(self, guess: str) -> str:
        """Return the normalised guess or raise ``InvalidGuess`` with a documented reason."""

        if guess is None:
            raise InvalidGuess("guess is required", reason="empty")
        word = guess.strip().casefold()
        if not word:
            raise InvalidGuess("guess is empty", reason="empty")
        if len(word) != self.length:
            raise InvalidGuess(
                f"guess {word!r} has length {len(word)}, expected {self.length}",
                reason="wrong_length",
            )
        outside = sorted({ch for ch in word if ch not in self.alphabet})
        if outside:
            raise InvalidGuess(
                f"guess {word!r} contains characters outside the alphabet: {outside}",
                reason="out_of_alphabet",
            )
        if word not in self.guess_index:
            raise InvalidGuess(
                f"guess {word!r} is not in the allowed guess set of {self.profile_id}",
                reason="unknown_word",
            )
        return word

    def validate_pattern(self, pattern: Pattern) -> Pattern:
        if pattern.length != self.length:
            raise InvalidPattern(
                f"pattern length {pattern.length} does not match profile length {self.length}"
            )
        return pattern

    def words_for(self, mask: Iterable[bool]) -> list[str]:
        return [w for w, keep in zip(self.guesses, mask) if keep]
