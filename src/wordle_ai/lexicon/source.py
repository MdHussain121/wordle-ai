"""Source acquisition and integrity verification (§3 dataset plan step 1–2).

Sources are pinned by version *and* checksum in ``sources.lock``. A file that does not
match its pinned checksum is refused; it is never silently re-downloaded or replaced.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ..errors import SourceIntegrityError

LOCK_PATH = Path("sources.lock")
SCOWL_LEVELS = (10, 20, 35, 40, 50, 55, 60, 70, 80, 95)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_lock(path: Path | None = None) -> dict:
    target = Path(path) if path is not None else LOCK_PATH
    if not target.exists():
        raise SourceIntegrityError(f"source lock file not found: {target}", path=str(target))
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceIntegrityError(f"{target}: invalid JSON: {exc}", path=str(target)) from exc


@dataclass(frozen=True)
class SourceStatus:
    id: str
    path: Path
    sha256: str
    expected: str
    verified: bool


def verify_source(source_id: str, lock: dict) -> SourceStatus:
    try:
        spec = lock["sources"][source_id]
    except KeyError:
        raise SourceIntegrityError(f"unknown source {source_id!r}") from None
    local = Path(spec.get("archive") or spec.get("path"))
    if not local.exists():
        raise SourceIntegrityError(
            f"source {source_id!r} is not present at {local}; run `wordle-ai lex fetch --source "
            f"{source_id}` first",
            source=source_id,
            path=str(local),
        )
    actual = sha256_file(local)
    if actual != spec["sha256"]:
        raise SourceIntegrityError(
            f"source {source_id!r} checksum mismatch: expected {spec['sha256']}, got {actual}",
            source=source_id,
            expected=spec["sha256"],
            actual=actual,
        )
    return SourceStatus(
        id=source_id, path=local, sha256=actual, expected=spec["sha256"], verified=True
    )


def verify_all(lock: dict) -> list[SourceStatus]:
    return [verify_source(key, lock) for key in lock["sources"]]


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as response, open(temporary, "wb") as handle:
        shutil.copyfileobj(response, handle)
    temporary.replace(destination)


def fetch_source(source_id: str, lock: dict) -> SourceStatus:
    """Ensure a pinned source exists locally and matches its checksum."""

    try:
        spec = lock["sources"][source_id]
    except KeyError:
        raise SourceIntegrityError(f"unknown source {source_id!r}") from None
    local = Path(spec.get("archive") or spec.get("path"))
    if not local.exists():
        _download(spec["url"], local)
    status = verify_source(source_id, lock)
    if spec["kind"] == "zip":
        extract_to = Path(spec["extract_to"])
        marker = extract_to / "final"
        if not marker.exists():
            extract_to.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(local) as archive:
                archive.extractall(extract_to.parent)
            # The archive expands to a versioned directory; normalise its name.
            extracted = [p for p in extract_to.parent.iterdir() if p.is_dir() and p.name.startswith("scowl-")]
            if not marker.exists() and extracted:
                if extract_to.exists():
                    shutil.rmtree(extract_to)
                extracted[0].rename(extract_to)
        if not marker.exists():
            raise SourceIntegrityError(
                f"archive {local} did not produce {marker}", path=str(marker)
            )
    return status


def import_user_source(
    answers_path: Path,
    guesses_path: Path,
    *,
    destination_dir: Path,
    attest_license: bool,
) -> tuple[Path, Path]:
    """Copy user-supplied lists into ``data/user`` after an explicit licence attestation.

    The classic Wordle lists have no verified open licence, so they are never bundled;
    they only ever live in the ignored user directory.
    """

    if not attest_license:
        raise SourceIntegrityError(
            "user-supplied lists require --attest-license: the licence status of the classic "
            "Wordle lists is unverified and they are never redistributed"
        )
    for path in (answers_path, guesses_path):
        if not path.exists():
            raise SourceIntegrityError(f"user source not found: {path}", path=str(path))
    destination_dir.mkdir(parents=True, exist_ok=True)
    answers_dest = destination_dir / "classic_answers.txt"
    guesses_dest = destination_dir / "classic_guesses.txt"
    for source, dest in ((answers_path, answers_dest), (guesses_path, guesses_dest)):
        words = sorted(
            {
                line.strip().casefold()
                for line in source.read_text(encoding="utf-8").splitlines()
                if line.strip()
            }
        )
        if not words:
            raise SourceIntegrityError(f"user source {source} contains no words")
        dest.write_text("\n".join(words) + "\n", encoding="ascii", newline="\n")
    return answers_dest, guesses_dest
