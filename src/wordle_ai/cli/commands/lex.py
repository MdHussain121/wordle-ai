"""`wordle-ai lex` commands: fetch, build, inspect, verify, diff."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from ...config import DEFAULT_CONFIG_PATH, Settings, load_config
from ...errors import ProfileIntegrityError, WordleError
from ...lexicon.build import (
    BuildResult,
    ProfileRequest,
    all_profile_ids,
    build,
    parse_profile_id,
    request_from_config,
)
from ...lexicon.profile import (
    MANIFEST_NAME,
    load_profile,
    read_manifest,
    verify_profile_dir,
)
from ...lexicon.source import (
    fetch_source,
    import_user_source,
    load_lock,
    verify_all,
)
from ..output import emit, fail

app = typer.Typer(no_args_is_help=True, help="Lexicon fetch, build, inspection and verification.")


def _result_payload(result: BuildResult) -> dict:
    return {
        "profile_id": result.profile_id,
        "output_dir": str(result.output_dir),
        "answers": result.answers,
        "guesses": result.guesses,
        "raw_entries": result.raw_entries,
        "rejected_total": result.rejected_total,
        "duplicates_removed": result.duplicates_removed,
        "single_letter_exclusions": result.single_letter_exclusions,
        "lexicon_sha256": result.lexicon_sha256,
        "answers_sha256": result.answers_sha256,
        "manifest_sha256": result.manifest_sha256,
        "table_sha256": result.table_sha256,
        "table_bytes": result.table_bytes,
        "table_policy_used": result.table_policy_used,
        "elapsed_s": round(result.elapsed_s, 3),
    }


@app.command("fetch")
def fetch(
    source: str = typer.Option(..., "--source", help="scowl | enable | user"),
    dest: Path = typer.Option(Path("data/raw"), "--dest", help="Destination for downloads."),
    answers: Optional[Path] = typer.Option(None, "--answers", help="User answers file."),
    guesses: Optional[Path] = typer.Option(None, "--guesses", help="User guesses file."),
    attest_license: bool = typer.Option(
        False, "--attest-license", help="Confirm you may use the supplied lists locally."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Fetch or import a pinned source."""

    try:
        lock = load_lock()
        if source == "user":
            if answers is None or guesses is None:
                raise ProfileIntegrityError(
                    "--source user requires --answers and --guesses", source=source
                )
            user_dir = Path("data/user")
            answer_path, guess_path = import_user_source(
                answers, guesses, destination_dir=user_dir, attest_license=attest_license
            )
            payload = {
                "source": "user",
                "answers": str(answer_path),
                "guesses": str(guess_path),
                "license": "unverified; never redistributed",
            }
        elif source in lock["sources"]:
            status = fetch_source(source, lock)
            payload = {
                "source": source,
                "path": str(status.path),
                "sha256": status.sha256,
                "verified": status.verified,
            }
        else:
            raise ProfileIntegrityError(f"unknown source {source!r}", source=source)
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return

    if as_json:
        emit(payload)
    else:
        typer.echo(f"{payload['source']}: {payload}")


