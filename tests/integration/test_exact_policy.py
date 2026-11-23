"""End-to-end exact solving on a real profile.

The full ``strict.en.3`` profile (588 answers) is not tractable in the test budget with
this pure-Python kernel, so the check runs on the first 12 of its answers, using the
profile's full 588-word guess list. The DP value is compared with the average guesses
the serialised policy actually takes over those answers.
"""

from __future__ import annotations

import numpy as np

from wordle_ai.engine.table import ComputedRows
from wordle_ai.sim.runner import run_profile
from wordle_ai.solver.dp import ExactSolver
from wordle_ai.solver.policy import build_artifact
from wordle_ai.strategy.exact import ExactStrategy
from wordle_ai.types import Profile, RuleMode

SUBSET = 12
ATTEMPTS = 4


def _subset_profile(profile: Profile, size: int) -> Profile:
    answers = profile.answers[:size]
    return Profile(
        profile_id=profile.profile_id,
        language=profile.language,
        dialect=profile.dialect,
        length=profile.length,
        alphabet=profile.alphabet,
        answers=answers,
        guesses=profile.guesses,
        manifest_sha256=profile.manifest_sha256,
        source_ids=profile.source_ids,
        answer_index={word: i for i, word in enumerate(answers)},
        guess_index=dict(profile.guess_index),
    )


def test_exact_policy_value_equals_measured_average(strict_profiles) -> None:
    profile: Profile = _subset_profile(strict_profiles["strict.en.3"], SUBSET)
    rows = ComputedRows(profile)
    solution = ExactSolver(profile, rows, max_attempts=ATTEMPTS).solve()
    assert 2.0 <= solution.value < ATTEMPTS
    assert solution.max_guesses <= ATTEMPTS

    payload = build_artifact(
        solution,
        profile,
        mode=RuleMode.NORMAL,
        prior="uniform",
        attempts=ATTEMPTS,
    )
    records, _ = run_profile(
        profile,
        ExactStrategy(payload),
        rows=rows,
        max_attempts=ATTEMPTS,
    )
    assert len(records) == SUBSET
    assert all(record.solved for record in records)
    measured = float(np.mean([record.turns for record in records]))
    assert abs(measured - solution.value) < 1e-9
    assert max(record.turns for record in records) == solution.max_guesses
