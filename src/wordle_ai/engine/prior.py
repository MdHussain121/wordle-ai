"""Answer priors: uniform, Zipf and empirical (technical specification §8).

A prior answers one question — how likely is each answer word before any feedback —
and it must never change what is *valid*. It only reweights the answer set; the guess
set, the feedback rules and the lexicon are untouched.

The Zipf prior is ``pi_beta(a) ∝ exp(beta * (z(a) - z_max))`` where ``z`` is the
``wordfreq`` Zipf score (0..8, 0 for a word the corpus has never seen). ``beta = 0``
returns the uniform weights bit-for-bit: the same float64 ones uniform uses, so a
strategic decision under ``beta = 0`` is the uniform decision, not merely close to it.

``wordfreq`` is an optional runtime dependency. The scores are cached per (language,
answer tuple) for the life of the process and are never written to disk, because its
data is CC BY-SA and this project does not redistribute derived tables.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

from ..errors import PriorCalibrationError, WordleError
from ..types import PriorKind, Profile

#: wordfreq's documented score ceiling; used only for the shift, which cancels in the
#: normalisation, so an off-by-a-fraction here cannot change a distribution.
ZIPF_MAX = 8.0
#: Laplace smoothing for the empirical prior: every answer starts with this mass.
DEFAULT_ALPHA = 1.0

_ZIPF_CACHE: dict[tuple[str, tuple[str, ...]], np.ndarray] = {}


@runtime_checkable
class Prior(Protocol):
    """A distribution over answers, before normalisation over candidates."""

    kind: PriorKind
    prior_id: str

    def weights(self, profile: Profile) -> np.ndarray: ...


class UniformPrior:
    """Every answer equally likely: the default, and the calibration baseline."""

    kind = PriorKind.UNIFORM
    prior_id = "uniform"

    def weights(self, profile: Profile) -> np.ndarray:
        return np.ones(len(profile.answers), dtype=np.float64)


class ZipfPrior:
    """Frequency prior from ``wordfreq``, optionally tempered by ``beta``.

    ``beta`` is fitted on a validation split by the calibration harness, never on the
    answers a benchmark reports. Negative values are rejected: a negative beta would
    favour words the corpus has never seen and is not the hypothesis under test.
    """

    kind = PriorKind.ZIPF

    def __init__(self, beta: float = 0.0, *, language: str | None = None) -> None:
        if beta < 0:
            raise PriorCalibrationError(f"zipf beta must be >= 0, got {beta}")
        self.beta = float(beta)
        self.language = language

    @property
    def prior_id(self) -> str:
        return "zipf" if self.beta == 0.0 else f"zipf:beta={self.beta:g}"

    def weights(self, profile: Profile) -> np.ndarray:
        if self.beta == 0.0:
            # Exactly uniform, not exp(0 * something) that could differ in the last bit.
            return np.ones(len(profile.answers), dtype=np.float64)
        scores = _zipf_scores(profile, language=self.language)
        weights = np.exp(self.beta * (scores - ZIPF_MAX))
        total = float(weights.sum())
        if not np.isfinite(total) or total <= 0.0:  # pragma: no cover - defensive
            raise PriorCalibrationError(
                f"zipf prior with beta={self.beta} produced no finite mass"
            )
        return weights


class EmpiricalPrior:
    """Laplace-smoothed counts from a user-supplied answer history.

    The history is one answer per line (blank lines and ``#`` comments ignored). Words
    outside the profile are counted but cannot be assigned mass: a history entry that
    is not an answer of this profile is reported rather than silently dropped.
    """

    kind = PriorKind.EMPIRICAL

    def __init__(self, path: str | Path, *, alpha: float = DEFAULT_ALPHA) -> None:
        if alpha <= 0:
            raise PriorCalibrationError(f"empirical alpha must be > 0, got {alpha}")
        self.path = Path(path)
        self.alpha = float(alpha)
        if not self.path.exists():
            raise PriorCalibrationError(
                f"empirical prior history not found: {self.path}", path=str(self.path)
            )
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.prior_id = f"empirical:{digest[:8]}"
        self._counts: dict[str, int] = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            word = line.split("#", 1)[0].strip().casefold()
            if not word:
                continue
            self._counts[word] = self._counts.get(word, 0) + 1

    def weights(self, profile: Profile) -> np.ndarray:
        n = len(profile.answers)
        counts = np.fromiter(
            (self._counts.get(word, 0) for word in profile.answers),
            dtype=np.float64,
            count=n,
        )
        return counts + self.alpha


def _zipf_scores(profile: Profile, *, language: str | None = None) -> np.ndarray:
    """``wordfreq`` scores for the profile's answers, cached per language and list."""

    language = language or profile.language
    key = (language, profile.answers)
    cached = _ZIPF_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        from wordfreq import zipf_frequency
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise PriorCalibrationError(
            "the zipf prior needs the optional 'wordfreq' package: "
            "install wordle-ai[prior] (or `uv pip install wordfreq`)",
            code="prior_unavailable",
        ) from exc
    scores = np.fromiter(
        (zipf_frequency(word, language) for word in profile.answers),
        dtype=np.float64,
        count=len(profile.answers),
    )
    _ZIPF_CACHE[key] = scores
    return scores


def parse_prior_id(text: str) -> Prior:
    """Build a prior from its CLI/benchmark identifier.

    Accepted forms: ``uniform``, ``zipf``, ``zipf:0.5``, ``zipf:beta=0.5`` and
    ``empirical:<history path>``. Anything else is an error rather than a fallback,
    because a silently uniform run mislabelled as ``zipf`` would corrupt a benchmark.
    """

    value = (text or "").strip()
    if not value or value == "uniform":
        return UniformPrior()
    if value == "zipf":
        return ZipfPrior(0.0)
    if value.startswith("zipf:"):
        payload = value.split(":", 1)[1].strip()
        if payload.startswith("beta="):
            payload = payload.split("=", 1)[1]
        try:
            beta = float(payload)
        except ValueError:
            raise WordleError(
                f"invalid zipf prior {text!r}; use zipf:<beta>, for example zipf:0.5",
                code="invalid_prior",
            ) from None
        return ZipfPrior(beta)
    if value.startswith("empirical:"):
        path = value.split(":", 1)[1].strip()
        if not path:
            raise WordleError(
                "empirical prior needs a history path: empirical:<path>",
                code="invalid_prior",
            )
        return EmpiricalPrior(path)
    raise WordleError(
        f"unknown prior {text!r}; choose uniform, zipf[:<beta>] or empirical:<path>",
        code="invalid_prior",
    )


def normalised_weights(prior: Prior, profile: Profile) -> np.ndarray:
    """The prior as a proper distribution over ``profile.answers`` (sums to 1)."""

    weights = np.asarray(prior.weights(profile), dtype=np.float64)
    if weights.shape != (len(profile.answers),):
        raise PriorCalibrationError(
            f"prior {prior.prior_id} produced {weights.shape[0] if weights.ndim else 0} "
            f"weights for {len(profile.answers)} answers"
        )
    if not np.all(np.isfinite(weights)) or np.any(weights < 0):
        raise PriorCalibrationError(
            f"prior {prior.prior_id} produced negative or non-finite weights"
        )
    total = float(weights.sum())
    if total <= 0.0:
        raise PriorCalibrationError(f"prior {prior.prior_id} assigns no mass")
    return weights / total


def prior_id_of(prior: Prior) -> str:
    return prior.prior_id


__all__ = [
    "DEFAULT_ALPHA",
    "EmpiricalPrior",
    "Prior",
    "UniformPrior",
    "ZIPF_MAX",
    "ZipfPrior",
    "normalised_weights",
    "parse_prior_id",
    "prior_id_of",
]
