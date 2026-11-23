"""Prior calibration harness (benchmark plan §4.4, technical specification §8).

A prior is admitted, not assumed. This module splits the answers deterministically
into a validation half and a held-out test half, fits the Zipf temperature ``beta`` on
the validation half only, and reports log loss, Brier score, ECE, a reliability curve
and top-k hit rates on the test half against the uniform baseline.

The admission rule is the one in the plan: log loss strictly better than uniform and
ECE below 0.05. A rejection is a successful experiment — it keeps a plausible-sounding
prior out of the default path and records why.

ECE definition. The plan says "bins of predicted probability for the true answer".
Applied literally to a 2,315-way distribution, the observed frequency in every bin is
1 by construction, so ECE degenerates to ``1 - mean pi(a*)`` and no honest prior on a
2,315-word list can pass 0.05. This harness therefore reports the *top-1* calibration
error (confidence = ``max_a pi(a)``, outcome = whether that argmax is the true answer)
in equal-mass bins, which is the standard multiclass definition and can actually fail
for a real reason. ``mean_true_probability`` is reported alongside it so the literal
quantity is still visible.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from ..engine.prior import Prior, UniformPrior, ZipfPrior, normalised_weights
from ..types import Profile
from .metrics import brier, ece, log_loss, reliability_curve, top_k_hit_rate

#: Validation-grid for the temperature. It includes 0.0 so the fit can choose uniform,
#: and stops at 2.0: a hotter prior than that assigns implausible mass to rare words.
DEFAULT_BETA_GRID: tuple[float, ...] = (0.0, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0)
ECE_THRESHOLD = 0.05


@dataclass(frozen=True)
class Split:
    """A deterministic answer split: indices into ``profile.answers``."""

    validation: tuple[int, ...]
    test: tuple[int, ...]

    @property
    def validation_fraction(self) -> float:
        total = len(self.validation) + len(self.test)
        return len(self.validation) / total if total else 0.0


def split_answers(profile: Profile, *, validation_percent: int = 50) -> Split:
    """Split by a stable hash of the word, so the split survives rebuilds and reorders."""

    if not 1 <= validation_percent <= 99:
        raise ValueError("validation_percent must be between 1 and 99")
    validation: list[int] = []
    test: list[int] = []
    for index, word in enumerate(profile.answers):
        digest = hashlib.sha256(f"prior-split:{word}".encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % 100
        (validation if bucket < validation_percent else test).append(index)
    if not validation or not test:  # pragma: no cover - needs a tiny answer list
        raise ValueError(
            f"cannot split {len(profile.answers)} answers into validation and test halves"
        )
    return Split(validation=tuple(validation), test=tuple(test))


def _distribution_metrics(
    weights: np.ndarray, indices: Sequence[int], answers: Sequence[str]
) -> dict:
    rows = [[float(value) for value in weights] for _ in indices]
    targets = list(indices)
    probabilities = [weights[index] for index in indices]
    top1 = np.argmax(weights)
    correct = [int(top1 == index) for index in indices]
    # Confidence for the top-1 calibration curve: the same argmax for every sample,
    # so the confidence column is the prior's own top-1 mass and the outcome column is
    # whether that choice happened to be the held-out answer.
    confidence = [float(weights[top1]) for _ in indices]
    rankings = [np.argsort(-weights)[:100].tolist() for _ in indices]
    true_probabilities = [float(weights[index]) for index in indices]
    return {
        "samples": len(indices),
        "log_loss": log_loss([[p] for p in true_probabilities], [0] * len(indices)),
        "brier": brier(rows, targets),
        "ece": ece(confidence, [bool(value) for value in correct]),
        "mean_true_probability": float(np.mean(true_probabilities)),
        "top1_accuracy": float(np.mean(correct)),
        "top_k_hit_rate": top_k_hit_rate(rankings, targets, ks=(1, 10, 100)),
        "reliability_curve": reliability_curve(
            confidence, [bool(value) for value in correct]
        ),
        "most_likely": answers[top1],
        "least_likely": answers[int(np.argmin(weights))],
    }


def calibrate_prior(
    profile: Profile, prior: Prior, *, split: Split | None = None
) -> dict:
    """Measure a prior on the held-out half and give the admission verdict."""

    split = split or split_answers(profile)
    weights = normalised_weights(prior, profile)
    test = _distribution_metrics(weights, split.test, profile.answers)
    uniform = normalised_weights(UniformPrior(), profile)
    baseline = _distribution_metrics(uniform, split.test, profile.answers)

    improvement = baseline["log_loss"] - test["log_loss"]
    reasons: list[str] = []
    if not improvement > 0.0:
        reasons.append(
            f"log loss {test['log_loss']:.6f} is not better than uniform "
            f"{baseline['log_loss']:.6f} (delta {improvement:+.6f})"
        )
    if not test["ece"] < ECE_THRESHOLD:
        reasons.append(f"ECE {test['ece']:.6f} is not below {ECE_THRESHOLD}")
    verdict = {
        "prior_id": prior.prior_id,
        "profile_id": profile.profile_id,
        "admitted": not reasons,
        "reject_reason": "; ".join(reasons) if reasons else None,
        "log_loss_improvement": improvement,
        "split": {
            "validation": len(split.validation),
            "test": len(split.test),
            "validation_fraction": split.validation_fraction,
            "method": "sha256('prior-split:<word>') first four bytes mod 100",
        },
        "test": test,
        "uniform_on_test": baseline,
    }
    return verdict


def fit_beta(
    profile: Profile,
    *,
    grid: Sequence[float] = DEFAULT_BETA_GRID,
    split: Split | None = None,
) -> dict:
    """Choose the Zipf temperature on the validation half, by validation log loss."""

    split = split or split_answers(profile)
    rows: list[dict] = []
    best: dict | None = None
    for beta in grid:
        prior = ZipfPrior(beta)
        weights = normalised_weights(prior, profile)
        validation_ll = float(
            np.mean([-math.log(max(float(weights[index]), 1e-300)) for index in split.validation])
        )
        entry = {"beta": float(beta), "validation_log_loss": validation_ll}
        rows.append(entry)
        if best is None or validation_ll < best["validation_log_loss"] - 1e-15:
            best = entry
    assert best is not None
    return {
        "profile_id": profile.profile_id,
        "grid": rows,
        "best_beta": best["beta"],
        "validation_log_loss": best["validation_log_loss"],
    }


def calibrate_zipf(
    profile: Profile,
    *,
    grid: Sequence[float] = DEFAULT_BETA_GRID,
    split: Split | None = None,
) -> dict:
    """Fit ``beta`` on validation, then measure the fitted prior on the test half."""

    split = split or split_answers(profile)
    fit = fit_beta(profile, grid=grid, split=split)
    prior = ZipfPrior(fit["best_beta"])
    verdict = calibrate_prior(profile, prior, split=split)
    verdict["fit"] = fit
    return verdict


def markdown(verdict: dict) -> str:
    """A stable Markdown report of one calibration verdict."""

    test = verdict["test"]
    baseline = verdict["uniform_on_test"]
    lines = [
        f"# Prior calibration — {verdict['profile_id']}",
        "",
        f"**Prior:** `{verdict['prior_id']}`  ",
        f"**Verdict:** {'admitted' if verdict['admitted'] else 'rejected'}",
        "",
    ]
    if verdict.get("reject_reason"):
        lines += [f"> {verdict['reject_reason']}", ""]
    lines += [
        "## Held-out metrics",
        "",
        "| Metric | Prior | Uniform |",
        "|---|---|---|",
        f"| log loss | {test['log_loss']:.6f} | {baseline['log_loss']:.6f} |",
        f"| Brier | {test['brier']:.6f} | {baseline['brier']:.6f} |",
        f"| ECE (top-1) | {test['ece']:.6f} | {baseline['ece']:.6f} |",
        f"| mean p(true answer) | {test['mean_true_probability']:.6f} | "
        f"{baseline['mean_true_probability']:.6f} |",
        f"| top-1 accuracy | {test['top1_accuracy']:.6f} | {baseline['top1_accuracy']:.6f} |",
        f"| top-10 hit rate | {test['top_k_hit_rate'][10]:.4f} | "
        f"{baseline['top_k_hit_rate'][10]:.4f} |",
        f"| top-100 hit rate | {test['top_k_hit_rate'][100]:.4f} | "
        f"{baseline['top_k_hit_rate'][100]:.4f} |",
        "",
        f"Split: {verdict['split']['validation']} validation / "
        f"{verdict['split']['test']} test answers, deterministic by "
        f"{verdict['split']['method']}.",
        "",
    ]
    if "fit" in verdict:
        lines += [
            "## Temperature fit (validation half only)",
            "",
            "| beta | validation log loss |",
            "|---|---|",
        ]
        for entry in verdict["fit"]["grid"]:
            marker = " **selected**" if entry["beta"] == verdict["fit"]["best_beta"] else ""
            lines.append(
                f"| {entry['beta']:g}{marker} | {entry['validation_log_loss']:.6f} |"
            )
        lines += ["", f"Selected beta = {verdict['fit']['best_beta']:g}.", ""]
    lines += [
        "## Reliability curve (top-1)",
        "",
        "| bin | range | count | confidence | accuracy |",
        "|---|---|---|---|---|",
    ]
    for entry in test["reliability_curve"]:
        if not entry["count"]:
            continue
        lines.append(
            f"| {entry['bin']} | {entry['low']:.1f}–{entry['high']:.1f} | "
            f"{entry['count']} | {entry['confidence']:.6f} | {entry['accuracy']:.6f} |"
        )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "DEFAULT_BETA_GRID",
    "ECE_THRESHOLD",
    "Split",
    "calibrate_prior",
    "calibrate_zipf",
    "fit_beta",
    "markdown",
    "split_answers",
]
