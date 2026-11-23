"""The Phase 2 heuristics, each documented by the objective it actually minimises.

Scores follow technical specification §6.2 exactly. Every strategy scores the legal
guesses of the profile; the candidate-only variants score only the answers, which is
the configuration the published heuristic numbers use (Greenberg 2024).

No strategy contains an opener. The first guess is the argmin over the profile, so a
different guess list or answer list produces a different opener.
"""

from __future__ import annotations

from collections import Counter

import numpy as np

from ..engine.state import GameState
from .base import HeuristicStrategy, PartitionStats


class FirstCandidate(HeuristicStrategy):
    """Deterministic sanity path: the alphabetically first remaining candidate.

    Score: ``0`` for a candidate, ``1`` otherwise, tie-broken by index. It is the
    floor every other strategy must beat.
    """

    name = "first_candidate"
    needs_partitions = False
    objective = "pick the lowest-index remaining candidate (sanity floor)"

    def _score(self, state, stats, words):
        candidates = set(state.candidate_words)
        primary = np.fromiter((0.0 if word in candidates else 1.0 for word in words), dtype=float)
        return primary, [], "first_candidate"


class LetterFrequency(HeuristicStrategy):
    """Prefer guesses made of letters that are common *among the remaining candidates*.

    Score: ``-sum_{c in distinct(g)} f(c)`` with ``f`` the letter share of the current
    candidate set. Position-blind, which is why it is a baseline and not a default.

    The frequency must be measured on the candidates, not the whole corpus: a
    corpus-wide table is the same for every state, so the strategy would repeat one
    word until it failed (measured on classic: 5.6832 average, 67.0% unsolved).
    """

    name = "letter_frequency"
    needs_partitions = False
    objective = "maximise the summed frequency of the guess's distinct letters among candidates"

    def _score(self, state, stats, words):
        candidates = state.candidate_words
        counts = Counter(letter for word in candidates for letter in word)
        total = float(sum(counts.values())) or 1.0
        frequency = {letter: counts[letter] / total for letter in state.profile.alphabet}
        primary = np.fromiter(
            (-sum(frequency[letter] for letter in set(word)) for word in words), dtype=float
        )
        return primary, [], "letter_frequency"


class PositionalFrequency(HeuristicStrategy):
    """Prefer letters that are common *in their position among the candidates*.

    Score: ``-sum_i f_i(g_i)`` with ``f_i`` the candidate-set letter share at position i.
    """

    name = "positional_frequency"
    needs_partitions = False
    objective = "maximise the summed per-position candidate frequency of the guess"

    def _tables(self, state: GameState) -> list[dict[str, float]]:
        candidates = state.candidate_words
        total = float(len(candidates)) or 1.0
        tables = []
        for position in range(state.profile.length):
            counts = Counter(word[position] for word in candidates)
            tables.append({letter: counts[letter] / total for letter in state.profile.alphabet})
        return tables

    def _score(self, state, stats, words):
        tables = self._tables(state)
        primary = np.fromiter(
            (
                -sum(tables[position].get(letter, 0.0) for position, letter in enumerate(word))
                for word in words
            ),
            dtype=float,
        )
        return primary, [], "positional_frequency"


class ExpectedRemaining(HeuristicStrategy):
    """One-step Bayesian expected cost: ``sum_r p_r |S_r|``.

    This is the L-squared/bin-count objective: for a uniform prior it equals
    ``sum_r |S_r|^2 / |S|``, the expected number of candidates left after the guess.
    Ties are broken by higher entropy.
    """

    name = "expected_remaining"
    objective = "minimise sum_r p_r |S_r| (one-step expected remaining candidates)"
    stat_keys = frozenset({"expected_remaining", "entropy"})

    def _score(self, state, stats, words):
        assert stats is not None
        return stats["expected_remaining"], [-stats["entropy"]], "expected_remaining"


