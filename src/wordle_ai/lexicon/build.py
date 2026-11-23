"""The twelve-step lexicon build pipeline (dataset plan §5).

Order of stages, with every rejection counted under exactly one reason:

    fetch/verify → decode → normalise → length → validity → whitelist → dedupe →
    provenance → answers/guesses → index → table → export

Two builds of the same pinned inputs produce byte-identical artifacts: JSON is written
with sorted keys, the lexicon archive has fixed zip metadata, and the manifest carries
no wall-clock timestamp unless ``SOURCE_DATE_EPOCH`` is supplied.

Timings are returned in :class:`BuildResult` and printed by the CLI, never written into
the manifest, because a timestamp there would destroy reproducibility.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..config import ProfileFamily, Settings
from ..engine.table import build_table, save_table, table_footprint
from ..errors import ConfigError, ProfileIntegrityError, SourceIntegrityError, UnsupportedProfile
from ..types import Profile
from .manifest import (
    Counts,
    LexiconManifest,
    Outputs,
    Rejected,
    SourceRef,
    dump_manifest,
)
from .normalize import RejectReason, classify, decode_bytes, normalize_word
from .profile import ANSWERS_NAME, LEXICON_NAME, MANIFEST_NAME, TABLE_NAME, save_lexicon
from .source import SCOWL_LEVELS, load_lock, sha256_file, verify_source

SINGLE_LETTER_WHITELIST = frozenset({"a", "i"})
SUPPORTED_DIALECTS = ("american", "british", "british_z", "canadian")


@dataclass
class Tally:
    raw: int = 0
    duplicates: int = 0
    counts: dict[str, int] = field(default_factory=dict)

    def reject(self, reason: RejectReason) -> None:
        self.counts[reason.value] = self.counts.get(reason.value, 0) + 1

    @property
    def rejected_total(self) -> int:
        return sum(self.counts.values())


@dataclass(frozen=True)
class ProfileRequest:
    profile_id: str
    family: str
    language: str
    dialect: str
    length: int
    alphabet: str
    data_dir: Path
    raw_dir: Path
    output_dir: Path
    scowl_size: int = 0
    include_enable: bool = False
    answer_policy: str = "same"
    answers_path: Path | None = None
    guesses_path: Path | None = None
    table_policy: str = "auto"
    table_max_bytes: int = 268_435_456
    lru_rows: int = 2048


@dataclass(frozen=True)
class BuildResult:
    profile_id: str
    output_dir: Path
    answers: int
    guesses: int
    raw_entries: int
    rejected_total: int
    duplicates_removed: int
    single_letter_exclusions: int
    lexicon_sha256: str
    answers_sha256: str
    manifest_sha256: str
    table_sha256: str | None
    table_bytes: int | None
    table_policy_used: str
    elapsed_s: float


def parse_profile_id(profile_id: str) -> tuple[str, str, int]:
    parts = profile_id.split(".")
    if len(parts) != 3:
        raise ConfigError(
            f"profile id must look like <family>.<language>.<length>, got {profile_id!r}",
            profile_id=profile_id,
        )
    family, language, length_text = parts
    try:
        length = int(length_text)
    except ValueError:
        raise ConfigError(f"profile id {profile_id!r} has a non-numeric length") from None
    if not (1 <= length <= 5):
        raise UnsupportedProfile(f"length {length} is outside the supported range 1..5")
    return family, language, length


def request_from_config(
    profile_id: str,
    settings: Settings,
    *,
    dialect: str = "american",
    data_dir: Path | None = None,
    processed_dir: Path | None = None,
    table_policy: str | None = None,
) -> ProfileRequest:
    family_name, language, length = parse_profile_id(profile_id)
    family: ProfileFamily = settings.family(family_name)
    if dialect not in SUPPORTED_DIALECTS:
        raise ConfigError(f"unsupported dialect {dialect!r}; choose from {SUPPORTED_DIALECTS}")
    if family.scowl_size and family.scowl_size not in SCOWL_LEVELS:
        raise ConfigError(f"SCOWL size {family.scowl_size} is not a published level")
    if family.answer_policy == "file" and not (family.answers_path and family.guesses_path):
        raise ConfigError(f"profile family {family_name!r} requires answers_path and guesses_path")

    root = Path(data_dir) if data_dir is not None else Path(settings.general.data_dir)
    processed = Path(processed_dir) if processed_dir is not None else root / "processed"
    policy = table_policy or settings.feedback.build_policy

    return ProfileRequest(
        profile_id=profile_id,
        family=family_name,
        language=language,
        dialect=dialect,
        length=length,
        alphabet=settings.profile.alphabet,
        data_dir=root,
        raw_dir=root / "raw",
        output_dir=processed / profile_id,
        scowl_size=family.scowl_size,
        include_enable=family.include_enable,
        answer_policy=family.answer_policy,
        answers_path=Path(family.answers_path) if family.answers_path else None,
        guesses_path=Path(family.guesses_path) if family.guesses_path else None,
        table_policy=policy,
        table_max_bytes=settings.feedback.table_max_bytes,
        lru_rows=settings.feedback.lru_rows,
    )


def _epoch() -> str | None:
    value = os.environ.get("SOURCE_DATE_EPOCH")
    if not value:
        return None
    try:
        stamp = int(value)
    except ValueError:
        return None
    return datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _absorb_lines(
    text: str,
    *,
    length: int,
    alphabet: str,
    tally: Tally,
    accepted: set[str],
    transforms: set[str],
) -> None:
    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        tally.raw += 1
        word = normalize_word(raw)
        reason = classify(word, length=length, alphabet=alphabet)
        if reason is not None:
            tally.reject(reason)
            continue
        accepted.add(word)
        transforms.add("filter:ascii_alpha" if word.isascii() else "filter:alphabet")


def _read_source_file(path: Path, transforms: set[str]) -> str:
    decoded = decode_bytes(path.read_bytes())
    transforms.add(f"decode:{decoded.encoding}")
    return decoded.text


def _apply_whitelist(
    words: set[str], length: int, tally: Tally
) -> tuple[set[str], int]:
    if length != 1:
        return words, 0
    removed = words - SINGLE_LETTER_WHITELIST
    for _ in removed:
        tally.reject(RejectReason.NOT_IN_WHITELIST)
    return words & SINGLE_LETTER_WHITELIST, len(removed)


def _scowl_words(
    request: ProfileRequest,
    tally: Tally,
    transforms: set[str],
) -> set[str]:
    if request.scowl_size == 0:
        return set()
    root = request.raw_dir / "scowl" / "final"
    if not root.exists():
        raise SourceIntegrityError(
            f"SCOWL final/ directory not found under {root.parent}; run `wordle-ai lex fetch "
            "--source scowl`",
            path=str(root),
        )
    categories = ("english", request.dialect)
    transforms.add(f"source:scowl:{'+'.join(categories)}:size<={request.scowl_size}")
    accepted: set[str] = set()
    for category in categories:
        for level in SCOWL_LEVELS:
            if level > request.scowl_size:
                continue
            path = root / f"{category}-words.{level}"
            if not path.exists():
                raise SourceIntegrityError(
                    f"missing SCOWL file {path}; expected a complete SCOWL 2020.12.07 tree",
                    path=str(path),
                )
            _absorb_lines(
                _read_source_file(path, transforms),
                length=request.length,
                alphabet=request.alphabet,
                tally=tally,
                accepted=accepted,
                transforms=transforms,
            )
    return accepted


def _enable_words(
    request: ProfileRequest,
    tally: Tally,
    transforms: set[str],
) -> set[str]:
    if not request.include_enable:
        return set()
    path = request.raw_dir / "enable1.txt"
    if not path.exists():
        raise SourceIntegrityError(
            f"ENABLE list not found at {path}; run `wordle-ai lex fetch --source enable`",
            path=str(path),
        )
    transforms.add("source:enable")
    accepted: set[str] = set()
    _absorb_lines(
        _read_source_file(path, transforms),
        length=request.length,
        alphabet=request.alphabet,
        tally=tally,
        accepted=accepted,
        transforms=transforms,
    )
    return accepted


def _user_lists(
    request: ProfileRequest,
    tally: Tally,
    transforms: set[str],
) -> tuple[set[str], set[str]]:
    if request.answers_path is None or request.guesses_path is None:
        raise ConfigError("file-based profile requires answers_path and guesses_path")
    for path in (request.answers_path, request.guesses_path):
        if not path.exists():
            raise ProfileIntegrityError(
                f"user-supplied list not found: {path}. The classic profile is never bundled; "
                "import it with `wordle-ai lex fetch --source user ... --attest-license`.",
                path=str(path),
            )
    transforms.add("source:user:supplied")
    answers: set[str] = set()
    _absorb_lines(
        _read_source_file(request.answers_path, transforms),
        length=request.length,
        alphabet=request.alphabet,
        tally=tally,
        accepted=answers,
        transforms=transforms,
    )
    guesses: set[str] = set()
    _absorb_lines(
        _read_source_file(request.guesses_path, transforms),
        length=request.length,
        alphabet=request.alphabet,
        tally=tally,
        accepted=guesses,
        transforms=transforms,
    )
    return answers, guesses


def _source_refs(request: ProfileRequest, lock: dict, epoch: str | None) -> list[SourceRef]:
    refs: list[SourceRef] = []
    if request.scowl_size:
        spec = lock["sources"]["scowl"]
        refs.append(
            SourceRef(
                id="scowl",
                version=spec["version"],
                url=spec["url"],
                retrieved_utc=epoch,
                sha256=spec["sha256"],
                license=spec["license"],
                license_file=spec.get("license_file"),
            )
        )
    if request.include_enable:
        spec = lock["sources"]["enable"]
        refs.append(
            SourceRef(
                id="enable",
                version=spec["version"],
                url=spec["url"],
                retrieved_utc=epoch,
                sha256=spec["sha256"],
                license=spec["license"],
                license_file=spec.get("license_file"),
            )
        )
    if request.answer_policy == "file":
        user = lock["user_sources"]["classic"]
        refs.append(
            SourceRef(
                id="user:classic",
                version=user["version"],
                url=None,
                retrieved_utc=epoch,
                sha256=None,
                license=user["license"],
                license_file=None,
            )
        )
    return refs


def build(request: ProfileRequest, *, lock: dict | None = None) -> BuildResult:
    started = time.perf_counter()
    if not (1 <= request.length <= 5):
        raise UnsupportedProfile(f"length {request.length} is outside 1..5")
    if request.table_policy not in ("auto", "full", "none", "hybrid"):
        raise ConfigError(f"unknown table policy {request.table_policy!r}")

    registry = lock if lock is not None else load_lock()
    if request.scowl_size:
        verify_source("scowl", registry)
    if request.include_enable:
        verify_source("enable", registry)

    tally = Tally()
    transforms: set[str] = {"normalize:NFC", "casefold", "sort", "dedupe"}
    if request.answer_policy == "same":
        words = _scowl_words(request, tally, transforms) | _enable_words(request, tally, transforms)
        words, single_letter_exclusions = _apply_whitelist(words, request.length, tally)
        answers = guesses = words
    elif request.answer_policy == "file":
        answers, guesses = _user_lists(request, tally, transforms)
        answers, excluded_a = _apply_whitelist(answers, request.length, tally)
        guesses, excluded_g = _apply_whitelist(guesses, request.length, tally)
        single_letter_exclusions = max(excluded_a, excluded_g)
    else:  # pragma: no cover - config model restricts the values
        raise ConfigError(f"unknown answer policy {request.answer_policy!r}")

    accepted_unique = len(guesses | answers)
    tally.duplicates = tally.raw - tally.rejected_total - accepted_unique
    if tally.duplicates < 0:
        raise ProfileIntegrityError(
            "accounting invariant failed: rejections exceed raw entries",
            raw=tally.raw,
            rejected=tally.rejected_total,
            accepted=accepted_unique,
        )
    if not answers:
        raise ProfileIntegrityError(f"profile {request.profile_id} has no answers")
    if not answers <= guesses:
        raise ProfileIntegrityError(
            f"profile {request.profile_id}: answers are not a subset of guesses"
        )

    answer_tuple = tuple(sorted(answers))
    guess_tuple = tuple(sorted(guesses))
    if len(guess_tuple) != len(set(guess_tuple)) or len(answer_tuple) != len(set(answer_tuple)):
        raise ProfileIntegrityError("duplicate entries survived deduplication")

    output_dir = request.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    transforms.add(f"filter:length=={request.length}")
    if request.length == 1:
        transforms.add("filter:single_letter_whitelist")
    transforms.add("assert:answers_subset_guesses")

    lexicon_sha, lexicon_bytes = save_lexicon(
        output_dir / LEXICON_NAME,
        answers=answer_tuple,
        guesses=guess_tuple,
        alphabet=request.alphabet,
        length=request.length,
    )
    answers_text = "\n".join(answer_tuple) + "\n"
    answers_path = output_dir / ANSWERS_NAME
    answers_temporary = answers_path.with_name(answers_path.name + ".tmp")
    answers_temporary.write_text(answers_text, encoding="ascii", newline="\n")
    answers_temporary.replace(answers_path)
    answers_sha = sha256_file(answers_path)

    profile = Profile(
        profile_id=request.profile_id,
        language=request.language,
        dialect=request.dialect,
        length=request.length,
        alphabet=request.alphabet,
        answers=answer_tuple,
        guesses=guess_tuple,
        manifest_sha256="",
        source_ids=tuple(ref.id for ref in _source_refs(request, registry, None)),
        answer_index={w: i for i, w in enumerate(answer_tuple)},
        guess_index={w: i for i, w in enumerate(guess_tuple)},
    )

    footprint = table_footprint(profile)
    table_path: str | None = None
    table_sha: str | None = None
    table_bytes: int | None = None
    policy_used = "none"
    wants_table = request.table_policy == "full" or (
        request.table_policy in ("auto", "hybrid") and footprint <= request.table_max_bytes
    )
    if wants_table:
        table = build_table(profile, max_bytes=None if request.table_policy == "full" else request.table_max_bytes)
        table_file = output_dir / TABLE_NAME
        table_sha, table_bytes = save_table(table, table_file)
        table_path = str(table_file)
        policy_used = "full"
        del table

    epoch = _epoch()
    manifest = LexiconManifest(
        profile_id=request.profile_id,
        created_utc=epoch,
        language=request.language,
        dialect=request.dialect,
        length=request.length,
        alphabet=request.alphabet,
        sources=_source_refs(request, registry, epoch),
        transforms=sorted(transforms),
        counts=Counts(
            answers=len(answer_tuple),
            guesses=len(guess_tuple),
            by_length={str(request.length): len(guess_tuple)},
        ),
        raw_entries=tally.raw,
        duplicates_removed=tally.duplicates,
        rejected=Rejected(
            total=tally.rejected_total,
            **{key: tally.counts.get(key, 0) for key in (
                "empty",
                "apostrophe",
                "hyphen",
                "space",
                "digit",
                "non_ascii",
                "outside_alphabet",
                "wrong_length",
                "not_in_whitelist",
            )},
        ),
        single_letter_exclusions=single_letter_exclusions,
        outputs=Outputs(
            lexicon=str(output_dir / LEXICON_NAME),
            lexicon_sha256=lexicon_sha,
            lexicon_bytes=lexicon_bytes,
            answers=str(answers_path),
            answers_sha256=answers_sha,
            feedback_table=table_path,
            table_sha256=table_sha,
            feedback_table_bytes=table_bytes,
        ),
        policy={
            "answer_policy": request.answer_policy,
            "dialect": request.dialect,
            "scowl_size": request.scowl_size,
            "include_enable": request.include_enable,
            "ascii_only": True,
            "include_possessives": False,
            "include_proper_nouns": False,
            "include_abbreviations": False,
            "excluded_source_categories": ["proper-names", "abbreviations", "upper", "contractions"],
            "single_letter_whitelist": sorted(SINGLE_LETTER_WHITELIST),
            "table_policy": request.table_policy,
            "table_policy_used": policy_used,
            "table_budget_bytes": request.table_max_bytes,
            "table_footprint_bytes": footprint,
        },
    )
    manifest_path = output_dir / MANIFEST_NAME
    dump_manifest(manifest, manifest_path)
    manifest_sha = sha256_file(manifest_path)

    elapsed = time.perf_counter() - started
    return BuildResult(
        profile_id=request.profile_id,
        output_dir=output_dir,
        answers=len(answer_tuple),
        guesses=len(guess_tuple),
        raw_entries=tally.raw,
        rejected_total=tally.rejected_total,
        duplicates_removed=tally.duplicates,
        single_letter_exclusions=single_letter_exclusions,
        lexicon_sha256=lexicon_sha,
        answers_sha256=answers_sha,
        manifest_sha256=manifest_sha,
        table_sha256=table_sha,
        table_bytes=table_bytes,
        table_policy_used=policy_used,
        elapsed_s=elapsed,
    )


def all_profile_ids(settings: Settings) -> list[str]:
    """Every profile the configured families can build.

    Open families cover lengths 1-5; the classic family is five letters only, because
    its user-supplied lists are five-letter lists.
    """

    ids: list[str] = []
    for family, spec in settings.profiles.items():
        lengths = (5,) if spec.answer_policy == "file" else range(1, 6)
        ids.extend(f"{family}.{settings.profile.language}.{length}" for length in lengths)
    return ids
