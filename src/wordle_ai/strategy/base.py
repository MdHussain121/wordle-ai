"""Strategy protocol, partition statistics and deterministic selection (§6).

A strategy sees a state (candidate mask, history, mode, attempts left), a row source
(the feedback table or an equivalent on-demand computation), an optional prior and a
budget, and returns a :class:`Decision`. Nothing here holds an opener word: the first
guess is whatever the objective selects over the whole profile, so changing the
dictionary changes the opener.

Determinism. Scores are quantised at ``1e-12`` before comparison, ties are broken by
the declared tie-break then by ascending index in the profile's sorted guess list, and
no strategy uses random numbers. The same inputs therefore always produce the same
decision, in any process, in any order of games.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable

import numpy as np

from ..engine.constraints import constraint_for, legal_mask
from ..engine.state import GameState
from ..engine.table import RowSource
from ..errors import NoLegalGuessError
from ..types import RuleMode


@dataclass(frozen=True)
class Budget:
    """Limits a strategy may consult; exceeding one is reported, never silent."""

    pairwise_limit: int = 20_000_000
    max_candidates: int = 0


@dataclass(frozen=True)
class ScoreBreakdown:
    guess: str
    score: float
    breakdown: dict[str, float]


@dataclass(frozen=True)
class Decision:
    guess: str
    strategy: str
    score: float
    breakdown: dict[str, float | str]
    candidates_before: int
    candidates_after_expected: float
    p_solve_now: float
    explanation: str
    exact: bool
    elapsed_ms: float


@runtime_checkable
class Strategy(Protocol):
    name: str
    candidate_only: bool
    objective: str

    def choose(
        self,
        state: GameState,
        table: RowSource,
        *,
        prior: np.ndarray | None = None,
        budget: Budget | None = None,
        cache: dict | None = None,
    ) -> Decision: ...

    def score(
        self,
        state: GameState,
        table: RowSource,
        *,
        prior: np.ndarray | None = None,
    ) -> list[ScoreBreakdown]: ...


class PartitionStats:
    """Bucket statistics for every row of a guess subset.

    For a candidate mask and a guess ``g``, the partition is the number of candidates
    that would remain for each feedback code. All objectives in §6.2 are functions of
    those counts and of the prior weights, so they are computed together in chunks to
    keep peak memory bounded on the classic profile (12,972 guesses x 2,315 answers).
    """

    def __init__(self, rows: np.ndarray, pattern_count: int, *, chunk_rows: int = 512) -> None:
        if rows.ndim != 2:
            raise ValueError("rows must be a 2-D array")
        self.rows = rows
        self.pattern_count = pattern_count
        self.chunk_rows = max(1, chunk_rows)

    def compute(
        self,
        mask: np.ndarray,
        weights: np.ndarray | None = None,
        keys: Sequence[str] | None = None,
    ) -> dict[str, np.ndarray]:
        """Partition metrics for every guess row.

        ``keys`` selects the objectives to reduce. A strategy reads only its primary
        and tie-break metrics, so computing the other five over a 12,972\xd7243 table is
        pure cost; ``None`` keeps the full set for callers that display a breakdown.
        """
        columns = np.flatnonzero(mask)
        n_candidates = int(columns.size)
        if n_candidates == 0:
            raise ValueError("cannot score an empty candidate set")
        if weights is None:
            w = np.ones(n_candidates, dtype=np.float64)
        else:
            w = np.asarray(weights, dtype=np.float64)[columns]
        total = float(w.sum())
        if total <= 0:
            raise ValueError("candidate weights must have positive mass")

        solved_code = self.pattern_count - 1  # every tile green
        uniform = weights is None
        need_solved = keys is None or "p_solve_now" in set(keys)
        if n_candidates >= self.pattern_count:
            counts, weighted, solved_weight = self._dense(
                columns, w, solved_code, uniform=uniform, need_solved=need_solved
            )
        else:
            counts, weighted, solved_weight = self._sparse(
                columns, w, solved_code, uniform=uniform, need_solved=need_solved
            )

        wanted = None if keys is None else set(keys)

        def need(name: str) -> bool:
            return wanted is None or name in wanted

        out: dict[str, np.ndarray] = {}
        if need("expected_remaining"):
            # Under a uniform prior this is sum(c^2)/total. The integer products are
            # exact below 2^53, so this matches the float64 weighted product exactly
            # while avoiding a whole-table float multiply.
            out["expected_remaining"] = (
                np.einsum("ij,ij->i", counts, counts, dtype=np.float64) / total
                if uniform
                else (weighted * counts).sum(axis=1) / total
            )
        if need("entropy"):
            # Same expression and order as before (p = c/total; skip zero bins), so the
            # float64 result is bit-identical to the weighted version under a uniform
            # prior. Non-uniform priors still use their explicit weights below.
            if uniform:
                probabilities = counts.astype(np.float64)
                probabilities /= total
            else:
                probabilities = weighted / total
            safe = np.where(probabilities > 0, probabilities, 1.0)
            out["entropy"] = -np.where(
                probabilities > 0, probabilities * np.log2(safe), 0.0
            ).sum(axis=1)
        if need("worst_case"):
            out["worst_case"] = counts.max(axis=1).astype(np.float64)
        if need("second_worst"):
            second = (
                np.partition(counts, -2, axis=1)[:, -2]
                if counts.shape[1] >= 2
                else np.zeros(counts.shape[0], dtype=counts.dtype)
            )
            out["second_worst"] = second.astype(np.float64)
        if need("buckets"):
            out["buckets"] = (counts > 0).sum(axis=1).astype(np.float64)
        if need("p_solve_now"):
            assert solved_weight is not None
            out["p_solve_now"] = solved_weight / total
        if need("expected_sqrt"):
            # One-step Bayesian cost (§6.2): sum_r p_r sqrt(|S_r|). The analytic value
            # estimate is V(s) = sqrt(s) - 1, the fixed point of "a guess leaves about
            # sqrt(s) candidates", so 1 + V(s) = sqrt(s) for every non-empty bucket.
            if uniform:
                out["expected_sqrt"] = (
                    np.einsum(
                        "ij,ij->i", np.sqrt(counts, dtype=np.float64), counts
                    )
                    / total
                )
            else:
                out["expected_sqrt"] = (weighted * np.sqrt(counts)).sum(axis=1) / total
        return out

    def _dense(
        self,
        columns: np.ndarray,
        w: np.ndarray,
        solved_code: int,
        *,
        uniform: bool = False,
        need_solved: bool = True,
    ) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
        """One bin per pattern code; efficient when candidates exceed the code space.

        Each guess row is reduced with a single ``bincount`` over its contiguous
        candidate slice. The previous version tiled the codes into one flat array and
        built an offset vector per chunk; that allocates several int64 copies of the
        guess\xd7answer block (~200 MiB per 512-row chunk on ``full.en.5``) and is
        3\xd7 slower than the row loop, which reads the memory map sequentially and
        allocates only the result.

        Under a uniform prior the weighted counts are the counts themselves, so the
        weighted reduction is skipped. The values are identical either way (integer
        counts are exact in float64), which is why decisions and determinism hashes do
        not change.
        """

        n_guesses = self.rows.shape[0]
        pattern_count = self.pattern_count
        counts = np.empty((n_guesses, pattern_count), dtype=np.int32)
        weighted = (
            None
            if uniform
            else np.empty((n_guesses, pattern_count), dtype=np.float64)
        )
        solved_weight = (
            np.empty(n_guesses, dtype=np.float64) if need_solved else None
        )
        all_columns = columns.size == self.rows.shape[1]
        for start in range(0, n_guesses, self.chunk_rows):
            stop = min(start + self.chunk_rows, n_guesses)
            sub = self.rows[start:stop] if all_columns else self.rows[start:stop][:, columns]
            for row_offset in range(stop - start):
                row = sub[row_offset]
                position = start + row_offset
                counts[position] = np.bincount(row, minlength=pattern_count)
                if uniform:
                    if solved_weight is not None:
                        solved_weight[position] = float(
                            np.count_nonzero(row == solved_code)
                        )
                else:
                    assert weighted is not None
                    weighted[position] = np.bincount(
                        row, weights=w, minlength=pattern_count
                    )
                    if solved_weight is not None:
                        solved_weight[position] = float(w[row == solved_code].sum())
        return counts, weighted, solved_weight

    def _sparse(
        self,
        columns: np.ndarray,
        w: np.ndarray,
        solved_code: int,
        *,
        uniform: bool = False,
        need_solved: bool = True,
    ) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
        """One bin per *observed* bucket, found by sorting each row's codes.

        With ``n`` candidates there are at most ``n`` non-empty buckets, so the dense
        ``3**L`` columns are wasted work in the endgame. Sorting ``n`` codes per guess
        and counting run lengths gives exactly the same counts with a budget of
        ``O(|G| n log n)`` and no dependence on the pattern space.
        """

        n_guesses = self.rows.shape[0]
        n_candidates = columns.size
        counts = np.empty((n_guesses, n_candidates), dtype=np.int32)
        weighted = (
            None
            if uniform
            else np.empty((n_guesses, n_candidates), dtype=np.float64)
        )
        solved_weight = (
            np.empty(n_guesses, dtype=np.float64) if need_solved else None
        )
        chunk = max(self.chunk_rows, 2048)
        for start in range(0, n_guesses, chunk):
            stop = min(start + chunk, n_guesses)
            width = stop - start
            sub = self.rows[start:stop][:, columns]
            if uniform:
                # Only the sorted codes are needed: counts are run lengths, and the
                # solved bucket is counted before sorting. This halves the work of
                # argsort + take_along_axis and skips the weight tiling entirely.
                # Order within equal codes is irrelevant to the bucket counts, so the
                # default quicksort is both correct and cheaper than a stable sort.
                sorted_codes = np.sort(sub, axis=1)
                if solved_weight is not None:
                    solved_weight[start:stop] = np.count_nonzero(
                        sub == solved_code, axis=1
                    )
            else:
                order = np.argsort(sub, axis=1, kind="stable")
                sorted_codes = np.take_along_axis(sub, order, axis=1).astype(np.int32)
                sorted_weights = np.take_along_axis(
                    np.tile(w, (width, 1)), order, axis=1
                )
            new_run = np.empty(sorted_codes.shape, dtype=bool)
            new_run[:, 0] = True
            new_run[:, 1:] = sorted_codes[:, 1:] != sorted_codes[:, :-1]
            run_id = np.cumsum(new_run, axis=1) - 1
            flat = (run_id + np.arange(width, dtype=np.int64)[:, None] * n_candidates).ravel()
            counts[start:stop] = np.bincount(
                flat, minlength=width * n_candidates
            ).reshape(width, n_candidates)
            if not uniform:
                assert weighted is not None
                weighted[start:stop] = np.bincount(
                    flat,
                    weights=sorted_weights.ravel(),
                    minlength=width * n_candidates,
                ).reshape(width, n_candidates)
                if solved_weight is not None:
                    solved_weight[start:stop] = (
                        sorted_weights * (sorted_codes == solved_code)
                    ).sum(axis=1)
        return counts, weighted, solved_weight


class HeuristicStrategy:
    """Common machinery for the Phase 2 heuristics: legality, scoring, tie-breaks."""

    name: str = ""
    candidate_only: bool = False
    needs_partitions: bool = True
    objective: str = ""
    exact: bool = False
    tie_epsilon: float = 1e-12
    #: Partition metrics the objective and its tie-breaks read. ``None`` means all.
    stat_keys: frozenset[str] | None = None

    def __init__(
        self,
        *,
        tie_epsilon: float = 1e-12,
        prior_weights: np.ndarray | None = None,
    ) -> None:
        self.tie_epsilon = tie_epsilon
        self.prior_weights = (
            None if prior_weights is None else np.asarray(prior_weights, dtype=np.float64)
        )
        self._table: RowSource | None = None
        self._matrix: np.ndarray | None = None
        self._frequency: dict[str, float] | None = None
        self._positional: list[dict[str, float]] | None = None

    # ---- inputs -----------------------------------------------------------
    def _guess_rows(
        self, state: GameState, table: RowSource
    ) -> tuple[tuple[str, ...], np.ndarray, np.ndarray]:
        if self._table is not table:
            self._table = table
            self._matrix = np.asarray(table.matrix())
        assert self._matrix is not None
        profile = state.profile
        if self.candidate_only:
            indices = np.flatnonzero(state.candidates).astype(np.int64)
            words = tuple(profile.answers[i] for i in indices)
            rows = self._matrix[[profile.guess_index_of(word) for word in words]]
            return words, rows, indices
        return profile.guesses, self._matrix, np.arange(len(profile.guesses), dtype=np.int64)

    def _legal(
        self, state: GameState, words: Sequence[str]
    ) -> np.ndarray:
        if state.mode is RuleMode.NORMAL:
            # Normal rules constrain nothing beyond membership in the profile's guess
            # list, which ``words`` already is. Building the constraint object and
            # testing 12,972 words per decision is pure overhead on this path.
            return np.ones(len(words), dtype=bool)
        constraint = constraint_for(state)
        candidates = set(state.candidate_words) if state.mode is RuleMode.SUPERHARD else None
        mask = legal_mask(
            list(words), constraint=constraint, mode=state.mode, candidates=candidates
        )
        if not bool(mask.any()):
            raise NoLegalGuessError(
                f"{self.name}: no guess in {state.profile.profile_id} satisfies "
                f"{state.mode.value} constraints after {state.attempts_used} turn(s)"
            )
        return mask

    def _weights(self, state: GameState, prior: np.ndarray | None) -> np.ndarray | None:
        if prior is None:
            prior = self.prior_weights
        if prior is None:
            return None
        weights = np.asarray(prior, dtype=np.float64)
        if weights.shape != state.candidates.shape:
            raise ValueError(
                f"prior shape {weights.shape} does not match candidate mask {state.candidates.shape}"
            )
        if float(weights[state.candidates].sum()) <= 0:
            raise ValueError("prior assigns no mass to the remaining candidates")
        return weights

    # ---- objectives -------------------------------------------------------
    def _score(
        self, state: GameState, stats: dict[str, np.ndarray] | None, words: Sequence[str]
    ) -> tuple[np.ndarray, list[np.ndarray], str]:
        """Return (primary score, tie-break keys in priority order, branch)."""

        assert stats is not None
        return (
            stats["expected_remaining"],
            [-stats["entropy"]],
            "expected_remaining",
        )

    def _branch(self, state: GameState) -> str:
        return self.name

    # ---- public API -------------------------------------------------------
    def score(
        self,
        state: GameState,
        table: RowSource,
        *,
        prior: np.ndarray | None = None,
    ) -> list[ScoreBreakdown]:
        words, rows, _ = self._guess_rows(state, table)
        legal = self._legal(state, words)
        all_legal = bool(legal.all())
        selected_words = words if all_legal else [
            word for word, keep in zip(words, legal) if keep
        ]
        stats = None
        if self.needs_partitions:
            selected_rows = rows if all_legal else rows[legal]
            stats = PartitionStats(selected_rows, state.profile.pattern_count).compute(
                state.candidates, self._weights(state, prior), keys=self.stat_keys
            )
        primary, ties, _branch = self._score(state, stats, selected_words)
        out: list[ScoreBreakdown] = []
        for position, word in enumerate(selected_words):
            breakdown = {"score": float(primary[position])}
            for rank, key in enumerate(ties):
                breakdown[f"tie_{rank}"] = float(key[position])
            out.append(ScoreBreakdown(guess=word, score=float(primary[position]), breakdown=breakdown))
        return out

    def choose(
        self,
        state: GameState,
        table: RowSource,
        *,
        prior: np.ndarray | None = None,
        budget: Budget | None = None,
        cache: dict | None = None,
    ) -> Decision:
        started = time.perf_counter()
        weights = self._weights(state, prior)
        cache_key = None
        if cache is not None:
            cache_key = (
                self.name,
                state.mode.value,
                state.attempts_left,
                state.candidates.tobytes(),
                self._prior_key(weights),
            )
            hit = cache.get(cache_key)
            if hit is not None:
                return hit

        words, rows, indices = self._guess_rows(state, table)
        legal = self._legal(state, words)
        all_legal = bool(legal.all())
        selected_words = words if all_legal else [
            word for word, keep in zip(words, legal) if keep
        ]
        selected_rows = rows if all_legal else rows[legal]
        selected_indices = indices if all_legal else indices[legal]

        # Two forced cases, recorded as their own branch: with one candidate there is
        # nothing to choose, and with two turns left only a winning guess can help
        # (a splitter cannot be cashed in with the single remaining turn).
        branch = self._branch(state)
        if state.remaining == 1:
            best_word = state.candidate_words[0]
            best_position = selected_words.index(best_word)
            branch = "single_candidate"
            primary = np.zeros(len(selected_words))
        elif state.attempts_left <= 2:
            posterior = self._posterior(state, weights)
            scores = np.fromiter(
                (
                    -float(posterior[state.profile.answer_index_of(word)])
                    if word in state.profile.answer_index
                    else 0.0
                    for word in selected_words
                ),
                dtype=float,
                count=len(selected_words),
            )
            primary = scores
            best_position = int(np.lexsort((selected_indices, primary))[0])
            best_word = selected_words[best_position]
            branch = "endgame_candidate"
        else:
            stats = None
            if self.needs_partitions:
                stats = PartitionStats(
                    selected_rows, state.profile.pattern_count
                ).compute(state.candidates, weights, keys=self.stat_keys)
            primary, ties, branch = self._score(state, stats, selected_words)
            keys = [np.round(primary, 12), *(np.round(key, 12) for key in ties), selected_indices]
            order = np.lexsort(tuple(reversed(keys)))
            best_position = int(order[0])
            best_word = selected_words[best_position]

        detail_stats = PartitionStats(
            selected_rows[best_position : best_position + 1], state.profile.pattern_count
        ).compute(state.candidates, weights)
        detail = {key: float(value[0]) for key, value in detail_stats.items()}
        decision = Decision(
            guess=best_word,
            strategy=self.name,
            score=float(primary[best_position]),
            breakdown={
                "entropy": detail["entropy"],
                "expected_remaining": detail["expected_remaining"],
                "worst_case": detail["worst_case"],
                "second_worst": detail["second_worst"],
                "buckets": detail["buckets"],
                "p_solve_now": detail["p_solve_now"],
                "bayes_cost": detail["expected_sqrt"],
                "branch": branch,
                "legal_guesses": float(len(selected_words)),
            },
            candidates_before=state.remaining,
            candidates_after_expected=detail["expected_remaining"],
            p_solve_now=detail["p_solve_now"],
            explanation=self._explain(best_word, state.remaining, detail, branch),
            exact=self.exact,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )
        if cache_key is not None and cache is not None:
            cache[cache_key] = decision
        return decision

    @staticmethod
    def _prior_key(weights: np.ndarray | None) -> str:
        """Cache identity of a prior: two weight vectors must not share a decision."""

        if weights is None:
            return "uniform"
        return hashlib.blake2b(
            np.ascontiguousarray(weights, dtype=np.float64).tobytes(), digest_size=8
        ).hexdigest()

    @staticmethod
    def _posterior(state: GameState, weights: np.ndarray | None) -> np.ndarray:
        if weights is None:
            return state.posterior
        masked = np.where(state.candidates, weights, 0.0)
        total = float(masked.sum())
        if total <= 0:
            return state.posterior
        return masked / total

    def _explain(
        self, guess: str, candidates: int, detail: dict[str, float], branch: str
    ) -> str:
        return (
            f"{self.name} chose '{guess}': {candidates:,} candidates fall into "
            f"{int(detail['buckets'])} groups (largest {int(detail['worst_case'])}); "
            f"expected to leave {detail['expected_remaining']:.1f} candidates and win "
            f"immediately in {detail['p_solve_now'] * 100:.1f}% of games."
        )
