"""`wordle-ai play`: the solver assistant (Phase 7, criterion 1).

Three ways to use it:

* ``--answer WORD`` plays a whole game against a secret answer and prints every
  recommendation, its reason and the feedback.
* ``--history "salet:BBYBB,horse:GBGBB"`` replays a real game and recommends the next
  guess.
* no ``--answer``/``--history`` starts the interactive flow: the assistant recommends a
  guess, the player types the feedback the game gave, and it continues until solved, out
  of attempts, or Ctrl-C.

Every recommendation is shown with the strategy's own plain-language sentence and the
candidate count, so the player can disagree with it on the evidence rather than on
trust.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from ...api.service import RecommendationView, SolverService
from ...config import DEFAULT_CONFIG_PATH, load_config
from ...engine.prior import normalised_weights, parse_prior_id
from ...engine.table import open_rows
from ...errors import WordleError
from ...lexicon.profile import TABLE_NAME, load_profile
from ...solver.policy import load_policy
from ...types import Pattern, RuleMode, Turn
from ..output import emit, fail

app = typer.Typer(no_args_is_help=True, help="Play with an assistant that explains every guess.")


def _history(text: str) -> list[Turn]:
    turns: list[Turn] = []
    for entry in (part.strip() for part in text.replace(";", ",").split(",")):
        if not entry:
            continue
        if ":" not in entry:
            raise WordleError(
                f"history entry {entry!r} must look like guess:feedback, "
                "for example salet:BBYBB",
                code="invalid_history",
            )
        guess, feedback = entry.split(":", 1)
        try:
            pattern = Pattern.parse(feedback)
        except WordleError as exc:
            raise WordleError(f"{entry!r}: {exc}", code="invalid_history") from exc
        turns.append(Turn(guess=guess.strip().casefold(), pattern=pattern))
    if not turns:
        raise WordleError("--history is empty", code="invalid_history")
    return turns


def _print_recommendation(view: RecommendationView) -> None:
    typer.echo(
        f"  {view.guess.upper()}  ({view.strategy}, {view.elapsed_ms:.1f} ms, "
        f"{view.candidates_before:,} candidates)"
    )
    typer.echo(f"    {view.explanation}")


@app.command("play")
def play(
    profile: str = typer.Option("classic.en.5", "--profile", help="Profile id to play."),
    answer: Optional[str] = typer.Option(
        None, "--answer", help="Play a whole game against this secret answer."
    ),
    history: Optional[str] = typer.Option(
        None,
        "--history",
        help="Replay past turns as guess:feedback, e.g. 'salet:BBYBB,horse:GBGBB'.",
    ),
    strategy: str = typer.Option(
        "hybrid.balanced", "--strategy", help="Strategy to recommend with."
    ),
    policy: Optional[Path] = typer.Option(
        None, "--policy", help="Policy artifact when --strategy exact."
    ),
    mode: str = typer.Option("normal", "--mode", help="normal | hard | superhard"),
    attempts: int = typer.Option(6, "--attempts", help="Attempt limit."),
    prior: str = typer.Option("uniform", "--prior", help="Prior id (uniform by default)."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Override data directory."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Recommend a guess, with a plain-language reason."""

    try:
        settings = load_config(config)
        root = Path(data_dir) if data_dir is not None else Path(settings.general.data_dir)
        profile_dir = root / "processed" / profile
        loaded = load_profile(profile_dir)
        try:
            rule_mode = RuleMode(mode)
        except ValueError:
            raise WordleError(
                f"unknown mode {mode!r}; choose normal, hard or superhard", code="invalid_mode"
            ) from None
        if attempts < 1:
            raise WordleError("--attempts must be >= 1", code="invalid_attempts")
        table_path = profile_dir / TABLE_NAME
        rows = open_rows(loaded, table_path if table_path.exists() else None)
        prior_object = parse_prior_id(prior)
        weights = (
            None
            if prior.strip() in ("", "uniform")
            else normalised_weights(prior_object, loaded)
        )
        policy_payload = (
            load_policy(
                policy,
                profile=loaded,
                mode=rule_mode,
                prior=prior.strip() or "uniform",
                attempts=attempts,
            )
            if policy is not None
            else None
        )
        service = SolverService(
            loaded,
            rows=rows,
            strategy=strategy,
            mode=rule_mode,
            attempts=attempts,
            prior_weights=weights,
            policy=policy_payload,
        )
    except KeyError as exc:
        fail(WordleError(str(exc), code="unknown_strategy"), as_json=as_json)
        return
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return

    if answer is not None:
        _play_answer(service, loaded, answer, as_json=as_json)
        return
    if history is not None:
        try:
            turns = _history(history)
        except WordleError as exc:
            fail(exc, as_json=as_json)
            return
        _advise_after_history(service, turns, as_json=as_json)
        return
    _interactive(service, as_json=as_json)


