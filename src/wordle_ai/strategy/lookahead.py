"""Two-ply lookahead and seeded rollout strategies (Phase 8, B-10).

Both strategies are one-step strategies on large candidate sets and switch to a
two-ply evaluation once the set is small enough for the extra work to be honest:

* ``lookahead.two_ply`` refines the best one-step guesses by enumerating the best
  candidate-only follow-up in every feedback bucket.
* ``rollout.random`` plays seeded, deterministic random-candidate playouts against
  answers sampled from the current candidates and picks the lowest average.

The switch is a runtime budget decision, not a hidden change of objective; the
``branch`` in ``Decision.breakdown`` records which path ran. Randomness is seeded
from the state so the same state always produces the same decision, which keeps the
determinism hash stable.
"""

from __future__ import annotations

import hashlib

import numpy as np

from ..engine.filter import filter_mask
from .base import HeuristicStrategy, PartitionStats
from .heuristics import ExpectedRemaining

#: Above this many candidates the two-ply/rollout evaluation is skipped and the
#: strategy behaves as its one-step parent. The number is a measured cost guard, not
#: an acceptance threshold: the branch is recorded in the decision breakdown.
SMALL_STATE = 200


def _seed(state, extra: str) -> int:
    digest = hashlib.blake2b(
        state.candidates.tobytes()
        + state.mode.value.encode("ascii")
        + str(state.attempts_left).encode("ascii")
        + extra.encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big")


class LookaheadTwoPly(ExpectedRemaining):
    """Expected remaining candidates with a candidate-only second ply in the endgame."""

    name = "lookahead.two_ply"
    objective = (
        "minimise one-step expected remaining, refined by the best candidate-only "
        "follow-up in each feedback bucket when S<=200"
    )
    top_k = 12

    def _score(self, state, stats, words):
        primary, ties, branch = super()._score(state, stats, words)
        if state.remaining > SMALL_STATE or state.remaining <= 1:
            return primary, ties, branch

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

        # Score is "expected candidates left after two guesses" for the shortlisted
        # first guesses, in the same units as the one-step parent. Guesses outside
        # the shortlist are marked inf so the comparison is between refined rows only.
        refined = np.full(len(primary), np.inf)
        for position in order:
            guess_index = profile.guess_index_of(words[position])
            codes = matrix[guess_index][columns]
            total = 0.0
            for code in np.unique(codes):
                bucket = columns[codes == code]
                size = bucket.size
                if size == 1:
                    continue  # solved now, or solved by the follow-up
                child_mask = np.zeros(len(profile.answers), dtype=bool)
                child_mask[bucket] = True
                answer_rows = np.array(
                    [profile.guess_index_of(profile.answers[i]) for i in bucket],
                    dtype=np.int64,
                )
                follow = PartitionStats(
                    matrix[answer_rows], profile.pattern_count
                ).compute(child_mask, keys=("expected_remaining",))
                total += size * float(np.min(follow["expected_remaining"]))
            refined[position] = total / n
        return refined, ties, "lookahead_two_ply"


class RolloutRandom(ExpectedRemaining):
    """Expected remaining candidates, refined by seeded random-candidate rollouts."""

    name = "rollout.random"
    objective = (
        "minimise one-step expected remaining, refined by seeded random-candidate "
        "rollouts when S<=200"
    )
    top_k = 8
    playouts = 16

    def _score(self, state, stats, words):
        primary, ties, branch = super()._score(state, stats, words)
        if state.remaining > SMALL_STATE or state.remaining <= 1:
            return primary, ties, branch

        profile = state.profile
        matrix = self._matrix
        assert matrix is not None
        columns = np.flatnonzero(state.candidates)
        n = columns.size
        order = np.lexsort(
            (
                np.arange(len(primary)),
                np.round(primary, 12),
            )
        )[: self.top_k]

        refined = np.full(len(primary), np.inf)
        for position in order:
            guess_index = profile.guess_index_of(words[position])
            total = 0.0
            for _ in range(self.playouts):
                rng = np.random.default_rng(
                    _seed(state, f"{words[position]}:{total}")
                )
                answer = int(rng.choice(columns))
                mask = state.candidates.copy()
                turns = 0
                current = guess_index
                for _turn in range(state.attempts_left):
                    turns += 1
                    code = int(matrix[current][answer])
                    if code == profile.pattern_count - 1:
                        break
                    mask = filter_mask(mask, matrix[current], code)
                    if not mask.any():
                        break
                    options = np.flatnonzero(mask)
                    current = profile.guess_index_of(
                        profile.answers[int(rng.choice(options))]
                    )
                else:
                    turns = state.attempts_left + 1
                total += turns
            refined[position] = total / self.playouts
        return refined, ties, "rollout_random"


__all__ = ["LookaheadTwoPly", "RolloutRandom", "SMALL_STATE"]
