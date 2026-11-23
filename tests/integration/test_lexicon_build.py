"""The lexicon pipeline against the measured dataset plan (§3, §6, §10)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wordle_ai.errors import ProfileIntegrityError
from wordle_ai.lexicon.build import build, request_from_config
from wordle_ai.lexicon.manifest import load_manifest
from wordle_ai.lexicon.profile import (
    load_arrays,
    load_profile,
    read_manifest,
    verify_profile_dir,
)
from wordle_ai.lexicon.source import load_lock, sha256_file

REPO_ROOT = Path(__file__).resolve().parents[2]

# Measured in Phase 0 from the pinned sources; the dataset plan records these values.
EXPECTED = {
    "strict.en.1": (2, 2),
    "strict.en.2": (65, 65),
    "strict.en.3": (588, 588),
    "strict.en.4": (2303, 2303),
    "strict.en.5": (4444, 4444),
    "extended.en.1": (2, 2),
    "extended.en.2": (148, 148),
    "extended.en.3": (1223, 1223),
    "extended.en.4": (5059, 5059),
    "extended.en.5": (11411, 11411),
    "full.en.1": (2, 2),
    "full.en.2": (276, 276),
    "full.en.3": (2000, 2000),
    "full.en.4": (7441, 7441),
    "full.en.5": (17410, 17410),
    "classic.en.5": (2315, 12972),
}


@pytest.mark.parametrize("profile_id,expected", sorted(EXPECTED.items()))
def test_counts_match_dataset_plan(profile_id, expected, builder, request):
    if profile_id.startswith("classic"):
        request.getfixturevalue("classic_lists")
    result = builder(profile_id)
    assert (result.answers, result.guesses) == expected


def test_single_letter_profile_uses_whitelist(builder, processed_root):
    builder("strict.en.1")
    profile = load_profile(processed_root / "strict.en.1")
    assert profile.answers == ("a", "i")
    manifest = read_manifest(processed_root / "strict.en.1")
    assert manifest.single_letter_exclusions == 24
    assert manifest.rejected.not_in_whitelist == 24


def test_manifest_accounting_is_exact(builder, processed_root):
    for profile_id in ("strict.en.5", "extended.en.2", "full.en.4"):
        builder(profile_id)
        manifest = read_manifest(processed_root / profile_id)
        reason_sum = sum(
            getattr(manifest.rejected, key)
            for key in (
                "empty",
                "apostrophe",
                "hyphen",
                "space",
                "digit",
                "non_ascii",
                "outside_alphabet",
                "wrong_length",
                "not_in_whitelist",
            )
        )
        assert reason_sum == manifest.rejected.total
        assert (
            manifest.raw_entries
            == manifest.counts.guesses
            + manifest.rejected.total
            + manifest.duplicates_removed
        )


def test_manifest_is_schema_valid_and_records_provenance(builder, processed_root):
    result = builder("strict.en.5")
    manifest = load_manifest(processed_root / "strict.en.5" / "manifest.json")
    assert manifest.profile_id == "strict.en.5"
    assert manifest.schema_version == 1
    assert manifest.counts.answers == result.answers
    assert manifest.counts.guesses == result.guesses
    assert manifest.outputs.lexicon_sha256 == result.lexicon_sha256
    assert manifest.outputs.answers_sha256 == result.answers_sha256
    assert [source.id for source in manifest.sources] == ["scowl"]
    for source in manifest.sources:
        assert source.version
        assert source.license
        assert source.sha256
    assert manifest.created_utc is None  # deterministic by default
    assert "normalize:NFC" in manifest.transforms
    assert "casefold" in manifest.transforms
    assert manifest.policy["ascii_only"] is True
    assert manifest.policy["include_possessives"] is False


def test_artifact_checksums_match_files(builder, processed_root):
    builder("strict.en.3")
    directory = processed_root / "strict.en.3"
    manifest = read_manifest(directory)
    assert sha256_file(directory / "lexicon.npz") == manifest.outputs.lexicon_sha256
    assert sha256_file(directory / "answers.txt") == manifest.outputs.answers_sha256
    assert verify_profile_dir(directory) == []


def test_classic_profile_never_bundles_source(builder, processed_root, classic_lists):
    result = builder("classic.en.5")
    manifest = read_manifest(processed_root / "classic.en.5")
    assert manifest.policy["answer_policy"] == "file"
    assert manifest.sources[0].id == "user:classic"
    assert manifest.sources[0].license == "unverified; never redistributed"
    assert (result.answers, result.guesses) == (2315, 12972)
    # The classic answers are a strict subset of the allowed guesses.
    arrays = load_arrays(processed_root / "classic.en.5" / "lexicon.npz")
    answers = set(arrays["answers"].tolist())
    guesses = set(arrays["guesses"].tolist())
    assert len(answers) == 2315
    assert answers <= guesses


def test_classic_table_built_under_budget(settings, tmp_path, classic_lists):
    # A dedicated directory: the session builder caches by (profile, policy), while
    # every build writes the manifest of the *same* profile id, so sharing the root
    # with a table="none" build would compare this result against the wrong manifest.
    result = build(
        request_from_config(
            "classic.en.5", settings, processed_dir=tmp_path, table_policy="auto"
        )
    )
    assert result.table_policy_used == "full"
    manifest = read_manifest(tmp_path / "classic.en.5")
    # The footprint is one byte per pair; the file adds the fixed ``.npy`` header.
    assert manifest.policy["table_footprint_bytes"] == 2315 * 12972
    assert result.table_bytes >= 2315 * 12972
    assert manifest.outputs.table_sha256 == result.table_sha256
    assert Path(manifest.outputs.feedback_table).exists()
    assert sha256_file(Path(manifest.outputs.feedback_table)) == manifest.outputs.table_sha256


def test_missing_user_lists_raise_clear_error(settings, tmp_path):
    request = request_from_config(
        "classic.en.5",
        settings,
        processed_dir=tmp_path,
        table_policy="none",
    )
    # Point the request at a directory with no imported lists.
    from dataclasses import replace

    absent = tmp_path / "absent"
    request = replace(
        request,
        answers_path=absent / "classic_answers.txt",
        guesses_path=absent / "classic_guesses.txt",
    )
    with pytest.raises(ProfileIntegrityError) as excinfo:
        build(request)
    assert "--attest-license" in excinfo.value.message


def test_sources_lock_is_complete():
    lock = load_lock(REPO_ROOT / "sources.lock")
    for source_id in ("scowl", "enable"):
        spec = lock["sources"][source_id]
        assert len(spec["sha256"]) == 64
        assert spec["license"]
        assert spec["version"]
        assert spec["url"].startswith("https://")
    assert lock["user_sources"]["classic"]["license"] == "unverified; never redistributed"


def test_answers_file_is_newline_terminated_ascii(builder, processed_root):
    builder("extended.en.2")
    payload = (processed_root / "extended.en.2" / "answers.txt").read_bytes()
    assert payload.endswith(b"\n")
    assert payload.decode("ascii")
    words = payload.decode("ascii").splitlines()
    assert len(words) == len(set(words)) == 148
    assert words == sorted(words)
