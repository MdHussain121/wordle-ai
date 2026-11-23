"""Phase 7 acceptance surfaces: labs, copy check, HTTP adapter and interactive play."""

from __future__ import annotations

import json
import shutil

import pytest
from typer.testing import CliRunner

from wordle_ai.api.copy import banned_terms_in
from wordle_ai.api.service import (
    SolverService,
    compare_strategies,
    dictionary_report,
)
from wordle_ai.cli.main import app
from wordle_ai.engine.table import ComputedRows, open_rows
from wordle_ai.lexicon.profile import TABLE_NAME
from wordle_ai.types import Pattern, Turn


@pytest.fixture()
def service(strict_profiles):
    profile = strict_profiles["strict.en.2"]
    return SolverService(profile, rows=ComputedRows(profile), strategy="entropy")


def test_strategy_lab_groups_picks_with_numbers(service):
    report = compare_strategies(
        service,
        service.new_game(),
        ["entropy", "expected_remaining", "minimax", "first_candidate"],
    )
    assert len(report["results"]) == 4
    assert sum(len(group["strategies"]) for group in report["groups"]) == 4
    assert set(report["distinct_guesses"]) == {entry["guess"] for entry in report["results"]}
    assert all("expected_remaining" in entry for entry in report["results"])
    assert report["pairwise_disagreements"] >= 0


def test_strategy_lab_rejects_duplicate_names(service):
    with pytest.raises(ValueError):
        compare_strategies(service, service.new_game(), ["entropy", "entropy"])


def test_dictionary_lab_explains_every_case(strict_profiles):
    profile = strict_profiles["strict.en.2"]
    assert dictionary_report(profile, "")["reason"] == "empty"
    assert dictionary_report(profile, "a")["reason"] == "wrong_length"
    assert dictionary_report(profile, "a!")["reason"] == "out_of_alphabet"
    assert dictionary_report(profile, "zz")["reason"] in {
        "not_in_guesses",
        "not_an_answer",
    }
    assert dictionary_report(profile, profile.answers[0])["reason"] == "answer"
    guess_only = [word for word in profile.guesses if word not in profile.answer_index]
    if guess_only:
        report = dictionary_report(profile, guess_only[0])
        assert report["reason"] == "not_an_answer"
        assert report["in_guesses"] is True and report["in_answers"] is False


def test_default_copy_has_no_ml_terminology(service):
    state = service.new_game()
    recommendation = service.recommend(state)
    rendered = " ".join(
        [
            json.dumps(service.view(state).to_dict()),
            json.dumps(recommendation.to_dict()),
            recommendation.explanation,
        ]
    )
    assert banned_terms_in(rendered) == []


def _profile_copy(profile_dir, tmp_path):
    shutil.copytree(profile_dir("strict.en.2"), tmp_path / "processed" / "strict.en.2")
    return tmp_path


def test_cli_play_copy_and_selfplay_copy_are_plain(strict_profiles, profile_dir, tmp_path):
    profile = strict_profiles["strict.en.2"]
    root = _profile_copy(profile_dir, tmp_path)
    play = CliRunner().invoke(
        app,
        [
            "play",
            "--profile",
            "strict.en.2",
            "--answer",
            profile.answers[1],
            "--data-dir",
            str(root),
            "--strategy",
            "entropy",
        ],
    )
    assert play.exit_code == 0, play.output
    assert banned_terms_in(play.output) == []
    selfplay = CliRunner().invoke(
        app,
        [
            "selfplay",
            "--profile",
            "strict.en.2",
            "--games",
            "2",
            "--data-dir",
            str(root),
            "--strategy",
            "entropy",
        ],
    )
    assert selfplay.exit_code == 0, selfplay.output
    assert banned_terms_in(selfplay.output) == []


