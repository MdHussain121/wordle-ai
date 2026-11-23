"""`wordle-ai config` commands."""

from __future__ import annotations

from pathlib import Path

import typer

from ...config import DEFAULT_CONFIG_PATH, dump_settings, load_config
from ...errors import WordleError
from ..output import emit, fail

app = typer.Typer(no_args_is_help=True, help="Inspect and validate configuration.")


@app.command("show")
def show(
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Print the effective configuration."""

    try:
        settings = load_config(config)
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return
    payload = dump_settings(settings)
    if as_json:
        emit(payload)
        return
    typer.echo(f"config: {config}")
    for section, values in payload.items():
        if isinstance(values, dict):
            typer.echo(f"[{section}]")
            for key, value in sorted(values.items()):
                typer.echo(f"  {key} = {value!r}")
        else:  # pragma: no cover - every section is a table
            typer.echo(f"{section} = {values!r}")


@app.command("validate")
def validate(
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Validate configuration and exit non-zero on any problem."""

    try:
        settings = load_config(config)
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return
    payload = {
        "valid": True,
        "path": str(config),
        "families": sorted(settings.profiles),
        "alphabet": settings.profile.alphabet,
        "length": settings.profile.length,
        "table_policy": settings.feedback.build_policy,
    }
    if as_json:
        emit(payload)
    else:
        typer.echo(
            f"valid: {config} ({len(settings.profiles)} families: "
            f"{', '.join(sorted(settings.profiles))})"
        )
