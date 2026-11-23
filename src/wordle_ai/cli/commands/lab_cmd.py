"""`wordle-ai lab`: the Strategy and Dictionary Laboratories (Phase 7, tasks 3–4).

Both labs are read-only views over the service layer. The Strategy Laboratory asks
every requested strategy for its choice on one state and reports the numbers and the
disagreements; the Dictionary Laboratory explains why one word is or is not in the
profile's lists. No solving logic lives here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from ...api.service import compare_strategies, dictionary_report
from ...config import DEFAULT_CONFIG_PATH, load_config
from ...engine.prior import normalised_weights, parse_prior_id
from ...engine.table import open_rows
from ...errors import WordleError
from ...lexicon.profile import TABLE_NAME, load_profile
from ...strategy import HEURISTIC_STRATEGY_NAMES, get_strategy
from ...types import RuleMode
from ..output import emit, fail
from .play_cmd import _history

app = typer.Typer(no_args_is_help=True, help="Compare strategies and inspect the dictionary.")


def _load(profile: str, config: Path, data_dir: Optional[Path]):
    settings = load_config(config)
    root = Path(data_dir) if data_dir is not None else Path(settings.general.data_dir)
    profile_dir = root / "processed" / profile
    loaded = load_profile(profile_dir)
    table_path = profile_dir / TABLE_NAME
    rows = open_rows(loaded, table_path if table_path.exists() else None)
    return loaded, rows, profile_dir


@app.command("strategies")
def strategies(
    profile: str = typer.Option("classic.en.5", "--profile", help="Profile id to inspect."),
    history: Optional[str] = typer.Option(
        None, "--history", help="State to inspect as guess:feedback, e.g. 'salet:BBYBB'."
    ),
    names: str = typer.Option(
        "all", "--strategies", help="'all' or a comma-separated list of strategy names."
    ),
    mode: str = typer.Option("normal", "--mode", help="normal | hard | superhard"),
    attempts: int = typer.Option(6, "--attempts", help="Attempt limit for the state."),
    prior: str = typer.Option("uniform", "--prior", help="Prior id (uniform by default)."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Override data directory."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Run several strategies on one state and show where they disagree."""

    try:
        loaded, rows, _ = _load(profile, config, data_dir)
        try:
            rule_mode = RuleMode(mode)
        except ValueError:
            raise WordleError(
                f"unknown mode {mode!r}; choose normal, hard or superhard", code="invalid_mode"
            ) from None
        if attempts < 1:
            raise WordleError("--attempts must be >= 1", code="invalid_attempts")
        selected = (
            list(HEURISTIC_STRATEGY_NAMES)
            if names.strip().lower() == "all"
            else [name.strip() for name in names.split(",") if name.strip()]
        )
        for name in selected:
            get_strategy(name)  # validate before any scoring work starts
        prior_object = parse_prior_id(prior)
        weights = (
            None
            if prior.strip() in ("", "uniform")
            else normalised_weights(prior_object, loaded)
        )
        from ...api.service import SolverService

        service = SolverService(
            loaded,
            rows=rows,
            strategy="hybrid.balanced",
            mode=rule_mode,
            attempts=attempts,
            prior_weights=weights,
            top_candidates=0,
        )
        state = service.turns(_history(history)) if history else service.new_game()
        report = compare_strategies(service, state, selected)
    except KeyError as exc:
        fail(WordleError(str(exc), code="unknown_strategy"), as_json=as_json)
        return
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return

    if as_json:
        emit(report)
        return
    state = report["state"]
    typer.echo(
        f"{state['profile_id']}: {state['remaining']:,} candidates, "
        f"{state['attempts_left']} attempts left, {state['mode']} rules"
    )
    header = f"{'strategy':<26} {'guess':<7} {'exp':>7} {'worst':>6} {'p_solve':>8} {'ms':>8}"
    typer.echo(header)
    typer.echo("-" * len(header))
    for entry in report["results"]:
        typer.echo(
            f"{entry['strategy']:<26} {entry['guess'].upper():<7} "
            f"{entry['expected_remaining']:>7.2f} {entry['worst_case']:>6.0f} "
            f"{entry['p_solve_now'] * 100:>7.2f}% {entry['elapsed_ms']:>8.1f}"
        )
    typer.echo("")
    typer.echo(
        f"{len(report['distinct_guesses'])} distinct guesses, "
        f"{report['pairwise_disagreements']} disagreeing strategy pairs"
    )
    for group in report["groups"]:
        typer.echo(
            f"  {group['guess'].upper()}: {', '.join(group['strategies'])} "
            f"(expected {group['expected_remaining']:.2f}, worst {group['worst_case']:.0f})"
        )


@app.command("dictionary")
def dictionary(
    word: str = typer.Argument(..., help="The word to explain."),
    profile: str = typer.Option("classic.en.5", "--profile", help="Profile id to inspect."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Override data directory."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Explain why a word is or is not in this profile's lists."""

    try:
        loaded, _, _ = _load(profile, config, data_dir)
        report = dictionary_report(loaded, word)
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return

    if as_json:
        emit(report)
        return
    typer.echo(f"{report['profile_id']} ({report['answers']:,} answers, "
               f"{report['guesses']:,} legal guesses)")
    typer.echo(f"  {report['explanation']}")
    typer.echo(
        f"  in guesses: {'yes' if report['in_guesses'] else 'no'}; "
        f"in answers: {'yes' if report['in_answers'] else 'no'}"
    )


if __name__ == "__main__":  # pragma: no cover
    app()
