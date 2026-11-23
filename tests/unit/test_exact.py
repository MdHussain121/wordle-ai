"""Exact solver correctness: DP value, policy round-trip, gate and tamper checks."""

from __future__ import annotations

import json
from collections import defaultdict

import numpy as np
import pytest

from wordle_ai.engine.table import ComputedRows
from wordle_ai.errors import ArtifactMismatchError, UnsupportedProfile
from wordle_ai.solver.dp import ExactSolver
from wordle_ai.solver.policy import (
    build_artifact,
    feasibility,
    load_policy,
    policy_digest,
    save_policy,
)
from wordle_ai.strategy import HEURISTIC_STRATEGY_NAMES, STRATEGY_NAMES, get_strategy
from wordle_ai.strategy.exact import ExactStrategy
from wordle_ai.types import Profile, RuleMode

INF = float("inf")


def toy_profile() -> Profile:
    words = ("aa", "ab", "ba", "bb")
    return Profile(
        profile_id="toy.en.2",
        language="en",
        dialect=None,
        length=2,
        alphabet="ab",
        answers=words,
        guesses=words,
        manifest_sha256="0" * 64,
        answer_index={word: i for i, word in enumerate(words)},
        guess_index={word: i for i, word in enumerate(words)},
    )


def brute_force_value(profile: Profile, matrix: np.ndarray, mask: frozenset[int], k: int) -> float:
    """Independent, unmemoised enumeration of the optimal expected guesses."""

    if len(mask) == 1:
        return 1.0
    if k == 1:
        return INF
    best = INF
    for guess_index in range(len(profile.guesses)):
        buckets: dict[int, list[int]] = defaultdict(list)
        for answer_index in mask:
            buckets[int(matrix[guess_index, answer_index])].append(answer_index)
        if len(buckets) == 1:
            continue
        total = 0.0
        feasible = True
        guess_word = profile.guesses[guess_index]
        for code, members in buckets.items():
            if len(members) == 1 and profile.answers[members[0]] == guess_word:
                # This guess solves that answer; no further guess is charged.
                continue
            value = brute_force_value(profile, matrix, frozenset(members), k - 1)
            if not np.isfinite(value):
                feasible = False
                break
            total += len(members) * value
        if feasible:
            best = min(best, 1.0 + total / len(mask))
    return best


def test_solver_value_equals_brute_force_enumeration() -> None:
    profile = toy_profile()
    rows = ComputedRows(profile)
    solver = ExactSolver(profile, rows, max_attempts=3)
    solution = solver.solve()
    expected = brute_force_value(
        profile, np.asarray(rows.matrix()), frozenset(range(len(profile.answers))), 3
    )
    assert solution.value == pytest.approx(expected, abs=1e-12)
    assert solution.max_guesses <= 3
    assert solution.policy["guess"] in profile.guesses


def test_solver_is_deterministic() -> None:
    profile = toy_profile()
    rows = ComputedRows(profile)
    first = ExactSolver(profile, rows, max_attempts=4).solve()
    second = ExactSolver(profile, rows, max_attempts=4).solve()
    assert first.value == second.value
    assert json.dumps(first.policy, sort_keys=True) == json.dumps(second.policy, sort_keys=True)


def test_solver_returns_infinite_when_attempts_too_few() -> None:
    from wordle_ai.errors import BudgetExceeded

    profile = toy_profile()
    solver = ExactSolver(profile, ComputedRows(profile), max_attempts=1)
    with pytest.raises(BudgetExceeded):
        solver.solve()


def test_solver_refuses_hard_mode() -> None:
    profile = toy_profile()
    with pytest.raises(UnsupportedProfile):
        ExactSolver(profile, ComputedRows(profile), mode=RuleMode.HARD)


def test_policy_round_trip_and_tamper_detection(tmp_path) -> None:
    profile = toy_profile()
    solution = ExactSolver(profile, ComputedRows(profile), max_attempts=4).solve()
    payload = build_artifact(
        solution, profile, mode=RuleMode.NORMAL, prior="uniform", attempts=4
    )
    path = tmp_path / "toy.policy.json"
    save_policy(path, solution, profile, attempts=4)
    loaded = load_policy(path, profile=profile, mode=RuleMode.NORMAL, attempts=4)
    assert loaded["expected_guesses"] == payload["expected_guesses"]

    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["expected_guesses"] = 1.0
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ArtifactMismatchError):
        load_policy(path)

    # Repair the payload checksum but leave the sidecar stale: still refused.
    tampered["sha256"] = policy_digest(tampered)
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ArtifactMismatchError):
        load_policy(path)


