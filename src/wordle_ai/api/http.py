"""HTTP and Web GUI adapter over ``SolverService`` (Phase 7 & Web GUI).

No solver logic lives here: the adapter parses requests into the same service calls the
terminal uses, and returns the service's views. That is what lets one integration test
suite run against both surfaces and compare decisions.

Provides:
- Interactive Single-Page Application (SPA) Web GUI at ``GET /`` and ``GET /app``.
- REST API for live copilot recommendations (``/recommend``, ``/api/recommend``).
- Strategy Arena multi-algorithm comparisons (``/compare``, ``/api/compare``).
- AI self-play simulation (``/api/simulate``).
- Lexicon validation (``/dictionary``, ``/api/dictionary``).
- Phase 6 ML gate summary & model status (``/api/ml/summary``).
- Random target word generation (``/api/random-word``).
"""

from __future__ import annotations

import json
from pathlib import Path
import random
from typing import Sequence

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..errors import WordleError
from ..strategy import HEURISTIC_STRATEGY_NAMES, get_strategy
from ..strategy.exact import ExactStrategy
from ..types import Pattern, Profile, Turn
from .service import RecommendationView, SolverService, compare_strategies, dictionary_report
from .web_gui import WEB_GUI_HTML


class TurnModel(BaseModel):
    guess: str
    feedback: str = Field(min_length=1, description="B/Y/G or 0/1/2 feedback")


class HistoryRequest(BaseModel):
    history: list[TurnModel] = Field(default_factory=list)
    strategy: str | None = None


class CompareRequest(HistoryRequest):
    strategies: list[str] | None = None


class DictionaryRequest(BaseModel):
    word: str


class SimulateRequest(BaseModel):
    answer: str
    strategy: str = "hybrid.balanced"


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


def create_app(service: SolverService, *, policy: dict | None = None) -> FastAPI:
    """Build an application bound to one profile/strategy service and Web GUI."""

    # Resolve policy if available
    active_policy = policy or getattr(service, "policy", None)
    if active_policy is None and isinstance(service.strategy, ExactStrategy):
        active_policy = service.strategy.policy
    if active_policy is None:
        default_policy = Path("policies") / f"{service.profile.profile_id}.normal.uniform.policy.json"
        if default_policy.exists():
            try:
                from ..solver.policy import load_policy
                active_policy = load_policy(default_policy, profile=service.profile, verify=False)
            except Exception:
                active_policy = None
    if active_policy is not None:
        service.policy = active_policy

    app = FastAPI(
        title="Wordle AI — Studio & Copilot",
        version="1.0.0",
        description="Wordle assistant and strategy laboratory backed by SolverService.",
    )

    # Web GUI routes
    @app.get("/", response_class=HTMLResponse)
    @app.get("/app", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(WEB_GUI_HTML)

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

    def _handle_recommend(request: HistoryRequest) -> dict:
        state = _state(service, request.history)
        if state.is_solved():
            return {
                "state": service.view(state).to_dict(),
                "recommendation": None,
                "solved": True,
            }
        if state.attempts_left <= 0:
            raise HTTPException(status_code=409, detail="no attempts remain")

        # Determine strategy to use
        strat = service.strategy
        if request.strategy and request.strategy != service.strategy.name:
            try:
                if request.strategy == "exact":
                    if active_policy is None:
                        raise HTTPException(
                            status_code=400,
                            detail="Exact strategy requires a policy artifact; none found.",
                        )
                    strat = get_strategy("exact", policy=active_policy)
                else:
                    strat = get_strategy(request.strategy, prior_weights=service.prior_weights)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        rec = RecommendationView.from_decision(
            strat.choose(state, service.rows, cache=service._cache)
        )
        return {
            "state": service.view(state).to_dict(),
            "recommendation": rec.to_dict(),
            "solved": False,
        }

    @app.post("/recommend")
    @app.post("/api/recommend")
    def recommend(request: HistoryRequest) -> dict:
        return _handle_recommend(request)

    def _handle_compare(request: CompareRequest) -> dict:
        state = _state(service, request.history)
        try:
            return compare_strategies(service, state, request.strategies)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/compare")
    @app.post("/api/compare")
    def compare(request: CompareRequest) -> dict:
        return _handle_compare(request)

    def _handle_dictionary(request: DictionaryRequest) -> dict:
        rep = dictionary_report(service.profile, request.word)
        rep["is_answer"] = rep.get("in_answers", False)
        rep["is_guess"] = rep.get("in_guesses", False)
        return rep

    @app.post("/dictionary")
    @app.post("/api/dictionary")
    def dictionary(request: DictionaryRequest) -> dict:
        return _handle_dictionary(request)

    @app.get("/api/random-word")
    def random_word() -> dict:
        return {"word": random.choice(service.profile.answers)}

    @app.post("/api/simulate")
    def simulate(request: SimulateRequest) -> dict:
        word = request.answer.lower().strip()
        if word not in service.profile.answer_index:
            raise HTTPException(status_code=400, detail=f"'{word}' is not in the answer bank.")

        strat_name = request.strategy or "hybrid.balanced"
        if strat_name == "exact":
            if active_policy is None:
                raise HTTPException(status_code=400, detail="Exact strategy requires policy artifact.")
            sim_strategy = get_strategy("exact", policy=active_policy)
        else:
            try:
                sim_strategy = get_strategy(strat_name, prior_weights=service.prior_weights)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        state = service.new_game()
        turns: list[dict] = []
        solved = False

        while state.attempts_left > 0:
            remaining_before = state.remaining
            decision = sim_strategy.choose(state, service.rows)
            rec = RecommendationView.from_decision(decision)
            pattern = service._feedback(rec.guess, word)
            is_win = rec.guess == word
            next_state = state.apply(rec.guess, pattern, table=service.rows)

            turns.append({
                "turn": state.attempts_used + 1,
                "guess": rec.guess,
                "pattern": pattern.render(),
                "remaining_before": remaining_before,
                "remaining_after": next_state.remaining if not is_win else 1,
                "explanation": rec.explanation,
                "elapsed_ms": rec.elapsed_ms,
                "solved": is_win,
            })

            state = next_state
            if is_win:
                solved = True
                break

        return {
            "answer": word,
            "strategy": strat_name,
            "solved": solved,
            "turns": turns,
            "total_turns": len(turns),
        }

    @app.get("/api/ml/summary")
    def ml_summary() -> dict:
        reports = {}
        for mod in ("ml.value_lookahead", "ml.policy_ranker"):
            report_file = Path("docs") / f"gate_report_{mod.replace('.', '_')}.json"
            if report_file.exists():
                try:
                    reports[mod] = json.loads(report_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
        return {
            "profile_id": service.profile.profile_id,
            "gate_reports": reports,
            "models_present": {
                "value_network": Path("models/value_network.pt").exists(),
                "value_regressor": Path("models/value_regressor.joblib").exists(),
                "policy_ranker": Path("models/policy_ranker.joblib").exists(),
            },
        }

    return app


def app_from_profile(
    profile: Profile,
    *,
    strategy: str = "hybrid.balanced",
    attempts: int = 6,
    rows=None,
    policy: dict | None = None,
) -> FastAPI:
    """Factory for ``uvicorn --factory``; the caller supplies the loaded profile."""

    return create_app(
        SolverService(profile, rows=rows, strategy=strategy, attempts=attempts, policy=policy),
        policy=policy,
    )


__all__ = [
    "CompareRequest",
    "DictionaryRequest",
    "HistoryRequest",
    "SimulateRequest",
    "TurnModel",
    "app_from_profile",
    "create_app",
]
