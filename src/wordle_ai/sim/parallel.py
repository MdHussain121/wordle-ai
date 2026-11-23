"""Process-pool runner: shard by answer, reduce in answer order (Phase 4).

The reduction is order independent by construction: workers return records for
disjoint answers, and the parent re-sorts them into the requested answer order before
hashing or reporting. Worker count therefore cannot change the determinism hash, which
is exactly what B-12 measures.

Each worker builds its own profile, row source and strategy once, in an initialiser, so
nothing large is pickled per game. Sharding is by answer index, never by game state.
"""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Sequence

from ..engine.table import open_rows
from ..lexicon.profile import load_profile
from ..solver.policy import subset_profile
from ..strategy import get_strategy
from ..types import Profile, RuleMode
from .runner import GameRecord, play_game, run_profile

_WORKER: dict[str, Any] = {}


def _load(profile_dir: Path, subset_size: int | None) -> Profile:
    return subset_profile(load_profile(Path(profile_dir)), subset_size)


def _init_worker(
    profile_dir: str,
    subset_size: int | None,
    table_path: str | None,
    strategy_name: str,
    strategy_kwargs: dict[str, Any],
    mode: str,
    max_attempts: int,
    feedback_source: str,
    strict_legality: bool,
) -> None:
    profile = _load(Path(profile_dir), subset_size)
    _WORKER.update(
        profile=profile,
        rows=open_rows(profile, Path(table_path) if table_path else None),
        strategy=get_strategy(strategy_name, **strategy_kwargs),
        cache={},
        mode=RuleMode(mode),
        max_attempts=max_attempts,
        feedback_source=feedback_source,
        strict_legality=strict_legality,
    )


def _play_chunk(answers: list[str]) -> list[GameRecord]:
    worker = _WORKER
    return [
        play_game(
            worker["profile"],
            worker["strategy"],
            answer,
            rows=worker["rows"],
            mode=worker["mode"],
            max_attempts=worker["max_attempts"],
            cache=worker["cache"],
            feedback_source=worker["feedback_source"],
            strict_legality=worker["strict_legality"],
        )
        for answer in answers
    ]


def shards(answers: Sequence[str], workers: int) -> list[list[str]]:
    """Split answers into at most ``workers`` contiguous, near-equal chunks."""

    if not answers:
        return []
    count = max(1, min(workers, len(answers)))
    size = -(-len(answers) // count)
    return [list(answers[start : start + size]) for start in range(0, len(answers), size)]


def run_profile_parallel(
    *,
    profile_dir: Path,
    subset_size: int | None = None,
    table_path: Path | None = None,
    strategy_name: str = "",
    strategy_kwargs: dict[str, Any] | None = None,
    answers: Sequence[str],
    workers: int = 1,
    mode: RuleMode = RuleMode.NORMAL,
    max_attempts: int = 6,
    feedback_source: str = "table",
    strict_legality: bool = True,
) -> tuple[list[GameRecord], float]:
    """Play ``answers`` across ``workers`` processes and return records in answer order."""

    selected = list(answers)
    kwargs = dict(strategy_kwargs or {})
    started = time.perf_counter()
    if workers <= 1 or len(selected) <= 1:
        profile = _load(Path(profile_dir), subset_size)
        rows = open_rows(profile, Path(table_path) if table_path else None)
        return run_profile(
            profile,
            get_strategy(strategy_name, **kwargs),
            rows=rows,
            mode=mode,
            max_attempts=max_attempts,
            answers=selected,
            feedback_source=feedback_source,
            strict_legality=strict_legality,
        )

    chunks = shards(selected, workers)
    with ProcessPoolExecutor(
        max_workers=len(chunks),
        initializer=_init_worker,
        initargs=(
            str(profile_dir),
            subset_size,
            str(table_path) if table_path else None,
            strategy_name,
            kwargs,
            mode.value,
            max_attempts,
            feedback_source,
            strict_legality,
        ),
    ) as pool:
        parts = list(pool.map(_play_chunk, chunks))

    records = [record for part in parts for record in part]
    position = {answer: index for index, answer in enumerate(selected)}
    records.sort(key=lambda record: position[record.answer])
    return records, time.perf_counter() - started