def _play_answer(service: SolverService, profile, answer: str, *, as_json: bool) -> None:
    word = answer.strip().casefold()
    if word not in profile.answer_index:
        fail(
            WordleError(
                f"{word!r} is not an answer of {profile.profile_id}", code="unknown_answer"
            ),
            as_json=as_json,
        )
        return
    turns, solved = service.play(word)
    if as_json:
        emit(
            {
                "mode": "answer",
                "profile_id": profile.profile_id,
                "answer": word,
                "solved": solved,
                "turns": turns,
                "n_guesses": len(turns),
            }
        )
        return
    typer.echo(f"{profile.profile_id}: playing answer {word!r}")
    for turn in turns:
        recommendation = turn["recommendation"]
        typer.echo(f"turn {turn['turn']}  {turn['remaining_before']:,} candidates")
        typer.echo(
            f"  {recommendation['guess'].upper()}  ({recommendation['strategy']}, "
            f"{recommendation['elapsed_ms']:.1f} ms)"
        )
        typer.echo(f"    {recommendation['explanation']}")
        typer.echo(f"    feedback {turn['pattern']}")
    typer.echo("solved" if solved else f"not solved in {service.attempts} guesses")


def _advise_after_history(
    service: SolverService, history: list[Turn], *, as_json: bool
) -> None:
    try:
        state = service.turns(history)
    except WordleError as exc:
        fail(WordleError(str(exc), code="invalid_history"), as_json=as_json)
        return
    if state.is_solved():
        if as_json:
            emit({"solved": True, "history": service.view(state).to_dict()})
        else:
            typer.echo("That history is already solved — nothing left to guess.")
        return
    if state.attempts_left <= 0:
        fail(
            WordleError("no attempts remain in that history", code="game_over"),
            as_json=as_json,
        )
        return
    recommendation = service.recommend(state)
    view = service.view(state)
    if as_json:
        emit(
            {
                "mode": "history",
                "state": view.to_dict(),
                "recommendation": recommendation.to_dict(),
            }
        )
        return
    for turn in history:
        typer.echo(f"  {turn.guess.upper()}  {turn.pattern.render()}")
    typer.echo(
        f"{view.remaining:,} candidates remain ({view.attempts_left} attempts left)"
    )
    _print_recommendation(recommendation)