@app.command("build")
def build_command(
    profile: list[str] = typer.Option(None, "--profile", help="Profile id, e.g. strict.en.5."),
    build_all: bool = typer.Option(False, "--all", help="Build every configured profile."),
    dialect: str = typer.Option("american", "--dialect", help="american | british | ..."),
    table: Optional[str] = typer.Option(
        None, "--table", help="auto | full | none | hybrid (default: config)"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the plan without writing."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Override data directory."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Build one or more profiles from pinned sources."""

    try:
        settings: Settings = load_config(config)
        ids = list(profile or [])
        if build_all:
            ids.extend(all_profile_ids(settings))
        if not ids:
            raise ProfileIntegrityError("no profile requested; use --profile or --all")
        unique_ids = list(dict.fromkeys(ids))
        requests: list[ProfileRequest] = [
            request_from_config(
                pid,
                settings,
                dialect=dialect,
                data_dir=data_dir,
                table_policy=table,
            )
            for pid in unique_ids
        ]
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return

    if dry_run:
        payload = {
            "dry_run": True,
            "profiles": [
                {
                    "profile_id": request.profile_id,
                    "family": request.family,
                    "length": request.length,
                    "output_dir": str(request.output_dir),
                    "table_policy": request.table_policy,
                }
                for request in requests
            ],
        }
        if as_json:
            emit(payload)
        else:
            for item in payload["profiles"]:
                typer.echo(
                    f"would build {item['profile_id']} -> {item['output_dir']} "
                    f"(table={item['table_policy']})"
                )
        return

    results = []
    try:
        for request in requests:
            results.append(build(request))
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return

    payload = {"built": [_result_payload(result) for result in results]}
    if as_json:
        emit(payload)
        return
    for result in results:
        typer.echo(
            f"{result.profile_id}: answers={result.answers} guesses={result.guesses} "
            f"raw={result.raw_entries} rejected={result.rejected_total} "
            f"dupes={result.duplicates_removed} table={'yes' if result.table_sha256 else 'no'} "
            f"{result.elapsed_s:.2f}s"
        )
        typer.echo(f"  lexicon {result.lexicon_sha256}")
        typer.echo(f"  manifest {result.manifest_sha256}")


@app.command("inspect")
def inspect(
    profile: str = typer.Option(..., "--profile", help="Profile id, e.g. strict.en.5."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Override data directory."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Show counts, sources, licences, policy and checksums for a built profile."""

    try:
        settings = load_config(config)
        family, language, length = parse_profile_id(profile)
        root = Path(data_dir) if data_dir is not None else Path(settings.general.data_dir)
        profile_dir = root / "processed" / profile
        manifest = read_manifest(profile_dir)
        loaded = load_profile(profile_dir)
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return

    payload = {
        "profile_id": manifest.profile_id,
        "family": family,
        "language": language,
        "length": length,
        "dialect": manifest.dialect,
        "alphabet": manifest.alphabet,
        "counts": manifest.counts.model_dump(),
        "raw_entries": manifest.raw_entries,
        "duplicates_removed": manifest.duplicates_removed,
        "rejected": manifest.rejected.model_dump(),
        "single_letter_exclusions": manifest.single_letter_exclusions,
        "transforms": manifest.transforms,
        "sources": [source.model_dump() for source in manifest.sources],
        "policy": manifest.policy,
        "outputs": manifest.outputs.model_dump(),
        "first_words": list(loaded.answers[:5]),
        "last_words": list(loaded.answers[-5:]),
    }
    if as_json:
        emit(payload)
        return
    typer.echo(f"{manifest.profile_id}  length={manifest.length} dialect={manifest.dialect}")
    typer.echo(f"  answers={manifest.counts.answers} guesses={manifest.counts.guesses}")
    typer.echo(f"  raw={manifest.raw_entries} rejected={manifest.rejected.total} "
               f"duplicates={manifest.duplicates_removed}")
    if manifest.single_letter_exclusions:
        typer.echo(f"  single-letter exclusions={manifest.single_letter_exclusions}")
    for source in manifest.sources:
        typer.echo(f"  source {source.id} {source.version} ({source.license})")
    typer.echo(f"  lexicon {manifest.outputs.lexicon_sha256}")
    if manifest.outputs.table_sha256:
        typer.echo(f"  table   {manifest.outputs.table_sha256}")


@app.command("verify")
def verify(
    profile: list[str] = typer.Option(None, "--profile", help="Profile id to verify."),
    all_profiles: bool = typer.Option(False, "--all", help="Verify every built profile."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Override data directory."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Re-derive checksums and re-assert invariants for built profiles."""

    try:
        settings = load_config(config)
        root = Path(data_dir) if data_dir is not None else Path(settings.general.data_dir)
        processed = root / "processed"
        ids = list(profile or [])
        if all_profiles:
            ids = sorted(p.name for p in processed.iterdir() if p.is_dir()) if processed.exists() else []
        if not ids:
            raise ProfileIntegrityError("no profile requested; use --profile or --all")
        results = {}
        problems: list[str] = []
        for pid in ids:
            found = verify_profile_dir(processed / pid)
            results[pid] = {"ok": not found, "problems": found}
            problems.extend(found)
        lock = load_lock()
        sources = verify_all(lock)
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return

    payload = {
        "profiles": results,
        "sources": [
            {"id": status.id, "sha256": status.sha256, "verified": status.verified}
            for status in sources
        ],
        "ok": not problems,
    }
    if as_json:
        emit(payload)
    else:
        for pid, entry in results.items():
            typer.echo(f"{pid}: {'ok' if entry['ok'] else 'FAILED'}")
            for problem in entry["problems"]:
                typer.echo(f"  {problem}")
        for status in sources:
            typer.echo(f"source {status.id}: verified {status.sha256[:12]}…")
    if problems:
        raise typer.Exit(3)


@app.command("diff")
def diff(
    profile: str = typer.Option(..., "--profile", help="Current profile id."),
    manifest_old: Path = typer.Option(..., "--manifest-old", help="Older manifest.json."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Override data directory."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Report words added to and removed from a profile since an older manifest."""

    try:
        settings = load_config(config)
        root = Path(data_dir) if data_dir is not None else Path(settings.general.data_dir)
        current_dir = root / "processed" / profile
        current = read_manifest(current_dir)
        old = json.loads(Path(manifest_old).read_text(encoding="utf-8"))

        def words_from(entry: dict) -> set[str]:
            answers_path = Path(entry["outputs"]["answers"])
            if not answers_path.exists():
                raise ProfileIntegrityError(
                    f"answers file referenced by manifest is missing: {answers_path}"
                )
            return set(answers_path.read_text(encoding="utf-8").split())

        old_words = words_from(old)
        new_words = words_from(current.model_dump(mode="json"))
    except WordleError as exc:
        fail(exc, as_json=as_json)
        return
    except (KeyError, json.JSONDecodeError) as exc:
        fail(
            ProfileIntegrityError(f"cannot read old manifest {manifest_old}: {exc}"),
            as_json=as_json,
        )
        return

    added = sorted(new_words - old_words)
    removed = sorted(old_words - new_words)
    payload = {
        "profile_id": profile,
        "old_manifest": str(manifest_old),
        "current_manifest": str(current_dir / MANIFEST_NAME),
        "added_count": len(added),
        "removed_count": len(removed),
        "added": added[:50],
        "removed": removed[:50],
    }
    if as_json:
        emit(payload)
    else:
        typer.echo(f"{profile}: +{len(added)} -{len(removed)}")
        if added:
            typer.echo(f"  added:   {' '.join(added[:10])}")
        if removed:
            typer.echo(f"  removed: {' '.join(removed[:10])}")
