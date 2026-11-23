"""Run the required release benchmark set B-01…B-12 (Phase 8, criterion 5).

Each row is either executed on the shipped profiles or recorded as blocked with the
reason, because the plan's rule is that a missing cell is a visible decision rather than
an accident. Runs are stored in SQLite and resumed by run key; the report carries the
determinism hash and both averages for every executed row.

Deviations from the plan are named in the report (prefix subsets instead of samples for
B-07/B-08, reduced answer counts for the hard modes), so no row is labelled exhaustive
when it is not. B-07/B-08 use labelled answer prefixes; the full-profile B-08 row is run
at both 100 and 500 answers so the opener cost is measured at two scales.

Run::

    .venv/Scripts/python.exe -u tools/run_release.py
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from wordle_ai.bench.report import result_from_dict
from wordle_ai.bench.runner import (
    PACKAGE_VERSION,
    RunSpec,
    config_digest,
    execute,
    prepare,
)
from wordle_ai.config import DEFAULT_CONFIG_PATH, load_config
from wordle_ai.errors import BudgetExceeded, WordleError
from wordle_ai.lexicon.profile import load_profile
from wordle_ai.store.sqlite import RunStore
from wordle_ai.types import RuleMode

OUT = Path("data/phase8")
DATA = Path("data")
RUN_BUDGET_S = 300.0


@dataclass(frozen=True)
class Entry:
    id: str
    spec: RunSpec | None
    note: str = ""


def duplicate_answers(answers: tuple[str, ...]) -> tuple[str, ...]:
    """Answers with at least two duplicated letters — the B-11 adversarial subset."""

    return tuple(
        word
        for word in answers
        if sum(1 for count in Counter(word).values() if count >= 2) >= 2
    )


def build_entries(profile_answers: tuple[str, ...]) -> list[Entry]:
    classic_policy = Path("policies/classic.en.5.normal.uniform.policy.json")
    entries: list[Entry] = []

    def run(
        run_id: str,
        strategy: str,
        profile_id: str = "classic.en.5",
        *,
        mode: RuleMode = RuleMode.NORMAL,
        prior: str = "uniform",
        answers: tuple[str, ...] | None = None,
        workers: int = 16,
        policy_path: Path | None = None,
        note: str = "",
    ) -> Entry:
        return Entry(
            run_id,
            RunSpec(
                profile_id=profile_id,
                profile_dir=DATA / "processed" / profile_id,
                strategy=strategy,
                mode=mode,
                prior=prior,
                # Benchmark plan §5.2: 6 attempts at L=5, 4 at L=3–4, 3 at L=1–2.
                attempts=(
                    6
                    if profile_id.endswith("5")
                    else 3
                    if profile_id.endswith(("1", "2"))
                    else 4
                ),
                answers=answers,
                workers=workers,
                policy_path=policy_path,
            ),
            note,
        )

    if classic_policy.exists():
        entries.append(
            run(
                "B-01",
                "exact",
                policy_path=classic_policy,
                note="canonical exact DP policy; B-01 reproduced 3.4212 avg",
            )
        )
    else:
        entries.append(
            Entry(
                "B-01",
                None,
                "blocked: no classic exact policy exists",
            )
        )

    entries += [
        run("B-02", "hybrid.balanced"),
        run("B-03", "entropy"),
        run("B-03", "expected_remaining"),
        run("B-03", "minimax"),
        run(
            "B-04",
            "hybrid.balanced",
            mode=RuleMode.HARD,
            answers=profile_answers[:200],
            note="first 200 answers (hard-mode runtime), not exhaustive",
        ),
        run(
            "B-05",
            "hybrid.balanced",
            mode=RuleMode.SUPERHARD,
            answers=profile_answers[:200],
            note="first 200 answers (superhard runtime), not exhaustive",
        ),
    ]
    for length in range(1, 6):
        entries.append(
            run(f"B-06.L{length}", "hybrid.balanced", f"strict.en.{length}")
        )
    entries += [
        run(
            "B-07",
            "hybrid.balanced",
            "extended.en.5",
            answers=profile_answers_extended()[:500],
            note="first 500 answers (prefix, not a stratified sample)",
        ),
        run(
            "B-08",
            "hybrid.balanced",
            "full.en.5",
            answers=profile_answers_full()[:500],
            note="first 500 answers (prefix, not a stratified sample)",
        ),
        run(
            "B-08.100",
            "hybrid.balanced",
            "full.en.5",
            answers=profile_answers_full()[:100],
            note="first 100 answers (prefix, not a stratified sample)",
        ),
        run("B-09", "hybrid.balanced", prior="zipf:beta=0.05"),
        run(
            "B-10.lookahead",
            "lookahead.two_ply",
            "strict.en.5",
            answers=profile_answers_strict5()[:200],
            note="first 200 answers (labelled prefix; the full 4,444-answer row is a "
            "separate compute decision)",
        ),
        run(
            "B-10.rollout",
            "rollout.random",
            "strict.en.5",
            answers=profile_answers_strict5()[:200],
            note="first 200 answers (labelled prefix; the full 4,444-answer row is a "
            "separate compute decision)",
        ),
        run(
            "B-11",
            "hybrid.balanced",
            answers=duplicate_answers(profile_answers),
            note="all classic answers with at least two duplicated letters",
        ),
        run("B-12.16w", "hybrid.balanced", workers=16),
        run("B-12.1w", "hybrid.balanced", workers=1),
        run(
            "AB-08",
            "ml.value_lookahead",
            note="Phase 6 neural value lookahead (G1-G8 passed, admitted)",
        ),
    ]
    return entries


def _fmt(value) -> str:
    return "—" if value is None else f"{value:.4f}"


def profile_answers_extended() -> tuple[str, ...]:
    return load_profile(DATA / "processed" / "extended.en.5").answers


def profile_answers_full() -> tuple[str, ...]:
    return load_profile(DATA / "processed" / "full.en.5").answers


def profile_answers_strict5() -> tuple[str, ...]:
    return load_profile(DATA / "processed" / "strict.en.5").answers


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    settings = load_config(DEFAULT_CONFIG_PATH)
    classic = load_profile(DATA / "processed" / "classic.en.5")
    digest = config_digest(DEFAULT_CONFIG_PATH)
    store = RunStore(Path(settings.general.data_dir) / "bench" / "runs.sqlite")
    records: list[dict] = []
    try:
        for entry in build_entries(classic.answers):
            if entry.spec is None:
                records.append(
                    {
                        "id": entry.id,
                        "status": "blocked",
                        "note": entry.note,
                    }
                )
                continue
            prepared = prepare(entry.spec, config_sha256=digest)
            # B-12's two worker counts share one run key by design (the key is the
            # experiment, not the machine), so the serial re-run is not stored.
            reuse_store = entry.id != "B-12.1w"
            if reuse_store and store.has_completed(prepared.run_key):
                stored = store.get(prepared.run_key)
                result = result_from_dict(stored.record)
                status = "resumed"
            else:
                try:
                    result = execute(
                        entry.spec,
                        store=store if reuse_store else None,
                        config_sha256=digest,
                        time_budget_s=RUN_BUDGET_S,
                    )
                    status = "succeeded"
                except BudgetExceeded as exc:
                    records.append(
                        {
                            "id": entry.id,
                            "status": "blocked",
                            "note": f"budget exceeded: {exc}",
                        }
                    )
                    continue
                except WordleError as exc:
                    records.append(
                        {
                            "id": entry.id,
                            "status": "blocked",
                            "note": f"{exc.code}: {exc}",
                        }
                    )
                    continue
            records.append(
                {
                    "id": entry.id,
                    "status": status,
                    "run_key": result.run_key,
                    "strategy": result.strategy,
                    "profile_id": result.profile_id,
                    "mode": result.mode,
                    "prior": entry.spec.prior,
                    "answers": result.answers,
                    "exhaustive": result.exhaustive,
                    "answer_set_id": result.answer_set_id,
                    "avg_guesses_solved": result.avg_guesses_solved,
                    "avg_guesses_all": result.avg_guesses_all,
                    "worst_case": result.worst_case,
                    "failed": result.failed,
                    "determinism_sha256": result.determinism_sha256,
                    "total_s": result.total_s,
                    "note": entry.note,
                }
            )
    finally:
        store.close()

    by_id = {record["id"]: record for record in records}
    determinism = "not comparable"
    if "B-12.16w" in by_id and "B-12.1w" in by_id:
        same = (
            by_id["B-12.16w"].get("determinism_sha256")
            == by_id["B-12.1w"].get("determinism_sha256")
        )
        determinism = "identical" if same else "DIFFERS"
    payload = {
        "package_version": PACKAGE_VERSION,
        "profile_id": classic.profile_id,
        "runs": records,
        "b12_determinism": determinism,
    }
    (OUT / "release_matrix.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )

    lines = [
        "# Phase 8 release report",
        "",
        f"Package {PACKAGE_VERSION}, profile `{classic.profile_id}`, normal rules and "
        "uniform prior unless the row says otherwise.",
        "",
        "| Id | Profile | Strategy | Mode | Prior | Answers | Exhaustive | Avg solved | Avg all | Worst | Fails | Determinism | Wall s | Status |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for record in records:
        if record["status"] == "blocked":
            lines.append(
                f"| {record['id']} | — | — | — | — | — | — | — | — | — | — | — | — | "
                f"blocked |"
            )
            continue
        lines.append(
            f"| {record['id']} | {record['profile_id']} | {record['strategy']} | "
            f"{record['mode']} | {record['prior']} | {record['answers']:,} | "
            f"{'yes' if record['exhaustive'] else 'no'} | "
            f"{_fmt(record['avg_guesses_solved'])} | {_fmt(record['avg_guesses_all'])} | "
            f"{record['worst_case']} | {record['failed']} | "
            f"{record['determinism_sha256'][:16]}… | {record['total_s']:.1f} | "
            f"{record['status']} |"
        )
    lines += [
        "",
        "## Blocked and deviating rows",
        "",
    ]
    for record in records:
        if record.get("note"):
            lines.append(f"- **{record['id']}** — {record['note']}")
    lines += [
        "",
        f"**B-12:** determinism hashes are {determinism} at 1 and 16 workers.",
        "",
        "## Stored runs",
        "",
    ]
    for record in records:
        if record["status"] != "blocked":
            lines.append(f"- **{record['id']}** — `{record['run_key']}`")
    lines += [
        "",
        "## Negative ablations",
        "",
        "- The Zipf prior (B-09) is the Phase 5 rejection: beta=0.05 cost −0.0052 guesses "
        "against uniform for `hybrid.balanced`, with a 95% bootstrap interval spanning "
        "zero; the default remains uniform (`data/bench/phase5/`).",
        "- No learned ranker or value model exists (Phase 6 is blocked on classic DP "
        "labels), so AB-3/AB-9/AB-10 are not claimed.",
        "",
    ]
    (OUT / "release_report.md").write_text(
        "\n".join(lines), encoding="utf-8", newline="\n"
    )
    print(f"B-12 determinism: {determinism}")
    for record in records:
        if record["status"] == "blocked":
            print(f"{record['id']:<10} blocked: {record['note'][:100]}")
        else:
            print(
                f"{record['id']:<10} {record['status']:<9} "
                f"avg={record['avg_guesses_solved']:.4f} "
                f"answers={record['answers']} "
                f"det={record['determinism_sha256'][:12]}"
            )
    print(f"wrote {OUT / 'release_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
