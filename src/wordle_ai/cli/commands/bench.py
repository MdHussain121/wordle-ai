"""`wordle-ai bench` commands: run, report and compare (Phase 2 harness, Phase 4 bench)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from ...bench.report import (
    aggregates_from_csv,
    compare_to_published,
    csv_rows,
    csv_text,
    format_table,
    markdown,
    payload,
    result_from_dict,
)
from ...bench.runner import (
    PACKAGE_VERSION,
    RunSpec,
    config_digest,
    execute,
    records_from_store,
)
from ...bench.stats import paired_comparison
from ...config import DEFAULT_CONFIG_PATH, load_config
from ...engine.prior import parse_prior_id
from ...errors import WordleError
from ...lexicon.profile import load_profile
from ...store.sqlite import RunStore, StoreError
from ...strategy import HEURISTIC_STRATEGY_NAMES, get_strategy
from ...types import RuleMode
from ..output import emit, fail

app = typer.Typer(no_args_is_help=True, help="Run strategies over a profile and report the baseline.")


def _profile_dir(root: Path, profile_id: str) -> Path:
    return root / "processed" / profile_id


def _store(path: Path) -> RunStore:
    return RunStore(path)


def _store_path(data_dir: Path, override: Path | None) -> Path:
    return Path(override) if override is not None else data_dir / "bench" / "runs.sqlite"


def _names(strategies: str) -> list[str]:
    if strategies.strip().lower() == "all":
        return list(HEURISTIC_STRATEGY_NAMES)
    return [name.strip() for name in strategies.split(",") if name.strip()]


@app.command("run")
def run(
    profile: str = typer.Option("classic.en.5", "--profile", help="Profile id to play."),
    strategies: str = typer.Option(
        "all", "--strategies", help="'all' or a comma-separated list of strategy names."
    ),
    mode: str = typer.Option("normal", "--mode", help="normal | hard | superhard"),
    max_attempts: int = typer.Option(6, "--max-attempts", help="Attempt limit K."),
    prior: str = typer.Option(
        "uniform",
        "--prior",
        help="Prior id: uniform | zipf | zipf:<beta> | empirical:<history path>.",
    ),
    prior_beta: Optional[float] = typer.Option(
        None, "--prior-beta", help="Zipf temperature; shorthand for --prior zipf:<beta>."
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", help="Play only the first N answers (a labelled subset, not a sample)."
    ),
    feedback_source: str = typer.Option(
        "table", "--feedback", help="table (shipped .npy) | reference (two-pass function)"
    ),
    policy: Optional[Path] = typer.Option(
        None, "--policy", help="Policy artifact required by the exact strategy."
    ),
    workers: int = typer.Option(
        1, "--workers", help="Processes to use; 1 runs in-process, and outcomes never depend on it."
    ),
    seed: Optional[int] = typer.Option(
        None, "--seed", help="Seed recorded in the run key (no strategy uses randomness)."
    ),
    store_path: Optional[Path] = typer.Option(
        None, "--store", help="SQLite store path; defaults to <data-dir>/bench/runs.sqlite."
    ),
    no_store: bool = typer.Option(False, "--no-store", help="Do not persist the run."),
    time_budget: Optional[float] = typer.Option(
        None, "--time-budget", help="Seconds before the run is refused as over budget."
    ),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Override data directory."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Play every requested answer against each strategy, store the run and report it."""

    try:
        settings = load_config(config)
        root = Path(data_dir) if data_dir is not None else Path(settings.general.data_dir)
        profile_dir = _profile_dir(root, profile)
        loaded = load_profile(profile_dir)
        try:
            rule_mode = RuleMode(mode)
        except ValueError:
            raise WordleError(
                f"unknown mode {mode!r}; choose normal, hard or superhard", code="invalid_mode"
            ) from None
        if max_attempts < 1:
            raise WordleError("--max-attempts must be >= 1", code="invalid_attempts")
        if workers < 1:
            raise WordleError("--workers must be >= 1", code="invalid_workers")
        names = _names(strategies)
        for name in names:
            get_strategy(name)  # validates the name before any work starts
        if limit is not None and limit < 1:
            raise WordleError("--limit must be >= 1", code="invalid_limit")
        prior_spec = prior
        if prior_beta is not None:
            if prior_beta < 0:
                raise WordleError("--prior-beta must be >= 0", code="invalid_prior")
            if prior.strip() not in ("", "zipf"):
                raise WordleError(
                    "--prior-beta is only valid with --prior zipf", code="invalid_prior"
                )
            prior_spec = f"zipf:beta={prior_beta:g}"
        parse_prior_id(prior_spec)  # validate before any game is played
        answers = tuple(loaded.answers[:limit]) if limit is not None else None
        specs = [
            RunSpec(
                profile_id=loaded.profile_id,
                profile_dir=profile_dir,
                strategy=name,
                mode=rule_mode,
                prior=prior_spec,
                attempts=max_attempts,
                answers=answers,
                workers=workers,
                seed=seed,
                policy_path=policy,
            )
            for name in names
        ]
        digest = config_digest(config)
        store = None if no_store else _store(_store_path(root, store_path))
    except KeyError as exc:
        fail(WordleError(str(exc), code="unknown_strategy"), as_json=as_json)
        return
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return

    results = []
    provenance: dict = {}
    try:
        for spec in specs:
            result = execute(
                spec,
                store=store,
                package_version=PACKAGE_VERSION,
                config_sha256=digest,
                time_budget_s=time_budget,
                feedback_source=feedback_source,
            )
            results.append(result)
            if store is not None:
                provenance = store.get(result.run_key).provenance
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return
    finally:
        if store is not None:
            store.close()

    if not provenance:
        provenance = {
            "profile_id": loaded.profile_id,
            "manifest_sha256": loaded.manifest_sha256,
            "rules": rule_mode.value,
            "prior": prior_spec,
            "attempts": max_attempts,
            "answer_set_id": results[0].answer_set_id,
            "exhaustive": results[0].exhaustive,
            "workers": workers,
            "seed": seed,
            "package_version": PACKAGE_VERSION,
            "config_sha256": digest,
            "table_sha256": None,
        }

    if as_json:
        emit(payload(results, provenance=provenance))
        return

    typer.echo(
        f"{loaded.profile_id}: {results[0].answers} answers ({results[0].answer_set_id}), "
        f"mode={rule_mode.value}, prior={prior_spec}, attempts={max_attempts}, workers={workers}"
    )
    typer.echo(format_table(results, max_attempts=max_attempts))
    typer.echo("")
    for result in results:
        typer.echo(
            f"{result.strategy}: run {result.run_key[:16]}… determinism "
            f"{result.determinism_sha256[:16]}…, {result.total_s:.1f}s wall clock"
        )
        if result.failed:
            shown = ", ".join(result.failed_answers[:5])
            more = "" if result.failed <= 5 else f" (+{result.failed - 5} more)"
            typer.echo(f"  {result.failed} unsolved answer(s): {shown}{more}")
        for row in compare_to_published(result):
            delta = "n/a" if row["delta"] is None else f"{row['delta']:+.4f}"
            typer.echo(
                f"  vs published {row['published']:.4f}: {delta} ({row['status']}; "
                f"{row['source']})"
            )


