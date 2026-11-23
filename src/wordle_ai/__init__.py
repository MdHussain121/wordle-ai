"""Wordle-solving AI: Phase 1 lexicon pipeline and feedback engine."""

from .errors import (
    ArtifactMismatchError,
    BudgetExceeded,
    ConfigError,
    InconsistentFeedback,
    InvalidGuess,
    InvalidPattern,
    PriorCalibrationError,
    ProfileIntegrityError,
    SourceIntegrityError,
    UnsupportedProfile,
    WordleError,
)
from .types import Pattern, PriorKind, Profile, RuleMode, Tile, Turn

__version__ = "0.1.0"

__all__ = [
    "ArtifactMismatchError",
    "BudgetExceeded",
    "ConfigError",
    "InconsistentFeedback",
    "InvalidGuess",
    "InvalidPattern",
    "Pattern",
    "PriorCalibrationError",
    "PriorKind",
    "Profile",
    "ProfileIntegrityError",
    "RuleMode",
    "SourceIntegrityError",
    "Tile",
    "Turn",
    "UnsupportedProfile",
    "WordleError",
    "__version__",
]
