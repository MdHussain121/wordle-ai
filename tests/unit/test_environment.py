"""Environment contract (§9): reset, step, reward, legality, determinism."""

from __future__ import annotations

import pytest

from wordle_ai.engine.constraints import derive_constraint, is_legal
from wordle_ai.errors import InvalidGuess, ProfileIntegrityError
from wordle_ai.sim import Environment, shards
from wordle_ai.types import RuleMode


def test_reset_samples_from_the_seeded_rng(strict_profiles):
    profile = strict_profiles["strict.en.3"]
    first_env = Environment(profile, seed=11)
    second_env = Environment(profile, seed=11)
    first = first_env.reset()
    second_env.reset()
    assert first.remaining == len(profile.answers)
    assert first.attempts_left == 6
    assert first_env.answer == second_env.answer
    assert first_env.answer in profile.answers


def test_solving_a_game_ends_it_with_the_spec_reward(strict_profiles):
    profile = strict_profiles["strict.en.3"]
    answer = profile.answers[0]
    env = Environment(profile, seed=1)
    env.reset(answer=answer)
    result = env.step(answer)
    assert result.done is True
    assert result.info["solved"] is True
    assert result.observation.remaining == 1
    assert result.reward == pytest.approx(0.0)  # -1 for the guess, +1 for the solve
    with pytest.raises(ProfileIntegrityError, match="game is over"):
        env.step(answer)


def test_step_before_reset_is_refused(strict_profiles):
    env = Environment(strict_profiles["strict.en.3"])
    with pytest.raises(ProfileIntegrityError, match="reset"):
        env.step("aaa")


def test_unknown_guess_is_refused_not_coerced(strict_profiles):
    profile = strict_profiles["strict.en.3"]
    env = Environment(profile)
    env.reset(answer=profile.answers[0])
    with pytest.raises(InvalidGuess):
        env.step("zzz")


def test_hard_mode_rejects_a_guess_that_contradicts_feedback(strict_profiles):
    profile = strict_profiles["strict.en.2"]
    for first in profile.guesses:
        env = Environment(profile, mode=RuleMode.HARD, seed=5)
        env.reset()
        if env.step(first).done:  # an instant solve gives no history to contradict
            continue
        constraint = derive_constraint(profile.length, env.observation().history)
        illegal = next(
            (
                word
                for word in profile.guesses
                if not is_legal(
                    word,
                    profile_guesses=profile.guess_index,
                    constraint=constraint,
                    mode=RuleMode.HARD,
                )
            ),
            None,
        )
        if illegal is not None:
            with pytest.raises(InvalidGuess, match="contradicts"):
                env.step(illegal)
            return
    pytest.fail("no hard-mode guess in strict.en.2 contradicts one turn of feedback")


def test_legal_actions_mask_matches_the_mode(strict_profiles):
    profile = strict_profiles["strict.en.3"]
    env = Environment(profile)
    env.reset(answer=profile.answers[0])
    assert env.legal_actions().all()


def test_shards_cover_every_answer_once():
    answers = [f"w{index}" for index in range(10)]
    for workers in (1, 2, 3, 4, 16):
        chunks = shards(answers, workers)
        assert [item for chunk in chunks for item in chunk] == answers
        assert len(chunks) <= max(1, workers)
    assert shards([], 4) == []
