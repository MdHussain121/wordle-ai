"""SQLite store contract: schema version, round-trip, prefixes, concurrent readers."""

from __future__ import annotations

import sqlite3

import pytest

from wordle_ai.bench.metrics import summarise
from wordle_ai.sim.runner import GameRecord
from wordle_ai.store.sqlite import RunStore, StoreError, connect, migrate, schema_version
from wordle_ai.types import RuleMode


def _records() -> list[GameRecord]:
    return [
        GameRecord(answer="aaaa", guesses=("cccc", "aaaa"), solved=True, decision_ms=(1.0, 1.0),
                   candidates_before=(100, 4), candidates_after=(4, 1)),
        GameRecord(answer="bbbb", guesses=("dddd",), solved=False, decision_ms=(1.0,),
                   candidates_before=(100,), candidates_after=(9,)),
    ]


def _result(run_key: str = "a" * 64):
    return summarise(
        _records(),
        profile_id="fixture.en.5",
        profile_manifest_sha256="b" * 64,
        strategy="entropy",
        objective="maximise information gain",
        mode=RuleMode.NORMAL,
        max_attempts=6,
        total_s=0.5,
        run_key=run_key,
        answer_set_id="fixture.en.5.all.deadbeef",
    )


def test_schema_is_versioned_and_migration_is_idempotent(tmp_path):
    path = tmp_path / "runs.sqlite"
    connection = connect(path)
    assert schema_version(connection) == 1
    assert migrate(connection) == 1
    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"dataset", "run", "game", "artifact", "cache_meta"} <= tables
    assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    connection.close()


def test_save_and_read_back_a_run(tmp_path):
    with RunStore(tmp_path / "runs.sqlite") as store:
        result = _result()
        provenance = {"started_utc": "2026-11-20T00:00:00Z", "prior": "uniform", "wall_s": 0.5}
        run_id = store.save(result, _records(), provenance=provenance)
        assert run_id == "a" * 64
        assert store.has_completed(run_id)

        stored = store.get(run_id[:10])
        assert stored.record["strategy"] == "entropy"
        assert stored.status == "succeeded"
        assert stored.provenance["prior"] == "uniform"

        games = store.games(run_id)
        assert [row["answer"] for row in games] == ["aaaa", "bbbb"]
        assert games[0]["opener"] == "cccc"
        assert games[0]["final_candidates"] == 1
        assert games[1]["final_candidates"] == 9

        listed = store.list_runs()
        assert [entry["run_id"] for entry in listed] == [run_id]


def test_status_is_persisted_and_resume_ignores_failed_runs(tmp_path):
    with RunStore(tmp_path / "runs.sqlite") as store:
        result = _result()
        store.save(result, _records(), provenance={}, status="budget_exceeded")
        assert store.has_completed(result.run_key) is False
        assert store.get(result.run_key).status == "budget_exceeded"


def test_refuses_a_run_without_a_key(tmp_path):
    with RunStore(tmp_path / "runs.sqlite") as store:
        with pytest.raises(StoreError, match="run key"):
            store.save(_result(run_key=""), _records(), provenance={})


def test_unknown_and_ambiguous_prefixes_are_refused(tmp_path):
    with RunStore(tmp_path / "runs.sqlite") as store:
        store.save(_result(run_key="ab" + "0" * 62), _records(), provenance={})
        store.save(_result(run_key="ab" + "1" * 62), _records(), provenance={})
        with pytest.raises(StoreError, match="ambiguous"):
            store.get("ab")
        with pytest.raises(StoreError, match="no run"):
            store.get("zz")
        assert store.get("ab0") is not None


def test_two_readers_can_open_the_same_store(tmp_path):
    path = tmp_path / "runs.sqlite"
    with RunStore(path) as writer:
        writer.save(_result(), _records(), provenance={})
    first = connect(path)
    second = connect(path)
    try:
        assert first.execute("SELECT COUNT(*) FROM game").fetchone()[0] == 2
        assert second.execute("SELECT COUNT(*) FROM run").fetchone()[0] == 1
    finally:
        first.close()
        second.close()


def test_a_newer_schema_is_not_silently_downgraded(tmp_path):
    path = tmp_path / "runs.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version=99")
    connection.commit()
    with pytest.raises(StoreError, match="newer"):
        migrate(connection)
    connection.close()