@app.command("selfplay")
def selfplay(
    profile: str = typer.Option("classic.en.5", "--profile", help="Profile id to play."),
    games: int = typer.Option(1, "--games", help="Play the first N answers (deterministic prefix)."),
    strategy: str = typer.Option(
        "hybrid.balanced", "--strategy", help="Strategy to play with."
    ),
    mode: str = typer.Option("normal", "--mode", help="normal | hard | superhard"),
    attempts: int = typer.Option(6, "--attempts", help="Attempt limit."),
    prior: str = typer.Option("uniform", "--prior", help="Prior id (uniform by default)."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Override data directory."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Self-play: a visible trace for one game, aggregates for many."""

    try:
        settings = load_config(config)
        root = Path(data_dir) if data_dir is not None else Path(settings.general.data_dir)
        profile_dir = root / "processed" / profile
        loaded = load_profile(profile_dir)
        try:
            rule_mode = RuleMode(mode)
        except ValueError:
            raise WordleError(
                f"unknown mode {mode!r}; choose normal, hard or superhard", code="invalid_mode"
            ) from None
        if games < 1:
            raise WordleError("--games must be >= 1", code="invalid_games")
        if games > len(loaded.answers):
            raise WordleError(
                f"--games {games} exceeds the {len(loaded.answers)} answers of "
                f"{loaded.profile_id}",
                code="invalid_games",
            )
        if attempts < 1:
            raise WordleError("--attempts must be >= 1", code="invalid_attempts")
        table_path = profile_dir / TABLE_NAME
        rows = open_rows(loaded, table_path if table_path.exists() else None)
        prior_object = parse_prior_id(prior)
        weights = (
            None
            if prior.strip() in ("", "uniform")
            else normalised_weights(prior_object, loaded)
        )
        service = SolverService(
            loaded,
            rows=rows,
            strategy=strategy,
            mode=rule_mode,
            attempts=attempts,
            prior_weights=weights,
            top_candidates=0,
        )
        selected = loaded.answers[:games]
        results = []
        for answer in selected:
            turns, solved = service.play(answer)
            results.append(
                {
                    "answer": answer,
                    "solved": solved,
                    "n_guesses": len(turns),
                    "guesses": [turn["guess"] for turn in turns],
                }
            )
    except KeyError as exc:
        fail(WordleError(str(exc), code="unknown_strategy"), as_json=as_json)
        return
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return

    solved = sum(1 for row in results if row["solved"])
    distribution: dict[int, int] = {}
    for row in results:
        if row["solved"]:
            distribution[row["n_guesses"]] = distribution.get(row["n_guesses"], 0) + 1
    summary = {
        "profile_id": loaded.profile_id,
        "strategy": strategy,
        "rules": rule_mode.value,
        "prior": prior.strip() or "uniform",
        "answer_set_id": f"{loaded.profile_id}.first{games}",
        "games": games,
        "solved": solved,
        "failed": games - solved,
        "success_rate": solved / games,
        "avg_guesses_solved": (
            sum(row["n_guesses"] for row in results if row["solved"]) / solved
            if solved
            else None
        ),
        "worst_case": max((row["n_guesses"] for row in results if row["solved"]), default=None),
        "distribution": {str(k): v for k, v in sorted(distribution.items())},
    }
    if as_json:
        emit({**summary, "results": results})
        return
    if games == 1:
        row = results[0]
        typer.echo(
            f"{loaded.profile_id}: answer {row['answer']!r}, {strategy}, "
            f"{rule_mode.value} rules"
        )
        for number, guess in enumerate(row["guesses"], 1):
            typer.echo(f"  {number}. {guess.upper()}")
        typer.echo("solved" if row["solved"] else f"not solved in {attempts} guesses")
        return
    typer.echo(
        f"{loaded.profile_id}: {games} games ({summary['answer_set_id']}), "
        f"{strategy}, {rule_mode.value} rules, prior={summary['prior']}"
    )
    typer.echo(
        f"  solved {solved}/{games} ({summary['success_rate'] * 100:.2f}%), "
        f"average {summary['avg_guesses_solved']:.4f} guesses, "
        f"worst {summary['worst_case']}"
    )
    for n_guesses, count in sorted(distribution.items()):
        typer.echo(f"  {n_guesses} guesses: {count}")


def _interactive(service: SolverService, *, as_json: bool) -> None:
    state = service.new_game()
    typer.echo(
        f"{service.profile.profile_id}: {state.remaining:,} possible answers, "
        f"{service.attempts} attempts, {service.mode.value} rules"
    )
    while state.attempts_left > 0 and not state.is_solved():
        _print_recommendation(service.recommend(state))
        try:
            guess = typer.prompt("  your guess").strip().casefold()
            feedback = typer.prompt("  feedback (B/Y/G or 0/1/2)")
        except (KeyboardInterrupt, EOFError):  # pragma: no cover - interactive
            typer.echo("\nstopped")
            return
        try:
            state = state.apply(guess, Pattern.parse(feedback), table=service.rows)
        except WordleError as exc:
            typer.echo(f"  {exc}; try again")
            continue
    typer.echo("solved" if state.is_solved() else "no attempts left")


if __name__ == "__main__":  # pragma: no cover
    app()
