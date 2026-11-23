"""`wordle-ai strategy` commands: list the selectable strategies and their objectives."""

from __future__ import annotations

import typer

from ...strategy import describe
from ..output import emit


app = typer.Typer(no_args_is_help=True, help="Inspect the strategy registry.")


@app.command("list")
def list_strategies(
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """List every strategy name, its objective and whether it guesses only answers."""

    entries = describe()
    if as_json:
        emit({"strategies": entries})
        return
    width = max(len(str(entry["name"])) for entry in entries)
    for entry in entries:
        scope = "answers only" if entry["candidate_only"] else "all guesses"
        typer.echo(f"{str(entry['name']).ljust(width)}  {scope:<13}  {entry['objective']}")
