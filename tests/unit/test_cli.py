"""CLI contracts: JSON shapes, exit codes and error payloads (§12.1, §15).

Every test runs against a throwaway data directory built by the session fixture, so the
suite neither skips when the shipped artifacts are absent nor depends on their state.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wordle_ai.cli.main import app
from wordle_ai.lexicon.build import build, request_from_config

REPO_ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner()


def invoke(*args: str):
    return runner.invoke(app, list(args))


def payload(result) -> dict:
    return json.loads(result.stdout)


@pytest.fixture(scope="session")
def cli_root(settings, tmp_path_factory):
    """A temporary data root containing one open profile and the classic profile."""

    root = tmp_path_factory.mktemp("cli-data")
    processed = root / "processed"
    build(request_from_config("strict.en.5", settings, processed_dir=processed, table_policy="none"))
    build(request_from_config("classic.en.5", settings, processed_dir=processed, table_policy="auto"))
    return root


def test_version():
    result = invoke("version")
    assert result.exit_code == 0
    body = payload(result)
    assert body["manifest_schema_version"] == 1
    assert body["version"] == "0.1.0"
    assert body["build"]["python"]
    assert body["build"]["dependencies"]["numpy"]


def test_config_validate():
    result = invoke("config", "validate")
    assert result.exit_code == 0
    assert "valid" in result.stdout


def test_config_show_is_json():
    result = invoke("config", "show", "--json")
    assert result.exit_code == 0
    data = payload(result)
    assert data["profile"]["length"] == 5
    assert data["feedback"]["table_max_bytes"] == 268_435_456


def test_build_dry_run_writes_nothing(tmp_path):
    result = invoke("lex", "build", "--profile", "strict.en.3", "--dry-run", "--json")
    assert result.exit_code == 0
    data = payload(result)
    assert data["dry_run"] is True
    assert data["profiles"][0]["profile_id"] == "strict.en.3"


def test_invalid_profile_length_exits_2():
    result = invoke("lex", "build", "--profile", "strict.en.6", "--json")
    assert result.exit_code == 2
    assert payload(result)["code"] == "unsupported_profile"


def test_unknown_family_exits_1():
    result = invoke("lex", "build", "--profile", "unknown.en.5", "--json")
    assert result.exit_code == 1
    assert payload(result)["error"] == "ConfigError"


def test_missing_profile_exits_3():
    result = invoke("lex", "inspect", "--profile", "strict.en.5", "--json", "--data-dir", "no-such-dir")
    assert result.exit_code == 3
    assert payload(result)["code"] == "profile_integrity"


def test_user_fetch_requires_attestation():
    result = invoke(
        "lex",
        "fetch",
        "--source",
        "user",
        "--answers",
        "data/raw/wordle-word-bank.csv",
        "--guesses",
        "data/raw/wordle-valid-words.csv",
        "--json",
    )
    assert result.exit_code == 3
    assert "attest" in payload(result)["message"]


def test_inspect_built_profile(cli_root):
    result = invoke("lex", "inspect", "--profile", "classic.en.5", "--json", "--data-dir", str(cli_root))
    assert result.exit_code == 0
    data = payload(result)
    assert data["counts"]["answers"] == 2315
    assert data["counts"]["guesses"] == 12972
    assert data["policy"]["answer_policy"] == "file"


def test_verify_all_profiles(cli_root):
    result = invoke("lex", "verify", "--all", "--json", "--data-dir", str(cli_root))
    assert result.exit_code == 0, result.stdout
    data = payload(result)
    assert data["ok"] is True
    assert data["profiles"]["strict.en.5"]["ok"] is True
    assert data["profiles"]["classic.en.5"]["ok"] is True
    assert all(source["verified"] for source in data["sources"])


def test_config_unknown_key_exits_1(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("[general]\ndata_dir = 'data'\nnope = 1\n", encoding="utf-8")
    result = invoke("config", "validate", "--config", str(bad), "--json")
    assert result.exit_code == 1
    assert payload(result)["code"] == "invalid_configuration"


def test_policy_build_and_verify_key_on_the_answer_set(cli_root, tmp_path):
    out = tmp_path / "subset.policy.json"
    built = invoke(
        "policy", "build", "--profile", "strict.en.5", "--limit", "4",
        "--attempts", "4", "--out", str(out), "--data-dir", str(cli_root), "--json",
    )
    assert built.exit_code == 0, built.stdout + (built.stderr or "")
    summary = payload(built)
    assert summary["answer_set_size"] == 4
    assert summary["path"] == str(out)

    verified = invoke(
        "policy", "verify", "--path", str(out), "--profile", "strict.en.5",
        "--limit", "4", "--attempts", "4", "--data-dir", str(cli_root), "--json",
    )
    assert verified.exit_code == 0, verified.stdout + (verified.stderr or "")

    full = invoke(
        "policy", "verify", "--path", str(out), "--profile", "strict.en.5",
        "--attempts", "4", "--data-dir", str(cli_root), "--json",
    )
    assert full.exit_code == 5
    assert payload(full)["code"] == "artifact_mismatch"