def _load_runs(store: RunStore, keys: str) -> list[tuple[object, list[dict]]]:
    out = []
    for key in [part.strip() for part in keys.split(",") if part.strip()]:
        stored = store.get(key)
        out.append((stored, store.games(stored.run_id)))
    return out


@app.command("report")
def report(
    run_ids: str = typer.Option(
        ..., "--run", help="Run id or unique prefix; comma-separate several."
    ),
    format: str = typer.Option("markdown", "--format", help="markdown | csv | json"),
    out: Optional[Path] = typer.Option(None, "--out", help="Write the report to this file."),
    store_path: Optional[Path] = typer.Option(None, "--store", help="SQLite store path."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Override data directory."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Render a stored run as Markdown, per-game CSV or JSON."""

    try:
        settings = load_config(config)
        root = Path(data_dir) if data_dir is not None else Path(settings.general.data_dir)
        store = _store(_store_path(root, store_path))
        try:
            loaded = _load_runs(store, run_ids)
        finally:
            store.close()
        if not loaded:
            raise StoreError("no run ids were given")
        results = [result_from_dict(stored.record) for stored, _ in loaded]
        games_by_run = {
            stored.run_id: [
                {
                    "answer": row["answer"],
                    "guesses": json.loads(row["guesses_json"]),
                    "n_guesses": row["n_guesses"],
                    "solved": bool(row["solved"]),
                    "elapsed_ms": row["elapsed_ms"],
                    "final_candidates": row["final_candidates"],
                    "opener": row["opener"],
                }
                for row in rows
            ]
            for stored, rows in loaded
        }
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return

    kind = format.strip().lower()
    if kind == "markdown":
        text = markdown(
            results,
            provenance=loaded[0][0].provenance,
            comparisons=[row for result in results for row in compare_to_published(result)],
        )
    elif kind == "csv":
        rows = csv_rows(results, games_by_run)
        text = csv_text(rows)
        aggregates = aggregates_from_csv(rows, max_attempts=results[0].max_attempts)
        for result in results:
            measured = aggregates[result.run_key]
            if abs(measured["avg_guesses_all"] - result.avg_guesses_all) > 1e-9:  # pragma: no cover
                raise WordleError(
                    "the CSV does not reproduce the stored average; refusing to export",
                    code="csv_mismatch",
                )
    elif kind == "json":
        text = json.dumps(
            payload(results, provenance=loaded[0][0].provenance), indent=2, sort_keys=True
        )
    else:
        fail(WordleError(f"unknown --format {format!r}", code="invalid_format"), as_json=as_json)
        return

    if out is not None:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8", newline="\n")
        typer.echo(f"wrote {out} ({len(text.splitlines())} lines)")
        return
    typer.echo(text)


@app.command("compare")
def compare(
    run_a: str = typer.Option(..., "--run", help="Baseline run id or prefix."),
    other: str = typer.Option(..., "--other", help="Run id or prefix to compare against."),
    metric: str = typer.Option(
        "avg_guesses_solved", "--metric", help="Metric to headline (all metrics are reported)."
    ),
    allow_mismatch: bool = typer.Option(
        False, "--allow-mismatch", help="Compare runs whose provenance differs (informal)."
    ),
    check_determinism: bool = typer.Option(
        False, "--check-determinism", help="Require identical determinism hashes."
    ),
    store_path: Optional[Path] = typer.Option(None, "--store", help="SQLite store path."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Override data directory."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Compare two stored runs answer by answer; refuse mismatched provenance."""

    try:
        settings = load_config(config)
        root = Path(data_dir) if data_dir is not None else Path(settings.general.data_dir)
        store = _store(_store_path(root, store_path))
        try:
            first, first_rows = _load_runs(store, run_a)[0]
            second, second_rows = _load_runs(store, other)[0]
        finally:
            store.close()
        if metric not in {"avg_guesses_solved", "avg_guesses_all"}:
            raise WordleError(
                f"unknown --metric {metric!r}; choose avg_guesses_solved or avg_guesses_all",
                code="invalid_metric",
            )

        keys = ("profile_id", "profile_manifest_sha256", "mode", "prior", "attempts", "answer_set_id")
        mismatched = [
            key for key in keys if first.record.get(key) != second.record.get(key)
        ]
        if mismatched and not allow_mismatch:
            raise WordleError(
                "the runs are not comparable: "
                + ", ".join(
                    f"{key} {first.record.get(key)!r} vs {second.record.get(key)!r}"
                    for key in mismatched
                )
                + "; pass --allow-mismatch to compare them informally",
                code="incomparable_runs",
                fields=mismatched,
            )
        if check_determinism and (
            first.record["determinism_sha256"] != second.record["determinism_sha256"]
        ):
            raise WordleError(
                "determinism hashes differ: "
                f"{first.record['determinism_sha256']} vs {second.record['determinism_sha256']}",
                code="determinism_mismatch",
            )
        records_a = records_from_store(first_rows)
        records_b = records_from_store(second_rows)
        if mismatched:
            shared = {record.answer for record in records_a} & {
                record.answer for record in records_b
            }
            if not shared:
                raise WordleError(
                    "the two runs share no answers, so no paired comparison exists",
                    code="incomparable_runs",
                )
            records_a = [record for record in records_a if record.answer in shared]
            records_b = [record for record in records_b if record.answer in shared]
        comparison = paired_comparison(
            records_a,
            records_b,
            max_attempts=int(first.record["max_attempts"]),
        )
        comparison["informal"] = bool(mismatched)
        comparison["determinism_match"] = (
            first.record["determinism_sha256"] == second.record["determinism_sha256"]
        )
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return

    summary = {
        "a": {"run": first.run_id, "strategy": first.record["strategy"], "metric": first.record[metric]},
        "b": {
            "run": second.run_id,
            "strategy": second.record["strategy"],
            "metric": second.record[metric],
        },
        "comparison": comparison,
    }
    if as_json:
        emit(summary)
        return
    typer.echo(
        f"A {first.record['strategy']} {first.record[metric]!r} vs "
        f"B {second.record['strategy']} {second.record[metric]!r}"
    )
    interval = comparison["bootstrap"]
    typer.echo(
        f"  mean difference {interval['mean_difference']:+.4f} guesses "
        f"(95% CI {interval['ci_low']:+.4f} .. {interval['ci_high']:+.4f}, "
        f"{'significant' if interval['significant'] else 'not significant'})"
    )
    typer.echo(
        f"  McNemar p={comparison['mcnemar']['p_value']:.4g}; "
        f"Wilcoxon p={comparison['wilcoxon']['p_value']:.4g}, "
        f"rank-biserial {comparison['wilcoxon']['rank_biserial']:+.3f}"
    )
    typer.echo(
        f"  determinism {'identical' if comparison['determinism_match'] else 'differs'}"
        + (" (informal comparison)" if comparison["informal"] else "")
    )


if __name__ == "__main__":  # pragma: no cover
    app()
