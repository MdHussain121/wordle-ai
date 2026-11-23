"""`wordle-ai policy` commands: build and verify exact policy artifacts (§7.3)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from ...config import DEFAULT_CONFIG_PATH, load_config
from ...engine.table import open_rows
from ...errors import WordleError
from ...lexicon.profile import TABLE_NAME, load_profile
from ...solver.dp import ExactSolver
from ...solver.policy import (
    default_policy_name,
    feasibility,
    load_policy,
    policy_summary,
    save_policy,
    subset_profile,
)
from ...types import RuleMode
from ..output import emit, fail

app = typer.Typer(no_args_is_help=True, help="Build and verify exact DP policy artifacts.")


def _progress(message: dict) -> None:
    typer.echo(
        "  nodes={nodes} memo={memo} candidates={candidates} elapsed={elapsed_s:.1f}s".format(
            **message
        ),
        err=True,
    )


@app.command("build")
def build(
    profile: str = typer.Option("classic.en.5", "--profile", help="Profile id to solve."),
    mode: str = typer.Option("normal", "--mode", help="normal (the only exact mode built)."),
    attempts: int = typer.Option(6, "--attempts", help="Attempt limit K."),
    guess_set: str = typer.Option(
        "all", "--guess-set", help="all (proven optimal) | candidates (restricted action set)."
    ),
    prior: str = typer.Option(
        "uniform",
        "--prior",
        help="Prior id an artifact is built for; only 'uniform' is solvable today.",
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", help="Solve only the first N answers (a labelled answer subset)."
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Artifact path; defaults to policies/<profile>.<rules>.<prior>.a<K>."
    ),
    time_budget: Optional[float] = typer.Option(
        None, "--time-budget", help="Seconds before the solve refuses to continue."
    ),
    force: bool = typer.Option(
        False, "--force", help="Start even when the profile is above the feasibility gate."
    ),
    progress: bool = typer.Option(False, "--progress", help="Print solver progress to stderr."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Override data directory."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Solve a profile exactly (or over its answers) and write a checksummed policy."""

    try:
        settings = load_config(config)
        root = Path(data_dir) if data_dir is not None else Path(settings.general.data_dir)
        profile_dir = root / "processed" / profile
        if limit is not None and limit < 1:
            raise WordleError("--limit must be >= 1", code="invalid_limit")
        loaded = subset_profile(load_profile(profile_dir), limit)
        try:
            rule_mode = RuleMode(mode)
        except ValueError:
            raise WordleError(
                f"unknown mode {mode!r}; choose normal, hard or superhard", code="invalid_mode"
            ) from None
        if rule_mode is not RuleMode.NORMAL:
            raise WordleError(
                "exact policies are implemented for normal mode only; hard and "
                "superhard need a history-keyed state",
                code="unsupported_mode",
            )
        if attempts < 1:
            raise WordleError("--attempts must be >= 1", code="invalid_attempts")
        if prior.strip() not in ("", "uniform"):
            raise WordleError(
                "exact policies are solved against the uniform answer prior; a "
                f"policy under {prior!r} would mislabel a uniform optimum. Use the "
                "prior-aware heuristics for a non-uniform prior.",
                code="unsupported_prior",
            )
        if not force:
            ok, reason = feasibility(
                loaded,
                max_answers=settings.exact.max_answers,
                max_guesses=settings.exact.max_guesses,
            )
            if not ok:
                raise WordleError(
                    f"{reason}; the solve is not started. Pass --force to override, or "
                    "benchmark a heuristic/rollout strategy instead.",
                    code="exact_infeasible",
                )
        table_path = profile_dir / TABLE_NAME
        rows = open_rows(loaded, table_path if table_path.exists() else None)
        budget = time_budget if time_budget is not None else float(settings.exact.time_budget_s)
        solver = ExactSolver(
            loaded,
            rows,
            max_attempts=attempts,
            mode=rule_mode,
            guess_set=guess_set,
            memo_max_entries=settings.exact.memo_max_entries,
            time_budget_s=budget,
            progress=_progress if progress else None,
        )
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return

    try:
        solution = solver.solve()
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return

    target = (
        Path(out)
        if out is not None
        else Path("policies") / default_policy_name(loaded.profile_id, rule_mode, "uniform", attempts)
    )
    payload = save_policy(
        target,
        solution,
        loaded,
        mode=rule_mode,
        prior="uniform",
        attempts=attempts,
    )
    summary = policy_summary(payload)
    summary["path"] = str(target)
    summary["elapsed_s"] = round(solution.elapsed_s, 3)
    summary["search_nodes"] = solution.nodes
    summary["guess_evaluations"] = solution.guess_evaluations
    summary["memo_entries"] = solution.memo_entries
    if as_json:
        emit(summary)
        return
    typer.echo(f"{loaded.profile_id}: exact solve over {guess_set} guesses")
    typer.echo(
        f"  expected {solution.value:.4f} guesses, worst case {solution.max_guesses}, "
        f"opener {solution.root_guess!r}"
    )
    typer.echo(
        f"  {solution.nodes:,} search nodes, {solution.guess_evaluations:,} guess "
        f"evaluations, {solution.memo_entries:,} memo entries, {solution.elapsed_s:.1f}s"
    )
    typer.echo(f"  wrote {target} ({payload['sha256'][:16]}…)")


@app.command("verify")
def verify(
    path: Path = typer.Option(..., "--path", help="Policy artifact to verify."),
    profile: Optional[str] = typer.Option(None, "--profile", help="Expected profile id."),
    limit: Optional[int] = typer.Option(
        None, "--limit", help="Expected answer-set size for a subset policy."
    ),
    mode: str = typer.Option("normal", "--mode", help="Expected rule mode."),
    attempts: int = typer.Option(6, "--attempts", help="Expected attempt limit."),
    prior: str = typer.Option("uniform", "--prior", help="Expected prior id."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Override data directory."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Verify an artifact's checksum and its key against a profile."""

    try:
        settings = load_config(config)
        root = Path(data_dir) if data_dir is not None else Path(settings.general.data_dir)
        loaded = subset_profile(load_profile(root / "processed" / profile), limit) if profile else None
        payload = load_policy(
            path,
            profile=loaded,
            mode=RuleMode(mode),
            attempts=attempts,
            prior=prior,
        )
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return
    summary = policy_summary(payload)
    summary["path"] = str(path)
    if as_json:
        emit(summary)
        return
    typer.echo(
        f"ok: {summary['profile_id']} {summary['rules']} a{summary['attempts']} "
        f"expected {summary['expected_guesses']} max {summary['max_guesses']} "
        f"checksum {summary['sha256'][:16]}…"
    )


@app.command("show")
def show(
    path: Path = typer.Option(..., "--path", help="Policy artifact to summarise."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Print the artifact's header without walking the tree."""

    try:
        payload = load_policy(path)
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return
    summary = policy_summary(payload)
    summary["path"] = str(path)
    if as_json:
        emit(summary)
        return
    for key in sorted(summary):
        typer.echo(f"{key}: {summary[key]}")


if __name__ == "__main__":  # pragma: no cover
    app()
