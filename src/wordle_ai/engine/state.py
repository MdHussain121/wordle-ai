"""Game state, replay and invariants (§3.4, §4.3).

``candidates`` is authoritative; the posterior is derived from it. A state is always
rebuilt by replaying history, so a persisted state cannot disagree with its own turns.

Hard and superhard legality is derived from the history in ``engine.constraints``;
this module stores the mode and validates guess membership, length and alphabet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

from ..errors import InconsistentFeedback, ProfileIntegrityError
from ..types import Pattern, PriorKind, Profile, RuleMode, Turn
from .feedback import feedback_row
from .filter import filter_mask
from .table import FeedbackTable


@dataclass
class GameState:
    profile: Profile
    mode: RuleMode = RuleMode.NORMAL
    max_attempts: int = 6
    prior_kind: PriorKind = PriorKind.UNIFORM
    prior_params: dict[str, float] = field(default_factory=dict)
    history: list[Turn] = field(default_factory=list)
    candidates: np.ndarray = field(default=None)  # type: ignore[assignment]
    prior_weights: np.ndarray | None = field(default=None, repr=False)
    _posterior: np.ndarray | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ProfileIntegrityError("max_attempts must be >= 1")
        if self.candidates is None:
            self.candidates = np.ones(len(self.profile.answers), dtype=bool)
        self.candidates = np.asarray(self.candidates, dtype=bool)
        if self.prior_weights is not None:
            self.prior_weights = np.asarray(self.prior_weights, dtype=np.float64)
        self._check_invariants()

    # ---- invariants -------------------------------------------------------
    def _check_invariants(self) -> None:
        if self.candidates.shape != (len(self.profile.answers),):
            raise ProfileIntegrityError(
                f"candidate mask shape {self.candidates.shape} does not match "
                f"{len(self.profile.answers)} answers"
            )
        if not bool(self.candidates.any()):
            raise InconsistentFeedback("candidate set is empty")
        if self.prior_weights is not None:
            if self.prior_weights.shape != self.candidates.shape:
                raise ProfileIntegrityError(
                    f"prior weight shape {self.prior_weights.shape} does not match "
                    f"{self.candidates.shape} answers"
                )
            if np.any(self.prior_weights < 0) or not np.all(np.isfinite(self.prior_weights)):
                raise ProfileIntegrityError("prior weights must be finite and non-negative")
        if len(self.history) > self.max_attempts:
            raise ProfileIntegrityError("history is longer than the attempt limit")
        if self.is_solved():
            last = self.history[-1]
            if last.guess not in self.profile.answer_index:
                raise ProfileIntegrityError("solved state's last guess is not an answer")
            if self.profile.answers[int(np.flatnonzero(self.candidates)[0])] != last.guess:
                raise ProfileIntegrityError("solved state's candidate is not the last guess")

    # ---- derived properties ----------------------------------------------
    @property
    def attempts_used(self) -> int:
        return len(self.history)

    @property
    def remaining(self) -> int:
        return int(np.count_nonzero(self.candidates))

    @property
    def attempts_left(self) -> int:
        return self.max_attempts - self.attempts_used

    @property
    def candidate_words(self) -> list[str]:
        return [self.profile.answers[i] for i in np.flatnonzero(self.candidates)]

    @property
    def posterior(self) -> np.ndarray:
        """Posterior over the candidate set under the configured prior.

        Uniform when ``prior_weights`` is ``None``; otherwise the prior reweighted by
        the surviving candidates. The contract is sums to 1 over candidates and zero
        elsewhere, and a prior with no mass on the candidates is an error rather than
        a zero vector.
        """

        if self._posterior is None or self._posterior.shape != self.candidates.shape:
            weights = self.candidates.astype(np.float64)
            if self.prior_weights is not None:
                weights = weights * self.prior_weights
            total = float(weights.sum())
            if total <= 0:
                raise InconsistentFeedback(
                    "cannot normalise a candidate set with no prior mass"
                )
            self._posterior = weights / total
            if abs(float(self._posterior.sum()) - 1.0) > 1e-9:  # pragma: no cover
                raise InconsistentFeedback("posterior does not sum to 1")
        return self._posterior

    def is_solved(self) -> bool:
        return bool(self.history) and self.remaining == 1 and self.history[-1].guess == self.candidate_words[0]

    # ---- transitions ------------------------------------------------------
    def apply(self, guess: str, pattern: Pattern, table: FeedbackTable | None = None) -> "GameState":
        """Apply one (guess, feedback) pair, returning a new state."""

        word = self.profile.validate_guess(guess)
        self.profile.validate_pattern(pattern)
        if self.attempts_used >= self.max_attempts:
            raise ProfileIntegrityError("no attempts remain")
        if table is not None:
            row = table.row(word)
        else:
            row = feedback_row(word, self.profile.answers, self.profile.alphabet)
        new_mask = filter_mask(self.candidates, row, pattern.code)
        return GameState(
            profile=self.profile,
            mode=self.mode,
            max_attempts=self.max_attempts,
            prior_kind=self.prior_kind,
            prior_params=dict(self.prior_params),
            history=[*self.history, Turn(guess=word, pattern=pattern)],
            candidates=new_mask,
            prior_weights=self.prior_weights,
        )

    def replay(
        self,
        history: Sequence[Turn],
        table: FeedbackTable | None = None,
    ) -> "GameState":
        state = GameState(
            profile=self.profile,
            mode=self.mode,
            max_attempts=self.max_attempts,
            prior_kind=self.prior_kind,
            prior_params=dict(self.prior_params),
            prior_weights=self.prior_weights,
        )
        for turn in history:
            state = state.apply(turn.guess, turn.pattern, table=table)
        return state


def new_game(
    profile: Profile,
    *,
    mode: RuleMode = RuleMode.NORMAL,
    max_attempts: int = 6,
    prior_kind: PriorKind = PriorKind.UNIFORM,
    prior_params: dict[str, float] | None = None,
    prior_weights: np.ndarray | None = None,
) -> GameState:
    return GameState(
        profile=profile,
        mode=mode,
        max_attempts=max_attempts,
        prior_kind=prior_kind,
        prior_params=dict(prior_params or {}),
        prior_weights=prior_weights,
    )


def replay(
    profile: Profile,
    history: Iterable[Turn],
    *,
    mode: RuleMode = RuleMode.NORMAL,
    max_attempts: int = 6,
    table: FeedbackTable | None = None,
) -> GameState:
    return GameState(profile=profile, mode=mode, max_attempts=max_attempts).replay(
        list(history), table=table
    )
