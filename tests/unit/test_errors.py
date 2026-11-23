"""Error taxonomy (§15): every documented case raises its typed error and exit code."""

from __future__ import annotations

import pytest

from wordle_ai.config import load_config
from wordle_ai.engine.feedback import feedback_code
from wordle_ai.engine.state import new_game
from wordle_ai.engine.table import build_table
from wordle_ai.errors import (
    ArtifactMismatchError,
    BudgetExceeded,
    ConfigError,
    InconsistentFeedback,
    InvalidGuess,
    InvalidPattern,
    ProfileIntegrityError,
    SourceIntegrityError,
    UnsupportedProfile,
)
from wordle_ai.lexicon.build import parse_profile_id
from wordle_ai.lexicon.profile import load_profile, save_lexicon
from wordle_ai.lexicon.source import verify_source
from wordle_ai.types import Pattern, Profile

ALPHABET = "ab"


def tiny_profile(**overrides) -> Profile:
    data = {
        "profile_id": "tiny.ab.2",
        "language": "ab",
        "dialect": None,
        "length": 2,
        "alphabet": ALPHABET,
        "answers": ("aa",),
        "guesses": ("aa", "ab"),
        "manifest_sha256": "0" * 64,
    }
    data.update(overrides)
    answers = tuple(data["answers"])
    guesses = tuple(data["guesses"])
    return Profile(
        **data,
        answer_index={w: i for i, w in enumerate(answers)},
        guess_index={w: i for i, w in enumerate(guesses)},
    )


# ---- InvalidGuess: the four documented cases ------------------------------
@pytest.mark.parametrize(
    "guess,reason",
    [
        ("", "empty"),
        ("   ", "empty"),
        (None, "empty"),
        ("a", "wrong_length"),
        ("aaa", "wrong_length"),
        ("ac", "out_of_alphabet"),
    ],
)
def test_invalid_guess_cases(guess, reason):
    profile = tiny_profile(guesses=("aa", "ab", "ba", "bb"))
    with pytest.raises(InvalidGuess) as excinfo:
        profile.validate_guess(guess)
    assert excinfo.value.reason == reason
    assert excinfo.value.code == "invalid_guess"
    assert excinfo.value.exit_code == 1


def test_unknown_word_is_distinct_from_out_of_alphabet():
    profile = tiny_profile(guesses=("aa", "ab"))
    profile.validate_guess("aa")  # legal
    with pytest.raises(InvalidGuess) as excinfo:
        profile.validate_guess("ba")  # right shape, not in the guess set
    assert excinfo.value.reason == "unknown_word"


# ---- InvalidPattern ------------------------------------------------------
@pytest.mark.parametrize("text", ["", "GGX", "12 3x"])
def test_invalid_pattern(text):
    with pytest.raises(InvalidPattern):
        Pattern.parse(text)


def test_pattern_length_must_match_profile():
    profile = tiny_profile()
    with pytest.raises(InvalidPattern):
        profile.validate_pattern(Pattern.parse("GGG"))


# ---- ProfileIntegrityError ----------------------------------------------
@pytest.mark.parametrize(
    "overrides",
    [
        {"answers": ("ba",)},                       # not a subset of guesses
        {"guesses": ("aa", "aa")},                  # duplicate
        {"guesses": ("ab", "aa")},                  # unsorted
        {"guesses": ("aa", "ac")},                  # outside alphabet
        {"length": 6},                              # unsupported length
        {"alphabet": "aa"},                         # not distinct
    ],
)
def test_profile_integrity_violations(overrides):
    with pytest.raises(ProfileIntegrityError):
        tiny_profile(**overrides)


# ---- InconsistentFeedback ------------------------------------------------
def test_inconsistent_feedback_raises():
    profile = tiny_profile(guesses=("aa", "ab"))
    state = new_game(profile, max_attempts=2)
    # Code 0 is all-gray; neither "aa" nor "ab" produces it against "ab".
    assert feedback_code("ab", "aa") != 0
    assert feedback_code("ab", "ab") != 0
    with pytest.raises(InconsistentFeedback) as excinfo:
        state.apply("ab", Pattern(code=0, length=2))
    assert excinfo.value.exit_code == 3


# ---- SourceIntegrityError -------------------------------------------------
def test_source_checksum_mismatch(tmp_path):
    target = tmp_path / "list.txt"
    target.write_text("apple\n", encoding="utf-8")
    lock = {
        "sources": {
            "fake": {
                "kind": "text",
                "path": str(target),
                "sha256": "f" * 64,
                "url": "https://example.invalid/list.txt",
            }
        }
    }
    with pytest.raises(SourceIntegrityError) as excinfo:
        verify_source("fake", lock)
    assert excinfo.value.exit_code == 3


def test_missing_source_is_reported(tmp_path):
    lock = {"sources": {"fake": {"kind": "text", "path": str(tmp_path / "nope"), "sha256": "0" * 64}}}
    with pytest.raises(SourceIntegrityError):
        verify_source("fake", lock)


# ---- ArtifactMismatchError ------------------------------------------------
def test_tampered_lexicon_is_refused(settings, tmp_path):
    from wordle_ai.lexicon.build import build, request_from_config
    from wordle_ai.lexicon.profile import load_arrays, save_lexicon

    request = request_from_config("strict.en.1", settings, processed_dir=tmp_path, table_policy="none")
    build(request)
    profile_dir = tmp_path / "strict.en.1"
    # Replace the archive with a *valid* archive of different content: the file still
    # loads, so only the recorded checksum can catch the substitution.
    arrays = load_arrays(profile_dir / "lexicon.npz")
    answers = tuple(str(w) for w in arrays["answers"].tolist())
    guesses = tuple(str(w) for w in arrays["guesses"].tolist())[:-1]
    save_lexicon(
        profile_dir / "lexicon.npz",
        answers=answers,
        guesses=guesses,
        alphabet=str(arrays["alphabet"].tolist()),
        length=int(arrays["length"]),
    )
    with pytest.raises(ArtifactMismatchError) as excinfo:
        load_profile(profile_dir)
    assert excinfo.value.exit_code == 5


# ---- BudgetExceeded -------------------------------------------------------
def test_table_budget_exceeded():
    profile = tiny_profile(guesses=("aa", "ab", "ba", "bb"))
    with pytest.raises(BudgetExceeded) as excinfo:
        build_table(profile, max_bytes=1)
    assert excinfo.value.exit_code == 4


# ---- UnsupportedProfile / ConfigError ------------------------------------
def test_unsupported_length_in_profile_id():
    with pytest.raises(UnsupportedProfile):
        parse_profile_id("strict.en.6")


def test_malformed_profile_id():
    with pytest.raises(ConfigError):
        parse_profile_id("strict.en")


def test_unknown_config_key_is_rejected(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("[general]\ndata_dir = 'data'\nnot_a_key = 1\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(bad)


def test_unknown_family_is_rejected(settings):
    with pytest.raises(ConfigError):
        settings.family("does-not-exist")


# ---- exit codes are stable -----------------------------------------------
def test_exit_code_map():
    assert InvalidGuess("x", reason="empty").exit_code == 1
    assert InvalidPattern("x").exit_code == 1
    assert ConfigError("x").exit_code == 1
    assert UnsupportedProfile("x").exit_code == 2
    assert ProfileIntegrityError("x").exit_code == 3
    assert SourceIntegrityError("x").exit_code == 3
    assert InconsistentFeedback("x").exit_code == 3
    assert BudgetExceeded("x").exit_code == 4
    assert ArtifactMismatchError("x").exit_code == 5
