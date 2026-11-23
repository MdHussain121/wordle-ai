"""`wordle-ai diagnose`: health-check an installation (Phase 8, task 5)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from ...config import DEFAULT_CONFIG_PATH
from ...diagnose import run_diagnostics
from ...errors import WordleError
from ...types import RuleMode
from ..output import emit, fail

app = typer.Typer(no_args_is_help=True, help="Check an installation and its artifacts.")


@app.command("diagnose")
def diagnose(
    profile: str = typer.Option("classic.en.5", "--profile", help="Profile id to check."),
    policy: Optional[Path] = typer.Option(
        None, "--policy", help="Optional policy artifact to verify."
    ),
    mode: str = typer.Option("normal", "--mode", help="Rule mode the policy was built for."),
    prior: str = typer.Option("uniform", "--prior", help="Prior the policy was built for."),
    attempts: int = typer.Option(6, "--attempts", help="Attempt limit the policy was built for."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Override data directory."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Run every health check; exit non-zero when one fails."""

    try:
        rule_mode = RuleMode(mode)
    except ValueError:
        fail(
            WordleError(
                f"unknown mode {mode!r}; choose normal, hard or superhard", code="invalid_mode"
            ),
            as_json=as_json,
        )
        return
    root = Path(data_dir) if data_dir is not None else Path("data")
    report = run_diagnostics(
        config_path=config,
        data_dir=root,
        profile_id=profile,
        policy_path=policy,
        mode=rule_mode,
        prior=prior,
        attempts=attempts,
    )
    if as_json:
        emit(report)
    else:
        for check in report["checks"]:
            typer.echo(f"{check['status'].upper():<7} {check['name']:<13} {check['message']}")
        summary = report["summary"]
        typer.echo(
            f"\n{summary.get('ok', 0)} ok, {summary.get('warn', 0)} warning(s), "
            f"{summary.get('fail', 0)} failure(s), {summary.get('blocked', 0)} blocked"
        )
    if report["status"] == "fail":
        fail(
            WordleError(
                "diagnose found failures; see the report above",
                code="diagnose_failed",
                exit_code=3,
            ),
            as_json=False,
        )


if __name__ == "__main__":  # pragma: no cover
    app()
