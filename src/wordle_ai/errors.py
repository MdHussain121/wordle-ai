"""Typed error taxonomy (technical specification §15).

Every error carries a machine-readable ``code`` and the process exit code that the
CLI uses for it. Nothing in the pipeline reports a problem by printing a string and
continuing; each condition below has exactly one class.
"""

from __future__ import annotations

from typing import Any


class WordleError(Exception):
    """Base class for every error this project raises deliberately."""

    code: str = "wordle_error"
    exit_code: int = 1

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        exit_code: int | None = None,
        **context: Any,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if exit_code is not None:
            self.exit_code = exit_code
        self.context: dict[str, Any] = context

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": type(self).__name__,
            "code": self.code,
            "message": self.message,
            "exit_code": self.exit_code,
            "context": self.context,
        }

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.code}] {self.message}"


class ConfigError(WordleError):
    """Invalid TOML, unknown key, or an out-of-range value."""

    code = "invalid_configuration"
    exit_code = 1


class SourceIntegrityError(WordleError):
    """A source file is missing or its checksum does not match the lock file."""

    code = "source_integrity"
    exit_code = 3


class ProfileIntegrityError(WordleError):
    """A profile violates an invariant (subset, alphabet, length, duplicates, manifest)."""

    code = "profile_integrity"
    exit_code = 3


class UnsupportedProfile(WordleError):
    """A length or alphabet this build of the engine does not support."""

    code = "unsupported_profile"
    exit_code = 2


class InvalidGuess(WordleError):
    """A guess is empty, the wrong length, outside the alphabet, or not an allowed word.

    ``reason`` is one of ``empty``, ``wrong_length``, ``out_of_alphabet``,
    ``unknown_word``; the four documented cases each map to one of them.
    """

    code = "invalid_guess"
    exit_code = 1

    def __init__(self, message: str, *, reason: str, **context: Any) -> None:
        super().__init__(message, reason=reason, **context)
        self.reason = reason


class InvalidPattern(WordleError):
    """A feedback pattern string is malformed (wrong length or character).

    The technical specification requires ``Pattern.parse`` to reject anything that is
    not a valid pattern; this class names that rejection.
    """

    code = "invalid_pattern"
    exit_code = 1


class InconsistentFeedback(WordleError):
    """The feedback history eliminates every candidate; the history is unrealisable."""

    code = "inconsistent_feedback"
    exit_code = 3


class ModeViolationError(WordleError):
    """A strategy produced a guess that contradicts feedback the game already gave."""

    code = "mode_violation"
    exit_code = 3


class NoLegalGuessError(WordleError):
    """No guess in the profile satisfies the active mode's constraints.

    A strategy that cannot produce a legal guess fails with this class instead of
    returning one that contradicts the history.
    """

    code = "no_legal_guess"
    exit_code = 1


class ArtifactMismatchError(WordleError):
    """A cached artifact does not match its profile, rules, prior, attempts or checksum."""

    code = "artifact_mismatch"
    exit_code = 5


class BudgetExceeded(WordleError):
    """A configured memory or time budget was exceeded before or during a computation."""

    code = "budget_exceeded"
    exit_code = 4


class PriorCalibrationError(WordleError):
    """A prior failed its calibration gate and must not be enabled."""

    code = "prior_calibration"
    exit_code = 3
