"""End-to-end harness: arithmetic, reproducibility, hard-mode legality, CLI (§9)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from wordle_ai.bench.metrics import summarise
from wordle_ai.cli.main import app
from wordle_ai.lexicon.build import build, request_from_config
from wordle_ai.engine.constraints import derive_constraint, is_legal
from wordle_ai.engine.feedback import feedback_pattern
from wordle_ai.engine.state import new_game
from wordle_ai.engine.table import ComputedRows, open_rows
from wordle_ai.lexicon.profile import TABLE_NAME
from wordle_ai.sim.runner import play_game, run_profile
from wordle_ai.strategy import get_strategy
from wordle_ai.types import RuleMode, Turn

runner = CliRunner()


@pytest.fixture(scope="session")
def classic_rows(classic_profile, profile_dir):
    path = profile_dir("classic.en.5", table="auto") / TABLE_NAME
    return open_rows(classic_profile, path)


@pytest.fixture(scope="session")
def bench_root(settings, tmp_path_factory):
    """A throwaway data root with one open profile, so the CLI test needs no shipped state."""

    root = tmp_path_factory.mktemp("bench-data")
    build(
        request_from_config(
            "strict.en.2", settings, processed_dir=root / "processed", table_policy="none"
        )
    )
    return root


def summarised(records, profile, elapsed, strategy, mode=RuleMode.NORMAL, max_attempts=6):
    return summarise(
        records,
        profile_id=profile.profile_id,
        profile_manifest_sha256=profile.manifest_sha256,
        strategy=strategy.name,
        objective=strategy.objective,
        mode=mode,
        max_attempts=max_attempts,
        total_s=elapsed,
    )


def test_histogram_and_average_arithmetic(strict_profiles):
    profile = strict_profiles["strict.en.2"]
    strategy = get_strategy("entropy")
    answers = list(profile.answers[:20])
    records, elapsed = run_profile(profile, strategy, answers=answers)
    result = summarised(records, profile, elapsed, strategy)

    assert result.answers == 20
    assert sum(result.distribution.values()) == result.solved
    assert result.solved + result.failed == result.answers
    solved_turns = [record.turns for record in records if record.solved]
    if solved_turns:
        assert result.avg_guesses_solved == pytest.approx(sum(solved_turns) / len(solved_turns))
        assert result.worst_case == max(solved_turns)
    charged = sum(solved_turns) + result.failed * 7
    assert result.avg_guesses_all == pytest.approx(charged / 20)
    assert result.failure_rate == pytest.approx(result.failed / 20)


def test_repeated_runs_are_identical(strict_profiles):
    profile = strict_profiles["strict.en.2"]
    strategy = get_strategy("minimax")
    answers = list(profile.answers[:25])
    first, elapsed_first = run_profile(profile, strategy, answers=answers)
    second, elapsed_second = run_profile(profile, strategy, answers=answers)
    first_summary = summarised(first, profile, elapsed_first, strategy)
    second_summary = summarised(second, profile, elapsed_second, strategy)
    assert [record.guesses for record in first] == [record.guesses for record in second]
    assert first_summary.determinism_sha256 == second_summary.determinism_sha256
    assert first_summary.distribution == second_summary.distribution


def test_table_and_reference_feedback_produce_the_same_games(classic_profile, classic_rows):
    strategy = get_strategy("entropy")
    answers = list(classic_profile.answers[:40])
    with_table, elapsed_table = run_profile(
        classic_profile, strategy, rows=classic_rows, answers=answers, feedback_source="table"
    )
    with_reference, elapsed_reference = run_profile(
        classic_profile,
        strategy,
        rows=ComputedRows(classic_profile),
        answers=answers,
        feedback_source="reference",
    )
    table_summary = summarised(with_table, classic_profile, elapsed_table, strategy)
    reference_summary = summarised(with_reference, classic_profile, elapsed_reference, strategy)
    assert table_summary.determinism_sha256 == reference_summary.determinism_sha256
    assert [r.guesses for r in with_table] == [r.guesses for r in with_reference]


def test_hard_mode_never_contradicts_prior_feedback(classic_profile, classic_rows):
    strategy = get_strategy("entropy")
    answers = list(classic_profile.answers[:120])
    records, elapsed = run_profile(
        classic_profile,
        strategy,
        rows=classic_rows,
        answers=answers,
        mode=RuleMode.HARD,
    )
    assert len(records) == 120
    assert any(record.solved for record in records)
    checked = 0
    for record in records:
        history: list[Turn] = []
        for guess in record.guesses:
            constraint = derive_constraint(classic_profile.length, history)
            assert is_legal(
                guess,
                profile_guesses=classic_profile.guess_index,
                constraint=constraint,
                mode=RuleMode.HARD,
            ), f"{guess} violates hard-mode feedback in game for {record.answer}: {history}"
            if guess == record.answer:
                break
            history.append(Turn(guess=guess, pattern=feedback_pattern(guess, record.answer)))
            checked += 1
    assert checked > 200


def test_play_game_records_the_full_sequence(strict_profiles):
    profile = strict_profiles["strict.en.3"]
    rows = ComputedRows(profile)
    strategy = get_strategy("expected_remaining")
    answer = profile.answers[3]
    record = play_game(profile, strategy, answer, rows=rows)
    assert record.answer == answer
    assert record.turns == len(record.guesses)
    assert record.turns <= 6
    assert (record.guesses[-1] == answer) == record.solved


def test_cli_baseline_is_json_and_reproducible(bench_root):
    args = [
        "bench",
        "run",
        "--profile",
        "strict.en.2",
        "--strategies",
        "entropy,expected_remaining,first_candidate",
        "--limit",
        "15",
        "--data-dir",
        str(bench_root),
        "--json",
    ]
    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.stdout
    second = runner.invoke(app, args)
    assert second.exit_code == 0, second.stdout
    first_payload = json.loads(first.stdout)
    second_payload = json.loads(second.stdout)
    timing = {"total_s", "decision_p50_ms", "decision_p95_ms", "decision_max_ms"}

    def stable(payload: dict) -> list[dict]:
        return [{k: v for k, v in run.items() if k not in timing} for run in payload["runs"]]

    assert stable(first_payload) == stable(second_payload)
    assert first_payload["runs"][0]["profile_id"] == "strict.en.2"
    assert first_payload["runs"][0]["answers"] == 15
    for run in first_payload["runs"]:
        assert sum(run["distribution"].values()) == run["solved"]
        assert run["strategy"] in {"entropy", "expected_remaining", "first_candidate"}
        assert run["determinism_sha256"]


def test_cli_unknown_strategy_fails_loudly(bench_root):
    result = runner.invoke(
        app,
        [
            "bench",
            "run",
            "--profile",
            "strict.en.2",
            "--strategies",
            "nope",
            "--data-dir",
            str(bench_root),
            "--json",
        ],
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["code"] == "unknown_strategy"
