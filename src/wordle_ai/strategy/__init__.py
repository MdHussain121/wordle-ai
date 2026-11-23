"""Strategy registry: names are the CLI's selection surface."""

from __future__ import annotations

from typing import Callable

from .base import Budget, Decision, HeuristicStrategy, PartitionStats, ScoreBreakdown, Strategy
from .exact import ExactStrategy
from .lookahead import LookaheadTwoPly, RolloutRandom
try:
    from ..ml.strategy import LearnedValueStrategy, LearnedRankerStrategy
    _ML_STRATEGIES = (LearnedValueStrategy, LearnedRankerStrategy)
except ImportError:
    _ML_STRATEGIES = ()
from .heuristics import (
    BayesCost,
    Entropy,
    EntropyCandidates,
    ExpectedRemaining,
    ExpectedRemainingCandidates,
    FirstCandidate,
    Hybrid,
    LetterFrequency,
    Minimax,
    MinimaxCandidates,
    PositionalFrequency,
    WeightedEntropy,
)

_FACTORIES: dict[str, Callable[..., object]] = {
    cls.name: cls
    for cls in (
        BayesCost,
        ExactStrategy,
        Entropy,
        EntropyCandidates,
        ExpectedRemaining,
        ExpectedRemainingCandidates,
        FirstCandidate,
        Hybrid,
        LetterFrequency,
        LookaheadTwoPly,
        Minimax,
        MinimaxCandidates,
        PositionalFrequency,
        RolloutRandom,
        WeightedEntropy,
        *_ML_STRATEGIES,
    )
}

STRATEGY_NAMES: tuple[str, ...] = tuple(sorted(_FACTORIES))

#: Strategies that need no external artifact; ``bench run --strategies all`` uses
#: these. ``exact`` is opt-in because it requires a policy built for the profile.
HEURISTIC_STRATEGY_NAMES: tuple[str, ...] = tuple(
    name for name in STRATEGY_NAMES if name != "exact" and not name.startswith("ml.")
)


def get_strategy(name: str, **kwargs) -> object:
    try:
        return _FACTORIES[name](**kwargs)
    except KeyError:
        raise KeyError(
            f"unknown strategy {name!r}; available: {', '.join(STRATEGY_NAMES)}"
        ) from None


def describe() -> list[dict[str, object]]:
    return [
        {
            "name": name,
            "objective": _FACTORIES[name].objective,
            "candidate_only": _FACTORIES[name].candidate_only,
            "requires_policy": name == "exact",
        }
        for name in STRATEGY_NAMES
    ]


__all__ = [
    "Budget",
    "Decision",
    "ExactStrategy",
    "HEURISTIC_STRATEGY_NAMES",
    "HeuristicStrategy",
    "PartitionStats",
    "ScoreBreakdown",
    "Strategy",
    "STRATEGY_NAMES",
    "describe",
    "get_strategy",
]
