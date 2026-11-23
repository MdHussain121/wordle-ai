"""Lexicon manifest schema and deterministic serialisation (§3.6).

The manifest is the only accepted source of truth for a profile. It is written with
sorted keys and explicit ASCII escaping so that two builds of the same inputs produce
byte-identical files. ``created_utc`` is therefore null unless the builder is given a
``SOURCE_DATE_EPOCH``; timestamps are provenance, not content, and must not make an
otherwise reproducible artifact differ.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ..errors import ProfileIntegrityError

SCHEMA_VERSION = 1
GENERATOR_VERSION = "0.1.0"


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    version: str
    url: str | None = None
    retrieved_utc: str | None = None
    sha256: str | None = None
    license: str
    license_file: str | None = None


class Counts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    answers: int = Field(ge=0)
    guesses: int = Field(ge=0)
    by_length: dict[str, int]


class Rejected(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total: int = Field(ge=0)
    empty: int = Field(default=0, ge=0)
    apostrophe: int = Field(default=0, ge=0)
    hyphen: int = Field(default=0, ge=0)
    space: int = Field(default=0, ge=0)
    digit: int = Field(default=0, ge=0)
    non_ascii: int = Field(default=0, ge=0)
    outside_alphabet: int = Field(default=0, ge=0)
    wrong_length: int = Field(default=0, ge=0)
    not_in_whitelist: int = Field(default=0, ge=0)
    other: int = Field(default=0, ge=0)


class Outputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lexicon: str
    lexicon_sha256: str
    lexicon_bytes: int
    answers: str
    answers_sha256: str
    feedback_table: str | None = None
    table_sha256: str | None = None
    feedback_table_bytes: int | None = None


class LexiconManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = SCHEMA_VERSION
    profile_id: str
    created_utc: str | None = None
    generator_version: str = GENERATOR_VERSION
    language: str
    dialect: str | None
    length: int = Field(ge=1, le=5)
    alphabet: str
    sources: list[SourceRef]
    transforms: list[str]
    counts: Counts
    raw_entries: int = Field(ge=0)
    duplicates_removed: int = Field(default=0, ge=0)
    rejected: Rejected
    single_letter_exclusions: int = Field(default=0, ge=0)
    outputs: Outputs
    policy: dict
    policy_artifacts: list[str] = Field(default_factory=list)


def dump_manifest(manifest: LexiconManifest, path: Path) -> None:
    payload = manifest.model_dump(mode="json")
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="ascii", newline="\n")
    temporary.replace(path)


def load_manifest(path: Path) -> LexiconManifest:
    if not path.exists():
        raise ProfileIntegrityError(f"manifest not found: {path}", path=str(path))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileIntegrityError(f"{path}: invalid JSON: {exc}", path=str(path)) from exc
    try:
        return LexiconManifest.model_validate(payload)
    except Exception as exc:  # pydantic ValidationError
        raise ProfileIntegrityError(f"{path}: schema violation: {exc}", path=str(path)) from exc