class ExpectedRemainingCandidates(ExpectedRemaining):
    """``sum_r p_r |S_r|`` with guesses restricted to the answer list."""

    name = "expected_remaining_candidates"
    candidate_only = True
    objective = "minimise sum_r p_r |S_r| using only answers as guesses"


class Entropy(HeuristicStrategy):
    """Max-entropy (negentropy) greedy: maximise ``H(pattern)``.

    Score: ``-sum_r p_r log2 p_r``, ties broken by lower expected remaining. Entropy is
    a baseline, not the objective: it maximises information, not progress.
    """

    name = "entropy"
    objective = "maximise expected information gain (-sum_r p_r log2 p_r)"
    stat_keys = frozenset({"entropy", "expected_remaining"})

    def _score(self, state, stats, words):
        assert stats is not None
        return -stats["entropy"], [stats["expected_remaining"]], "entropy"


class EntropyCandidates(Entropy):
    """Max-entropy with guesses restricted to the answer list."""

    name = "entropy_candidates"
    candidate_only = True
    objective = "maximise information gain using only answers as guesses"


class WeightedEntropy(Entropy):
    """Max-entropy under the answer prior: ``-sum_r p_r log2 p_r`` with weighted ``p``.

    Identical to :class:`Entropy` when the prior is uniform, including when a Zipf
    prior is configured with ``beta = 0``: the same float64 ones, the same partitions
    and therefore the same decisions.
    """

    name = "weighted_entropy"
    objective = "maximise prior-weighted information gain (-sum_r p_r log2 p_r)"

    def _score(self, state, stats, words):
        assert stats is not None
        return -stats["entropy"], [stats["expected_remaining"]], "weighted_entropy"


class BayesCost(HeuristicStrategy):
    """One-step Bayesian cost with an analytic continuation value (§6.2).

    Score: ``sum_r p_r (1 + V(|S_r|))`` where ``V(s) = sqrt(s) - 1`` is the fixed
    point of "each further guess leaves about ``sqrt(s)`` candidates" — the same
    reduction the expected-remaining objective achieves. The constant ``1`` is the
    guess itself, so the score is ``sum_r p_r sqrt(|S_r|)``. It sits between
    ``entropy`` (logarithmic in bucket size) and ``expected_remaining`` (linear), and
    is prior-aware through ``p``.
    """

    name = "bayes_cost"
    objective = "minimise sum_r p_r (1 + V(|S_r|)), V(s)=sqrt(s)-1 (one-step Bayesian cost)"
    stat_keys = frozenset({"expected_sqrt", "entropy"})

    def _score(self, state, stats, words):
        assert stats is not None
        return stats["expected_sqrt"], [-stats["entropy"]], "bayes_cost"


class Minimax(HeuristicStrategy):
    """Worst-case strategy: minimise the largest feedback bucket.

    Score: ``max_r |S_r|``, tie-broken by the second-largest bucket and then by higher
    entropy. This is the strategy a worst-case guarantee is built on, and the reason
    hard mode needs its own constraint engine.
    """

    name = "minimax"
    objective = "minimise max_r |S_r| (largest remaining bucket)"
    stat_keys = frozenset({"worst_case", "second_worst", "entropy"})

    def _score(self, state, stats, words):
        assert stats is not None
        return stats["worst_case"], [stats["second_worst"], -stats["entropy"]], "minimax"


class MinimaxCandidates(Minimax):
    """Minimax with guesses restricted to the answer list."""

    name = "minimax_candidates"
    candidate_only = True
    objective = "minimise the largest bucket using only answers as guesses"


class Hybrid(ExpectedRemaining):
    """Default Phase 2 policy: expected cost now, with the forced endgame branches.

    Phase 2 has no lookahead; the branch taken is recorded in
    ``Decision.breakdown['branch']`` so a later phase can extend it without changing
    what this one did.
    """

    name = "hybrid.balanced"
    objective = "expected_remaining with forced single-candidate and last-turn branches"

    def _branch(self, state: GameState) -> str:
        return "expected_remaining"
