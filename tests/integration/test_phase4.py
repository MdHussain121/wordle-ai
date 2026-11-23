"""Phase 4 end to end: worker invariance, reports, CSV round-trip, refusals, exact runs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wordle_ai.bench.report import aggregates_from_csv, parse_csv
from wordle_ai.bench.runner import RunSpec, prepare
from wordle_ai.cli.main import app
from wordle_ai.lexicon.build import build, request_from_config

runner = CliRunner()


@pytest.fixture(scope="session")
def phase4_root(settings, tmp_path_factory):
    """A throwaway data root with two open profiles and no shipped artifacts."""

    root = tmp_path_factory.mktemp("phase4-data")
    processed = root / "processed"
    for profile_id in ("strict.en.2", "strict.en.3"):
        build(request_from_config(profile_id, settings, processed_dir=processed, table_policy="none"))
    return root


def invoke(*args: str):
    return runner.invoke(app, list(args))


def bench_args(root: Path, *extra: str) -> list[str]:
    return ["bench", *extra, "--data-dir", str(root)]


def run_bench(root: Path, *extra: str):
    result = invoke(*bench_args(root, "run", *extra, "--json"))
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    return json.loads(result.stdout)


def test_bench_run_reports_and_persists(phase4_root):
    payload = run_bench(
        phase4_root,
        "--profile", "strict.en.3",
        "--strategies", "entropy",
        "--limit", "8",
    )
    run = payload["runs"][0]
    assert run["answers"] == 8
    assert run["exhaustive"] is False
    assert run["answer_set_id"].startswith("strict.en.3.first8.")
    assert run["run_key"] and run["determinism_sha256"]
    assert sum(run["distribution"].values()) == run["solved"]
    assert 0.0 <= run["candidate_reduction_geomean"] <= 1.0
    assert run["information_gain_bits"] > 0.0
    assert run["invalid_guess_count"] == 0
    assert run["pct_solved_in_k"]["6"] == pytest.approx(run["success_rate"])
    assert payload["provenance"]["exhaustive"] is False
    assert payload["provenance"]["cpu_count"] >= 1

    report = invoke(
        *bench_args(
            phase4_root, "report", "--run", run["run_key"][:12], "--format", "markdown"
        )
    )
    assert report.exit_code == 0, report.stdout
    text = report.stdout
    assert "## Provenance" in text
    assert "## Failures" in text
    assert "exhaustive" in text and "sampled" in text
    assert "first8" in text
    assert run["strategy"] in text


def test_csv_export_regenerates_the_aggregates(phase4_root, tmp_path):
    payload = run_bench(
        phase4_root,
        "--profile", "strict.en.3",
        "--strategies", "entropy,minimax",
        "--limit", "6",
    )
    run = payload["runs"][0]
    out = tmp_path / "games.csv"
    exported = invoke(
        *bench_args(
            phase4_root,
            "report",
            "--run",
            run["run_key"][:12],
            "--format",
            "csv",
            "--out",
            str(out),
        )
    )
    assert exported.exit_code == 0, exported.stdout
    rows = parse_csv(out.read_text(encoding="utf-8"))
    aggregates = aggregates_from_csv(rows, max_attempts=run["max_attempts"])
    measured = aggregates[run["run_key"]]
    assert measured["answers"] == run["answers"]
    assert measured["solved"] == run["solved"]
    assert measured["worst_case"] == run["worst_case"]
    assert measured["avg_guesses_solved"] == pytest.approx(run["avg_guesses_solved"])
    assert measured["avg_guesses_all"] == pytest.approx(run["avg_guesses_all"])
    assert measured["openers"]


def test_worker_count_does_not_change_the_determinism_hash(phase4_root):
    serial = run_bench(
        phase4_root,
        "--profile", "strict.en.3",
        "--strategies", "entropy",
        "--limit", "10",
        "--workers", "1",
    )
    parallel = run_bench(
        phase4_root,
        "--profile", "strict.en.3",
        "--strategies", "entropy",
        "--limit", "10",
        "--workers", "4",
    )
    first = serial["runs"][0]
    second = parallel["runs"][0]
    assert first["run_key"] == second["run_key"]
    assert first["determinism_sha256"] == second["determinism_sha256"]
    assert first["distribution"] == second["distribution"]

    compared = invoke(
        *bench_args(
            phase4_root,
            "compare",
            "--run", first["run_key"][:12],
            "--other", second["run_key"][:12],
            "--check-determinism",
            "--json",
        )
    )
    assert compared.exit_code == 0, compared.stdout
    summary = json.loads(compared.stdout)
    assert summary["comparison"]["determinism_match"] is True
    assert summary["comparison"]["bootstrap"]["mean_difference"] == pytest.approx(0.0)


def test_compare_refuses_incomparable_runs(phase4_root):
    first = run_bench(
        phase4_root,
        "--profile", "strict.en.3",
        "--strategies", "entropy",
        "--limit", "5",
    )["runs"][0]
    second = run_bench(
        phase4_root,
        "--profile", "strict.en.3",
        "--strategies", "entropy",
        "--limit", "6",
    )["runs"][0]
    refused = invoke(
        *bench_args(
            phase4_root,
            "compare",
            "--run", first["run_key"][:12],
            "--other", second["run_key"][:12],
            "--json",
        )
    )
    assert refused.exit_code == 1
    assert json.loads(refused.stdout)["code"] == "incomparable_runs"

    allowed = invoke(
        *bench_args(
            phase4_root,
            "compare",
            "--run", first["run_key"][:12],
            "--other", second["run_key"][:12],
            "--allow-mismatch",
            "--json",
        )
    )
    assert allowed.exit_code == 0, allowed.stdout
    assert json.loads(allowed.stdout)["comparison"]["informal"] is True


def test_induced_failures_are_reported_with_both_averages(phase4_root):
    payload = run_bench(
        phase4_root,
        "--profile", "strict.en.3",
        "--strategies", "entropy",
        "--limit", "12",
        "--max-attempts", "2",
    )
    run = payload["runs"][0]
    assert run["failed"] > 0
    assert run["success_rate"] < 1.0
    if run["avg_guesses_solved"] is not None:
        assert run["avg_guesses_all"] > run["avg_guesses_solved"]

    report = invoke(
        *bench_args(phase4_root, "report", "--run", run["run_key"][:12], "--format", "markdown")
    )
    assert report.exit_code == 0
    assert "unsolved" in report.stdout
    assert f"{run['failed']} unsolved" in report.stdout


def test_exact_policy_runs_end_to_end_on_its_answer_subset(phase4_root, tmp_path):
    policy = tmp_path / "subset.policy.json"
    built = invoke(
        "policy",
        "build",
        "--profile", "strict.en.3",
        "--limit", "4",
        "--out", str(policy),
        "--data-dir", str(phase4_root),
        "--json",
    )
    assert built.exit_code == 0, built.stdout + (built.stderr or "")
    expected = json.loads(built.stdout)["expected_guesses"]

    payload = run_bench(
        phase4_root,
        "--profile", "strict.en.3",
        "--strategies", "exact",
        "--limit", "4",
        "--policy", str(policy),
    )
    run = payload["runs"][0]
    assert run["answers"] == 4
    assert run["exhaustive"] is True
    assert run["solved"] == 4
    assert run["avg_guesses_solved"] == pytest.approx(expected, abs=1e-9)
    assert run["total_guesses"] == round(expected * 4)
    assert run["mode_violation_count"] == 0
    assert payload["comparisons"] == []  # nothing published for a 4-answer subset


def test_prepare_treats_a_subset_policy_as_its_own_universe(phase4_root, tmp_path):
    policy = tmp_path / "subset.policy.json"
    built = invoke(
        "policy",
        "build",
        "--profile", "strict.en.3",
        "--limit", "3",
        "--attempts", "6",
        "--out", str(policy),
        "--data-dir", str(phase4_root),
        "--json",
    )
    assert built.exit_code == 0, built.stdout + (built.stderr or "")
    profile_dir = phase4_root / "processed" / "strict.en.3"

    subset = prepare(
        RunSpec(
            profile_id="strict.en.3",
            profile_dir=profile_dir,
            strategy="exact",
            attempts=6,
            answers=None,
            policy_path=policy,
        )
    )
    assert subset.subset_size == 3
    assert len(subset.universe.answers) == 3
    assert subset.exhaustive is True

    heuristic = prepare(
        RunSpec(
            profile_id="strict.en.3",
            profile_dir=profile_dir,
            strategy="entropy",
            attempts=6,
            answers=None,
        )
    )
    assert heuristic.subset_size is None
    assert heuristic.universe.profile_id == "strict.en.3"
    assert len(heuristic.answers) == 588
    assert subset.run_key != heuristic.run_key
