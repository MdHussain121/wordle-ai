"""Banned-terms check for user-facing copy (Phase 7, criterion 5).

The default view is a word-game assistant, not a research console. Naming a model, a
training procedure or a tensor in the recommendation sentence would be jargon the
player cannot act on, and the roadmap requires the absence to be *tested* rather than
asserted.

This module is deliberately one function: give it rendered text and it returns the
banned terms it found. Tests apply it to every default-mode surface (service views,
`play`, `selfplay`, labs), and the check is cheap enough to call before printing.
"""

from __future__ import annotations

import re

#: Terms that belong to ML/research writing, not to a player-facing explanation. Matched
#: case-insensitively as whole words, so "mode" is not "model" and "trained" is caught by
#: its own entry rather than by "train" + suffix magic.
BANNED_TERMS: tuple[str, ...] = (
    "machine learning",
    "neural",
    "neural network",
    "model",
    "models",
    "training",
    "trained",
    "dataset",
    "distillation",
    "distilled",
    "gradient",
    "gradient boosting",
    "embedding",
    "embeddings",
    "transformer",
    "reinforcement learning",
    "classifier",
    "classification",
    "regression",
    "logistic",
    "inference",
    "hyperparameter",
    "hyperparameters",
    "feature vector",
    "features",
    "reward function",
    "policy gradient",
    "epoch",
    "epochs",
    "loss function",
    "backpropagation",
    "supervised",
    "unsupervised",
)

_PATTERNS = tuple(
    (term, re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", re.IGNORECASE))
    for term in BANNED_TERMS
)


def banned_terms_in(text: str) -> list[str]:
    """Terms from :data:`BANNED_TERMS` present in ``text``, in list order, deduplicated."""

    lowered = text or ""
    found: list[str] = []
    for term, pattern in _PATTERNS:
        if pattern.search(lowered):
            found.append(term)
    return found


def assert_copy_is_plain(text: str) -> None:
    """Raise ``AssertionError`` naming the offending terms, for callers that must check."""

    found = banned_terms_in(text)
    if found:
        raise AssertionError(
            f"user-facing copy contains ML terminology: {', '.join(found)}"
        )


__all__ = ["BANNED_TERMS", "assert_copy_is_plain", "banned_terms_in"]
