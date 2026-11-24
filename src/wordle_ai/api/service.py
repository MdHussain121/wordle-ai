"""Service layer between the engine and any interface (Phase 7, task 1).

The service owns no solving policy: it builds a state, asks the selected strategy for a
decision, applies feedback through the engine and renders views. A terminal UI, an HTTP
adapter or a test can therefore observe the same behaviour, and no interface has to
reach into ``PartitionStats`` to explain a recommendation.

Plain language. Views carry the numbers a player can act on — how many candidates
remain, how many the guess is expected to leave, and the chance it wins now — and the
strategy's own sentence. No ML vocabulary is introduced here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from ..engine.state import GameState, new_game
from ..engine.table import ComputedRows, RowSource, open_rows
from ..errors import ArtifactMismatchError
from ..strategy import HEURISTIC_STRATEGY_NAMES, get_strategy
from ..strategy.base import Decision, Strategy
from ..strategy.exact import ExactStrategy
from ..types import Pattern, Profile, RuleMode, Turn


@dataclass(frozen=True)
class CandidateView:
    word: str
    probability: float


@dataclass(frozen=True)
class RecommendationView:
    guess: str
    strategy: str
    score: float
    explanation: str
    expected_remaining: float
    worst_case: float
    p_solve_now: float
    candidates_before: int
    branch: str
    elapsed_ms: float

    @classmethod
    def from_decision(cls, decision: Decision) -> "RecommendationView":
        return cls(
            guess=decision.guess,
            strategy=decision.strategy,
            score=decision.score,
            explanation=decision.explanation,
            expected_remaining=decision.candidates_after_expected,
            worst_case=float(decision.breakdown.get("worst_case", float("nan"))),
            p_solve_now=decision.p_solve_now,
            candidates_before=decision.candidates_before,
            branch=str(decision.breakdown.get("branch", decision.strategy)),
            elapsed_ms=decision.elapsed_ms,
        )

    def to_dict(self) -> dict:
        return {
            "guess": self.guess,
            "strategy": self.strategy,
            "score": self.score,
            "explanation": self.explanation,
            "expected_remaining": self.expected_remaining,
            "worst_case": self.worst_case,
            "p_solve_now": self.p_solve_now,
            "candidates_before": self.candidates_before,
            "branch": self.branch,
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass(frozen=True)
class GameView:
    profile_id: str
    mode: str
    attempts_used: int
    attempts_left: int
    remaining: int
    solved: bool
    history: tuple[str, ...]
    top_candidates: tuple[CandidateView, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "mode": self.mode,
            "attempts_used": self.attempts_used,
            "attempts_left": self.attempts_left,
            "remaining": self.remaining,
            "solved": self.solved,
            "history": list(self.history),
            "top_candidates": [
                {"word": entry.word, "probability": entry.probability}
                for entry in self.top_candidates
            ],
        }


class SolverService:
    """One profile, one strategy and one rule configuration, ready to play."""

    def __init__(
        self,
        profile: Profile,
        *,
        rows: RowSource | None = None,
        strategy: str = "hybrid.balanced",
        mode: RuleMode = RuleMode.NORMAL,
        attempts: int = 6,
        prior_weights: np.ndarray | None = None,
        top_candidates: int = 8,
        policy: dict | None = None,
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts must be >= 1")
        if top_candidates < 0:
            raise ValueError("top_candidates must be >= 0")
        self.profile = profile
        self.rows = rows if rows is not None else open_rows(profile, None)
        self.mode = mode
        self.attempts = attempts
        self.prior_weights = prior_weights
        self.top_candidates = top_candidates
        self.policy = policy
        if strategy == "exact":
            if policy is None:
                raise ValueError(
                    "the exact strategy needs a policy artifact; build one with "
                    "`wordle-ai policy build`"
                )
            self.strategy: Strategy = get_strategy("exact", policy=policy)
        else:
            self.strategy = get_strategy(strategy, prior_weights=prior_weights)
        # Shared across games so self-play does not recompute the opener: the cache is
        # keyed by state and prior, so it changes no decision (Phase 4 proved that).
        self._cache: dict = {}

    # ---- states -----------------------------------------------------------
    def new_game(self) -> GameState:
        return new_game(self.profile, mode=self.mode, max_attempts=self.attempts)

    def view(self, state: GameState) -> GameView:
        top: list[CandidateView] = []
        if self.top_candidates and state.remaining > 0:
            posterior = state.posterior
            if self.prior_weights is not None:
                masked = np.where(state.candidates, self.prior_weights, 0.0)
                total = float(masked.sum())
                if total > 0:
                    posterior = masked / total
            indices = np.argsort(-posterior, kind="stable")[: self.top_candidates]
            top = [
                CandidateView(
                    word=self.profile.answers[int(index)],
                    probability=float(posterior[int(index)]),
                )
                for index in indices
                if posterior[int(index)] > 0.0
            ]
        return GameView(
            profile_id=self.profile.profile_id,
            mode=state.mode.value,
            attempts_used=state.attempts_used,
            attempts_left=state.attempts_left,
            remaining=state.remaining,
            solved=state.is_solved(),
            history=tuple(turn.guess for turn in state.history),
            top_candidates=tuple(top),
        )

    # ---- play -------------------------------------------------------------
    def recommend(self, state: GameState) -> RecommendationView:
        if state.attempts_left <= 0:
            raise ValueError("no attempts remain; the game is over")
        return RecommendationView.from_decision(
            self.strategy.choose(state, self.rows, cache=self._cache)
        )

    def apply(self, state: GameState, guess: str, pattern: str | Pattern) -> GameState:
        parsed = (
            pattern
            if isinstance(pattern, Pattern)
            else Pattern.parse(pattern, self.profile.alphabet)
        )
        return state.apply(guess, parsed, table=self.rows)

    def turns(self, history: Sequence[Turn]) -> GameState:
        state = self.new_game()
        for turn in history:
            state = state.apply(turn.guess, turn.pattern, table=self.rows)
        return state

    def play(self, answer: str) -> tuple[list[dict], bool]:
        """Play one answer with the selected strategy; return (turns, solved).

        Every turn is a plain dict so the CLI can print it or emit it as JSON without a
        second rendering path.
        """

        state = self.new_game()
        turn_rows: list[dict] = []
        while state.attempts_left > 0:
            view = self.view(state)
            recommendation = self.recommend(state)
            pattern = self._feedback(recommendation.guess, answer)
            solved = recommendation.guess == answer
            turn_rows.append(
                {
                    "turn": state.attempts_used + 1,
                    "recommendation": recommendation.to_dict(),
                    "guess": recommendation.guess,
                    "pattern": pattern.render(),
                    "solved": solved,
                    "remaining_before": view.remaining,
                    "remaining_after": 1 if solved else None,
                    "explanation": recommendation.explanation,
                }
            )
            if solved:
                return turn_rows, True
            state = state.apply(recommendation.guess, pattern, table=self.rows)
            turn_rows[-1]["remaining_after"] = state.remaining
        return turn_rows, False

    # ---- internals --------------------------------------------------------
    def _feedback(self, guess: str, answer: str) -> Pattern:
        if answer not in self.profile.answer_index:
            raise ValueError(f"{answer!r} is not an answer of {self.profile.profile_id}")
        code = int(self.rows.row(guess)[self.profile.answer_index[answer]])
        return Pattern(code=code, length=self.profile.length)


@dataclass(frozen=True)
class StrategyComparison:
    """One strategy's choice on one state, with the numbers behind it."""

    strategy: str
    objective: str
    guess: str
    score: float
    expected_remaining: float
    worst_case: float
    p_solve_now: float
    branch: str
    elapsed_ms: float
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "objective": self.objective,
            "guess": self.guess,
            "score": self.score,
            "expected_remaining": self.expected_remaining,
            "worst_case": self.worst_case,
            "p_solve_now": self.p_solve_now,
            "branch": self.branch,
            "elapsed_ms": self.elapsed_ms,
            "explanation": self.explanation,
        }


