"""Byte-level reproducibility of the build (§5 step 12, dataset plan §7)."""

from __future__ import annotations

import json

import pytest

from wordle_ai.lexicon.build import build, request_from_config
from wordle_ai.lexicon.manifest import load_manifest
from wordle_ai.lexicon.profile import load_profile
from wordle_ai.lexicon.source import sha256_file


def _hashes(directory):
    return {path.name: sha256_file(path) for path in sorted(directory.iterdir())}


def test_two_builds_are_byte_identical(settings, tmp_path):
    request = request_from_config(
        "strict.en.2", settings, processed_dir=tmp_path, table_policy="none"
    )
    first = build(request)
    hashes_first = _hashes(request.output_dir)
    second = build(request)
    hashes_second = _hashes(request.output_dir)

    assert hashes_first == hashes_second
    assert first.lexicon_sha256 == second.lexicon_sha256
    assert first.manifest_sha256 == second.manifest_sha256
    assert set(hashes_first) == {"answers.txt", "lexicon.npz", "manifest.json"}


def test_rebuild_after_deletion_is_identical(settings, tmp_path):
    request = request_from_config(
        "strict.en.2", settings, processed_dir=tmp_path, table_policy="none"
    )
    build(request)
    before = _hashes(request.output_dir)
    for path in request.output_dir.iterdir():
        path.unlink()
    build(request)
    assert _hashes(request.output_dir) == before


def test_two_directories_produce_identical_content(settings, tmp_path):
    """Dataset plan §7: builds into different directories agree on content checksums.

    Only the recorded output paths differ, because the manifest describes where each
    artifact lives; the lexicon, answers and table bytes are identical.
    """

    first_request = request_from_config(
        "strict.en.2", settings, processed_dir=tmp_path / "a", table_policy="none"
    )
    second_request = request_from_config(
        "strict.en.2", settings, processed_dir=tmp_path / "b", table_policy="none"
    )
    first = build(first_request)
    second = build(second_request)

    assert first.lexicon_sha256 == second.lexicon_sha256
    assert first.answers_sha256 == second.answers_sha256
    assert first.table_sha256 is None and second.table_sha256 is None

    first_manifest = json.loads((first_request.output_dir / "manifest.json").read_text())
    second_manifest = json.loads((second_request.output_dir / "manifest.json").read_text())
    for manifest in (first_manifest, second_manifest):
        for key in ("lexicon", "answers", "feedback_table"):
            manifest["outputs"][key] = None
    assert first_manifest == second_manifest


def test_created_utc_only_when_source_date_epoch_is_set(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1704067200")
    request = request_from_config(
        "strict.en.2", settings, processed_dir=tmp_path, table_policy="none"
    )
    build(request)
    manifest = load_manifest(request.output_dir / "manifest.json")
    assert manifest.created_utc == "2024-01-01T00:00:00Z"
    epoch_hash = manifest.outputs.lexicon_sha256

    monkeypatch.delenv("SOURCE_DATE_EPOCH")
    build(request)
    manifest = load_manifest(request.output_dir / "manifest.json")
    assert manifest.created_utc is None
    # The lexicon content is unaffected by provenance timestamps.
    assert manifest.outputs.lexicon_sha256 == epoch_hash


def test_table_build_is_deterministic(settings, tmp_path):
    request = request_from_config(
        "strict.en.3", settings, processed_dir=tmp_path, table_policy="full"
    )
    first = build(request)
    assert first.table_sha256
    second = build(request)
    assert second.table_sha256 == first.table_sha256
    assert second.manifest_sha256 == first.manifest_sha256


def test_profile_reload_matches_build(settings, tmp_path):
    request = request_from_config(
        "strict.en.4", settings, processed_dir=tmp_path, table_policy="none"
    )
    result = build(request)
    profile = load_profile(request.output_dir)
    assert len(profile.answers) == result.answers
    assert len(profile.guesses) == result.guesses
    assert profile.manifest_sha256 == result.manifest_sha256
