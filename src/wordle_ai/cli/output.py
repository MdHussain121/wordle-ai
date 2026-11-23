"""Shared CLI output helpers, kept separate from the app to avoid import cycles."""

from __future__ import annotations

import json

import typer

from ..errors import WordleError


def emit(payload: dict) -> None:
    typer.echo(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True))


def fail(exc: WordleError, *, as_json: bool = False) -> None:
    if as_json:
        emit(exc.to_dict())
    else:
        typer.secho(f"error [{exc.code}]: {exc.message}", err=True, fg=typer.colors.RED)
        for key, value in sorted(exc.context.items()):
            typer.secho(f"  {key}: {value}", err=True, fg=typer.colors.RED)
    raise typer.Exit(exc.exit_code)
