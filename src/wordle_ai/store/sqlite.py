"""SQLite persistence for benchmark runs (technical specification §11).

One file, WAL mode, no server. Writers are single-threaded (the CLI); readers may be
concurrent, which is what the analysis and report commands rely on. The schema is
versioned and migrated forward in place, so an older store keeps working after an
upgrade instead of being silently reinterpreted.

Per-turn data lives on the ``game`` row (``candidates_json``) rather than in a row per
decision: every §4 metric needs the candidate counts around each turn, and nothing in
the benchmark needs a separate decision table. The service API (Phase 7) owns per
decision records.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..bench.metrics import RunResult
from ..errors import WordleError
from ..sim.runner import GameRecord

SCHEMA_VERSION = 1
DEFAULT_GAME_DB = Path("data") / "bench" / "runs.sqlite"

_MIGRATIONS: dict[int, str] = {
    1: """
    CREATE TABLE IF NOT EXISTS dataset (
        profile_id      TEXT PRIMARY KEY,
        manifest_sha256 TEXT NOT NULL,
        built_utc       TEXT NOT NULL,
        counts_json     TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS run (
        run_id             TEXT PRIMARY KEY,
        profile_id         TEXT NOT NULL,
        rules              TEXT NOT NULL,
        prior              TEXT NOT NULL,
        attempts           INTEGER NOT NULL,
        strategy           TEXT NOT NULL,
        answer_set         TEXT NOT NULL,
        seed               INTEGER,
        config_sha256      TEXT NOT NULL,
        created_utc        TEXT NOT NULL,
        metrics_json       TEXT NOT NULL,
        determinism_sha256 TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS game (
        run_id             TEXT NOT NULL REFERENCES run(run_id),
        answer             TEXT NOT NULL,
        guesses_json       TEXT NOT NULL,
        solved             INTEGER NOT NULL,
        n_guesses          INTEGER NOT NULL,
        elapsed_ms         REAL NOT NULL,
        final_candidates   INTEGER NOT NULL,
        opener             TEXT NOT NULL,
        candidates_json    TEXT NOT NULL,
        PRIMARY KEY (run_id, answer)
    );
    CREATE TABLE IF NOT EXISTS artifact (
        kind        TEXT NOT NULL,
        profile_id  TEXT NOT NULL,
        rules       TEXT NOT NULL,
        prior       TEXT NOT NULL,
        attempts    INTEGER NOT NULL,
        path        TEXT NOT NULL,
        sha256      TEXT NOT NULL,
        created_utc TEXT NOT NULL,
        PRIMARY KEY (kind, profile_id, rules, prior, attempts)
    );
    CREATE TABLE IF NOT EXISTS cache_meta (
        key         TEXT PRIMARY KEY,
        sha256      TEXT NOT NULL,
        bytes       INTEGER NOT NULL,
        created_utc TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS run_profile_strategy ON run(profile_id, strategy);
    """,
}


class StoreError(WordleError):
    """A store operation failed or a requested run is not present."""

    code = "store_error"
    exit_code = 3


@dataclass(frozen=True)
class StoredRun:
    run_id: str
    record: dict
    provenance: dict

    @property
    def status(self) -> str:
        return str(self.record.get("status", "succeeded"))

    @property
    def strategy(self) -> str:
        return str(self.record.get("strategy", ""))


def connect(path: Path | str) -> sqlite3.Connection:
    """Open (creating if needed) a store with WAL enabled and migrate it."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    migrate(connection)
    return connection


def schema_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def migrate(connection: sqlite3.Connection) -> int:
    """Apply every migration above the stored version; return the final version."""

    current = schema_version(connection)
    if current > SCHEMA_VERSION:
        raise StoreError(
            f"store schema version {current} is newer than this build's {SCHEMA_VERSION}; "
            "upgrade the package instead of downgrading the store"
        )
    for version in range(current + 1, SCHEMA_VERSION + 1):
        with connection:
            connection.executescript(_MIGRATIONS[version])
            connection.execute(f"PRAGMA user_version={version}")
    return schema_version(connection)


class RunStore:
    """Write and read benchmark runs, one connection per instance."""

    def __init__(self, path: Path | str = DEFAULT_GAME_DB) -> None:
        self.path = Path(path)
        self._connection = connect(self.path)

    # ---- lifecycle --------------------------------------------------------
    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "RunStore":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # ---- writes -----------------------------------------------------------
    def save(
        self,
        result: RunResult,
        games: Sequence[GameRecord],
        *,
        provenance: dict,
        status: str = "succeeded",
        decisions: bool = False,
    ) -> str:
        """Persist a run and its games atomically; return the run id."""

        if not result.run_key:
            raise StoreError("refusing to store a run without a run key")
        if decisions:  # pragma: no cover - reserved for the Phase 7 service
            raise StoreError("per-decision rows are not part of the Phase 4 schema")

        record = result.to_dict()
        record["status"] = status
        record["provenance"] = provenance
        created = provenance.get("finished_utc") or provenance.get("started_utc") or ""
        payload = json.dumps(record, sort_keys=True)
        rows = [
            (
                result.run_key,
                game.answer,
                json.dumps(list(game.guesses)),
                int(game.solved),
                game.turns,
                game.elapsed_ms,
                game.final_candidates,
                game.opener,
                json.dumps(
                    {
                        "before": list(game.candidates_before),
                        "after": list(game.candidates_after),
                    }
                ),
            )
            for game in games
        ]
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO run (run_id, profile_id, rules, prior, attempts, strategy,
                                 answer_set, seed, config_sha256, created_utc,
                                 metrics_json, determinism_sha256)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    metrics_json = excluded.metrics_json,
                    determinism_sha256 = excluded.determinism_sha256
                """,
                (
                    result.run_key,
                    result.profile_id,
                    result.mode,
                    provenance.get("prior", "uniform"),
                    result.max_attempts,
                    result.strategy,
                    result.answer_set_id,
                    result.seed,
                    provenance.get("config_sha256", ""),
                    created,
                    payload,
                    result.determinism_sha256,
                ),
            )
            self._connection.executemany(
                """
                INSERT OR REPLACE INTO game (run_id, answer, guesses_json, solved, n_guesses,
                                             elapsed_ms, final_candidates, opener,
                                             candidates_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return result.run_key

    def save_artifact(
        self,
        *,
        kind: str,
        profile_id: str,
        rules: str,
        prior: str,
        attempts: int,
        path: str,
        sha256: str,
        created_utc: str,
    ) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO artifact
                    (kind, profile_id, rules, prior, attempts, path, sha256, created_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (kind, profile_id, rules, prior, attempts, path, sha256, created_utc),
            )

    # ---- reads ------------------------------------------------------------
    def resolve(self, run_id: str) -> str:
        """Resolve a full run id or an unambiguous prefix."""

        matches = [
            row[0]
            for row in self._connection.execute(
                "SELECT run_id FROM run WHERE run_id LIKE ?", (f"{run_id}%",)
            )
        ]
        if not matches:
            raise StoreError(f"no run in {self.path} starts with {run_id!r}")
        if len(matches) > 1:
            raise StoreError(
                f"run prefix {run_id!r} is ambiguous ({len(matches)} matches); use more characters"
            )
        return matches[0]

    def get(self, run_id: str) -> StoredRun:
        full = self.resolve(run_id)
        row = self._connection.execute(
            "SELECT run_id, metrics_json FROM run WHERE run_id = ?", (full,)
        ).fetchone()
        if row is None:  # pragma: no cover - resolve() proved it exists
            raise StoreError(f"run {full} is not present")
        record = json.loads(row["metrics_json"])
        return StoredRun(
            run_id=full, record=record, provenance=dict(record.get("provenance", {}))
        )

    def games(self, run_id: str) -> list[dict]:
        full = self.resolve(run_id)
        return [
            dict(row)
            for row in self._connection.execute(
                "SELECT * FROM game WHERE run_id = ? ORDER BY rowid", (full,)
            )
        ]

    def list_runs(self, *, limit: int = 50) -> list[dict]:
        return [
            {
                "run_id": row["run_id"],
                "profile_id": row["profile_id"],
                "rules": row["rules"],
                "strategy": row["strategy"],
                "answer_set": row["answer_set"],
                "attempts": row["attempts"],
                "seed": row["seed"],
                "metrics": json.loads(row["metrics_json"]),
            }
            for row in self._connection.execute(
                "SELECT * FROM run ORDER BY created_utc DESC LIMIT ?", (limit,)
            )
        ]

    def has_completed(self, run_key: str) -> bool:
        row = self._connection.execute(
            "SELECT metrics_json FROM run WHERE run_id = ?", (run_key,)
        ).fetchone()
        if row is None:
            return False
        return json.loads(row["metrics_json"]).get("status") == "succeeded"
