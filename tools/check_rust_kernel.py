"""Parity check harness between Python ExactSolver and Rust wordle_core kernel.

Proves mathematical parity and measures acceleration between Python's
exact DP oracle (wordle_ai.solver.dp.ExactSolver) and the compiled Rust DP kernel
(rust/wordle_core).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

# Resolve repo root and ensure modules are importable without hardcoded paths
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from wordle_ai.engine.table import ComputedRows, FeedbackTable
from wordle_ai.lexicon.profile import TABLE_NAME, load_profile
from wordle_ai.solver.dp import ExactSolver
from wordle_ai.types import Profile


def get_hardcoded_findings_count() -> int:
    try:
        from tools.check_hardcoded import scan as scan_hardcoded

        return len(scan_hardcoded())
    except Exception:
        return 0


@dataclass(frozen=True)
class TestCase:
    name: str
    profile_id: str
    attempts: int
    subset_answers: int | None
    golden_value: float | None = None
    golden_nodes: int | None = None
    description: str = ""


CASES: list[TestCase] = [
    TestCase(
        name="strict.en.1",
        profile_id="strict.en.1",
        attempts=6,
        subset_answers=None,
        golden_value=1.5,
        golden_nodes=1,
        description="Minimal Smoke Test (2 answers, 2 guesses, 6 attempts)",
    ),
    TestCase(
        name="strict.en.3@12",
        profile_id="strict.en.3",
        attempts=6,
        subset_answers=12,
        golden_value=2.583333333333333,
        golden_nodes=2044,
        description="Phase 3 Golden Benchmark (12 answers, 588 allowable guesses, 6 attempts)",
    ),
]


@dataclass
class CaseResult:
    case_name: str
    description: str
    n_answers: int
    n_guesses: int
    attempts: int
    py_value: float
    py_nodes: int
    py_evals: int
    py_time: float
    rust_value: float
    rust_nodes: int
    rust_evals: int
    rust_time: float
    speedup: float
    value_delta: float
    parity: bool
    verdict: str


def resolve_or_build_binary(
    repo_root: Path,
    rebuild: bool = False,
    verbose: bool = False,
) -> tuple[Path, str]:
    bin_name = "wordle_core.exe" if sys.platform == "win32" else "wordle_core"
    cargo_manifest = repo_root / "rust" / "wordle_core" / "Cargo.toml"
    binary_path = repo_root / "rust" / "wordle_core" / "target" / "release" / bin_name

    build_status = "Skipped (pre-built)"
    if rebuild or not binary_path.exists():
        if verbose:
            print(f"[rust] Building {bin_name} via cargo (manifest: {cargo_manifest})...")
        cargo = shutil.which("cargo")
        if not cargo:
            raise RuntimeError(
                f"Cargo toolchain not found on PATH; cannot compile Rust binary at {binary_path}"
            )
        cmd = [cargo, "build", "--release", "--manifest-path", str(cargo_manifest)]
        res = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Cargo build failed with exit code {res.returncode}:\n{res.stderr}")
        build_status = "OK"
        if verbose:
            print(f"[rust] Cargo build completed successfully: {binary_path}")

    if not binary_path.exists():
        raise FileNotFoundError(f"Rust binary does not exist at {binary_path}")

    return binary_path, build_status


def load_case_profile(data_dir: Path, profile_id: str) -> Profile:
    profile_dir = data_dir / "processed" / profile_id
    if (profile_dir / "manifest.json").exists():
        return load_profile(profile_dir)

    # Fall back to building profile dynamically if not pre-processed
    try:
        from wordle_ai.config import load_config
        from wordle_ai.lexicon.build import build, request_from_config

        config_path = REPO_ROOT / "config" / "default.toml"
        cfg = load_config(config_path)
        req = request_from_config(
            profile_id,
            cfg,
            data_dir=data_dir,
            processed_dir=data_dir / "processed",
            table_policy="none",
        )
        return build(req)
    except Exception as exc:
        raise FileNotFoundError(
            f"Profile '{profile_id}' not found in {profile_dir} and could not be built: {exc}"
        ) from exc


def run_case(
    case: TestCase,
    data_dir: Path,
    binary_path: Path,
    verbose: bool = False,
) -> CaseResult:
    profile = load_case_profile(data_dir, case.profile_id)
    table_path = data_dir / "processed" / case.profile_id / TABLE_NAME
    rows = (
        FeedbackTable(table_path, profile)
        if table_path.exists()
        else ComputedRows(profile)
    )
    matrix = np.asarray(rows.matrix(), dtype=np.uint8)

    if case.subset_answers is not None:
        selected_answers = profile.answers[:case.subset_answers]
        mask = np.zeros(len(profile.answers), dtype=bool)
        mask[:case.subset_answers] = True
    else:
        selected_answers = profile.answers
        mask = np.ones(len(profile.answers), dtype=bool)
    selected_guesses = profile.guesses

    if verbose:
        print(f"\nEvaluating Case: {case.name} - {case.description}")
        print(
            f"  Answers: {len(selected_answers)} | "
            f"Guesses: {len(selected_guesses)} | "
            f"Attempts: {case.attempts}"
        )
        print("  [python] Running ExactSolver oracle...")

    # Run Python Oracle
    solver = ExactSolver(profile, rows, max_attempts=case.attempts, guess_set="all")
    py_start = time.perf_counter()
    py_solution = solver.solve(mask)
    py_time = time.perf_counter() - py_start

    if verbose:
        print(
            f"           Value: {py_solution.value:.6f} | "
            f"Nodes: {py_solution.nodes} | "
            f"Evaluations: {py_solution.guess_evaluations} | "
            f"Time: {py_time:.4f}s"
        )

    # Stage Rust inputs in a temporary directory
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        ans_file = tmp_path / "answers.txt"
        gue_file = tmp_path / "guesses.txt"
        tab_file = tmp_path / "table.raw"
        out_file = tmp_path / "rust_out.json"

        ans_file.write_text("\n".join(selected_answers) + "\n", encoding="utf-8")
        gue_file.write_text("\n".join(selected_guesses) + "\n", encoding="utf-8")

        # Slice matrix: [guess_idx, answer_idx]
        guess_indices = [profile.guess_index[g] for g in selected_guesses]
        ans_indices = [profile.answer_index[a] for a in selected_answers]
        table_slice = matrix[np.ix_(guess_indices, ans_indices)]
        table_bytes = np.ascontiguousarray(table_slice, dtype=np.uint8).tobytes()
        expected_len = len(selected_guesses) * len(selected_answers)
        if len(table_bytes) != expected_len:
            raise ValueError(
                f"Raw table length {len(table_bytes)} does not match expected {expected_len}"
            )
        tab_file.write_bytes(table_bytes)

        if verbose:
            print("  [rust]   Running wordle_core accelerator...")

        cmd = [
            str(binary_path),
            "--table",
            str(tab_file),
            "--answers",
            str(ans_file),
            "--guesses",
            str(gue_file),
            "--attempts",
            str(case.attempts),
            "--out",
            str(out_file),
        ]
        rust_proc = subprocess.run(cmd, capture_output=True, text=True)
        if rust_proc.returncode != 0:
            raise RuntimeError(
                f"Rust wordle_core execution failed with exit code {rust_proc.returncode}:\n{rust_proc.stderr}"
            )

        if not out_file.exists():
            raise FileNotFoundError(f"Rust output file not found: {out_file}")

        rust_data = json.loads(out_file.read_text(encoding="utf-8"))

    rust_value = float(rust_data["value"])
    rust_nodes = int(rust_data["nodes"])
    rust_evals = int(rust_data["evaluations"])
    rust_time = float(rust_data["elapsed_s"])

    if verbose:
        print(
            f"           Value: {rust_value:.6f} | "
            f"Nodes: {rust_nodes} | "
            f"Evaluations: {rust_evals} | "
            f"Time: {rust_time:.4f}s"
        )

    # Parity assertions
    value_delta = abs(py_solution.value - rust_value)
    value_match = value_delta < 1e-6
    nodes_match = py_solution.nodes == rust_nodes
    parity = value_match and nodes_match

    # Verify against golden values if specified
    if case.golden_value is not None:
        if abs(py_solution.value - case.golden_value) >= 1e-6 or abs(rust_value - case.golden_value) >= 1e-6:
            parity = False
    if case.golden_nodes is not None:
        if py_solution.nodes != case.golden_nodes or rust_nodes != case.golden_nodes:
            parity = False

    speedup = py_time / max(rust_time, 1e-6)
    verdict = "PASS" if parity else "FAIL"

    if verbose:
        print(
            f"  [check]  Value Delta: {value_delta:.6e} (< 1e-6) -> "
            f"{'PASS' if value_match else 'FAIL'}"
        )
        print(
            f"  [check]  Node Match:  Python {py_solution.nodes} == Rust {rust_nodes} -> "
            f"{'PASS' if nodes_match else 'FAIL'}"
        )
        if case.golden_value is not None:
            print(
                f"  [check]  Golden Ref:  Value {case.golden_value:.6f} | Nodes {case.golden_nodes} -> "
                f"{'MATCH' if parity else 'MISMATCH'}"
            )
        print(f"  [perf]   Speedup:     {speedup:.1f}x")

    return CaseResult(
        case_name=case.name,
        description=case.description,
        n_answers=len(selected_answers),
        n_guesses=len(selected_guesses),
        attempts=case.attempts,
        py_value=py_solution.value,
        py_nodes=py_solution.nodes,
        py_evals=py_solution.guess_evaluations,
        py_time=py_time,
        rust_value=rust_value,
        rust_nodes=rust_nodes,
        rust_evals=rust_evals,
        rust_time=rust_time,
        speedup=speedup,
        value_delta=value_delta,
        parity=parity,
        verdict=verdict,
    )


def print_summary_table(results: list[CaseResult]) -> None:
    print("\n" + "=" * 95)
    print("PARITY VERIFICATION RESULTS")
    print("=" * 95)
    header = f"{'Case':<32} {'Metric':<16} {'Python Oracle':<15} {'Rust Kernel':<15} {'Delta / Match':<18} {'Verdict':<7}"
    print(header)
    print("-" * 95)

    for r in results:
        label = f"{r.case_name} ({r.n_answers} ans / {r.n_guesses} guess)"
        # Value row
        val_delta_str = f"{r.value_delta:.6f}"
        print(
            f"{label:<32} {'Expected Value':<16} {r.py_value:<15.6f} {r.rust_value:<15.6f} {val_delta_str:<18} {r.verdict:<7}"
        )
        # Node row
        node_delta_str = "Exact (0)" if r.py_nodes == r.rust_nodes else f"{abs(r.py_nodes - r.rust_nodes)}"
        node_verdict = "PASS" if r.py_nodes == r.rust_nodes else "FAIL"
        print(
            f"{r.case_name:<32} {'Explored Nodes':<16} {r.py_nodes:<15} {r.rust_nodes:<15} {node_delta_str:<18} {node_verdict:<7}"
        )
        # Time row
        speedup_str = f"{r.speedup:.1f}x speedup"
        py_time_str = f"{r.py_time:.4f} s"
        rust_time_str = f"{r.rust_time:.4f} s"
        print(
            f"{r.case_name:<32} {'Elapsed Time':<16} {py_time_str:<15} {rust_time_str:<15} {speedup_str:<18} {'—':<7}"
        )

    print("-" * 95)
    all_passed = all(r.parity for r in results)
    if all_passed:
        print("ALL PARITY CHECKS PASSED: Bit-for-bit mathematical equivalence confirmed.")
    else:
        print("PARITY CHECKS FAILED: One or more assertions did not match.")
    print("=" * 95 + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify mathematical parity and measure acceleration between Python ExactSolver and Rust wordle_core kernel."
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Path to data directory (default: 'data')",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force cargo recompilation of the Rust kernel",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON to stdout",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Display detailed progress and execution metrics",
    )

    args = parser.parse_args(argv)

    # Resolve data directory
    data_dir = Path(args.data_dir)
    if not data_dir.is_absolute():
        data_dir = (REPO_ROOT / data_dir).resolve()

    try:
        binary_path, build_status = resolve_or_build_binary(
            REPO_ROOT,
            rebuild=args.rebuild,
            verbose=args.verbose,
        )
    except Exception as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "ERROR",
                        "error": str(exc),
                        "code": 2,
                    },
                    indent=2,
                )
            )
        else:
            print(f"Setup/Compilation Error: {exc}", file=sys.stderr)
        return 2

    if args.verbose and not args.json:
        print("=" * 80)
        print("RUST DP KERNEL PARITY HARNESS (tools/check_rust_kernel.py)")
        print("=" * 80)
        print(f"Rust Binary:  {binary_path.relative_to(REPO_ROOT)}")
        print(f"Build Status: {build_status}")
        print(f"Data Dir:     {data_dir.relative_to(REPO_ROOT) if data_dir.is_relative_to(REPO_ROOT) else data_dir}")

    results: list[CaseResult] = []
    try:
        for case in CASES:
            res = run_case(
                case=case,
                data_dir=data_dir,
                binary_path=binary_path,
                verbose=args.verbose and not args.json,
            )
            results.append(res)
    except Exception as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "ERROR",
                        "error": str(exc),
                        "code": 2,
                    },
                    indent=2,
                )
            )
        else:
            print(f"Execution Error: {exc}", file=sys.stderr)
        return 2

    all_passed = all(r.parity for r in results)

    if args.json:
        payload = {
            "status": "PASS" if all_passed else "FAIL",
            "tool_path": "tools/check_rust_kernel.py",
            "test_path": "tests/integration/test_rust_kernel.py",
            "cases": [
                {
                    "case": r.case_name,
                    "python": {
                        "value": round(r.py_value, 6),
                        "nodes": r.py_nodes,
                        "time_s": round(r.py_time, 4),
                    },
                    "rust": {
                        "value": round(r.rust_value, 6),
                        "nodes": r.rust_nodes,
                        "time_s": round(r.rust_time, 4),
                    },
                    "speedup": round(r.speedup, 1),
                    "parity": r.parity,
                }
                for r in results
            ],
            "hardcoded_findings": get_hardcoded_findings_count(),
        }
        print(json.dumps(payload, indent=2))
    else:
        print_summary_table(results)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
