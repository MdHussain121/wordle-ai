"""CLI entry point (technical specification §12.1).

Every repeatable operation is reachable here. Commands print a stable human summary, or
the documented JSON shape with ``--json``, and map typed errors to the exit codes in
``wordle_ai.errors``: 0 success, 1 usage, 2 missing/unsupported input, 3 integrity,
4 budget, 5 artifact mismatch.
"""

from __future__ import annotations

import typer

from ..buildinfo import build_info, version_line
from .commands import bench, config_cmd, lab_cmd, lex, ml_cmd, policy_cmd, prior_cmd, strategy_cmd, web_cmd
from .commands.diagnose_cmd import diagnose as diagnose_command
from .commands.play_cmd import play as play_command, selfplay as selfplay_command
from .commands.web_cmd import web as web_command
from .output import emit

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Wordle-solving AI: lexicon pipeline, feedback engine and strategy harness.",
)
app.add_typer(lex.app, name="lex")
app.add_typer(config_cmd.app, name="config")
app.add_typer(bench.app, name="bench")
app.add_typer(strategy_cmd.app, name="strategy")
app.add_typer(policy_cmd.app, name="policy")
app.add_typer(prior_cmd.app, name="prior")
app.add_typer(lab_cmd.app, name="lab")
app.add_typer(ml_cmd.app, name="ml")
# Root commands, not groups: `wordle-ai play ...`, not `play play`.
app.command("play")(play_command)
app.command("selfplay")(selfplay_command)
app.command("diagnose")(diagnose_command)
app.command("web")(web_command)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(version_line())
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print build metadata and exit.",
    ),
) -> None:
    """Wordle-solving AI: lexicon pipeline, feedback engine and strategy harness."""


@app.command("version")
def version() -> None:
    """Print the package version and schema version."""

    from ..lexicon.manifest import GENERATOR_VERSION, SCHEMA_VERSION

    emit(
        {
            "version": GENERATOR_VERSION,
            "manifest_schema_version": SCHEMA_VERSION,
            "build": build_info(),
        }
    )


if __name__ == "__main__":  # pragma: no cover
    app()
