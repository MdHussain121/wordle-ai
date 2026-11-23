"""Admission gate evaluation for Phase 6 machine learning models.

Implements Section 8 of WORDLE_AI_ML_RESEARCH_AND_TRAINING_PLAN.md:
Evaluates models against the 8 numeric gates (G1–G8):
- G1: Average guesses improvement >= 0.02 vs analytic baseline.
- G2: Worst-case guesses not worse.
- G3: Failure rate not worse (0.0%).
- G4: Decision latency added p95 <= 5.0 ms.
- G5: Cross-profile regression <= 0.02.
- G6: Calibration (ECE < 0.05).
- G7: Reproducibility (deterministic inference + versioned checksum).
- G8: Explainability (output renderable with structured breakdown).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


@dataclass
class GateMetric:
    id: str
    name: str
    threshold: str
    baseline: float | str
    model: float | str
    delta: float | str
    passed: bool
    rationale: str


@dataclass
class GateReport:
    model_name: str
    profile_id: str
    verdict: Literal["admitted", "rejected"]
    passed_all: bool
    metrics: list[GateMetric]
    summary: str

    def to_dict(self) -> dict:
        return asdict(self)

    def to_markdown(self) -> str:
        rows = [
            f"# Phase 6 ML Admission Gate Report: {self.model_name}",
            "",
            f"**Profile:** `{self.profile_id}`  ",
            f"**Verdict:** `{'ADMITTED' if self.passed_all else 'REJECTED'}`  ",
            f"**Summary:** {self.summary}",
            "",
            "## Gate Criteria Results (G1–G8)",
            "",
            "| Gate | Metric | Baseline | Model | Delta | Threshold | Pass? |",
            "|---|---|---|---|---|---|---|",
        ]
        for m in self.metrics:
            status = "PASS" if m.passed else "FAIL"
            rows.append(
                f"| {m.id} | {m.name} | {m.baseline} | {m.model} | {m.delta} | {m.threshold} | {status} |"
            )
        rows.append("")
        rows.append("### Detailed Rationales")
        for m in self.metrics:
            rows.append(f"- **{m.id} ({m.name}):** {m.rationale}")
        rows.append("")
        return "\n".join(rows)

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        md_path = path.with_suffix(".md")
        json_path = path.with_suffix(".json")
        md_path.write_text(self.to_markdown(), encoding="utf-8")
        json_path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")


def evaluate_gate_criteria(
    *,
    model_name: str,
    profile_id: str,
    baseline_avg_guesses: float,
    model_avg_guesses: float,
    baseline_worst_case: int,
    model_worst_case: int,
    baseline_failure_rate: float,
    model_failure_rate: float,
    baseline_p95_ms: float,
    model_p95_ms: float,
    cross_profile_delta: float = 0.0,
    ece: float = 0.0,
    is_deterministic: bool = True,
    has_checksum: bool = True,
    has_explanation: bool = True,
) -> GateReport:
    """Evaluate candidate model against G1–G8 criteria and render verdict."""
    metrics: list[GateMetric] = []

    # G1: Average guesses improvement >= 0.02
    avg_delta = baseline_avg_guesses - model_avg_guesses
    g1_pass = avg_delta >= 0.02
    metrics.append(
        GateMetric(
            id="G1",
            name="Average Guesses",
            threshold="improvement >= 0.02",
            baseline=f"{baseline_avg_guesses:.4f}",
            model=f"{model_avg_guesses:.4f}",
            delta=f"{avg_delta:+.4f}",
            passed=g1_pass,
            rationale=f"Delta is {avg_delta:+.4f}; requires >= +0.02 improvement.",
        )
    )

    # G2: Worst case not worse than baseline
    g2_pass = model_worst_case <= baseline_worst_case
    metrics.append(
        GateMetric(
            id="G2",
            name="Worst-Case Turns",
            threshold="<= baseline",
            baseline=baseline_worst_case,
            model=model_worst_case,
            delta=f"{model_worst_case - baseline_worst_case:+d}",
            passed=g2_pass,
            rationale=f"Model worst-case is {model_worst_case} vs baseline {baseline_worst_case}.",
        )
    )

    # G3: Failure rate not worse
    fail_delta = model_failure_rate - baseline_failure_rate
    g3_pass = model_failure_rate <= baseline_failure_rate
    metrics.append(
        GateMetric(
            id="G3",
            name="Failure Rate",
            threshold="<= baseline (0%)",
            baseline=f"{baseline_failure_rate * 100:.2f}%",
            model=f"{model_failure_rate * 100:.2f}%",
            delta=f"{fail_delta * 100:+.2f}%",
            passed=g3_pass,
            rationale=f"Model failure rate is {model_failure_rate * 100:.2f}%.",
        )
    )

    # G4: Decision latency added p95 <= 5.0 ms
    added_latency = model_p95_ms - baseline_p95_ms
    g4_pass = added_latency <= 5.0
    metrics.append(
        GateMetric(
            id="G4",
            name="Decision Latency (p95)",
            threshold="added p95 <= 5.0 ms",
            baseline=f"{baseline_p95_ms:.2f} ms",
            model=f"{model_p95_ms:.2f} ms",
            delta=f"{added_latency:+.2f} ms",
            passed=g4_pass,
            rationale=f"Added latency is {added_latency:+.2f} ms (budget 5.0 ms).",
        )
    )

    # G5: Cross-profile check: no regression > 0.02
    g5_pass = cross_profile_delta <= 0.02
    metrics.append(
        GateMetric(
            id="G5",
            name="Cross-Profile Check",
            threshold="regression <= 0.02",
            baseline="0.0000",
            model=f"{cross_profile_delta:.4f}",
            delta=f"{cross_profile_delta:+.4f}",
            passed=g5_pass,
            rationale=f"Cross-profile delta is {cross_profile_delta:+.4f} (threshold <= 0.02).",
        )
    )

    # G6: Calibration: ECE < 0.05
    g6_pass = ece < 0.05
    metrics.append(
        GateMetric(
            id="G6",
            name="Calibration (ECE)",
            threshold="< 0.05",
            baseline="< 0.05",
            model=f"{ece:.4f}",
            delta=f"{ece:.4f}",
            passed=g6_pass,
            rationale=f"Expected calibration error is {ece:.4f}.",
        )
    )

    # G7: Reproducibility: deterministic inference + checksum
    g7_pass = is_deterministic and has_checksum
    metrics.append(
        GateMetric(
            id="G7",
            name="Reproducibility",
            threshold="deterministic + checksum",
            baseline="true",
            model=f"det={is_deterministic}, sha={has_checksum}",
            delta="ok" if g7_pass else "missing",
            passed=g7_pass,
            rationale="Deterministic inference with versioned weights and SHA-256 sidecar.",
        )
    )

    # G8: Explainability: renderable reason
    g8_pass = has_explanation
    metrics.append(
        GateMetric(
            id="G8",
            name="Explainability",
            threshold="renderable breakdown",
            baseline="true",
            model=f"{has_explanation}",
            delta="ok" if g8_pass else "missing",
            passed=g8_pass,
            rationale="Model decisions include breakdown features and confidence values.",
        )
    )

    passed_all = all(m.passed for m in metrics)
    verdict: Literal["admitted", "rejected"] = "admitted" if passed_all else "rejected"

    if passed_all:
        summary = (
            f"All 8 admission gates PASSED. Model '{model_name}' qualifies for product admission "
            f"under flag ml.enabled = false."
        )
    else:
        failed_gates = [m.id for m in metrics if not m.passed]
        summary = (
            f"Gate check FAILED on: {', '.join(failed_gates)}. "
            f"Per Phase 6 governing rules, classical algorithm remains primary and model is REJECTED."
        )

    return GateReport(
        model_name=model_name,
        profile_id=profile_id,
        verdict=verdict,
        passed_all=passed_all,
        metrics=metrics,
        summary=summary,
    )
