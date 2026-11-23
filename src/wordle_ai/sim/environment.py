"""A gym-style environment for one Wordle game (technical specification §9).

No gym dependency: the interface is the four calls the specification fixes —
``reset``, ``step``, ``legal_actions`` and an observation type — so a future RL
appendix or a rollout strategy can drive the game without importing the harness.

Reward is ``-1`` per guess plus ``1`` on a solve and ``0`` on failure. Benchmarks
count guesses, never reward, so shaping cannot contaminate a reported average.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..engine.constraints import constraint_for, legal_mask
from ..engine.feedback import feedback_pattern
from ..engine.state import GameState, new_game
from ..engine.table import RowSource, open_rows
from ..errors import InvalidGuess, ProfileIntegrityError
from ..types import Pattern, Profile, RuleMode, Turn


@dataclass(frozen=True)
class Observation:
    """What a policy may see: the candidate mask and the game's progress."""

    candidates: np.ndarray = field(repr=False)
    remaining: int
    attempts_left: int
    solved: bool
    history: tuple[Turn, ...] = ()


@dataclass(frozen=True)
class StepResult:
    observation: Observation
    reward: float
    done: bool
    info: dict


class Environment:
    """One game: reset with a secret answer, then step guesses until it ends."""

    def __init__(
        self,
        profile: Profile,
        *,
        rows: RowSource | None = None,
        mode: RuleMode = RuleMode.NORMAL,
        max_attempts: int = 6,
        seed: int | None = None,
    ) -> None:
        self.profile = profile
        self.mode = mode
        self.max_attempts = max_attempts
        self.rows = rows if rows is not None else open_rows(profile, None)
        self._rng = np.random.default_rng(seed)
        self._state: GameState | None = None
        self._answer: str | None = None
        self._done = True

    # ---- public API -------------------------------------------------------
    def reset(self, answer: str | None = None, seed: int | None = None) -> Observation:
        """Start a game. ``answer=None`` samples uniformly with the seeded RNG."""

        if seed is not None:
            self._rng = np.random.default_rng(seed)
        if answer is None:
            answer = self.profile.answers[int(self._rng.integers(len(self.profile.answers)))]
        self._answer = self.profile.validate_guess(answer)
        self._state = new_game(self.profile, mode=self.mode, max_attempts=self.max_attempts)
        self._done = False
        return self._observe()

    def step(self, guess: str) -> StepResult:
        if self._state is None or self._answer is None:
            raise ProfileIntegrityError("call reset() before step()")
        if self._done:
            raise ProfileIntegrityError("the game is over; call reset() to play again")
        word = self.profile.validate_guess(guess)
        state = self._state
        if state.mode is not RuleMode.NORMAL:
            constraint = constraint_for(state)
            candidates = set(state.candidate_words) if state.mode is RuleMode.SUPERHARD else None
            mask = legal_mask(
                [word], constraint=constraint, mode=state.mode, candidates=candidates
            )
            if not bool(mask[0]):
                raise InvalidGuess(
                    f"{word!r} contradicts the {state.mode.value} feedback already given",
                    reason="unknown_word",
                )
        pattern = self._feedback(word)
        state = state.apply(word, pattern)
        self._state = state
        solved = word == self._answer
        turns_left = self.max_attempts - state.attempts_used
        self._done = solved or turns_left <= 0
        observation = self._observe()
        # -1 per guess, +1 on a solve, so a solve in n turns totals 1 - n.
        reward = -1.0 + (1.0 if solved else 0.0)
        return StepResult(
            observation=observation,
            reward=reward,
            done=self._done,
            info={
                "guess": word,
                "pattern": pattern.render(),
                "solved": solved,
                "remaining": observation.remaining,
            },
        )

    def legal_actions(self) -> np.ndarray:
        """Boolean mask over ``profile.guesses`` of the guesses the mode allows now."""

        if self._state is None:
            raise ProfileIntegrityError("call reset() before legal_actions()")
        return legal_mask(
            self.profile.guesses,
            constraint=constraint_for(self._state),
            mode=self._state.mode,
            candidates=set(self._state.candidate_words)
            if self._state.mode is RuleMode.SUPERHARD
            else None,
        )

    @property
    def answer(self) -> str | None:
        """The secret answer; ``None`` before the first reset. Not part of an observation."""

        return self._answer

    def observation(self) -> Observation:
        if self._state is None:
            raise ProfileIntegrityError("call reset() before observation()")
        return self._observe()

    # ---- internals --------------------------------------------------------
    def _feedback(self, guess: str) -> Pattern:
        assert self._answer is not None
        if self.rows is not None:
            code = int(self.rows.row(guess)[self.profile.answer_index[self._answer]])
            return Pattern(code=code, length=self.profile.length)
        return feedback_pattern(guess, self._answer)

    def _observe(self) -> Observation:
        assert self._state is not None
        state = self._state
        return Observation(
            candidates=state.candidates.copy(),
            remaining=state.remaining,
            attempts_left=state.attempts_left,
            solved=state.is_solved(),
            history=tuple(state.history),
        )