def test_cli_labs_run(strict_profiles, profile_dir, tmp_path):
    root = _profile_copy(profile_dir, tmp_path)
    lab = CliRunner().invoke(
        app,
        [
            "lab",
            "strategies",
            "--profile",
            "strict.en.2",
            "--data-dir",
            str(root),
            "--strategies",
            "entropy,expected_remaining,first_candidate",
        ],
    )
    assert lab.exit_code == 0, lab.output
    assert "distinct guesses" in lab.output
    assert banned_terms_in(lab.output) == []

    dictionary = CliRunner().invoke(
        app,
        [
            "lab",
            "dictionary",
            "zz",
            "--profile",
            "strict.en.2",
            "--data-dir",
            str(root),
        ],
    )
    assert dictionary.exit_code == 0, dictionary.output
    assert "legal guesses" in dictionary.output
    assert banned_terms_in(dictionary.output) == []


def test_http_adapter_matches_the_service(strict_profiles):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from wordle_ai.api.http import create_app

    profile = strict_profiles["strict.en.2"]
    service = SolverService(profile, rows=ComputedRows(profile), strategy="entropy")
    client = TestClient(create_app(service))

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["profile_id"] == profile.profile_id

    direct_state = service.new_game()
    direct = service.recommend(direct_state).guess
    response = client.post("/recommend", json={"history": []})
    assert response.status_code == 200
    assert response.json()["recommendation"]["guess"] == direct

    turns, solved = service.play(profile.answers[1])
    assert solved
    history = [{"guess": turn["guess"], "feedback": turn["pattern"]} for turn in turns[:-1]]
    direct_state = service.turns(
        [
            Turn(guess=entry["guess"], pattern=Pattern.parse(entry["feedback"]))
            for entry in history
        ]
    )
    direct_again = service.recommend(direct_state).guess
    via_http = client.post("/recommend", json={"history": history})
    assert via_http.status_code == 200
    assert via_http.json()["recommendation"]["guess"] == direct_again

    compare = client.post(
        "/compare",
        json={"history": [], "strategies": ["entropy", "expected_remaining"]},
    )
    assert compare.status_code == 200
    assert len(compare.json()["results"]) == 2

    dictionary = client.post("/dictionary", json={"word": profile.answers[0]})
    assert dictionary.status_code == 200
    assert dictionary.json()["reason"] == "answer"

    bad = client.post(
        "/recommend", json={"history": [{"guess": profile.answers[0], "feedback": "XY"}]}
    )
    assert bad.status_code == 400


def test_interactive_prompt_loop_end_to_end(strict_profiles, profile_dir, tmp_path):
    """Drive the real prompt loop with piped stdin; it must finish solved."""

    profile = strict_profiles["strict.en.2"]
    root = _profile_copy(profile_dir, tmp_path)
    service = SolverService(profile, rows=ComputedRows(profile), strategy="entropy")
    turns, solved = service.play(profile.answers[1])
    assert solved
    stdin = "".join(f"{turn['guess']}\n{turn['pattern']}\n" for turn in turns)
    result = CliRunner().invoke(
        app,
        [
            "play",
            "--profile",
            "strict.en.2",
            "--data-dir",
            str(root),
            "--strategy",
            "entropy",
        ],
        input=stdin,
    )
    assert result.exit_code == 0, result.output
    assert "possible answers" in result.output
    assert "solved" in result.output
    assert banned_terms_in(result.output) == []


def test_classic_opener_has_three_way_disagreement(classic_profile, profile_dir):
    """Criterion 3 on a real state: at least three different guesses, with numbers."""

    rows = open_rows(classic_profile, profile_dir("classic.en.5", "auto") / TABLE_NAME)
    service = SolverService(
        classic_profile,
        rows=rows,
        strategy="entropy",
        top_candidates=0,
    )
    report = compare_strategies(
        service,
        service.new_game(),
        [
            "entropy",
            "entropy_candidates",
            "expected_remaining",
            "expected_remaining_candidates",
            "minimax",
            "minimax_candidates",
            "letter_frequency",
            "positional_frequency",
        ],
    )
    assert len(report["distinct_guesses"]) >= 3
    assert all(entry["expected_remaining"] >= 1.0 for entry in report["results"])
