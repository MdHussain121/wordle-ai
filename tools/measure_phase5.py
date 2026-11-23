"""Measure the Phase 5 calibration gate and the AB-3/B-09 prior comparison.

Runs the prior calibration on the classic profile (fit on the validation half, measure
on the held-out half) and AB-3: the same strategies under the uniform prior and the
fitted Zipf prior, paired answer by answer. Every run is stored in SQLite; resume skips
runs already recorded as succeeded.

Run::

    .venv/Scripts/python.exe -u tools/measure_phase5.py [--workers 16]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from wordle_ai.bench.calibration import (
    DEFAULT_BETA_GRID,
    calibrate_zipf,
    markdown as calibration_markdown,
    split_answers,
)
from wordle_ai.bench.report import result_from_dict
from wordle_ai.bench.runner import (
    PACKAGE_VERSION,
    RunSpec,
    config_digest,
    prepare,
    records_from_store,
    run_matrix,
)
from wordle_ai.bench.stats import paired_comparison
from wordle_ai.config import DEFAULT_CONFIG_PATH, load_config
from wordle_ai.lexicon.profile import load_profile
from wordle_ai.store.sqlite import RunStore

OUT = Path("data/bench/phase5")
PROFILE = "classic.en.5"
STRATEGIES = ("hybrid.balanced", "weighted_entropy", "bayes_cost")


def _stored(store: RunStore, key: str):
    stored = store.get(key)
    return result_from_dict(stored.record), records_from_store(store.games(stored.run_id))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--beta-grid", default=",".join(f"{b:g}" for b in DEFAULT_BETA_GRID))
    parser.add_argument("--samples", type=int, default=10_000)
    args = parser.parse_args()

    settings = load_config(DEFAULT_CONFIG_PATH)
    root = Path(settings.general.data_dir)
    profile_dir = root / "processed" / PROFILE
    profile = load_profile(profile_dir)
    grid = tuple(float(value) for value in args.beta_grid.split(",") if value.strip())
    split = split_answers(profile)

    OUT.mkdir(parents=True, exist_ok=True)
    verdict = calibrate_zipf(profile, grid=grid, split=split)
    (OUT / "calibration.json").write_text(
        json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (OUT / "calibration_report.md").write_text(
        calibration_markdown(verdict), encoding="utf-8", newline="\n"
    )
    zipf = f"zipf:beta={verdict['fit']['best_beta']:g}"
    print(f"calibration: {zipf} -> {'admitted' if verdict['admitted'] else 'rejected'}")
    if verdict.get("reject_reason"):
        print(f"  {verdict['reject_reason']}")

    digest = config_digest(DEFAULT_CONFIG_PATH)
    specs = [
        RunSpec(
            profile_id=profile.profile_id,
            profile_dir=profile_dir,
            strategy=strategy,
            prior=prior,
            attempts=6,
            workers=args.workers,
        )
        for prior in ("uniform", zipf)
        for strategy in STRATEGIES
    ]
    store = RunStore(root / "bench" / "runs.sqlite")
    try:
        run_matrix(specs, store=store, config_sha256=digest, resume=True)
        runs: dict[str, dict] = {}
        comparisons = []
        for strategy in STRATEGIES:
            keys = {
                prior: prepare(
                    next(
                        spec
                        for spec in specs
                        if spec.strategy == strategy and spec.prior == prior
                    ),
                    config_sha256=digest,
                ).run_key
                for prior in ("uniform", zipf)
            }
            uniform_result, uniform_games = _stored(store, keys["uniform"])
            zipf_result, zipf_games = _stored(store, keys[zipf])
            for result in (uniform_result, zipf_result):
                runs[result.run_key] = result.to_dict()
            comparison = paired_comparison(
                uniform_games, zipf_games, max_attempts=6, samples=args.samples
            )
            comparisons.append(
                {
                    "strategy": strategy,
                    "prior": zipf,
                    "run_uniform": keys["uniform"],
                    "run_zipf": keys[zipf],
                    "uniform": {
                        "avg_guesses_solved": uniform_result.avg_guesses_solved,
                        "worst_case": uniform_result.worst_case,
                        "failed": uniform_result.failed,
                    },
                    "zipf": {
                        "avg_guesses_solved": zipf_result.avg_guesses_solved,
                        "worst_case": zipf_result.worst_case,
                        "failed": zipf_result.failed,
                    },
                    "paired": comparison,
                }
            )
            mean = comparison["bootstrap"]["mean_difference"]
            print(
                f"AB-3 {strategy}: uniform {uniform_result.avg_guesses_solved:.4f} vs "
                f"zipf {zipf_result.avg_guesses_solved:.4f} "
                f"(delta {mean:+.4f}, significant "
                f"{comparison['bootstrap']['significant']})"
            )
    finally:
        store.close()

    payload = {
        "package_version": PACKAGE_VERSION,
        "profile_id": profile.profile_id,
        "calibration": verdict,
        "comparisons": comparisons,
        "runs": runs,
    }
    (OUT / "measurements.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (OUT / "phase5_report.md").write_text(
        _report(profile, verdict, zipf, comparisons), encoding="utf-8", newline="\n"
    )
    print(f"wrote {OUT / 'phase5_report.md'}")
    return 0


def _report(profile, verdict: dict, zipf: str, comparisons: list[dict]) -> str:
    test = verdict["test"]
    baseline = verdict["uniform_on_test"]
    lines = [
        "# Phase 5 measurement: priors, calibration and AB-3",
        "",
        f"Profile `{profile.profile_id}` ({len(profile.answers)} answers), package "
        f"{PACKAGE_VERSION}, normal rules, 6 attempts, exhaustive.",
        "",
        "## Calibration gate",
        "",
        "| Metric (held-out half) | Zipf | Uniform |",
        "|---|---|---|",
        f"| log loss | {test['log_loss']:.6f} | {baseline['log_loss']:.6f} |",
        f"| Brier | {test['brier']:.6f} | {baseline['brier']:.6f} |",
        f"| ECE (top-1) | {test['ece']:.6f} | {baseline['ece']:.6f} |",
        f"| mean p(true) | {test['mean_true_probability']:.6f} | "
        f"{baseline['mean_true_probability']:.6f} |",
        f"| top-10 hit | {test['top_k_hit_rate'][10]:.4f} | "
        f"{baseline['top_k_hit_rate'][10]:.4f} |",
        "",
        f"Fitted beta = {verdict['fit']['best_beta']:g} on "
        f"{verdict['split']['validation']} validation answers; measured on "
        f"{verdict['split']['test']} held-out answers.",
        "",
        f"**Verdict: {'admitted' if verdict['admitted'] else 'rejected'}.** "
        + (verdict.get("reject_reason") or ""),
        "",
        "## AB-3 / B-09: uniform vs the fitted prior",
        "",
        "| Strategy | Uniform avg | Zipf avg | Delta | 95% CI | Significant | worst (u/z) | fails (u/z) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in comparisons:
        interval = row["paired"]["bootstrap"]
        lines.append(
            f"| `{row['strategy']}` | {row['uniform']['avg_guesses_solved']:.4f} | "
            f"{row['zipf']['avg_guesses_solved']:.4f} | "
            f"{interval['mean_difference']:+.4f} | "
            f"{interval['ci_low']:+.4f} .. {interval['ci_high']:+.4f} | "
            f"{'yes' if interval['significant'] else 'no'} | "
            f"{row['uniform']['worst_case']}/{row['zipf']['worst_case']} | "
            f"{row['uniform']['failed']}/{row['zipf']['failed']} |"
        )
    lines += [
        "",
        "The prior is rejected, so `uniform` remains the default and the prior-aware "
        "strategies run uniformly unless a calibrated prior is explicitly supplied. "
        "The uniform rows reproduce the Phase 4 matrix exactly.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
