"""Shared fixtures.

Profiles are built once per session into a temporary processed directory, from the
pinned sources in ``data/raw``. The classic profile needs the user-supplied lists in
``data/user``. Those lists are a hard prerequisite of the Phase 1 gate, so a missing
file fails the suite with instructions instead of skipping: a skipped classic test would
make the gate claim meaningless.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wordle_ai.config import load_config
from wordle_ai.lexicon.build import build, request_from_config
from wordle_ai.lexicon.profile import load_profile

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "default.toml"
DATA_DIR = REPO_ROOT / "data"


@pytest.fixture(scope="session")
def settings():
    return load_config(CONFIG_PATH)


@pytest.fixture(scope="session")
def classic_lists() -> tuple[Path, Path]:
    answers = DATA_DIR / "user" / "classic_answers.txt"
    guesses = DATA_DIR / "user" / "classic_guesses.txt"
    missing = [path for path in (answers, guesses) if not path.exists()]
    if missing:
        pytest.fail(
            "classic lists are missing: "
            + ", ".join(str(path) for path in missing)
            + ". Run `wordle-ai lex fetch --source user --answers <answers> --guesses <guesses> "
            "--attest-license`. The Phase 1 gate requires the classic profile, so this is a "
            "failure rather than a skip.",
            pytrace=False,
        )
    return answers, guesses


@pytest.fixture(scope="session")
def processed_root(tmp_path_factory):
    return tmp_path_factory.mktemp("processed")


@pytest.fixture(scope="session")
def builder(settings, processed_root):
    cache: dict[tuple[str, str], object] = {}

    def get(profile_id: str, table: str = "none"):
        key = (profile_id, table)
        if key not in cache:
            request = request_from_config(
                profile_id,
                settings,
                data_dir=DATA_DIR,
                processed_dir=processed_root,
                table_policy=table,
            )
            cache[key] = build(request)
        return cache[key]

    return get


@pytest.fixture(scope="session")
def profile_dir(builder, processed_root):
    def get(profile_id: str, table: str = "none") -> Path:
        path = processed_root / profile_id
        if not (path / "manifest.json").exists():
            builder(profile_id, table)
        return path

    return get


@pytest.fixture(scope="session")
def strict_profiles(builder, profile_dir):
    ids = [f"strict.en.{length}" for length in range(1, 6)]
    return {pid: load_profile(profile_dir(pid)) for pid in ids}


@pytest.fixture(scope="session")
def classic_profile(builder, profile_dir, classic_lists):
    builder("classic.en.5", table="auto")
    return load_profile(profile_dir("classic.en.5", table="auto"))
