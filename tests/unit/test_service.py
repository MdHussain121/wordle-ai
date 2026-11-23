"""Phase 7 service layer and the `play` assistant."""

from __future__ import annotations

import shutil

import pytest
from typer.testing import CliRunner

from wordle_ai.api.service import SolverService
from wordle_ai.cli.main import app
from wordle_ai.engine.table import ComputedRows
from wordle_ai.types import RuleMode


@pytest.fixture()
def service(strict_profiles):
    profile = strict_profiles["strict.en.2"]
    return SolverService(profile, rows=ComputedRows(profile))


def test_new_game_view_and_recommendation(service):
    state = service.new_game()
    view = service.view(state)
    assert view.remaining == len(service.profile.answers)
    assert view.attempts_left == 6
    assert view.solved is False
    assert view.top_candidates and view.top_candidates[0].probability > 0

    recommendation = service.recommend(state)
    assert recommendation.guess in service.profile.guess_index
    assert recommendation.explanation
    assert recommendation.candidates_before == view.remaining
    assert 0.0 <= recommendation.p_solve_now <= 1.0


def test_apply_filters_candidates(service):
    state = service.new_game()
    guess = service.profile.answers[0]
    pattern = service.rows.row(guess)[0]
    from wordle_ai.types import Pattern

    pattern = Pattern(code=int(pattern), length=service.profile.length)
    updated = service.apply(state, guess, pattern)
    assert updated.attempts_used == 1
    assert updated.remaining <= state.remaining
    assert guess in service.view(updated).history


def test_play_solves_the_answer(service):
    answer = service.profile.answers[0]
    turns, solved = service.play(answer)
    assert solved
    assert turns[-1]["guess"] == answer
    assert len(turns) <= service.attempts
    assert all(turn["recommendation"]["explanation"] for turn in turns)


def test_attempt_limit_is_respected(service):
    limited = SolverService(
        service.profile, rows=service.rows, strategy="first_candidate", attempts=2
    )
    answer = service.profile.answers[-1]
    turns, solved = limited.play(answer)
    assert len(turns) <= 2
    assert solved in (True, False)


def test_exact_strategy_needs_a_policy(strict_profiles):
    profile = strict_profiles["strict.en.2"]
    with pytest.raises(ValueError):
        SolverService(profile, strategy="exact")


def test_cli_play_answer_mode(strict_profiles, profile_dir, tmp_path):
    profile = strict_profiles["strict.en.2"]
    source = profile_dir("strict.en.2")
    target = tmp_path / "processed" / "strict.en.2"
    shutil.copytree(source, target)
    result = CliRunner().invoke(
        app,
        [
            "play",
            "--profile",
            "strict.en.2",
            "--answer",
            profile.answers[0],
            "--data-dir",
            str(tmp_path),
            "--strategy",
            "entropy",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "solved" in result.output
    assert "candidates" in result.output


def test_cli_play_history_mode(strict_profiles, profile_dir, tmp_path):
    from wordle_ai.engine.feedback import feedback_row
    from wordle_ai.types import Pattern

    profile = strict_profiles["strict.en.2"]
    shutil.copytree(profile_dir("strict.en.2"), tmp_path / "processed" / "strict.en.2")
    guess = profile.answers[1]
    code = int(feedback_row(guess, profile.answers, profile.alphabet)[0])
    feedback = Pattern(code=code, length=profile.length).render()
    result = CliRunner().invoke(
        app,
        [
            "play",
            "--profile",
            "strict.en.2",
            "--history",
            f"{guess}:{feedback}",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "candidates remain" in result.output


def test_cli_selfplay_aggregates(strict_profiles, profile_dir, tmp_path):
    shutil.copytree(profile_dir("strict.en.2"), tmp_path / "processed" / "strict.en.2")
    result = CliRunner().invoke(
        app,
        [
            "selfplay",
            "--profile",
            "strict.en.2",
            "--games",
            "3",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "3 games" in result.output
    assert "solved" in result.output


def test_cli_play_rejects_an_unknown_answer(strict_profiles, profile_dir, tmp_path):
    shutil.copytree(profile_dir("strict.en.2"), tmp_path / "processed" / "strict.en.2")
    result = CliRunner().invoke(
        app,
        [
            "play",
            "--profile",
            "strict.en.2",
            "--answer",
            "zz",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code != 0
    assert "not an answer" in result.output
