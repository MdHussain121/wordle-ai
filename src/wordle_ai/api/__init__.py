"""Service layer: views and orchestration for interfaces (Phase 7)."""

from .service import (
    CandidateView,
    GameView,
    RecommendationView,
    SolverService,
    StrategyComparison,
    build_service,
    compare_strategies,
    dictionary_report,
)

__all__ = [
    "CandidateView",
    "GameView",
    "RecommendationView",
    "SolverService",
    "StrategyComparison",
    "build_service",
    "compare_strategies",
    "dictionary_report",
]
