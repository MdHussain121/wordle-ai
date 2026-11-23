"""Serial evaluation harness: play every answer in a profile (§9, Phase 2).

The harness is deliberately thin and honest: it records the full guess sequence and the
candidate count around every turn, it never drops a failed game from the denominator,
and it reads feedback either from the shipped table or from the reference two-pass
function (the two paths must agree).

Nothing here samples. A run is exhaustive over the answers it is given; when a caller
passes a subset, the run is labelled with that subset's size and the answer names, so
a partial run cannot be mistaken for a full one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..engine.constraints import derive_constraint, is_legal
from ..engine.feedback import feedback_code
from ..engine.state import new_game
from ..engine.table import RowSource, open_rows
from ..errors import ModeViolationError, ProfileIntegrityError
from ..strategy.base import Decision, Strategy
from ..types import Pattern, Profile, RuleMode


@dataclass(frozen=True)
class GameRecord:
    """One game: the guesses, the outcome and the candidate counts around each turn."""

    answer: str
    guesses: tuple[str, ...]
    solved: bool
    decision_ms: tuple[float, ...] = ()
    candidates_before: tuple[int, ...] = ()
    candidates_after: tuple[int, ...] = ()
    mode_violation: str | None = None
    answer_eliminated: bool = False

    @property
    def turns(self) -> int:
        return len(self.guesses)

    @property
    def opener(self) -> str:
        return self.guesses[0] if self.guesses else ""

    @property
    def elapsed_ms(self) -> float:
        return float(sum(self.decision_ms))

    @property
    def final_candidates(self) -> int:
        return self.candidates_after[-1] if self.candidates_after else 0


def _pattern_from(
    rows: RowSource,
    profile: Profile,
    guess: str,
    answer: str,
    answer_index: int,
    feedback_source: str,
) -> Pattern:
    if feedback_source == "table":
        code = int(rows.row(guess)[answer_index])
    elif feedback_source == "reference":
        code = feedback_code(guess, answer)
    else:  # pragma: no cover - guarded by the CLI
        raise ValueError(f"unknown feedback source {feedback_source!r}")
    return Pattern(code=code, length=profile.length)


def play_game(
    profile: Profile,
    strategy: Strategy,
    answer: str,
    *,
    rows: RowSource | None = None,
    mode: RuleMode = RuleMode.NORMAL,
    max_attempts: int = 6,
    cache: dict | None = None,
    feedback_source: str = "table",
    strict_legality: bool = True,
) -> GameRecord:
    """Play one game to completion (or to failure) and return its record.

    ``strict_legality`` decides what happens when a strategy recommends a guess that
    contradicts the feedback already given. Strict (the default, and what the tests
    use) raises. A benchmark may pass ``False`` to *count* the violation in the record
    and stop that game instead, so §4.3's ``mode_violation_count`` is measured rather
    than assumed to be zero.
    """

    if answer not in profile.answer_index:
        raise ProfileIntegrityError(f"{answer!r} is not an answer of {profile.profile_id}")
    source = rows if rows is not None else open_rows(profile, None)
    answer_index = profile.answer_index[answer]
    state = new_game(profile, mode=mode, max_attempts=max_attempts)
    guesses: list[str] = []
    decision_ms: list[float] = []
    before: list[int] = []
    after: list[int] = []
    eliminated = False

    def record(solved: bool, violation: str | None = None) -> GameRecord:
        return GameRecord(
            answer=answer,
            guesses=tuple(guesses),
            solved=solved,
            decision_ms=tuple(decision_ms),
            candidates_before=tuple(before),
            candidates_after=tuple(after),
            mode_violation=violation,
            answer_eliminated=eliminated,
        )

    for turn in range(1, max_attempts + 1):
        decision: Decision = strategy.choose(state, source, cache=cache)
        decision_ms.append(decision.elapsed_ms)
        if state.mode is not RuleMode.NORMAL:
            constraint = derive_constraint(profile.length, state.history)
            if not is_legal(
                decision.guess,
                profile_guesses=profile.guess_index,
                constraint=constraint,
                mode=state.mode,
                candidates=set(state.candidate_words),
            ):
                if strict_legality:
                    raise ModeViolationError(
                        f"{strategy.name} recommended {decision.guess!r} which contradicts "
                        f"{mode.value} feedback after {state.attempts_used} turn(s) "
                        f"on answer {answer!r}",
                        guess=decision.guess,
                        history=[f"{t.guess}:{t.pattern.render()}" for t in state.history],
                    )
                guesses.append(decision.guess)
                before.append(state.remaining)
                after.append(state.remaining)
                return record(False, violation=decision.guess)

        guesses.append(decision.guess)
        before.append(state.remaining)
        if decision.guess == answer:
            after.append(1)
            return record(True)
        if turn == max_attempts:
            after.append(state.remaining)
            break
        pattern = _pattern_from(source, profile, decision.guess, answer, answer_index, feedback_source)
        state = state.apply(decision.guess, pattern)
        after.append(state.remaining)
        if not bool(state.candidates[answer_index]):
            eliminated = True

    return record(False)


def run_profile(
    profile: Profile,
    strategy: Strategy,
    *,
    rows: RowSource | None = None,
    mode: RuleMode = RuleMode.NORMAL,
    max_attempts: int = 6,
    answers: Sequence[str] | None = None,
    feedback_source: str = "table",
    strict_legality: bool = True,
    progress: bool = False,
) -> tuple[list[GameRecord], float]:
    """Play every requested answer and return (records, wall-clock seconds).

    The decision cache is per run and keyed by the candidate mask and attempts left,
    so identical game states reached by different answers share one computation. It
    changes no decision; it only avoids recomputing the same partition statistics.
    """

    source = rows if rows is not None else open_rows(profile, None)
    selected = list(profile.answers if answers is None else answers)
    cache: dict = {}
    started = time.perf_counter()
    records: list[GameRecord] = []
    for position, answer in enumerate(selected, 1):
        records.append(
            play_game(
                profile,
                strategy,
                answer,
                rows=source,
                mode=mode,
                max_attempts=max_attempts,
                cache=cache,
                feedback_source=feedback_source,
                strict_legality=strict_legality,
            )
        )
        if progress and position % 500 == 0:  # pragma: no cover - CLI only
            elapsed = time.perf_counter() - started
            print(f"  {position}/{len(selected)} games in {elapsed:.1f}s", flush=True)
    return records, time.perf_counter() - started
