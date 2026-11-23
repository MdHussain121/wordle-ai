"""Normalisation and validity policy (dataset plan §4).

Rules implemented here, in the order the pipeline applies them:

1. Decode bytes as UTF-8, falling back to ISO-8859-1 and recording the fallback.
   SCOWL ships Latin-1; a UTF-8-only loader crashes on it (observed in Phase 0).
2. NFC normalise, then casefold.
3. Measure length in grapheme clusters, never code points.
4. Filter on an explicit character class (ASCII ``[a-z]`` for English profiles).
5. Reject possessives and other punctuation; never transliterate silently.

Transliteration exists as an explicit, off-by-default option, because converting
``café`` to ``cafe`` changes the word's identity.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

ASCII_ALPHA = re.compile(r"^[a-z]+$")

# Joiners and modifiers that belong to the preceding grapheme cluster.
_JOINERS = {"\u200d", "\ufe0e", "\ufe0f"}


class RejectReason(str, Enum):
    EMPTY = "empty"
    APOSTROPHE = "apostrophe"
    HYPHEN = "hyphen"
    SPACE = "space"
    DIGIT = "digit"
    NON_ASCII = "non_ascii"
    OUTSIDE_ALPHABET = "outside_alphabet"
    WRONG_LENGTH = "wrong_length"
    NOT_IN_WHITELIST = "not_in_whitelist"


@dataclass(frozen=True)
class DecodedText:
    text: str
    encoding: str
    used_fallback: bool


def decode_bytes(data: bytes) -> DecodedText:
    """Decode source bytes, recording whether the Latin-1 fallback was needed."""

    try:
        return DecodedText(text=data.decode("utf-8"), encoding="utf-8", used_fallback=False)
    except UnicodeDecodeError:
        return DecodedText(text=data.decode("latin-1"), encoding="latin-1", used_fallback=True)


def normalize_word(raw: str) -> str:
    """NFC normalise, casefold and strip outer whitespace. Never transliterates."""

    return unicodedata.normalize("NFC", raw).casefold().strip()


def strip_accents(word: str) -> str:
    """Explicit, opt-in transliteration. Off by default; recorded when used."""

    decomposed = unicodedata.normalize("NFKD", word)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def grapheme_length(text: str) -> int:
    """Number of user-perceived characters.

    Combines base characters with following combining marks, variation selectors and
    ZWJ sequences. This is deliberately not ``len(text)``: ``e`` + U+0301 is one
    character, and an emoji family sequence is one character even though it is many
    code points.
    """

    count = 0
    joined = False
    for ch in text:
        if ch == "\u200d":
            joined = True
            continue
        if unicodedata.combining(ch) or ch in _JOINERS:
            continue
        if joined:
            joined = False
            continue
        count += 1
    return count


def is_ascii_alpha(word: str) -> bool:
    return bool(ASCII_ALPHA.match(word))


def classify(
    word: str,
    *,
    length: int,
    alphabet: str,
    allow_non_ascii: bool = False,
) -> RejectReason | None:
    """Return the first policy rejection for ``word``, or ``None`` if it is accepted."""

    if not word:
        return RejectReason.EMPTY
    if "'" in word or "\u2019" in word:
        return RejectReason.APOSTROPHE
    if "-" in word:
        return RejectReason.HYPHEN
    if any(ch.isspace() for ch in word):
        return RejectReason.SPACE
    if any(ch.isdigit() for ch in word):
        return RejectReason.DIGIT
    if not allow_non_ascii and not word.isascii():
        return RejectReason.NON_ASCII
    if any(ch not in alphabet for ch in word):
        return RejectReason.OUTSIDE_ALPHABET
    if grapheme_length(word) != length:
        return RejectReason.WRONG_LENGTH
    return None
