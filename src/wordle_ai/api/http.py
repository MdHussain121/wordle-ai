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

from dataclasses import replace
import json
from pathlib import Path
import random
from typing import Sequence

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..errors import ArtifactMismatchError, InconsistentFeedback, ProfileIntegrityError, WordleError
from ..strategy import get_strategy
from ..strategy.exact import ExactStrategy
from ..types import Pattern, Profile, Turn
from .service import RecommendationView, SolverService, compare_strategies, dictionary_report


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

    # Enable CORS for React frontend (Vite dev server or custom port)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Web GUI routes / static files
    dist_dir = Path("web") / "dist"
    if dist_dir.exists():
        app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

    @app.get("/", response_class=HTMLResponse)
    @app.get("/app", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        dist_index = Path("web") / "dist" / "index.html"
        if dist_index.exists():
            return HTMLResponse(dist_index.read_text(encoding="utf-8"))
        return HTMLResponse(
            "<!DOCTYPE html><html><head><title>Wordle AI API</title></head>"
            "<body style='font-family: sans-serif; background: #121213; color: #fff; padding: 2rem;'>"
            "<h1>Wordle AI API is Active</h1>"
            "<p>GUI development server runs on <a style='color: #538d4e;' href='http://localhost:5173'>http://localhost:5173</a>.</p>"
            "<p>To build production assets, run <code>npm run build</code> inside <code>web/</code>.</p>"
            "</body></html>"
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

    def _handle_recommend(request: HistoryRequest) -> dict:
        try:
            state = service.turns(_turns(service, request.history))
        except InconsistentFeedback:
            return {
                "state": {
                    "profile_id": service.profile.profile_id,
                    "mode": service.mode.value,
                    "attempts_used": len(request.history),
                    "attempts_left": max(0, service.attempts - len(request.history)),
                    "remaining": 0,
                    "solved": False,
                    "history": [e.guess for e in request.history],
                    "top_candidates": [],
                },
                "recommendation": None,
                "solved": False,
                "error": "No dictionary words match this feedback pattern. Please verify your feedback tiles.",
            }
        except ProfileIntegrityError:
            return {
                "state": {
                    "profile_id": service.profile.profile_id,
                    "mode": service.mode.value,
                    "attempts_used": service.attempts,
                    "attempts_left": 0,
                    "remaining": 0,
                    "solved": False,
                    "history": [e.guess for e in request.history],
                    "top_candidates": [],
                },
                "recommendation": None,
                "solved": False,
                "game_over": True,
            }
        except WordleError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if state.is_solved():
            return {
                "state": service.view(state).to_dict(),
                "recommendation": None,
                "solved": True,
            }
        if state.attempts_left <= 0:
            return {
                "state": service.view(state).to_dict(),
                "recommendation": None,
                "solved": state.is_solved(),
                "game_over": True,
            }
        if state.remaining == 0:
            return {
                "state": service.view(state).to_dict(),
                "recommendation": None,
                "solved": False,
                "error": "No dictionary words match this feedback pattern. Please verify your feedback tiles.",
            }

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
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        try:
            decision = strat.choose(state, service.rows, cache=service._cache)
            rec = RecommendationView.from_decision(decision)
        except ArtifactMismatchError:
            # Fall back gracefully to balanced hybrid if exact DP tree was departed
            fallback_strat = get_strategy("hybrid.balanced", prior_weights=service.prior_weights)
            decision = fallback_strat.choose(state, service.rows, cache=service._cache)
            rec_fb = RecommendationView.from_decision(decision)
            rec = replace(
                rec_fb,
                explanation=f"(Exact DP tree departed at candidate size {state.remaining}; evaluated with Balanced Hybrid): {rec_fb.explanation}",
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        try:
            state = service.turns(_turns(service, request.history))
        except (InconsistentFeedback, ProfileIntegrityError):
            return {
                "state": {
                    "profile_id": service.profile.profile_id,
                    "mode": service.mode.value,
                    "attempts_used": len(request.history),
                    "attempts_left": max(0, service.attempts - len(request.history)),
                    "remaining": 0,
                    "solved": False,
                    "history": [e.guess for e in request.history],
                    "top_candidates": [],
                },
                "results": [],
                "rows": [],
                "distinct_guesses": [],
                "groups": [],
                "pairwise_disagreements": 0,
            }

        if state.remaining == 0:
            return {
                "state": service.view(state).to_dict(),
                "results": [],
                "rows": [],
                "distinct_guesses": [],
                "groups": [],
                "pairwise_disagreements": 0,
            }
        try:
            return compare_strategies(service, state, request.strategies)
        except (KeyError, ValueError, WordleError) as exc:
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
            try:
                decision = sim_strategy.choose(state, service.rows)
            except ArtifactMismatchError:
                fallback_strat = get_strategy("hybrid.balanced", prior_weights=service.prior_weights)
                decision = fallback_strat.choose(state, service.rows)
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
