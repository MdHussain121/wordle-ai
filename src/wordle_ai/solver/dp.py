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

        self._memo: dict[tuple[int, tuple[int, ...]], tuple[float, int]] = {}
        self._nodes = 0
        self._evaluations = 0
        self._started = 0.0
        self._deadline: float | None = None

    # ---- public -----------------------------------------------------------
    def solve(self, mask: np.ndarray | None = None) -> Solution:
        """Solve from the given candidate mask (all answers when ``None``)."""

        if mask is None:
            cols = tuple(range(len(self.profile.answers)))
        else:
            mask = np.asarray(mask, dtype=bool)
            if not bool(mask.any()):
                raise ValueError("cannot solve an empty candidate set")
            cols = tuple(int(x) for x in np.flatnonzero(mask))

        self._memo.clear()
        self._nodes = 0
        self._evaluations = 0
        self._started = time.perf_counter()
        self._deadline = (
            self._started + self.time_budget_s if self.time_budget_s is not None else None
        )

        value = self._value(self.max_attempts, cols)
        if not np.isfinite(value):
            raise BudgetExceeded(
                f"no strategy can guarantee a solve of {len(cols)} "
                f"candidates in {self.max_attempts} guesses"
            )
        root = self._build_tree(self.max_attempts, cols)
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
    def _candidate_guesses(self, cols: tuple[int, ...]) -> list[int]:
        cand_guesses = [int(self.answer_rows[i]) for i in cols if self.answer_rows[i] >= 0]
        cand_guesses = sorted(set(cand_guesses))
        if len(cols) > 2 and len(cand_guesses) > 2:
            def score(g: int) -> tuple[int, int]:
                row = self.matrix[g]
                counts: dict[int, int] = {}
                for c in cols:
                    cd = int(row[c])
                    counts[cd] = counts.get(cd, 0) + 1
                return max(counts.values()), g
            cand_guesses.sort(key=score)
        return cand_guesses

    def _value(self, k: int, cols: tuple[int, ...]) -> float:
        n = len(cols)
        if n == 1:
            return 1.0
        if k <= 1:
            return INF
        if n == 2:
            return 1.5
        if n == 3 and k >= 3:
            c0, c1, c2 = cols
            g0 = self.answer_rows[c0]
            g1 = self.answer_rows[c1]
            g2 = self.answer_rows[c2]
            if g0 >= 0 and self.matrix[g0, c1] != self.matrix[g0, c2]:
                return 5.0 / 3.0
            if g1 >= 0 and self.matrix[g1, c0] != self.matrix[g1, c2]:
                return 5.0 / 3.0
            if g2 >= 0 and self.matrix[g2, c0] != self.matrix[g2, c1]:
                return 5.0 / 3.0
            return 2.0

        key = (k, cols)
        cached = self._memo.get(key)
        if cached is not None:
            return cached[0]
        if len(self._memo) >= self.memo_max_entries:
            raise BudgetExceeded(
                f"exact memo reached {self.memo_max_entries} entries; raise "
                "exact.memo_max_entries or restrict the guess set"
            )
        self._check_deadline()

        best = INF
        best_guess = -1
        theoretical_min = 2.0 - 1.0 / n + EPS

        cand_guesses = self._candidate_guesses(cols)
        for guess_index in cand_guesses:
            cost = self._guess_cost(k, cols, guess_index, best)
            if cost < best - EPS:
                best = cost
                best_guess = guess_index
                if best <= theoretical_min:
                    break

        # Universal External Guess Elimination Bound:
        # Any external guess has cost >= 2.0. If best <= 2.0 + EPS, skip all non-candidates.
        if self.guess_set == "all" and best > 2.0 + EPS:
            cand_set = set(cand_guesses)
            for guess_index in range(len(self.profile.guesses)):
                if guess_index not in cand_set:
                    cost = self._guess_cost(k, cols, guess_index, best)
                    if cost < best - EPS:
                        best = cost
                        best_guess = guess_index
                        if best <= 2.0 + EPS:
                            break

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
        self._memo[key] = (best, best_guess)
        return best

    def _guess_cost(
        self,
        k: int,
        cols: tuple[int, ...],
        guess_index: int,
        incumbent: float,
    ) -> float:
        self._evaluations += 1
        n = len(cols)
        row = self.matrix[guess_index]

        has_match = False
        buckets: dict[int, list[int]] = {}
        for c in cols:
            if self.answer_rows[c] == guess_index:
                has_match = True
            code = int(row[c])
            try:
                buckets[code].append(c)
            except KeyError:
                buckets[code] = [c]

        if len(buckets) == 1:
            return INF

        if k == 2 and any(len(members) >= 2 for members in buckets.values()):
            return INF

        u = n - 1 if has_match else n
        b_unsolved = len(buckets) - 1 if has_match else len(buckets)
        lower_bound = 1.0 + (2 * u - b_unsolved) / n
        if incumbent < INF and lower_bound >= incumbent - EPS:
            return INF

        total = 0.0
        for members in buckets.values():
            size = len(members)
            if size == 1 and self.answer_rows[members[0]] == guess_index:
                continue
            if size == 1:
                total += 1.0
            else:
                value = self._value(k - 1, tuple(members))
                if not np.isfinite(value):
                    return INF
                total += size * value
            if incumbent < INF and 1.0 + total / n >= incumbent - EPS:
                return INF

        return 1.0 + total / n

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
    def _cols_to_signature(self, cols: tuple[int, ...] | list[int]) -> str:
        mask = np.zeros(len(self.profile.answers), dtype=bool)
        mask[list(cols)] = True
        return mask_signature(mask)

    def _build_tree(self, k: int, cols: tuple[int, ...] | np.ndarray) -> dict:
        if isinstance(cols, np.ndarray):
            cols = tuple(int(x) for x in np.flatnonzero(cols))
        n = len(cols)
        state_sig = self._cols_to_signature(cols)
        if n == 1:
            answer = cols[0]
            return {
                "state": state_sig,
                "guess": self.profile.answers[answer],
                "value": 1.0,
                "children": {},
            }
        if n == 2:
            c0, c1 = cols
            g0 = int(self.answer_rows[c0])
            code0 = int(self.matrix[g0, c0])
            code1 = int(self.matrix[g0, c1])
            children = {}
            if code0 <= code1:
                children[str(code0)] = {
                    "state": self._cols_to_signature((c0,)),
                    "guess": self.profile.answers[c0],
                    "value": 1.0,
                    "children": {},
                }
                children[str(code1)] = {
                    "state": self._cols_to_signature((c1,)),
                    "guess": self.profile.answers[c1],
                    "value": 1.0,
                    "children": {},
                }
            else:
                children[str(code1)] = {
                    "state": self._cols_to_signature((c1,)),
                    "guess": self.profile.answers[c1],
                    "value": 1.0,
                    "children": {},
                }
                children[str(code0)] = {
                    "state": self._cols_to_signature((c0,)),
                    "guess": self.profile.answers[c0],
                    "value": 1.0,
                    "children": {},
                }
            return {
                "state": state_sig,
                "guess": self.profile.guesses[g0],
                "value": 1.5,
                "children": children,
            }
        if n == 3 and k >= 3:
            c0, c1, c2 = cols
            g0 = int(self.answer_rows[c0])
            g1 = int(self.answer_rows[c1])
            g2 = int(self.answer_rows[c2])
            if g0 >= 0 and self.matrix[g0, c1] != self.matrix[g0, c2]:
                guess_index = g0
                val = 5.0 / 3.0
            elif g1 >= 0 and self.matrix[g1, c0] != self.matrix[g1, c2]:
                guess_index = g1
                val = 5.0 / 3.0
            elif g2 >= 0 and self.matrix[g2, c0] != self.matrix[g2, c1]:
                guess_index = g2
                val = 5.0 / 3.0
            else:
                guess_index = g0
                val = 2.0
            row = self.matrix[guess_index]
            buckets: dict[int, list[int]] = {}
            for c in cols:
                code = int(row[c])
                buckets.setdefault(code, []).append(c)
            children = {}
            for code in sorted(buckets.keys()):
                children[str(code)] = self._build_tree(k - 1, tuple(buckets[code]))
            return {
                "state": state_sig,
                "guess": self.profile.guesses[guess_index],
                "value": val,
                "children": children,
            }

        key = (k, cols)
        entry = self._memo.get(key)
        if entry is None or entry[1] < 0:
            raise AssertionError("policy requested for a state the DP did not solve")
        val, guess_index = entry
        row = self.matrix[guess_index]
        buckets = {}
        for c in cols:
            code = int(row[c])
            buckets.setdefault(code, []).append(c)
        children = {}
        for code in sorted(buckets.keys()):
            children[str(code)] = self._build_tree(k - 1, tuple(buckets[code]))
        return {
            "state": state_sig,
            "guess": self.profile.guesses[guess_index],
            "value": float(val),
            "children": children,
        }

    @staticmethod
    def _tree_depth(node: dict) -> int:
        children = node.get("children", {})
        if not children:
            return 1
        return 1 + max(ExactSolver._tree_depth(child) for child in children.values())