def test_policy_refuses_foreign_profile(tmp_path) -> None:
    profile = toy_profile()
    solution = ExactSolver(profile, ComputedRows(profile), max_attempts=4).solve()
    path = tmp_path / "toy.policy.json"
    save_policy(path, solution, profile, attempts=4)
    answers = ("aa", "ab")
    other = Profile(
        profile_id="toy.en.2b",
        language="en",
        dialect=None,
        length=2,
        alphabet="ab",
        answers=answers,
        guesses=profile.guesses,
        manifest_sha256="1" * 64,
        answer_index={word: i for i, word in enumerate(answers)},
        guess_index={word: i for i, word in enumerate(profile.guesses)},
    )
    with pytest.raises(ArtifactMismatchError):
        load_policy(path, profile=other)


def test_policy_built_for_a_subset_refuses_the_full_profile(tmp_path) -> None:
    full = toy_profile()
    answers = ("aa", "ab")
    subset = Profile(
        profile_id=full.profile_id,
        language=full.language,
        dialect=None,
        length=full.length,
        alphabet=full.alphabet,
        answers=answers,
        guesses=full.guesses,
        manifest_sha256=full.manifest_sha256,
        answer_index={word: i for i, word in enumerate(answers)},
        guess_index=dict(full.guess_index),
    )
    solution = ExactSolver(subset, ComputedRows(subset), max_attempts=3).solve()
    path = tmp_path / "subset.policy.json"
    save_policy(path, solution, subset, attempts=3)
    load_policy(path, profile=subset, attempts=3)
    with pytest.raises(ArtifactMismatchError):
        load_policy(path, profile=full, attempts=3)


def test_exact_strategy_plays_the_policy_tree() -> None:
    from wordle_ai.engine.state import new_game
    from wordle_ai.sim.runner import play_game

    profile = toy_profile()
    rows = ComputedRows(profile)
    solution = ExactSolver(profile, rows, max_attempts=4).solve()
    payload = build_artifact(
        solution, profile, mode=RuleMode.NORMAL, prior="uniform", attempts=4
    )
    strategy = ExactStrategy(payload)
    assert strategy.choose(new_game(profile), rows).guess == solution.root_guess
    for answer in profile.answers:
        record = play_game(profile, strategy, answer, rows=rows, max_attempts=4)
        assert record.solved
        assert record.turns <= solution.max_guesses


def test_exact_strategy_requires_a_policy_and_a_uniform_prior() -> None:
    from wordle_ai.engine.state import new_game

    profile = toy_profile()
    rows = ComputedRows(profile)
    with pytest.raises(ArtifactMismatchError):
        ExactStrategy().choose(new_game(profile), rows)

    solution = ExactSolver(profile, rows, max_attempts=4).solve()
    payload = build_artifact(
        solution, profile, mode=RuleMode.NORMAL, prior="uniform", attempts=4
    )
    prior = np.ones(len(profile.answers)) / len(profile.answers)
    with pytest.raises(ArtifactMismatchError):
        ExactStrategy(payload).choose(new_game(profile), rows, prior=prior)


def test_feasibility_gate_reports_the_reason() -> None:
    profile = toy_profile()
    ok, reason = feasibility(profile, max_answers=4, max_guesses=4)
    assert ok and reason is None
    ok, reason = feasibility(profile, max_answers=3, max_guesses=4)
    assert not ok and "max_answers" in reason
    ok, reason = feasibility(profile, max_answers=4, max_guesses=3)
    assert not ok and "max_guesses" in reason


def test_exact_is_registered_but_not_in_the_default_bench_set() -> None:
    assert "exact" in STRATEGY_NAMES
    assert "exact" not in HEURISTIC_STRATEGY_NAMES
    strategy = get_strategy("exact")
    assert strategy.name == "exact"
