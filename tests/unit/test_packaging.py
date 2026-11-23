"""Phase 8 packaging surfaces: version metadata, gates and budget arithmetic."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from wordle_ai.bench.budgets import evaluate

REPO = Path(__file__).resolve().parents[2]
RUNNER = CliRunner()


def _invoke(*args: str):
    return RUNNER.invoke(__import__("wordle_ai.cli.main", fromlist=["app"]).app, list(args))


def test_version_command_reports_build_metadata():
    result = _invoke("version")
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["version"] == "0.1.0"
    assert body["manifest_schema_version"] == 1
    build = body["build"]
    assert build["name"] == "wordle-ai"
    assert build["python"].startswith("3.")
    assert "numpy" in build["dependencies"]


def test_version_flag_prints_a_line_and_exits():
    result = _invoke("--version")
    assert result.exit_code == 0, result.output
    assert "wordle-ai" in result.output
    assert "python" in result.output
    assert "numpy" in result.output


def test_cli_reference_is_current():
    completed = subprocess.run(
        [sys.executable, "tools/build_cli_reference.py", "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_hardcoded_code_search_gate_is_clean():
    completed = subprocess.run(
        [sys.executable, "tools/check_hardcoded.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "findings: 0" in completed.stdout


def test_budget_evaluation_marks_met_missed_and_not_applicable():
    assert evaluate("decision_full", 0.2)["status"] == "met"
    assert evaluate("decision_full", 0.3)["status"] == "missed"
    assert evaluate("lookahead_two_ply", None)["status"] == "not_applicable"
    assert evaluate("exact_lookup", 0.0005)["status"] == "met"
