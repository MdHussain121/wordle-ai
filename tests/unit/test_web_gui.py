"""Unit and integration tests for Web GUI and HTTP API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from wordle_ai.api.http import create_app
from wordle_ai.api.service import SolverService
from wordle_ai.engine.table import ComputedRows


@pytest.fixture()
def client(strict_profiles):
    profile = strict_profiles["strict.en.2"]
    service = SolverService(profile, rows=ComputedRows(profile), strategy="entropy")
    app = create_app(service)
    return TestClient(app)


def test_web_gui_index_serves_html(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Wordle AI" in res.text
    assert "Strategy Arena" in res.text

    app_res = client.get("/app")
    assert app_res.status_code == 200
    assert "text/html" in app_res.headers["content-type"]


def test_api_recommend_endpoints(client):
    # Initial state
    res = client.post("/api/recommend", json={"history": []})
    assert res.status_code == 200
    data = res.json()
    assert data["solved"] is False
    assert "recommendation" in data
    assert "guess" in data["recommendation"]
    assert "explanation" in data["recommendation"]
    assert "top_candidates" in data["state"]

    # With a specific strategy
    res_strat = client.post("/api/recommend", json={"history": [], "strategy": "first_candidate"})
    assert res_strat.status_code == 200
    assert res_strat.json()["recommendation"]["strategy"] == "first_candidate"


def test_api_compare_endpoint(client):
    res = client.post(
        "/api/compare",
        json={
            "history": [],
            "strategies": ["entropy", "expected_remaining", "first_candidate"],
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "results" in data
    assert "rows" in data
    assert len(data["rows"]) == 3
    assert all("explanation" in r for r in data["rows"])


def test_api_random_word_endpoint(client, strict_profiles):
    res = client.get("/api/random-word")
    assert res.status_code == 200
    data = res.json()
    assert "word" in data
    profile = strict_profiles["strict.en.2"]
    assert data["word"] in profile.answers


def test_api_dictionary_endpoint(client, strict_profiles):
    profile = strict_profiles["strict.en.2"]
    valid_answer = profile.answers[0]
    res = client.post("/api/dictionary", json={"word": valid_answer})
    assert res.status_code == 200
    data = res.json()
    assert data["is_answer"] is True
    assert data["is_guess"] is True
    assert "explanation" in data

    res_invalid = client.post("/api/dictionary", json={"word": "xyzzy"})
    assert res_invalid.status_code == 200
    data_inv = res_invalid.json()
    assert data_inv["is_answer"] is False


def test_api_simulate_endpoint(client, strict_profiles):
    profile = strict_profiles["strict.en.2"]
    target = profile.answers[0]

    res = client.post("/api/simulate", json={"answer": target, "strategy": "entropy"})
    assert res.status_code == 200
    data = res.json()
    assert data["solved"] is True
    assert data["answer"] == target
    assert len(data["turns"]) >= 1
    first_turn = data["turns"][0]
    assert "turn" in first_turn
    assert "guess" in first_turn
    assert "pattern" in first_turn
    assert "remaining_before" in first_turn
    assert "remaining_after" in first_turn
    assert "explanation" in first_turn


def test_api_ml_summary_endpoint(client):
    res = client.get("/api/ml/summary")
    assert res.status_code == 200
    data = res.json()
    assert "profile_id" in data
    assert "gate_reports" in data
    assert "models_present" in data
