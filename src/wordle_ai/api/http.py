"""Optional HTTP adapter over ``SolverService`` (Phase 7, task 7).

No solver logic lives here: the adapter parses requests into the same service calls the
terminal uses, and returns the service's views. That is what lets one integration test
suite run against both surfaces and compare decisions.

Install with the ``http`` extra (``pip install 'wordle-ai[http]'``); the module imports
FastAPI lazily so the CLI never needs it. Run it with::

    uvicorn "wordle_ai.api.http:app_from_profile" --factory ...
"""

from __future__ import annotations

from typing import Sequence

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ..errors import WordleError
from ..types import Pattern, Profile, Turn
from .service import compare_strategies, dictionary_report
from .service import SolverService


class TurnModel(BaseModel):
    guess: str
    feedback: str = Field(min_length=1, description="B/Y/G or 0/1/2 feedback")


class HistoryRequest(BaseModel):
    history: list[TurnModel] = Field(default_factory=list)


class CompareRequest(HistoryRequest):
    strategies: list[str] | None = None


class DictionaryRequest(BaseModel):
    word: str


def _turns(service: SolverService, history: Sequence[TurnModel]) -> tuple:
    turns: list[Turn] = []
    for entry in history:
        try:
            turns.append(
                Turn(
                    guess=service.profile.validate_guess(entry.guess),
                    pattern=Pattern.parse(entry.feedback, service.profile.alphabet),
                )
            )
        except WordleError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return tuple(turns)


def _state(service: SolverService, history: Sequence[TurnModel]):
    try:
        return service.turns(_turns(service, history))
    except WordleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def create_app(service: SolverService) -> FastAPI:
    """Build an application bound to one profile/strategy service."""

    app = FastAPI(
        title="Wordle assistant",
        version="0.1.0",
        description="Recommendations from the same service the terminal assistant uses.",
    )

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "profile_id": service.profile.profile_id,
            "strategy": service.strategy.name,
            "answers": len(service.profile.answers),
        }

    @app.get("/profile")
    def profile() -> dict:
        return {
            "profile_id": service.profile.profile_id,
            "length": service.profile.length,
            "alphabet": service.profile.alphabet,
            "answers": len(service.profile.answers),
            "guesses": len(service.profile.guesses),
            "rules": service.mode.value,
            "attempts": service.attempts,
        }

    @app.post("/recommend")
    def recommend(request: HistoryRequest) -> dict:
        state = _state(service, request.history)
        if state.is_solved():
            return {
                "state": service.view(state).to_dict(),
                "recommendation": None,
                "solved": True,
            }
        if state.attempts_left <= 0:
            raise HTTPException(status_code=409, detail="no attempts remain")
        recommendation = service.recommend(state)
        return {
            "state": service.view(state).to_dict(),
            "recommendation": recommendation.to_dict(),
            "solved": False,
        }

    @app.post("/compare")
    def compare(request: CompareRequest) -> dict:
        state = _state(service, request.history)
        try:
            return compare_strategies(service, state, request.strategies)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/dictionary")
    def dictionary(request: DictionaryRequest) -> dict:
        return dictionary_report(service.profile, request.word)

    return app


def app_from_profile(
    profile: Profile,
    *,
    strategy: str = "hybrid.balanced",
    attempts: int = 6,
    rows=None,
) -> FastAPI:
    """Factory for ``uvicorn --factory``; the caller supplies the loaded profile."""

    return create_app(
        SolverService(profile, rows=rows, strategy=strategy, attempts=attempts)
    )


__all__ = [
    "CompareRequest",
    "DictionaryRequest",
    "HistoryRequest",
    "TurnModel",
    "app_from_profile",
    "create_app",
]
