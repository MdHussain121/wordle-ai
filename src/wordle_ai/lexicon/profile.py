"""Profile loading and deterministic artifact writing (§3.2, §3.6).

The lexicon is stored as a ``.npz`` archive written by :func:`save_lexicon`, which uses
fixed zip metadata and no compression so that the bytes are reproducible. ``numpy.savez``
cannot be used directly: it stamps the current time into every zip member, so two
identical builds would differ.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np

from ..errors import ArtifactMismatchError, ProfileIntegrityError
from ..types import Profile
from .manifest import Counts, LexiconManifest, load_manifest
from .source import sha256_file

LEXICON_NAME = "lexicon.npz"
ANSWERS_NAME = "answers.txt"
MANIFEST_NAME = "manifest.json"
TABLE_NAME = "feedback.npy"

_FIXED_DATE = (1980, 1, 1, 0, 0, 0)


def save_lexicon(
    path: Path,
    *,
    answers: tuple[str, ...],
    guesses: tuple[str, ...],
    alphabet: str,
    length: int,
) -> tuple[str, int]:
    """Write a deterministic ``.npz`` and return (sha256, bytes)."""

    width = max(length, 1)
    arrays = {
        "answers": np.array(answers, dtype=f"<U{width}"),
        "guesses": np.array(guesses, dtype=f"<U{width}"),
        "alphabet": np.array(alphabet, dtype=f"<U{max(len(alphabet), 1)}"),
        "length": np.array(length, dtype=np.int64),
        "schema_version": np.array(1, dtype=np.int64),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for name in sorted(arrays):
            member = io.BytesIO()
            np.save(member, arrays[name], allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=_FIXED_DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o600 << 16
            archive.writestr(info, member.getvalue())
    payload = buffer.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    return sha256_file(path), len(payload)


def load_arrays(path: Path) -> dict[str, np.ndarray]:
    if not path.exists():
        raise ProfileIntegrityError(f"lexicon not found: {path}", path=str(path))
    try:
        with np.load(path, allow_pickle=False) as archive:
            return {name: archive[name] for name in archive.files}
    except Exception as exc:
        raise ProfileIntegrityError(f"{path}: unreadable lexicon archive: {exc}", path=str(path)) from exc


def load_profile(profile_dir: Path, *, verify: bool = True) -> Profile:
    """Load and validate a profile, verifying every recorded checksum."""

    profile_dir = Path(profile_dir)
    manifest_path = profile_dir / MANIFEST_NAME
    manifest = load_manifest(manifest_path)

    arrays = load_arrays(profile_dir / LEXICON_NAME)
    answers = tuple(str(w) for w in arrays["answers"].tolist())
    guesses = tuple(str(w) for w in arrays["guesses"].tolist())

    if verify:
        actual = sha256_file(profile_dir / LEXICON_NAME)
        if actual != manifest.outputs.lexicon_sha256:
            raise ArtifactMismatchError(
                f"{profile_dir}: lexicon checksum {actual} does not match manifest "
                f"{manifest.outputs.lexicon_sha256}",
                path=str(profile_dir),
            )
        if manifest.counts.answers != len(answers) or manifest.counts.guesses != len(guesses):
            raise ProfileIntegrityError(
                f"{profile_dir}: manifest counts do not match the lexicon contents",
                manifest=manifest.counts.model_dump(),
                actual={"answers": len(answers), "guesses": len(guesses)},
            )

    try:
        profile = Profile(
            profile_id=manifest.profile_id,
            language=manifest.language,
            dialect=manifest.dialect,
            length=manifest.length,
            alphabet=manifest.alphabet,
            answers=answers,
            guesses=guesses,
            manifest_sha256=sha256_file(manifest_path),
            source_ids=tuple(source.id for source in manifest.sources),
            answer_index={word: i for i, word in enumerate(answers)},
            guess_index={word: i for i, word in enumerate(guesses)},
        )
    except ProfileIntegrityError:
        raise
    return profile


def read_manifest(profile_dir: Path) -> LexiconManifest:
    return load_manifest(Path(profile_dir) / MANIFEST_NAME)


def counts_for(answers: tuple[str, ...], guesses: tuple[str, ...], length: int) -> Counts:
    return Counts(
        answers=len(answers),
        guesses=len(guesses),
        by_length={str(length): len(guesses)},
    )


def verify_profile_dir(profile_dir: Path) -> list[str]:
    """Re-derive every checksum for a built profile; return a list of problems."""

    profile_dir = Path(profile_dir)
    problems: list[str] = []
    try:
        manifest = load_manifest(profile_dir / MANIFEST_NAME)
    except ProfileIntegrityError as exc:
        return [str(exc)]

    lexicon = profile_dir / LEXICON_NAME
    if not lexicon.exists():
        problems.append(f"{profile_dir}: missing {LEXICON_NAME}")
        return problems
    actual = sha256_file(lexicon)
    if actual != manifest.outputs.lexicon_sha256:
        problems.append(f"{profile_dir}: lexicon checksum mismatch")

    table = manifest.outputs.feedback_table
    if table:
        table_path = Path(table)
        if not table_path.exists():
            problems.append(f"{profile_dir}: manifest references a missing table {table}")
        elif sha256_file(table_path) != manifest.outputs.table_sha256:
            problems.append(f"{profile_dir}: table checksum mismatch")

    try:
        profile = load_profile(profile_dir)
    except (ProfileIntegrityError, ArtifactMismatchError) as exc:
        problems.append(str(exc))
        return problems

    if profile.length != manifest.length:
        problems.append(f"{profile_dir}: profile length disagrees with manifest")
    if len(profile.answers) != manifest.counts.answers:
        problems.append(f"{profile_dir}: answer count disagrees with manifest")
    return problems
