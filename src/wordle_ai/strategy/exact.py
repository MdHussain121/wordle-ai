"""The ``exact`` strategy: lookup in a verified policy artifact (§6.2, §7.3).

The strategy owns no search at solve time. It maps the current candidate set to a node
of the solved tree and returns that node's guess, so a decision costs a dictionary
lookup and a small partition for the explanation. When the artifact does not cover the
state (a game that left optimal play, or a different rule configuration) it raises
``ArtifactMismatchError`` instead of quietly substituting a heuristic.
"""

from __future__ import annotations

import time

import numpy as np

from ..engine.state import GameState
from ..engine.table import RowSource
from ..errors import ArtifactMismatchError
from ..types import RuleMode
from .base import Decision, PartitionStats, ScoreBreakdown
from ..solver.dp import mask_signature

INF = float("inf")


class ExactStrategy:
    """Proven-optimal play from a policy artifact."""

    name = "exact"
    candidate_only = False
    exact = True
    objective = "minimise expected guesses using a verified exact DP policy"

    def __init__(self, policy: dict | None = None) -> None:
        self.policy = policy
        self._index: dict[str, dict] | None = None
        self._matrix: np.ndarray | None = None
        self._table: RowSource | None = None

    # ---- loading ----------------------------------------------------------
    def attach(self, policy: dict) -> "ExactStrategy":
        if policy.get("strategy") != "exact":
            raise ArtifactMismatchError(
                f"artifact strategy {policy.get('strategy')!r} is not 'exact'"
            )
        self.policy = policy
        self._index = None
        return self

    @property
    def index(self) -> dict[str, dict]:
        if self._index is None:
            from ..solver.policy import index_nodes

            if self.policy is None:
                raise ArtifactMismatchError(
                    "the exact strategy needs a policy artifact; build one with "
                    "`wordle-ai policy build`"
                )
            self._index = index_nodes(self.policy)
        return self._index

    # ---- inputs -----------------------------------------------------------
    def _rows(self, table: RowSource) -> np.ndarray:
        if self._table is not table:
            self._table = table
            self._matrix = np.asarray(table.matrix(), dtype=np.uint8)
        assert self._matrix is not None
        return self._matrix

    def _node(self, state: GameState) -> dict:
        signature = mask_signature(state.candidates)
        try:
            return self.index[signature]
        except KeyError:
            raise ArtifactMismatchError(
                f"policy {self.policy.get('profile_id') if self.policy else '?'} has no "
                f"decision for this candidate set ({state.remaining} candidates); the "
                "game left the solved tree",
                candidates=state.remaining,
            ) from None

    # ---- public API -------------------------------------------------------
    def choose(
        self,
        state: GameState,
        table: RowSource,
        *,
        prior: np.ndarray | None = None,
        budget=None,
        cache: dict | None = None,
    ) -> Decision:
        started = time.perf_counter()
        if prior is not None:
            raise ArtifactMismatchError(
                "this exact policy was built under a uniform prior; a weighted "
                "decision would not be the policy's optimum"
            )
        if state.mode is not RuleMode.NORMAL:
            raise ArtifactMismatchError(
                "exact policies are built for normal mode; use a heuristic strategy "
                f"in {state.mode.value} mode"
            )
        node = self._node(state)
        guess = str(node["guess"])
        if guess not in state.profile.guess_index:
            raise ArtifactMismatchError(
                f"policy guess {guess!r} is not in profile {state.profile.profile_id}"
            )
        row = self._rows(table)[state.profile.guess_index_of(guess)]
        detail = PartitionStats(row[None, :], state.profile.pattern_count).compute(
            state.candidates
        )
        breakdown = {key: float(value[0]) for key, value in detail.items()}
        value = float(node["value"])
        return Decision(
            guess=guess,
            strategy=self.name,
            score=value,
            breakdown={
                **breakdown,
                "value": value,
                "branch": "exact_policy",
                "policy_nodes": float(len(self.index)),
                "legal_guesses": float(len(state.profile.guesses)),
            },
            candidates_before=state.remaining,
            candidates_after_expected=breakdown["expected_remaining"],
            p_solve_now=breakdown["p_solve_now"],
            explanation=(
                f"exact policy chose '{guess}': with {state.attempts_left} guess(es) "
                f"left this state needs {value:.4f} more guesses on average, the "
                f"minimum over every legal guess."
            ),
            exact=True,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )

    def score(
        self,
        state: GameState,
        table: RowSource,
        *,
        prior: np.ndarray | None = None,
    ) -> list[ScoreBreakdown]:
        """One-step cost of every legal guess, using policy values for the children.

        A child outside the artifact has value ``inf``: the policy cannot claim a bound
        for a state it never solved.
        """

        if prior is not None:
            raise ArtifactMismatchError("exact policy scores assume a uniform prior")
        matrix = self._rows(table)
        cols = np.flatnonzero(state.candidates)
        n = cols.size
        out: list[ScoreBreakdown] = []
        for word in state.profile.guesses:
            row = matrix[state.profile.guess_index_of(word)]
            codes = row[cols]
            order = np.argsort(codes, kind="stable")
            sorted_codes = codes[order]
            starts = np.flatnonzero(
                np.concatenate(([True], sorted_codes[1:] != sorted_codes[:-1]))
            )
            ends = np.concatenate((starts[1:], [n]))
            total = 0.0
            for start, end in zip(starts.tolist(), ends.tolist()):
                child_cols = cols[order[start:end]]
                child = np.zeros_like(state.candidates)
                child[child_cols] = True
                child_node = self.index.get(mask_signature(child))
                if child_node is None:
                    total = INF
                    break
                total += (end - start) * float(child_node["value"])
            score = INF if total == INF else 1.0 + total / n
            out.append(
                ScoreBreakdown(
                    guess=word, score=score, breakdown={"value": score}
                )
            )
        return out