def compare_strategies(
    service: "SolverService",
    state: GameState,
    strategies: Sequence[str] | None = None,
) -> dict:
    """Strategy Laboratory: every requested strategy on the same state (§7).

    Grouping is by chosen guess, so "who disagrees with whom" is a list of groups with
    their members and numbers, not a hand-waved count. The strategies are independent
    instances; none of them writes to the service's play cache.
    """

    names = list(strategies) if strategies else list(HEURISTIC_STRATEGY_NAMES)
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise ValueError(f"strategy {name!r} was named twice")
        seen.add(name)
    picks: list[StrategyComparison] = []
    for name in names:
        try:
            if name == "exact":
                pol = getattr(service, "policy", None)
                if pol is None and isinstance(service.strategy, ExactStrategy):
                    pol = service.strategy.policy
                if pol is None:
                    from pathlib import Path
                    default_p = Path("policies") / f"{service.profile.profile_id}.normal.uniform.policy.json"
                    if default_p.exists():
                        try:
                            from ..solver.policy import load_policy
                            pol = load_policy(default_p, profile=service.profile, verify=False)
                        except Exception:
                            pol = None
                if pol is None:
                    raise ValueError("exact strategy requires policy artifact")
                strategy = get_strategy("exact", policy=pol)
            else:
                strategy = get_strategy(name, prior_weights=service.prior_weights)

            try:
                decision = strategy.choose(state, service.rows)
                view = RecommendationView.from_decision(decision)
                explanation = view.explanation
            except ArtifactMismatchError:
                # State departed the exact DP policy tree; fall back to balanced hybrid
                fallback = get_strategy("hybrid.balanced", prior_weights=service.prior_weights)
                decision = fallback.choose(state, service.rows)
                view = RecommendationView.from_decision(decision)
                explanation = f"[Fallback: DP tree departed] {view.explanation}"

            picks.append(
                StrategyComparison(
                    strategy=name,
                    objective=str(getattr(strategy, "objective", "")),
                    guess=view.guess,
                    score=view.score,
                    expected_remaining=view.expected_remaining,
                    worst_case=view.worst_case,
                    p_solve_now=view.p_solve_now,
                    branch=view.branch,
                    elapsed_ms=view.elapsed_ms,
                    explanation=explanation,
                )
            )
        except Exception:
            # Continue so one unsupported strategy doesn't crash the entire arena
            continue
    groups: dict[str, list[StrategyComparison]] = {}
    for pick in picks:
        groups.setdefault(pick.guess, []).append(pick)
    results = [pick.to_dict() for pick in sorted(picks, key=lambda p: p.expected_remaining)]
    return {
        "state": service.view(state).to_dict(),
        "results": results,
        "rows": results,
        "distinct_guesses": sorted(groups),
        "groups": [
            {
                "guess": guess,
                "strategies": [pick.strategy for pick in members],
                "expected_remaining": members[0].expected_remaining,
                "worst_case": members[0].worst_case,
            }
            for guess, members in sorted(groups.items(), key=lambda item: -len(item[1]))
        ],
        "pairwise_disagreements": sum(
            1
            for index, left in enumerate(picks)
            for right in picks[index + 1 :]
            if left.guess != right.guess
        ),
    }


