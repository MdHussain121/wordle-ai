"""Vectorized feature extraction for Wordle game states and candidate guesses.

Implements WORDLE_AI_ML_RESEARCH_AND_TRAINING_PLAN.md (§4.1, §5.1, §6.2):
- Candidate set statistics: count, log2 count, turn index, attempts remaining.
- Candidate letter distributions: unpositioned (26) and positional (length * 26).
- Deterministic, zero-leakage, pre-indexed for sub-millisecond inference (<0.1 ms).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..types import Profile


@dataclass(frozen=True)
class FeatureSpec:
    alphabet: str = "abcdefghijklmnopqrstuvwxyz"
    length: int = 5
    max_attempts: int = 6

    @property
    def alphabet_size(self) -> int:
        return len(self.alphabet)

    @property
    def unpositioned_dim(self) -> int:
        return self.alphabet_size

    @property
    def positional_dim(self) -> int:
        return self.length * self.alphabet_size

    @property
    def scalar_dim(self) -> int:
        return 6  # count, log2_count, turn, attempts, attempts_ratio, inv_count

    @property
    def state_feature_dim(self) -> int:
        return self.scalar_dim + self.unpositioned_dim + self.positional_dim


class StateFeatureExtractor:
    """Fast, vectorized feature extractor for candidate masks and game turns."""

    def __init__(self, profile: Profile, max_attempts: int = 6) -> None:
        self.profile = profile
        self.max_attempts = max_attempts
        self.alphabet = profile.alphabet
        self.length = profile.length
        self.num_answers = len(profile.answers)
        self.char_to_idx = {c: i for i, c in enumerate(self.alphabet)}

        self.spec = FeatureSpec(
            alphabet=self.alphabet,
            length=self.length,
            max_attempts=self.max_attempts,
        )

        # Precompute boolean indicator matrices for all answer words
        # unpositioned: (N, 26)
        # positional: (N, length * 26)
        unpos = np.zeros((self.num_answers, self.spec.unpositioned_dim), dtype=np.float32)
        pos = np.zeros((self.num_answers, self.spec.positional_dim), dtype=np.float32)

        for i, word in enumerate(profile.answers):
            for c in set(word):
                if c in self.char_to_idx:
                    unpos[i, self.char_to_idx[c]] = 1.0
            for p, c in enumerate(word):
                if c in self.char_to_idx:
                    pos[i, p * self.spec.alphabet_size + self.char_to_idx[c]] = 1.0

        self._unpositioned_matrix = unpos
        self._positional_matrix = pos

    @property
    def feature_dim(self) -> int:
        return self.spec.state_feature_dim

    def extract_state(
        self,
        candidate_mask: np.ndarray,
        turn: int,
        attempts_left: int | None = None,
    ) -> np.ndarray:
        """Extract a 1D float32 feature vector for a candidate mask."""
        if attempts_left is None:
            attempts_left = max(self.max_attempts - turn, 0)

        mask = np.asarray(candidate_mask, dtype=bool)
        cand_count = float(mask.sum())
        safe_count = max(cand_count, 1.0)

        log2_count = math.log2(safe_count)
        turn_norm = float(turn)
        attempts_norm = float(attempts_left)
        attempts_ratio = float(attempts_left / self.max_attempts)
        inv_count = 1.0 / safe_count

        scalars = np.array(
            [
                cand_count,
                log2_count,
                turn_norm,
                attempts_norm,
                attempts_ratio,
                inv_count,
            ],
            dtype=np.float32,
        )

        # Vectorized letter presence frequencies
        # Matrix multiply (alphabet_size, N) @ (N,) -> (alphabet_size,)
        unpos_freq = (self._unpositioned_matrix.T @ mask) / safe_count
        pos_freq = (self._positional_matrix.T @ mask) / safe_count

        return np.concatenate([scalars, unpos_freq, pos_freq], dtype=np.float32)

    def extract_state_from_sig(
        self,
        hex_sig: str,
        turn: int,
        attempts_left: int | None = None,
    ) -> np.ndarray:
        """Unpack hex signature and extract features."""
        raw_bytes = bytes.fromhex(hex_sig)
        unpacked = np.unpackbits(np.frombuffer(raw_bytes, dtype=np.uint8))
        mask = unpacked[: self.num_answers].astype(bool)
        return self.extract_state(mask, turn, attempts_left)

    def extract_guess_features(
        self,
        word: str,
        is_candidate: bool,
        unpositioned_freq: np.ndarray,
    ) -> np.ndarray:
        """Extract structured features for a candidate guess word."""
        distinct_count = len(set(word)) / float(self.length)
        has_repeat = 1.0 if len(set(word)) < self.length else 0.0
        vowels = sum(1 for c in word if c in "aeiouy") / float(self.length)

        # Sum of unpositioned letter frequencies covered by this word
        letter_overlap = sum(
            unpositioned_freq[self.char_to_idx[c]]
            for c in set(word)
            if c in self.char_to_idx
        )

        return np.array(
            [
                1.0 if is_candidate else 0.0,
                distinct_count,
                has_repeat,
                vowels,
                letter_overlap,
            ],
            dtype=np.float32,
        )


def extract_state_features(
    profile: Profile,
    candidate_mask: np.ndarray,
    turn: int,
    attempts_left: int | None = None,
) -> np.ndarray:
    """Convenience helper to extract features for a single state."""
    extractor = StateFeatureExtractor(profile)
    return extractor.extract_state(candidate_mask, turn, attempts_left)
