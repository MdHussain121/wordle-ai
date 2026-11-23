"""`wordle-ai prior` commands: calibrate and inspect answer priors (Phase 5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from ...bench.calibration import (
    DEFAULT_BETA_GRID,
    calibrate_prior,
    calibrate_zipf,
    markdown,
    split_answers,
)
from ...config import DEFAULT_CONFIG_PATH, load_config
from ...engine.prior import (
    EmpiricalPrior,
    UniformPrior,
    ZipfPrior,
    normalised_weights,
    parse_prior_id,
)
from ...errors import WordleError
from ...lexicon.profile import load_profile
from ..output import emit, fail

app = typer.Typer(no_args_is_help=True, help="Calibrate answer priors against held-out answers.")


def _grid(text: str) -> tuple[float, ...]:
    values = [part.strip() for part in text.split(",") if part.strip()]
    if not values:
        raise WordleError("--beta-grid is empty", code="invalid_prior")
    try:
        grid = tuple(float(value) for value in values)
    except ValueError:
        raise WordleError(
            f"invalid --beta-grid {text!r}; use comma-separated numbers",
            code="invalid_prior",
        ) from None
    if any(beta < 0 for beta in grid):
        raise WordleError("--beta-grid values must be >= 0", code="invalid_prior")
    return grid


@app.command("calibrate")
def calibrate(
    profile: str = typer.Option("classic.en.5", "--profile", help="Profile id to calibrate on."),
    prior: str = typer.Option(
        "zipf",
        "--prior",
        help="uniform | zipf | zipf:<beta> | empirical:<history path>. "
        "'zipf' fits beta on the validation half.",
    ),
    beta: Optional[float] = typer.Option(
        None, "--beta", help="Fix the Zipf temperature instead of fitting it."
    ),
    beta_grid: str = typer.Option(
        ",".join(f"{value:g}" for value in DEFAULT_BETA_GRID),
        "--beta-grid",
        help="Comma-separated beta candidates for the validation fit.",
    ),
    validation_percent: int = typer.Option(
        50, "--validation-percent", help="Share of answers used for fitting (1–99)."
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Directory for calibration.json and calibration_report.md."
    ),
    require_admitted: bool = typer.Option(
        False, "--require-admitted", help="Exit non-zero when the prior is rejected."
    ),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Override data directory."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Measure a prior on a held-out answer half and apply the admission gate."""

    try:
        settings = load_config(config)
        root = Path(data_dir) if data_dir is not None else Path(settings.general.data_dir)
        loaded = load_profile(root / "processed" / profile)
        split = split_answers(loaded, validation_percent=validation_percent)
        if prior.strip() == "zipf" and beta is None:
            verdict = calibrate_zipf(loaded, grid=_grid(beta_grid), split=split)
        else:
            chosen = parse_prior_id(prior)
            if beta is not None:
                if not isinstance(chosen, ZipfPrior):
                    raise WordleError(
                        "--beta only applies to the zipf prior", code="invalid_prior"
                    )
                chosen = ZipfPrior(beta)
            if isinstance(chosen, (ZipfPrior, EmpiricalPrior, UniformPrior)):
                normalised_weights(chosen, loaded)  # fail early on a bad prior
            verdict = calibrate_prior(loaded, chosen, split=split)
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return

    text = markdown(verdict)
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "calibration.json").write_text(
            json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
        (out / "calibration_report.md").write_text(text, encoding="utf-8", newline="\n")
    if as_json:
        emit(verdict)
        return
    typer.echo(text)
    if out is not None:
        typer.echo(f"wrote {out / 'calibration.json'} and {out / 'calibration_report.md'}")
    if require_admitted and not verdict["admitted"]:
        fail(
            WordleError(
                f"prior {verdict['prior_id']} was rejected: {verdict['reject_reason']}",
                code="prior_calibration",
            ),
            as_json=False,
        )


@app.command("show")
def show(
    profile: str = typer.Option("classic.en.5", "--profile", help="Profile id to inspect."),
    prior: str = typer.Option("uniform", "--prior", help="Prior id, as in `prior calibrate`."),
    top: int = typer.Option(10, "--top", help="How many most/least likely answers to show."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Override data directory."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Show the normalised prior over a profile's answers (no calibration)."""

    try:
        settings = load_config(config)
        root = Path(data_dir) if data_dir is not None else Path(settings.general.data_dir)
        loaded = load_profile(root / "processed" / profile)
        chosen = parse_prior_id(prior)
        weights = normalised_weights(chosen, loaded)
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return

    order = weights.argsort()[::-1]
    summary = {
        "profile_id": loaded.profile_id,
        "prior_id": chosen.prior_id,
        "answers": len(loaded.answers),
        "top": [
            {"word": loaded.answers[int(index)], "probability": float(weights[index])}
            for index in order[: max(1, top)]
        ],
        "bottom": [
            {"word": loaded.answers[int(index)], "probability": float(weights[index])}
            for index in order[-max(1, top) :][::-1]
        ],
    }
    if as_json:
        emit(summary)
        return
    typer.echo(f"{loaded.profile_id}: prior {chosen.prior_id} over {len(loaded.answers)} answers")
    for entry in summary["top"]:
        typer.echo(f"  {entry['word']}  {entry['probability']:.6f}")
    typer.echo("  ...")
    for entry in summary["bottom"]:
        typer.echo(f"  {entry['word']}  {entry['probability']:.6f}")


if __name__ == "__main__":  # pragma: no cover
    app()
