"""Learned strategies for Wordle play using distilled value and policy models.

Implements Phase 6 ML strategy integration:
- LearnedValueStrategy: Two-ply surrogate lookahead guided by ValueNetwork regression.
- LearnedRankerStrategy: Direct candidate ranking via PolicyRanker.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Sequence

import numpy as np

from ..engine.state import GameState
from ..engine.table import RowSource
from ..strategy.base import Budget, Decision, HeuristicStrategy, PartitionStats, ScoreBreakdown
from ..strategy.heuristics import ExpectedRemaining
from .features import StateFeatureExtractor
from .models import PolicyRanker, ValueNetwork, ValueRegressor


class LearnedValueStrategy(ExpectedRemaining):
    """Refines candidate guesses using learned ValueNetwork V(s) predictions."""

    name = "ml.value_lookahead"
    objective = "one-step candidate search refined by neural ValueNetwork V(s) evaluation"
    candidate_only = False
    top_k = 16

    def __init__(
        self,
        value_model_path: Path | str = "models/value_network.pt",
        top_k: int = 16,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.top_k = top_k
        self.model_path = Path(value_model_path)
        self._model: ValueNetwork | None = None
        self._extractor: StateFeatureExtractor | None = None

    def _ensure_model(self, state: GameState) -> None:
        if self._model is None:
            if self.model_path.suffix == ".pt":
                self._model = ValueNetwork.load(self.model_path)
            else:
                self._model = ValueRegressor.load(self.model_path)
        if self._extractor is None:
            self._extractor = StateFeatureExtractor(state.profile)

    def _score(self, state: GameState, stats: PartitionStats, words: Sequence[str]):
        primary, ties, branch = super()._score(state, stats, words)
        # If very few candidates or last turn, stay with base
        if state.remaining <= 2 or state.remaining > 300:
            return primary, ties, branch

        self._ensure_model(state)
        extractor = self._extractor
        model = self._model
        assert extractor is not None
        assert model is not None

        profile = state.profile
        columns = np.flatnonzero(state.candidates)
        n = columns.size
        matrix = self._matrix
        assert matrix is not None

        order = np.lexsort(
            (
                np.arange(len(primary)),
                np.round(primary, 12),
            )
        )[: self.top_k]

        refined = np.full(len(primary), np.inf)
        child_features_batch = []
        bucket_sizes_batch = []
        pos_indices_batch = []

        turn = state.attempts_used
        attempts_left = state.attempts_left

        for position in order:
            guess_word = words[position]
            guess_idx = profile.guess_index_of(guess_word)
            codes = matrix[guess_idx][columns]

            unique_codes, counts = np.unique(codes, return_counts=True)
            exp_cost = 1.0  # turn cost

            # Build batch of child state features for buckets of size > 1
            for code, size in zip(unique_codes, counts):
                if size == 1:
                    exp_cost += (1.0 / n) * 1.0  # 1 turn to solve singleton
                else:
                    child_mask = np.zeros(len(profile.answers), dtype=bool)
                    child_mask[columns[codes == code]] = True
                    feat = extractor.extract_state(child_mask, turn + 1, attempts_left - 1)
                    child_features_batch.append(feat)
                    bucket_sizes_batch.append(size)
                    pos_indices_batch.append((position, size / n))

            refined[position] = exp_cost

        if child_features_batch:
            features_arr = np.array(child_features_batch, dtype=np.float32)
            preds = model.predict_batch(features_arr)
            for (pos, weight), v_hat in zip(pos_indices_batch, preds):
                refined[pos] += weight * max(float(v_hat), 1.0)

        return refined, ties, "learned_value_lookahead"


class LearnedRankerStrategy(HeuristicStrategy):
    """Direct candidate ranking using trained PolicyRanker model."""

    name = "ml.policy_ranker"
    objective = "rank candidate words directly using learned PolicyRanker"
    candidate_only = True

    def __init__(
        self,
        ranker_path: Path | str = "models/policy_ranker.joblib",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.ranker_path = Path(ranker_path)
        self._ranker: PolicyRanker | None = None
        self._extractor: StateFeatureExtractor | None = None

    def _ensure_ranker(self, state: GameState) -> None:
        if self._ranker is None:
            self._ranker = PolicyRanker.load(self.ranker_path)
        if self._extractor is None:
            self._extractor = StateFeatureExtractor(state.profile)

    def _score(self, state: GameState, stats: PartitionStats, words: Sequence[str]):
        self._ensure_ranker(state)
        extractor = self._extractor
        ranker = self._ranker
        assert extractor is not None
        assert ranker is not None

        profile = state.profile
        cand_indices = np.flatnonzero(state.candidates)
        cand_words = [profile.answers[i] for i in cand_indices]

        state_feat = extractor.extract_state(state.candidates, state.attempts_used, state.attempts_left)
        unpos_freq = state_feat[6 : 6 + extractor.spec.unpositioned_dim]

        guess_feats = np.array(
            [
                extractor.extract_guess_features(w, is_candidate=True, unpositioned_freq=unpos_freq)
                for w in words
            ],
            dtype=np.float32,
        )

        scores = ranker.score_candidates(state_feat, guess_feats)
        # We negate scores because HeuristicStrategy minimizes primary score
        primary = -scores.astype(np.float64)
        return primary, [], "learned_policy_ranker"