def dictionary_report(profile: Profile, word: str) -> dict:
    """Dictionary Laboratory: why a word is, or is not, in this profile (§7).

    The answer is decided by the same invariants ``Profile`` enforces on construction:
    length, alphabet, membership in the guess list, then membership in the answers. It
    never guesses at an external dictionary or suggests a "closest" word, because the
    question is about *this* profile's lists.
    """

    raw = (word or "").strip()
    normalised = raw.casefold()
    in_guesses = normalised in profile.guess_index
    in_answers = normalised in profile.answer_index
    if not normalised:
        reason = "empty"
        explanation = "An empty string has no characters to look up."
    elif len(normalised) != profile.length:
        reason = "wrong_length"
        explanation = (
            f"'{normalised}' has {len(normalised)} characters; {profile.profile_id} "
            f"words have {profile.length}."
        )
    else:
        outside = sorted({character for character in normalised if character not in profile.alphabet})
        if outside:
            reason = "out_of_alphabet"
            explanation = (
                f"'{normalised}' contains characters outside the profile alphabet: "
                f"{', '.join(outside)}."
            )
        elif not in_guesses:
            reason = "not_in_guesses"
            explanation = (
                f"'{normalised}' is not in the guess list of {profile.profile_id} "
                f"({len(profile.guesses):,} words), so it cannot be played."
            )
        elif not in_answers:
            reason = "not_an_answer"
            explanation = (
                f"'{normalised}' is a legal guess but is not one of the "
                f"{len(profile.answers):,} answers of {profile.profile_id}."
            )
        else:
            reason = "answer"
            explanation = (
                f"'{normalised}' is one of the {len(profile.answers):,} answers of "
                f"{profile.profile_id}."
            )
    return {
        "profile_id": profile.profile_id,
        "word": raw,
        "normalised": normalised,
        "length": profile.length,
        "alphabet": profile.alphabet,
        "answers": len(profile.answers),
        "guesses": len(profile.guesses),
        "in_guesses": in_guesses,
        "in_answers": in_answers,
        "valid_guess": in_guesses,
        "reason": reason,
        "explanation": explanation,
    }


def build_service(
    profile: Profile,
    *,
    strategy: str = "hybrid.balanced",
    mode: RuleMode = RuleMode.NORMAL,
    attempts: int = 6,
    table_path=None,
    prior_weights: np.ndarray | None = None,
) -> SolverService:
    """Convenience constructor for callers that only know the profile."""

    rows: RowSource = (
        open_rows(profile, table_path) if table_path is not None else ComputedRows(profile)
    )
    return SolverService(
        profile,
        rows=rows,
        strategy=strategy,
        mode=mode,
        attempts=attempts,
        prior_weights=prior_weights,
    )


__all__ = [
    "CandidateView",
    "GameView",
    "RecommendationView",
    "SolverService",
    "StrategyComparison",
    "build_service",
    "compare_strategies",
    "dictionary_report",
]
