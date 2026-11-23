"""Precomputed feedback tables and the memory-aware policy (§7, §11).

One byte per (guess, answer) pair, because 3**L <= 243 for the supported lengths.
Tables are ``.npy`` files so they can be memory-mapped instead of held as objects; the
sidecar checksum travels with them and is recorded in the lexicon manifest.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

from ..errors import BudgetExceeded, ProfileIntegrityError
from ..types import Profile
from .feedback import encode_words, feedback_row, feedback_row_codes


@runtime_checkable
class RowSource(Protocol):
    """Anything that can answer "the feedback row for this guess".

    Strategies depend on this narrow interface, so a memory-mapped artifact and an
    on-demand computation are interchangeable and must produce identical rows.
    """

    profile: Profile

    def row(self, guess: str) -> np.ndarray: ...

    def matrix(self) -> np.ndarray: ...


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def should_build(n_guesses: int, n_answers: int, max_bytes: int) -> tuple[bool, int]:
    """Return (decision, footprint) for the configured memory budget."""

    footprint = n_guesses * n_answers
    return footprint <= max_bytes, footprint


def build_table(profile: Profile, *, max_bytes: int | None = None) -> np.ndarray:
    """Compute the full ``uint8`` table for a profile.

    Raises ``BudgetExceeded`` when the footprint exceeds ``max_bytes``; the caller
    decides whether to skip, use the hybrid policy, or force the build.
    """

    n_guesses = len(profile.guesses)
    n_answers = len(profile.answers)
    footprint = n_guesses * n_answers
    if max_bytes is not None and footprint > max_bytes:
        raise BudgetExceeded(
            f"feedback table for {profile.profile_id} needs {footprint} bytes "
            f"({footprint / 1024 ** 2:.2f} MiB), budget is {max_bytes} bytes",
            bytes=footprint,
            budget=max_bytes,
        )

    answers = encode_words(profile.answers, profile.alphabet)
    guesses = encode_words(profile.guesses, profile.alphabet)
    table = np.empty((n_guesses, n_answers), dtype=np.uint8)
    n_letters = len(profile.alphabet)
    for row in range(n_guesses):
        table[row] = feedback_row_codes(guesses[row], answers, n_letters)
    return table


def save_table(table: np.ndarray, path: Path) -> tuple[str, int]:
    """Write a table with ``np.save`` (deterministic bytes) and return checksum, size.

    The file is written through a temporary sibling and replaced, so a reader never
    observes a half-written table.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "wb") as handle:
        np.save(handle, table, allow_pickle=False)
    temporary.replace(path)
    return sha256_file(path), path.stat().st_size


def table_footprint(profile: Profile) -> int:
    return len(profile.guesses) * len(profile.answers)


class FeedbackTable:
    """Read-only table with a bounded row cache.

    ``lru_rows=0`` disables caching, which is the honest way to model the "hybrid"
    policy: rows are gathered from the memory map on every access.
    """

    def __init__(self, path: Path, profile: Profile, *, lru_rows: int = 2048) -> None:
        self.path = Path(path)
        self.profile = profile
        self.lru_rows = lru_rows
        self._cache: OrderedDict[int, np.ndarray] = OrderedDict()
        try:
            self._array = np.load(self.path, mmap_mode="r", allow_pickle=False)
        except FileNotFoundError as exc:
            raise ProfileIntegrityError(f"feedback table not found: {self.path}") from exc
        expected = (len(profile.guesses), len(profile.answers))
        if self._array.shape != expected:
            raise ProfileIntegrityError(
                f"feedback table shape {self._array.shape} does not match profile {expected}"
            )
        if self._array.dtype != np.uint8:
            raise ProfileIntegrityError(f"feedback table dtype {self._array.dtype} is not uint8")
        self._matrix: np.ndarray | None = None

    def row(self, guess: str) -> np.ndarray:
        index = self.profile.guess_index_of(guess)
        if self.lru_rows <= 0:
            return np.asarray(self._array[index])
        cached = self._cache.get(index)
        if cached is not None:
            self._cache.move_to_end(index)
            return cached
        row = np.asarray(self._array[index])
        self._cache[index] = row
        if len(self._cache) > self.lru_rows:
            self._cache.popitem(last=False)
        return row

    def row_index(self, index: int) -> np.ndarray:
        return np.asarray(self._array[index])

    def matrix(self) -> np.ndarray:
        """The whole table as a memory-mapped array.

        The map is deliberately *not* copied into anonymous memory: on the 17,410\xd7
        17,410 ``full.en.5`` table a copy is ~300 MiB per worker process, and the
        strategies only ever read contiguous row slices. Returning the map keeps one
        shared page cache and lets the OS evict pages instead of each worker holding a
        private copy.
        """

        if self._matrix is None:
            self._matrix = self._array
        return self._matrix


class ComputedRows:
    """Table-shaped rows computed on demand from the reference feedback path.

    Profiles whose table was not built (policy ``none``) still need a row source for
    strategies and the harness. Rows are cached because the same guess is asked for
    repeatedly within a run.
    """

    def __init__(self, profile: Profile, *, lru_rows: int = 4096) -> None:
        self.profile = profile
        self.lru_rows = lru_rows
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._matrix: np.ndarray | None = None

    def row(self, guess: str) -> np.ndarray:
        word = self.profile.validate_guess(guess)
        if self.lru_rows <= 0:
            return feedback_row(word, self.profile.answers, self.profile.alphabet)
        cached = self._cache.get(word)
        if cached is not None:
            self._cache.move_to_end(word)
            return cached
        row = feedback_row(word, self.profile.answers, self.profile.alphabet)
        self._cache[word] = row
        if len(self._cache) > self.lru_rows:
            self._cache.popitem(last=False)
        return row

    def matrix(self) -> np.ndarray:
        if self._matrix is None:
            rows = [self.row(word) for word in self.profile.guesses]
            self._matrix = np.stack(rows) if rows else np.empty((0, len(self.profile.answers)), np.uint8)
        return self._matrix


def open_rows(profile: Profile, table_path: Path | None, *, lru_rows: int = 2048) -> RowSource:
    """Return the shipped table when present, else an on-demand row source."""

    if table_path is not None and Path(table_path).exists():
        return FeedbackTable(Path(table_path), profile, lru_rows=lru_rows)
    return ComputedRows(profile)
