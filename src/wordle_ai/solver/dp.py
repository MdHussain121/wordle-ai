"""Exact dynamic programme over candidate sets (technical specification §7).

The value being minimised is the expected number of *future* guesses::

    V(k, S) = 1                                        if |S| == 1
            = inf                                      if k == 1 and |S| > 1
            = min_g 1 + sum_{r: S_r != solved(g)} (|S_r| / |S|) * V(k-1, S_r)

where ``S_r`` is the subset of ``S`` whose answers produce feedback code ``r``
against ``g`` and ``solved(g)`` is the all-green bucket ``{g}``. That bucket costs
nothing further: the guess that produced it is the guess being paid for, so charging
``V({g}) = 1`` again would count a solved game twice. A guess is admissible only when
every remaining child is feasible, which is what makes a finite value a guarantee of
solving within the attempt limit.

The implementation is deliberately a plain memoised recursion with an incumbent
bound; the expensive part (partitioning a candidate set by one guess) is done with a
single sort, and the recursion stores the chosen guess so a policy tree can be
serialised without a second solve. Exactness is not an optimisation: the recursive
solver is the oracle, and ``tests/unit/test_exact.py`` compares it against an
independent brute-force enumeration on a small profile.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

from ..engine.table import RowSource
from ..errors import BudgetExceeded, UnsupportedProfile
from ..types import Profile, RuleMode

INF = float("inf")
EPS = 1e-12


def mask_signature(mask: np.ndarray) -> str:
    """Stable, compact key for a candidate mask (the DP's canonical form)."""

    return np.packbits(np.asarray(mask, dtype=bool)).tobytes().hex()


def _partition(codes: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Group candidate feedback codes into buckets with one stable sort.

    Returns ``(order, sorted_codes, starts, ends)`` where bucket ``i`` is the slice
    ``order[starts[i]:ends[i]]`` of the original candidate columns.
    """

    order = np.argsort(codes, kind="stable")
    sorted_codes = codes[order]
    starts = np.flatnonzero(
        np.concatenate(([True], sorted_codes[1:] != sorted_codes[:-1]))
    )
    ends = np.concatenate((starts[1:], [codes.size]))
    return order, sorted_codes, starts, ends


@dataclass
class Solution:
    """Result of a completed exact solve."""

    value: float
    root_guess: str
    policy: dict
    nodes: int
    memo_entries: int
    guess_evaluations: int
    elapsed_s: float
    max_guesses: int
    guess_set: str


class ExactSolver:
    """Memoised exact solver for one profile and one rule configuration.

    Only normal mode is supported. Hard and superhard legality depends on the
    accumulated history rather than on the candidate set alone, so those modes need a
    larger state (candidates + constraint) and are not claimed here; requesting them
    fails loudly instead of silently solving a different game.
    """

    def __init__(
        self,
        profile: Profile,
        rows: RowSource,
        *,
        max_attempts: int = 6,
        mode: RuleMode = RuleMode.NORMAL,
        guess_set: str = "all",
        memo_max_entries: int = 2_000_000,
        time_budget_s: float | None = None,
        progress: Callable[[dict], None] | None = None,
    ) -> None:
        if mode is not RuleMode.NORMAL:
            raise UnsupportedProfile(
                "exact policies are implemented for normal mode only; hard and "
                "superhard legality depends on the full history, not just the "
                "candidate set. Use the heuristic strategies for those modes."
            )
        if guess_set not in ("all", "candidates"):
            raise ValueError("guess_set must be 'all' or 'candidates'")
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

        self.profile = profile
        self.max_attempts = max_attempts
        self.guess_set = guess_set
        self.memo_max_entries = memo_max_entries
        self.time_budget_s = time_budget_s
        self.progress = progress
        self.matrix = np.asarray(rows.matrix(), dtype=np.uint8)
        if self.matrix.shape != (len(profile.guesses), len(profile.answers)):
            raise ValueError(
                f"row source has shape {self.matrix.shape}, profile expects "
                f"{(len(profile.guesses), len(profile.answers))}"
            )
        # Row of each answer in the guess list, or -1 when an answer is not a guess
        # (the profile asserts answers ⊆ guesses, so this is defensive only).
        self.answer_rows = np.array(
            [profile.guess_index.get(word, -1) for word in profile.answers], dtype=np.int64
        )
        self.pattern_count = profile.pattern_count

        self._memo: dict[tuple[int, str], float] = {}
        self._choice: dict[tuple[int, str], int] = {}
        self._nodes = 0
        self._evaluations = 0
        self._started = 0.0
        self._deadline: float | None = None

    # ---- public -----------------------------------------------------------
    def solve(self, mask: np.ndarray | None = None) -> Solution:
        """Solve from the given candidate mask (all answers when ``None``)."""

        if mask is None:
            mask = np.ones(len(self.profile.answers), dtype=bool)
        mask = np.asarray(mask, dtype=bool)
        if not bool(mask.any()):
            raise ValueError("cannot solve an empty candidate set")

        self._memo.clear()
        self._choice.clear()
        self._nodes = 0
        self._evaluations = 0
        self._started = time.perf_counter()
        self._deadline = (
            self._started + self.time_budget_s if self.time_budget_s is not None else None
        )

        value = self._value(self.max_attempts, mask)
        if not np.isfinite(value):
            raise BudgetExceeded(
                f"no strategy can guarantee a solve of {int(np.count_nonzero(mask))} "
                f"candidates in {self.max_attempts} guesses"
            )
        root = self._build_tree(self.max_attempts, mask)
        return Solution(
            value=value,
            root_guess=root["guess"],
            policy=root,
            nodes=self._nodes,
            memo_entries=len(self._memo),
            guess_evaluations=self._evaluations,
            elapsed_s=time.perf_counter() - self._started,
            max_guesses=self._tree_depth(root),
            guess_set=self.guess_set,
        )

    # ---- recursion --------------------------------------------------------
    def _value(self, k: int, mask: np.ndarray) -> float:
        cols = np.flatnonzero(mask)
        n = int(cols.size)
        if n == 1:
            return 1.0
        if k <= 1:
            return INF

        key = (k, mask_signature(mask))
        cached = self._memo.get(key)
        if cached is not None:
            return cached
        if len(self._memo) >= self.memo_max_entries:
            raise BudgetExceeded(
                f"exact memo reached {self.memo_max_entries} entries; raise "
                "exact.memo_max_entries or restrict the guess set"
            )
        self._check_deadline()

        best = INF
        best_guess = -1
        for guess_index in self._ordered_guesses(cols):
            cost = self._guess_cost(k, mask, cols, guess_index, best)
            if cost < best - EPS:
                best = cost
                best_guess = guess_index
        self._nodes += 1
        if self.progress is not None and self._nodes % 1000 == 0:
            self.progress(
                {
                    "nodes": self._nodes,
                    "memo": len(self._memo),
                    "candidates": n,
                    "elapsed_s": time.perf_counter() - self._started,
                }
            )
        self._memo[key] = best
        self._choice[key] = best_guess
        return best

    def _guess_cost(
        self,
        k: int,
        mask: np.ndarray,
        cols: np.ndarray,
        guess_index: int,
        incumbent: float,
    ) -> float:
        self._evaluations += 1
        n = cols.size
        codes = self.matrix[guess_index][cols]
        if codes.min() == codes.max():
            # One bucket: no information, so the guess cannot improve on guessing a
            # candidate (and would recurse on the same set).
            return INF

        order, _, starts, ends = _partition(codes)
        total = 0.0
        for start, end in zip(starts.tolist(), ends.tolist()):
            size = end - start
            child_cols = cols[order[start:end]]
            if size == 1 and self.answer_rows[int(child_cols[0])] == guess_index:
                # The guess itself: this turn solved that game, so it adds no future
                # guesses. Every other singleton still needs to be guessed.
                continue
            if size == 1:
                total += 1.0
            else:
                child = np.zeros_like(mask)
                child[child_cols] = True
                value = self._value(k - 1, child)
                if not np.isfinite(value):
                    return INF
                total += size * value
            if incumbent < INF and 1.0 + total / n >= incumbent - EPS:
                return INF
        return 1.0 + total / n

    def _ordered_guesses(self, cols: np.ndarray) -> list[int]:
        """Candidates first, then every other guess in index order.

        The order is deterministic and puts the guesses most likely to produce a good
        incumbent first; it never excludes a guess, so the result is unchanged.
        """

        if self.guess_set == "candidates":
            return [int(self.answer_rows[i]) for i in cols if self.answer_rows[i] >= 0]
        answer_flags = np.zeros(len(self.profile.guesses), dtype=bool)
        rows = self.answer_rows[cols]
        answer_flags[rows[rows >= 0]] = True
        candidates = np.flatnonzero(answer_flags).tolist()
        if len(candidates) == len(self.profile.guesses):
            return candidates
        rest = np.flatnonzero(~answer_flags).tolist()
        return candidates + rest

    def _check_deadline(self) -> None:
        if self._deadline is None:
            return
        if self._nodes % 32 != 0:
            return
        if time.perf_counter() > self._deadline:
            raise BudgetExceeded(
                f"exact solve exceeded its {self.time_budget_s:.0f}s budget after "
                f"{self._nodes} nodes and {len(self._memo)} memo entries; the "
                "candidate set is not tractable within this budget"
            )

    # ---- policy tree ------------------------------------------------------
    def _build_tree(self, k: int, mask: np.ndarray) -> dict:
        cols = np.flatnonzero(mask)
        n = int(cols.size)
        if n == 1:
            answer = int(cols[0])
            return {
                "state": mask_signature(mask),
                "guess": self.profile.answers[answer],
                "value": 1.0,
                "children": {},
            }
        key = (k, mask_signature(mask))
        guess_index = self._choice.get(key, -1)
        if guess_index < 0:
            raise AssertionError("policy requested for a state the DP did not solve")
        order, sorted_codes, starts, ends = _partition(self.matrix[guess_index][cols])
        children: dict[str, dict] = {}
        for start, end in zip(starts.tolist(), ends.tolist()):
            child_cols = cols[order[start:end]]
            child_mask = np.zeros_like(mask)
            child_mask[child_cols] = True
            code = int(sorted_codes[start])
            children[str(code)] = self._build_tree(k - 1, child_mask)
        return {
            "state": mask_signature(mask),
            "guess": self.profile.guesses[guess_index],
            "value": float(self._memo[key]),
            "children": children,
        }

    @staticmethod
    def _tree_depth(node: dict) -> int:
        children = node.get("children", {})
        if not children:
            return 1
        return 1 + max(ExactSolver._tree_depth(child) for child in children.values())
