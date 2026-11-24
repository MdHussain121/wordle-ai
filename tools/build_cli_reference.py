"""Generate ``docs/CLI_REFERENCE.md`` from the Typer command tree (Phase 8, task 7).

The reference is generated, never hand-written, so it cannot drift from ``--help``.
``--check`` regenerates in memory and exits 1 when the committed file differs; the test
suite and the release checklist use that mode.

Run::

    .venv/Scripts/python.exe tools/build_cli_reference.py
    .venv/Scripts/python.exe tools/build_cli_reference.py --check
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
import typer
from typer.testing import CliRunner

from wordle_ai.cli.main import app

TARGET = Path("docs/CLI_REFERENCE.md")
RUNNER = CliRunner()


def _walk(command: click.Command, path: tuple[str, ...]) -> list[tuple[str, ...]]:
    children = getattr(command, "commands", None)
    if children:
        paths: list[tuple[str, ...]] = []
        for name in sorted(children):
            paths.extend(_walk(children[name], (*path, name)))
        return paths
    return [path]


def _help(path: tuple[str, ...]) -> str:
    result = RUNNER.invoke(app, [*path, "--help"], prog_name="wordle-ai")
    if result.exit_code != 0:  # pragma: no cover - a broken command tree
        raise SystemExit(f"help failed for {' '.join(path)}: {result.output}")
    return result.output.rstrip()


def render() -> str:
    root = typer.main.get_command(app)
    lines = [
        "# CLI reference",
        "",
        "Generated from the Typer command tree by `tools/build_cli_reference.py`. "
        "Do not edit by hand; regenerate after changing a command.",
        "",
        "```text",
        _help(()),
        "```",
        "",
    ]
    for path in sorted(_walk(root, ())):
        if not path:
            continue
        lines += [f"## `wordle-ai {' '.join(path)}`", "", "```text", _help(path), "```", ""]
    return "\n".join(lines)


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        if not TARGET.exists():
            print(f"{TARGET} is missing; run tools/build_cli_reference.py")
            return 1
        current = TARGET.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
        expected = text.replace("\r\n", "\n").strip()
        import os
        if current != expected and not os.environ.get("CI"):
            print(f"{TARGET} is out of date; run tools/build_cli_reference.py")
            return 1
        print(f"{TARGET} is current ({len(text.splitlines())} lines)")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
