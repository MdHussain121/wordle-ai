"""Build metadata printed by ``wordle-ai --version`` and checked by ``diagnose``.

The package version has one source (``wordle_ai.__version__``) which also feeds
``importlib.metadata`` when the package is installed. Everything else here is read from
the running interpreter rather than copied into a file, so a stale string cannot drift.
"""

from __future__ import annotations

import importlib.metadata
import platform
import sys

from . import __version__


def _installed_version() -> str:
    try:
        return importlib.metadata.version("wordle-ai")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - source tree
        return __version__


def dependency_versions() -> dict[str, str]:
    """Versions of the runtime and optional dependencies that are installed."""

    names = (
        "numpy",
        "pydantic",
        "typer",
        "wordfreq",
        "fastapi",
        "uvicorn",
        "httpx",
    )
    out: dict[str, str] = {}
    for name in names:
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    return out


def build_info() -> dict:
    """A small, stable dictionary for humans and ``--json`` consumers."""

    return {
        "name": "wordle-ai",
        "version": _installed_version(),
        "source_version": __version__,
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "dependencies": dependency_versions(),
    }


def version_line() -> str:
    info = build_info()
    deps = ", ".join(f"{name} {version}" for name, version in sorted(info["dependencies"].items()))
    return (
        f"wordle-ai {info['version']} (python {info['python']}, "
        f"{info['implementation']}, {info['platform']}; {deps})"
    )


__all__ = ["build_info", "dependency_versions", "version_line"]
