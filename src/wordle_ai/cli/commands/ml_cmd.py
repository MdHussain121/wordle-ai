"""`wordle-ai ml` commands: dataset extraction, model training, and gate evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from ...config import DEFAULT_CONFIG_PATH, load_config
from ...errors import WordleError
from ...lexicon.profile import load_profile
from ...ml.dataset import extract_dp_dataset, save_dataset_parquet
from ...ml.distill import train_and_evaluate_all
from ...ml.gate import evaluate_gate_criteria
from ...types import Profile
from ..output import emit, fail

app = typer.Typer(no_args_is_help=True, help="Machine Learning research, distillation and gate commands.")


def _resolve_profile(profile_id: str, config_path: Path) -> Profile:
    config = load_config(config_path)
    profile_dir = Path(config.general.data_dir) / "processed" / profile_id
    if not profile_dir.exists():
        fail(f"profile directory not found: {profile_dir}")
    return load_profile(profile_dir)


@app.command("extract")
def extract(
    policy_path: Path = typer.Option(
        Path("policies/classic.en.5.normal.uniform.policy.json"),
        "--policy",
        help="Path to exact DP policy JSON.",
    ),
    profile: str = typer.Option("classic.en.5", "--profile", help="Profile id."),
    output: Path = typer.Option(
        Path("data/ml/dp_training_pairs.parquet"),
        "--output",
        help="Path to output Parquet file.",
    ),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Configuration file."),
    as_json: bool = typer.Option(False, "--json", help="Emit raw JSON summary."),
) -> None:
    """Extract (state, k, guess, value) dataset from verified DP policy with zero leakage."""
    try:
        prof = _resolve_profile(profile, config)
        dataset = extract_dp_dataset(policy_path, prof)
        meta = save_dataset_parquet(dataset, output)
        if as_json:
            emit(meta)
        else:
            emit(
                f"Extracted {meta['total_records']} trajectory records from {policy_path.name} "
                f"into {output} (SHA256: {meta['sha256'][:16]}…)"
            )
            emit(
                f"Split: {meta['split_summary']['train_answers']} train / "
                f"{meta['split_summary']['val_answers']} val / "
                f"{meta['split_summary']['test_answers']} test answers."
            )
    except WordleError as exc:
        fail(str(exc))


@app.command("train")
def train(
    policy_path: Path = typer.Option(
        Path("policies/classic.en.5.normal.uniform.policy.json"),
        "--policy",
        help="Path to exact DP policy JSON.",
    ),
    profile: str = typer.Option("classic.en.5", "--profile", help="Profile id."),
    output_dir: Path = typer.Option(Path("models"), "--output-dir", help="Directory to save models."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Configuration file."),
    as_json: bool = typer.Option(False, "--json", help="Emit raw JSON summary."),
) -> None:
    """Train ValueNetwork, ValueRegressor, and PolicyRanker distillation models."""
    try:
        prof = _resolve_profile(profile, config)
        dataset = extract_dp_dataset(policy_path, prof)
        results = train_and_evaluate_all(dataset, prof, output_dir=output_dir)

        summary = {}
        for name, m in results.items():
            summary[name] = {
                "model_name": m.model_name,
                "train_mae": m.train_mae,
                "val_mae": m.val_mae,
                "test_mae": m.test_mae,
                "train_time_s": m.training_time_s,
                "inference_p95_ms": m.inference_p95_ms,
                "top1_accuracy": m.top1_accuracy,
                "top3_accuracy": m.top3_accuracy,
            }

        if as_json:
            emit(summary)
        else:
            emit(f"Successfully trained distillation models into '{output_dir}':")
            for name, info in summary.items():
                acc_str = f", Top-1: {info['top1_accuracy']*100:.1f}%" if info["top1_accuracy"] is not None else ""
                emit(
                    f"  - {info['model_name']}: Test MAE={info['test_mae']:.4f}{acc_str}, "
                    f"p95={info['inference_p95_ms']:.2f}ms"
                )
    except WordleError as exc:
        fail(str(exc))


@app.command("gate")
def gate(
    bench_data: Path = typer.Option(
        Path("data/bench/phase6_ml_bench.json"),
        "--bench-data",
        help="Path to benchmark metrics JSON.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit raw JSON report."),
) -> None:
    """Display admission gate evaluation report (G1–G8)."""
    if not bench_data.exists():
        fail(f"Benchmark results file not found: {bench_data}. Run benchmark first.")

    payload = json.loads(bench_data.read_text(encoding="utf-8"))
    if as_json:
        emit(payload.get("gate_reports", {}))
    else:
        for model_name, rep_dict in payload.get("gate_reports", {}).items():
            emit(f"\n========================================================")
            emit(f"  Admission Gate Report: {model_name}")
            emit(f"  Verdict: {rep_dict['verdict'].upper()}")
            emit(f"========================================================")
            emit(f"Summary: {rep_dict['summary']}\n")
            emit("Gate Criteria (G1–G8):")
            for m in rep_dict["metrics"]:
                status = "PASS" if m["passed"] else "FAIL"
                emit(
                    f"  [{status}] {m['id']} {m['name']:<22} "
                    f"Base: {str(m['baseline']):<10} Model: {str(m['model']):<10} "
                    f"Delta: {str(m['delta']):<8} Thresh: {m['threshold']}"
                )
