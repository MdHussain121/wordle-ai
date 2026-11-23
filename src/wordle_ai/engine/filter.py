"""Candidate elimination and bitset helpers (§5).

Filtering is defined by recomputation: a candidate survives if its feedback for the
guess equals the observed pattern. No component maintains independent letter rules as
the source of truth.
"""

from __future__ import annotations

import numpy as np

from ..errors import InconsistentFeedback


def filter_mask(mask: np.ndarray, row: np.ndarray, pattern_code: int) -> np.ndarray:
    """Keep candidates whose precomputed feedback code equals ``pattern_code``."""

    if mask.shape != row.shape:
        raise ValueError(f"mask shape {mask.shape} does not match row shape {row.shape}")
    new_mask = np.logical_and(mask, row == pattern_code)
    if not bool(new_mask.any()):
        remaining = int(np.count_nonzero(mask))
        raise InconsistentFeedback(
            "feedback eliminates every remaining candidate",
            candidates_before=remaining,
            pattern_code=pattern_code,
        )
    return new_mask


def to_bitset(mask: np.ndarray) -> np.ndarray:
    """Pack a boolean mask into little-endian uint64 words."""

    bits = np.packbits(mask.astype(np.uint8), bitorder="little")
    pad = (-len(bits)) % 8
    if pad:
        bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    return bits.view(np.uint64)


def popcount(mask: np.ndarray) -> int:
    return int(np.count_nonzero(mask))


def from_bitset(words: np.ndarray, length: int) -> np.ndarray:
    bits = words.view(np.uint8)
    return np.unpackbits(bits, count=length, bitorder="little").astype(bool)
