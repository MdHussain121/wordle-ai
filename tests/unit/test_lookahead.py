"""The two-ply and rollout strategies: deterministic, legal, and recorded branches."""

from __future__ import annotations

from wordle_ai.engine.state import new_game
from wordle_ai.engine.table import ComputedRows
from wordle_ai.lexicon.profile import load_profile
from wordle_ai.solver.policy import subset_profile
from wordle_ai.strategy import get_strategy


def _state(profile_dir, limit: int, profile_id: str = "strict.en.2"):
    profile = subset_profile(load_profile(profile_dir(profile_id)), limit)
    return profile, new_game(profile), ComputedRows(profile)


def test_lookahead_two_ply_is_deterministic_and_legal(profile_dir):
    profile, state, rows = _state(profile_dir, 20)
    strategy = get_strategy("lookahead.two_ply")
    first = strategy.choose(state, rows)
    second = strategy.choose(state, rows)
    assert first.guess == second.guess
    assert first.guess in profile.guess_index
    assert first.breakdown["branch"] == "lookahead_two_ply"
    assert first.candidates_after_expected >= 0


def test_rollout_random_is_seeded_and_legal(profile_dir):
    profile, state, rows = _state(profile_dir, 20)
    strategy = get_strategy("rollout.random")
    first = strategy.choose(state, rows)
    second = strategy.choose(state, rows)
    assert first.guess == second.guess
    assert first.guess in profile.guess_index
    assert first.breakdown["branch"] == "rollout_random"
    assert 1.0 <= first.score <= state.attempts_left + 1


def test_large_state_falls_back_to_one_step(profile_dir):
    profile, state, rows = _state(profile_dir, 250, "strict.en.3")
    strategy = get_strategy("lookahead.two_ply")
    decision = strategy.choose(state, rows)
    assert decision.guess in profile.guess_index
    assert decision.breakdown["branch"] == "expected_remaining"
