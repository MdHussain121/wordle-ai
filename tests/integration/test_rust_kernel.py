"""Integration tests for the Rust DP kernel parity harness and policy serialization."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import check_rust_kernel
from wordle_ai.cli.main import app
from wordle_ai.engine.table import ComputedRows
from wordle_ai.lexicon.profile import load_profile
from wordle_ai.solver.policy import policy_digest


@pytest.mark.skipif(
    not (Path("rust/wordle_core/target/release/wordle_core.exe").exists() or shutil.which("cargo")),
    reason="Rust toolchain or binary unavailable",
)
def test_rust_kernel_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the parity check for strict.en.1 and strict.en.3 12-answer subset inside pytest."""
    monkeypatch.setattr(sys, "argv", ["check_rust_kernel.py", "--verbose"])
    assert check_rust_kernel.main() == 0


@pytest.mark.skipif(
    not (Path("rust/wordle_core/target/release/wordle_core.exe").exists() or shutil.which("cargo")),
    reason="Rust toolchain or binary unavailable",
)
def test_rust_generated_policy_verification_and_play(tmp_path: Path) -> None:
    """Verify Rust-generated policy artifact and play it with the CLI."""
    binary_path, _ = check_rust_kernel.resolve_or_build_binary(REPO_ROOT)
    data_dir = REPO_ROOT / "data"
    profile = load_profile(data_dir / "processed" / "strict.en.3")

    ans_file = tmp_path / "answers.txt"
    gue_file = tmp_path / "guesses.txt"
    tab_file = tmp_path / "table.raw"
    out_file = tmp_path / "result.json"
    out_policy = tmp_path / "rust_strict3_12.policy.json"
    out_sidecar = tmp_path / "rust_strict3_12.policy.json.sha256"

    selected_answers = profile.answers[:12]
    selected_guesses = profile.guesses
    ans_file.write_text("\n".join(selected_answers) + "\n", encoding="utf-8")
    gue_file.write_text("\n".join(selected_guesses) + "\n", encoding="utf-8")

    rows = ComputedRows(profile)
    matrix = np.asarray(rows.matrix(), dtype=np.uint8)
    guess_indices = [profile.guess_index[g] for g in selected_guesses]
    ans_indices = [profile.answer_index[a] for a in selected_answers]
    table_slice = matrix[np.ix_(guess_indices, ans_indices)]
    tab_file.write_bytes(np.ascontiguousarray(table_slice, dtype=np.uint8).tobytes())

    cmd = [
        str(binary_path),
        "--table",
        str(tab_file),
        "--answers",
        str(ans_file),
        "--guesses",
        str(gue_file),
        "--attempts",
        "6",
        "--profile-id",
        "strict.en.3",
        "--profile-sha256",
        profile.manifest_sha256,
        "--policy-out",
        str(out_policy),
        "--out",
        str(out_file),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert out_policy.exists()
    assert out_sidecar.exists()

    payload = json.loads(out_policy.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert abs(payload["expected_guesses"] - 2.583333333333333) < 1e-6
    assert payload["max_guesses"] == 4
    assert payload["nodes"] == 2044
    sidecar_hash = out_sidecar.read_text(encoding="utf-8").strip()
    assert payload["sha256"] == sidecar_hash
    assert payload["sha256"] == policy_digest(payload)

    runner = CliRunner()
    res_verify = runner.invoke(
        app,
        ["policy", "verify", "--path", str(out_policy), "--limit", "12"],
    )
    assert res_verify.exit_code == 0, res_verify.output
    assert "ok:" in res_verify.output

    res_bench = runner.invoke(
        app,
        [
            "bench",
            "run",
            "--profile",
            "strict.en.3",
            "--strategies",
            "exact",
            "--policy",
            str(out_policy),
            "--limit",
            "12",
            "--no-store",
        ],
    )
    assert res_bench.exit_code == 0, res_bench.output
    assert "2.5833" in res_bench.output
    assert "100.00" in res_bench.output
