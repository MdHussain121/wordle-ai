"""Normalisation and validity policy (dataset plan §4)."""

from __future__ import annotations

from wordle_ai.lexicon.normalize import (
    RejectReason,
    classify,
    decode_bytes,
    grapheme_length,
    is_ascii_alpha,
    normalize_word,
    strip_accents,
)


def test_decode_utf8_and_latin1_fallback():
    latin1 = b"caf\xe9\n"
    decoded = decode_bytes(latin1)
    # Decoding preserves the bytes' characters; line splitting is the pipeline's job.
    assert decoded.text == "café\n"
    assert decoded.encoding == "latin-1"
    assert decoded.used_fallback is True

    utf8 = "café\n".encode("utf-8")
    decoded = decode_bytes(utf8)
    assert decoded.text == "café\n"
    assert decoded.encoding == "utf-8"
    assert decoded.used_fallback is False


def test_normalize_is_nfc_casefolded_and_stripped():
    assert normalize_word("  APPLE \n") == "apple"
    # NFD input becomes NFC.
    assert normalize_word("cafe\u0301") == "café"
    assert normalize_word("cafe\u0301") == normalize_word("café")


def test_grapheme_length_vs_code_points():
    assert grapheme_length("apple") == 5
    assert grapheme_length("cafe\u0301") == 4          # 5 code points, 4 characters
    assert grapheme_length("\U0001F468\u200D\U0001F469\u200D\U0001F467") == 1  # ZWJ family
    assert grapheme_length("\uFE0F") == 0              # modifier alone


def test_transliteration_is_explicit_only():
    assert strip_accents("café") == "cafe"
    # And it is not applied by normalisation.
    assert normalize_word("café") == "café"


def test_is_ascii_alpha():
    assert is_ascii_alpha("apple")
    assert not is_ascii_alpha("café")
    assert not is_ascii_alpha("app1e")
    assert not is_ascii_alpha("")


def test_classify_accepts_valid_word():
    assert classify("apple", length=5, alphabet="abcdefghijklmnopqrstuvwxyz") is None


def test_classify_rejection_reasons():
    alpha = "abcdefghijklmnopqrstuvwxyz"
    assert classify("", length=5, alphabet=alpha) == RejectReason.EMPTY
    assert classify("apple's", length=6, alphabet=alpha + "'") == RejectReason.APOSTROPHE
    assert classify("apple’s", length=6, alphabet=alpha + "’") == RejectReason.APOSTROPHE
    assert classify("well-being", length=10, alphabet=alpha + "-") == RejectReason.HYPHEN
    assert classify("two words", length=9, alphabet=alpha + " ") == RejectReason.SPACE
    assert classify("abc12", length=5, alphabet=alpha + "0123456789") == RejectReason.DIGIT
    assert classify("café", length=4, alphabet=alpha + "é") == RejectReason.NON_ASCII
    assert classify("apple", length=5, alphabet="abcdefghijklmno") == RejectReason.OUTSIDE_ALPHABET
    assert classify("apples", length=5, alphabet=alpha) == RejectReason.WRONG_LENGTH


def test_classify_counts_graphemes_not_code_points():
    # "cafe" + combining acute is four user-perceived characters and is rejected as
    # non-ASCII before the length rule, never silently rewritten to "cafe".
    reason = classify("cafe\u0301", length=4, alphabet="abcdefghijklmnopqrstuvwxyz")
    assert reason == RejectReason.NON_ASCII
