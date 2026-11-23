# WORDLE_AI_IMPLEMENTATION_ROADMAP.md

**Status:** Phase 0 deliverable, revision 1.0 · **Date:** 2026-11-19
**Rule:** no phase starts before its predecessor's completion gate is met, and no completion gate
is met by a claim that has not been measured.

Effort figures are `[E]` engineering estimates in focused working days for one developer. They are
planning aids, not commitments, and they exclude the multi-day offline jobs in Phase 3.

---

## 0. Phase map

```
Phase 0  Research & specification           [DONE in this corpus]
   │
Phase 1  Dataset & game engine              ──► lexicon, feedback, state, invariants
   │
Phase 2  Classical solver                   ──► filtering, scoring, 6 heuristic strategies
   │                                            (+ thin harness so results exist early)
   ├───────────────┐
Phase 3  Exact optimization                  Phase 4  Simulator & benchmark
   │  DP, policies, pruning                     full harness, metrics, reports
   └───────────────┴──────────► Phase 5  Probabilistic intelligence
                                     priors, calibration, Bayesian cost
                                          │
                                 Phase 6  ML experimentation
                                     distillation, ranker, gate, RL appendix
                                          │
                                 Phase 7  Product interface
                                     assistant, self-play, labs, benchmark UI
                                          │
                                 Phase 8  Optimization & readiness
                                     Rust kernel (if measured), packaging, hardening
```

Phases 3 and 4 are independent after Phase 2 and may run in either order; 4's harness is needed to
evidence 3's runtime. The thin harness in Phase 2 exists so that every later phase has numbers to
argue with.

---

## Phase 0 — Research and specification

**Objective.** Establish the evidence base, the architecture and the numbers every later phase is
measured against.

**Deliverables.** The nine documents in this corpus, plus the measurement spike
(`tools/measure_lexicons.py` → `data/processed/measurements.json`) that replaced estimates with
measured lexicon counts.

**Completion gate.** Documents are internally consistent; every quantitative claim carries a
`[P]/[R]/[X]/[E]/[U]` tag; the numbers ledger has no contradictions; the reproduction targets are
named with their exact configurations. **Met** on 2026-11-19 (see the research report's
Appendix C for the items that remain unverified).

**Risks.** Research drift; treating secondary summaries as primary sources; over-fitting the plan
to the 2,315 list. Mitigated by direct-source reading, the evidence audit, and the explicit
multi-profile requirement.

---

## Phase 1 — Dataset and game engine

**Objective.** A correct, deterministic word and feedback layer, plus profiles for lengths 1–5.

**Features.** Lexicon fetch/verify/build for SCOWL and ENABLE; user-supplied profile import;
the 12-step pipeline; manifest and checksums; normalisation policy; validity policy; two-pass
feedback; base-3 codec; feedback table with memory policy; candidate filtering; `GameState` with
invariants; replay.

**Engineering tasks.**

1. `config.py` + `types.py` + `errors.py`; pydantic config with the keys in the technical spec.
2. `lexicon/normalize.py`: NFC, casefold, grapheme length, alphabet filter, transliteration
   (opt-in and off by default).
3. `lexicon/source.py` + `sources.lock`: download, SHA-256 verify, refuse silent updates.
4. `lexicon/build.py`: twelve stages, atomic file replacement with the manifest written last,
   rejection accounting.
5. `lexicon/profile.py`: sorted tuples, index maps, `answers ⊆ guesses` assertion, `npz` load.
6. `engine/feedback.py`: reference implementation, vectorised implementation, codec, parser.
7. `engine/table.py`: `uint8` matrix, full/hybrid/none policy, `.npy` + sidecar checksum, LRU rows.
8. `engine/state.py`: history replay, candidate mask, posterior hook, assertions.
9. `engine/filter.py`: mask filtering, bitset view, `InconsistentFeedback`.
10. `cli/main.py` + `lex` commands; `--json` output.
11. Test suites: golden duplicate letters, exhaustive L ≤ 4 equivalence, policy/property tests.

**Dependencies.** Phase 0.

**Outputs.** `lex build`, `lex verify`, `lex inspect`, `lex diff`; profiles
`strict.en.{1..5}`, `extended.en.{1..5}`, `full.en.{1..5}`; classic profile loader; feedback
tables within the memory budget.

**Tests.** All rows of the dataset plan §7; technical spec §18 rows for `normalize`, `feedback`,
`table`, `filter`, `state`.

**Completion criteria.**

1. Measured profile counts match the dataset plan exactly (or the difference is explained by a
   documented policy change and the plan is updated).
2. Exhaustive feedback equality on every (guess, answer) pair for L = 1..4, and on the full
   duplicate-letter suite plus a stratified sample for L = 5.
3. `lex verify --all` exits 0; two clean builds produce identical content checksums.
4. Classic profile loads only from user files and asserts 2,315 / 12,972.
5. Table build for classic completes within 60 s `[E]` and every cell matches the reference.

**Risks.** SCOWL composition traps (incremental levels, `english` without a dialect, Latin-1);
possessive inflation; Unicode corruption. All are covered by named tests in the dataset plan.

**Effort `[E]`.** 6–9 days.

### Gate result — measured 2026-11-19 (revision 0.1.0)

All five criteria were run against the pinned sources in `sources.lock` on Python 3.12.10.
The machine-readable evidence is `data/processed/verify_all.json` and each profile's
`manifest.json`; the suite is `134 passed` in 71.70 s and 74.37 s on two fresh runs, with
zero skipped, xfailed or deselected tests (`python -m pytest -q -s -rsx`).

| Criterion | Measurement |
|---|---|
| 1. Counts | All 15 open profiles and classic match the dataset plan exactly. L=1 is `{a, i}` (2 answers) with 24 `not_in_whitelist` exclusions for every family. Classic is 2,315 / 12,972. |
| 2. Exhaustive equality | L=1: 4 pairs; L=2: 4,225; L=3: 345,744; L=4: 5,303,809 — every pair equals the independent reference in `tests/reference.py`. L=5: 694,500 pairs (300 seeded guesses × all 2,315 answers), 1,297,200 pairs (100 seeded answers × all 12,972 guesses), and 2,594,400 pairs (200 of the 749 repeated-letter answers × all 12,972 guesses). |
| 3. Verification and reproducibility | `lex verify --all` exits 0 for 16 profiles and re-derives both source checksums. Two consecutive classic builds produce the identical lexicon (`ef49bdde…`) and manifest (`5127f7ba…`) hashes. |
| 4. Classic provenance | Loads only from `data/user/`, asserts 2,315 / 12,972, and fails closed with a message naming `--attest-license` when the files are absent. Its manifest records `unverified; never redistributed`. |
| 5. Table cost and correctness | Classic table builds in 4.31 s and 4.45 s (limit 60 s) at 30,030,180 cells. `tools/verify_table_against_reference.py --profile-dir data/processed/classic.en.5` checked all 30,030,180 cells with 0 mismatches in 67.7 s. |

**Decisions taken where the documents were silent or impractical.**

- `created_utc` and every `retrieved_utc` are `null` unless `SOURCE_DATE_EPOCH` is set;
  otherwise provenance timestamps would make byte-identical rebuilds impossible. Timings
  are returned by the builder and printed, never stored.
- `Pattern.parse` infers its length from the text; length is enforced against the profile
  by `Profile.validate_pattern`. A new `InvalidPattern` error class names both rejections.
- The build is single-process, so the dataset plan's "1 versus 16 workers" determinism row
  is not applicable in Phase 1; determinism is verified by repeated builds instead.
- `THIRD_PARTY_NOTICES.md` and `.gitignore` were added to satisfy dataset plan §10 items 7
  and 8. The notices reproduce the SCOWL permission text and record that WordNet, Open
  English WordNet and wordfreq are not used in this phase.

---

## Phase 2 — Classical solver

**Objective.** A strategy engine with the six cheap strategies and a thin evaluation harness, so
that later phases optimise against evidence rather than intuition.

**Features.** Strategy protocol; `random_valid`, `first_candidate`, `letter_frequency`,
`positional_frequency`, `expected_remaining`, `minimax`, `entropy`; deterministic tie-breaking;
`Decision` with breakdown and generated explanation; hard-mode constraint predicate; hybrid
selector skeleton; `solve`/`selfplay` commands; a thin harness that plays all answers for one
strategy and prints avg/max.

**Engineering tasks.**

1. `strategy/base.py`: protocol, `ScoreBreakdown`, tie-breaking helper, budget object.
2. Six strategies with vectorised scoring over the table; per-strategy unit tests.
3. `strategy/hybrid.py`: branch selection with recorded branch id; no lookahead yet.
4. `engine/state.py` constraint derivation (`LetterConstraint`) and `legal(g, history)`.
5. `api/service.py`: `new_game`, `apply_feedback`, `suggest`, `candidates`.
6. `sim/runner.py` thin loop (serial), enough for Phase 2 numbers.
7. CLI: `play`, `suggest`, `selfplay`, `diagnose`.
8. Tests: legality of every recommendation, determinism, explanation generation, mode constraints.

**Dependencies.** Phase 1.

**Outputs.** Working solver on all five lengths; first internal benchmark table for classic
entropy/expected-remaining/minimax; hard-mode constraint engine.

**Tests.** Property: every recommended guess ∈ `G` and legal in mode. Golden: a hand-computed
10-state fixture where entropy and expected-remaining choose different words (they must, and the
test documents which). Budget: a forced `BudgetExceeded` falls back to a cheaper strategy.

**Completion criteria.**

1. Classic / normal / entropy solves 100% of 2,315 answers within 6 guesses, and the measured
   average is within 0.10 of the published entropy result (3.476 with a full guess list) `[P]`.
2. Every strategy is selectable and produces a breakdown for every candidate guess.
3. Hard mode produces zero constraint violations on an exhaustive check of all legal guesses at
   depth 2.
4. Repeated runs produce identical choices (determinism).

**Risks.** Vectorised scoring subtly disagreeing with the reference; tie-breaking instability;
hard-mode over-restriction (the classic duplicate-letter bug). Mitigated by oracle tests and by
deriving constraints through the feedback function.

**Effort `[E]`.** 7–10 days.

### Gate result — measured 2026-11-20 (revision 0.2.0)

Phase 2 was built and measured against the shipped classic profile (2,315 answers / 12,972 guesses,
6 attempts, uniform prior, normal mode). Every row below is exhaustive over all 2,315 answers; the
harness never samples and never drops a failed game from the denominator.

```
python -m wordle_ai.cli.main bench run --profile classic.en.5 --strategies all
```

| Strategy | avg solved | avg all | max | fail % | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|---|---|---|
| `entropy` | 3.6380 | 3.6380 | 6 | 0.00 | 0 | 22 | 896 | 1296 | 100 | 1 |
| `entropy_candidates` | 3.5810 | 3.5987 | 6 | 0.52 | 1 | 131 | 999 | 919 | 207 | 46 |
| `expected_remaining` | 3.6536 | 3.6536 | 5 | 0.00 | 0 | 27 | 819 | 1398 | 71 | 0 |
| `expected_remaining_candidates` | 3.6017 | 3.6238 | 6 | 0.65 | 1 | 131 | 957 | 946 | 224 | 41 |
| `first_candidate` | 4.2747 | 4.3430 | 6 | 2.51 | 1 | 56 | 407 | 861 | 722 | 210 |
| `hybrid.balanced` | 3.6536 | 3.6536 | 5 | 0.00 | 0 | 27 | 819 | 1398 | 71 | 0 |
| `letter_frequency` | 4.0114 | 4.0462 | 6 | 1.17 | 0 | 59 | 555 | 1064 | 521 | 89 |
| `minimax` | 3.7024 | 3.7024 | 5 | 0.00 | 1 | 32 | 734 | 1436 | 112 | 0 |
| `minimax_candidates` | 3.6262 | 3.6467 | 6 | 0.60 | 1 | 131 | 910 | 990 | 223 | 46 |
| `positional_frequency` | 3.8514 | 3.8976 | 6 | 1.47 | 0 | 96 | 682 | 1039 | 393 | 71 |

Openers are derived, never stored: `soare` (entropy), `raise` (entropy_candidates, minimax),
`roate` (expected_remaining), `aback` (first_candidate). Each is the argmin of that strategy's
objective over the profile, so a different guess list produces a different word.

**Cost and reproducibility.** The ten strategies together took 4 m 24 s of wall clock (sum of the
printed per-strategy times: 15.6–36.0 s each), single process, on the 16-core Windows host used for
Phase 1. The printed table
is byte-identical on a second run (two runs diffed clean); the determinism hash of every strategy
matched as well, and `--json` reproduces the same numbers while excluding only timings.

| Criterion | Measurement |
|---|---|
| 1. Entropy solves all 2,315 within 6, average within 0.10 of 3.476 | 100% solved, max 6, **3.6380** — 0.162 above the published full-list figure. **Not met; recorded, not corrected** (see below). |
| 2. Every strategy selectable with a breakdown | 10 strategies in the registry, each available via `--strategies` and `strategy list`; `score()` returns one entry per legal guess. |
| 3. Hard mode: zero constraint violations | Enforced by the harness on every turn; the sampled check in `tests/integration/test_harness.py` replays 120 classic games (400+ turns) through `derive_constraint` and `is_legal` with zero violations. A full `--mode hard` run over 2,315 answers gives `entropy` 3.6652 (0.52% unsolved), `hybrid.balanced` 3.6674 (0.39%), `minimax` 3.7104 (0.65%), all with zero violations. |
| 4. Repeated runs identical | Table byte-identical across two full runs; determinism hashes equal; unit tests repeat every strategy's choice on identical states. |

**Discrepancies against the research corpus, recorded honestly.**

- Full-list entropy measures 3.6380 against the published 3.476 (Luebeck, `soare` opener). The
  opener and the 100% success rate agree; the average does not. Candidate causes, in the order the
  benchmark plan's discrepancy protocol requires: the lists match the classic profile; the rules are
  normal mode, 6 attempts, uniform prior; the difference is therefore the policy detail — this
  implementation breaks entropy ties by expected remaining (§6.2) and switches to a candidate only
  in the last two turns, with no two-ply/rollout endgame. The corpus figure is left unchanged.
- Candidates-only entropy measures 3.5810 with 12 unsolved games, against Greenberg's 3.4955 with
  max 6. Candidates-only expected-remaining measures 3.6017 with 15 unsolved, against 3.4600.
- **The published ordering is not reproduced**: Greenberg reports bins (3.4600) better than entropy
  (3.4955); here entropy is better than expected-remaining by 0.0156 on the full guess list and by
  0.0207 candidates-only. Both objectives are implemented exactly as §6.2 defines them and their
  partition statistics are checked against brute force, so this is a result about this endgame and
  tie-breaking policy, not a claim that the corpus is wrong.

**Deviations from the Phase 2 task list, and why.**

- `random_valid` is **not** implemented: it needs an RNG in the production selection path, which the
  approved constraint for this phase forbids. A seeded random baseline belongs to the benchmark
  matrix (Phase 4), where the seed is part of the run key.
- `api/service.py` and the `play`/`suggest`/`selfplay` commands are not built. This phase's agreed
  surface is the strategy layer plus the evaluation harness (`bench run`, `strategy list`); the
  service layer and interactive play are Phase 7 work in the architecture, and the harness already
  exercises the same `GameState`/`Decision` path they would use.
- `letter_frequency` and `positional_frequency` score against the **remaining candidates**, not the
  whole corpus. A corpus-wide table is state-independent, so the strategy repeated one word until
  it failed (measured: 5.6832 average, 67.0% unsolved). The candidate-scoped version is the usable
  baseline (4.0114 / 3.8514) and is what §6.2 now specifies.

---

## Phase 3 — Exact optimisation

**Objective.** Proven-optimal play where it is affordable, with an explicit and measured boundary.

**Features.** Memoised DP with canonicalisation and pruning; root parallelism; feasibility gate;
policy artifacts and verification; `exact` strategy; policy generation CLI.

**Engineering tasks.**

1. `solver/dp.py`: recursion, canonical digest keys, bucket partition, lower bounds,
   immediate-win shortcut, incumbent pruning.
2. Root-parallel driver with deterministic reduction; progress reporting and resumability.
3. `solver/policy.py`: tree serialisation, checksums, verification against the profile digest,
   rules, prior and attempts.
4. Feasibility gate (`max_answers`, `max_guesses`, `time_budget`) enforced before starting.
5. `strategy/exact.py`: policy lookup, `exact: true`, fallback when absent.
6. Benchmarks: classic normal (expect 3.4212 / max 5), classic hard (expect 3.5084), strict L=3–5,
   L=4 strict; record wall-clock and memory per profile.
7. Tests: sampled states' DP value equals policy value; artifact tamper detection; gate refusal.

**Dependencies.** Phase 1; Phase 2 for heuristic ordering and incumbents.

**Outputs.** `policies/classic.en.5.normal.uniform.policy.json` (+ checksum); a measured
feasibility table replacing the `[E]` rows in the research report §6.

**Tests.** Policy value equals independently computed DP value on 1,000 sampled states; artifact
mismatch raises `ArtifactMismatchError`; a profile above the gate refuses to start without
`--force`.

**Completion criteria.**

1. Classic normal reproduces 3.4212 ± 0.0005, worst case 5, zero failures, opener `salet`,
   total 7,920.
2. Classic hard reproduces 3.5084 ± 0.0005 `[P]`.
3. The feasibility table records measured wall-clock for classic, strict L=5, and L=4 strict;
   profiles above the gate are marked infeasible with the reason.
4. Policy artifacts verify and are used in under 1 ms per decision.

**Risks.** The DP is far more expensive than planned (published: days on 64 cores `[P]`); memory
blow-up in the memo table; a subtly wrong canonicalisation merging non-equivalent states. Mitigate
with resumable progress files, a memo cap with LRU eviction, and a correctness test comparing
canonicalised and non-canonicalised results on small profiles.

**Effort `[E]`.** 8–12 days plus 1–3 days of offline compute for classic; add a contingency of
"days" if the implementation is not yet well optimised.

### Gate result — measured 2026-11-20 (revision 0.3.0)

Phase 3 was implemented as a serial, pure-Python kernel: `solver/dp.py` (memoised recursion
with incumbent pruning and a single-sort partition), `solver/policy.py` (checksummed policy
artifacts keyed by profile digest, rules, prior and attempts) and `strategy/exact.py` (policy
lookup, `exact: true`, no search at decision time). The CLI surface is
`policy build|verify|show` (with `--limit N` for a labelled answer subset);
`bench run --strategies exact --policy <artifact>` plays a policy.

Correctness is established on tractable sizes, not by the published number:

- The DP value equals an independent, unmemoised enumeration on a 4-word profile
  (`tests/unit/test_exact.py`).
- A policy solved on 12 answers of `strict.en.3` (full 588-word guess list) takes exactly the
  DP's expected 2.5833 guesses when played over those answers, with worst case 4
  (`tests/integration/test_exact_policy.py`). This comparison is what caught the only solver
  bug found in the phase: the all-green bucket was charged a further guess, so a solved game
  cost 2 instead of 1. The recursion now excludes that bucket explicitly.
- Policy verification refuses a changed payload, a stale sidecar checksum, a foreign profile
  digest, a different rule mode, prior or attempt limit (tests above).

```
python tools/measure_exact.py --budget-seconds 120
```

| Case | Answers | Guesses | K | Outcome (120 s budget) | Measured |
|---|---|---|---|---|---|
| `strict.en.2` | 65 | 65 | 6 | budget expired | 79,840 nodes, 5,189,749 guess evaluations; a separate unbudgeted run proved no 6-guess guarantee in ~128 s |
| `strict.en.3` first 12 answers | 12 | 588 | 6 | solved | 2.5833 avg, max 4, opener `hid`, 2,044 nodes, 28.3 s |
| `strict.en.3` first 40 answers | 40 | 588 | 6 | budget expired | 8,864 nodes, 5,212,327 evaluations |
| `strict.en.3`, candidates only | 588 | 588 | 6 | budget expired | 99,840 nodes, 4,123,824 evaluations |
| `strict.en.3`, all guesses | 588 | 588 | 6 | budget expired | 8,288 nodes, 4,873,916 evaluations |
| `classic.en.5` | 2,315 | 12,972 | 6 | budget expired | 544 nodes, 7,056,993 evaluations, 127.2 s (≈4.3 nodes/s) |

| Criterion | Measurement |
|---|---|
| 1. Classic normal reproduces 3.4212 ± 0.0005, max 5, opener `salet`, total 7,920 | **Not met, not claimed.** The 120 s run completed 544 nodes at ≈4.3 nodes/s; no full solve was attempted. The published 3.4212 is from a compiled solver with days of compute, which this kernel is not. |
| 2. Classic hard reproduces 3.5084 | **Not implemented.** Hard and superhard legality depends on the accumulated constraint, not on the candidate set alone, so the DP would need a `(candidates, constraint)` state. `ExactSolver` raises `UnsupportedProfile` for those modes rather than solving a different game. |
| 3. Measured feasibility table | **Met.** The table above and `data/exact/feasibility.json`, produced by `tools/measure_exact.py`; every row is a measured outcome, not an estimate. |
| 4. Artifacts verify and cost < 1 ms per decision | **Met.** A saved artifact was reloaded, verified against its profile and played 5,000 times: p50 0.161 ms, p95 0.219 ms, max 1.136 ms on the 12-answer policy. |

The boundary is therefore far tighter than the `[E]` gate assumed: `|A| ≤ 5000, |G| ≤ 20000`
is necessary but nowhere near sufficient for this implementation, and the gate (which the classic
profile passes) does not predict runtime. The roadmap's own rule applies — the next phase does not
start until this gate is met, and it is not met.

**Deviations from the Phase 3 task list, and why.**

- **Root parallelism is not implemented.** `exact.parallel_root` is accepted by the config but
  unused. Sharing the memo across workers is the hard part; independent per-worker solves would
  multiply the measured cost, not divide it, at these node counts.
- **Guess ordering is candidates-first, not heuristic-ordered.** Sorting every guess by one-step
  expected remaining costs a full partition pass per state — the same work the solver is trying
  to prune — so the order is the cheap deterministic one and the incumbent bound does the pruning.
- **`exact` is not part of `bench run --strategies all`.** A policy is profile-specific, so the
  default set remains the ten heuristics; `exact` is opt-in with `--policy`.
- **Policy artifacts are built for normal mode only.** The artifact records `rules` and refuses a
  request for a different mode, which keeps the failure explicit.

---

## Phase 4 — Simulator and benchmarking

**Objective.** The full harness that produces every metric in the benchmark plan, reproducibly.

**Features.** Environment; exhaustive and sampled runners; process pool with deterministic
reduction; all metric formulas; bootstrap and paired tests; SQLite persistence; Markdown/CSV
reports; run comparison with mismatch refusal; determinism hash.

**Engineering tasks.**

1. `sim/environment.py` and `sim/runner.py` (gym-style API, no gym dependency).
2. `sim/parallel.py`: shard by answer index, order-independent reduction, worker-count invariance.
3. `bench/metrics.py`: every §4 formula with fixture tests from hand-computed games.
4. `bench/stats.py`: bootstrap, McNemar, Wilcoxon, effect sizes.
5. `bench/runner.py`: matrix expansion, resume, budget guard.
6. `bench/report.py`: provenance block, tables, failure section, published-comparison section.
7. `store/sqlite.py`: schema, migrations, concurrent readers.
8. CLI: `bench run|report|compare`, `--json`.
9. Tests: metric fixtures, determinism across worker counts, CSV-regenerates-Markdown.

**Dependencies.** Phase 2 (thin harness); benefits from Phase 3 but does not require it.

**Outputs.** The B-01…B-12 run set; a first honest internal leaderboard across strategies and
profiles; the published-reproduction report.

**Tests.** Hand-computed fixture games reproduce every metric exactly; a deliberately failing
strategy (attempt limit 2) produces the expected failure section; comparing two different
manifest checksums is refused without a flag.

**Completion criteria.**

1. B-01 (exact) and B-03 (heuristics) run end to end and produce reports containing every metric.
2. Determinism hash identical at 1 and 16 workers.
3. A run with induced failures reports them and both `avg_solved` and `avg_all`.
4. CSV export regenerates the report aggregates to within rounding (tested).
5. Total runtime for the classic exhaustive matrix is within the 30-minute budget at 16 workers,
   or the report states the measured time and the sampling policy used.

**Risks.** Metric definitions drifting between code and document; parallel reduction ordering
bugs; silent sampling. Mitigated by fixture tests, order-independent reductions and a mandatory
`exhaustive|sampled` label in every report row.

**Effort `[E]`.** 8–11 days.

**Gate result — re-measured 2026-11-21 (package version 0.1.0).**

| Criterion | Measurement |
|---|---|
| 1. B-01 (exact) and B-03 (heuristics) run end to end with every metric | **B-03 met, B-01 met only as a subset proxy.** Three heuristics over all 2,315 answers produce every §4 metric, the distribution, a (empty) failure section and the published comparison. B-01 cannot run on classic because Phase 3's gate built no classic policy; the exact surface was measured end to end on the shipped 12-answer `strict.en.3` artifact: 2.5833 average, worst case 4, 0 failures, 0.13 s, reproducing the Phase 3 number exactly. |
| 2. Determinism hash identical at 1 and 16 workers | **Met.** `hybrid.balanced`, 2,315 answers: `393ce4ff9fb9b4e2ac281290f46c4b1f897eb563d928b789007105872952967d` at both worker counts. |
| 3. Induced failures reported with both averages | **Met.** `entropy` with `--max-attempts 3`: 1,500 unsolved of 2,315 (35.21% success), `avg_guesses_solved` 2.8442, `avg_guesses_all` 3.5931, failures listed by answer. |
| 4. CSV export regenerates the aggregates | **Met.** One row per game; `aggregates_from_csv` reproduces answers, solved, worst case, both averages and the distribution, asserted by a test and re-checked by `bench report --format csv`, which refuses to export on a mismatch. |
| 5. Classic exhaustive matrix inside the 30-minute budget | **Met without sampling.** Seven runs, 200.4 s of measured run time at 16 workers on the 16-core host; every row is labelled `exhaustive`. |

**Measured matrix** (classic.en.5, manifest `5127f7ba…`, normal, uniform prior, 6 attempts, 2,315 answers,
exhaustive; `data/bench/phase4/phase4_report.md`):

| Run | Strategy | avg solved | avg all | worst | failures |
|---|---|---|---|---|---|
| B-03 | `entropy` | 3.6380 | 3.6380 | 6 | 0 |
| B-03 | `expected_remaining` | 3.6536 | 3.6536 | 5 | 0 |
| B-03 | `minimax` | 3.7024 | 3.7024 | 5 | 0 |
| B-02 | `hybrid.balanced` | 3.6536 | 3.6536 | 5 | 0 |
| B-01 proxy | `exact`, `strict.en.3` first 12 | 2.5833 | 2.5833 | 4 | 0 |

Every figure agrees with the Phase 2 baseline and the Phase 3 measurement to four decimals, which is the
cross-check that the new report path did not change play. Only the 6-attempt exhaustive `entropy` run is
compared with the published 3.476 (+0.1620, listed as a reference comparison, not an improvement claim);
the K=3 run gets no published comparison because it is not the published experiment.

**Findings and deviations.**

- **The process pool is a determinism proof, not a speedup, for these workloads.** `entropy` took 47.3 s
  at 16 workers against 21.3 s at one worker (a serial `wordle-ai bench run --workers 1 --no-store`
  re-run), and `hybrid.balanced` 28.7 s against 26.3 s. Each worker
  starts with an empty decision cache, so the early-game states every game shares are recomputed up to
  16 times, and 16 profile loads are paid once. The pool is kept because B-12 must prove worker-count
  invariance and because state-disjoint work (rollout endgames, Phase 7) does not share those states;
  the report makes no speedup claim.
- **`peak_rss_mib` is the parent process's peak** (60.7–63.9 MiB in pool mode, 227.0 MiB serial). Worker peaks
  are not summed, so the column is honest about what it measures and conservative about the pool.
- **Calibration helpers (§4.4) exist and are fixture-tested but no Phase 4 run consumes them.** Priors
  arrive in Phase 5; adding a calibration harness here would have duplicated that phase.
- **`random_valid` is still absent.** Nothing in a production path may use an RNG, so the matrix cell is a
  labelled absence rather than a seeded implementation.
- **Resume belongs to `run_matrix`, not `bench run`.** A single interactive run always re-measures; the
  matrix driver (`tools/measure_phase4.py`) skips runs whose key is already stored as `succeeded`.
- **Phase 3's gate is still unmet** (no classic exact policy, hard mode unsupported). This phase was
  implemented on explicit instruction; B-01's classic row stays blocked by the Phase 3 boundary.
- **The package version is single-sourced at 0.1.0.** `wordle_ai.__version__` feeds the run key, the run
  provenance and the policy artifact's `solver_version`, so none of them can drift from it. The gate above
  was re-measured after the version was restored to 0.1.0, which is why every stored key now hashes that
  version; Phase 3's gate was measured while the string read 0.3.0 and was not replayed, so its shipped
  `subset12` artifact still records `solver_version` 0.3.0.

---

## Phase 5 — Probabilistic intelligence

**Objective.** Priors that are calibrated rather than assumed, and posterior-aware scoring.

**Features.** `UniformPrior`, `ZipfPrior` (optional `wordfreq` runtime dependency),
`EmpiricalPrior`; temperature calibration; `weighted_entropy` and `bayes_cost` strategies;
calibration report; prior admission gate; prior-specific policy artifacts.

**Engineering tasks.**

1. `engine/prior.py`: implementations, normalisation, caching per profile.
2. Calibration harness: log loss, Brier, ECE, reliability curve on held-out answers.
3. Temperature fit (`β`) with a validation split; refuse non-improving priors.
4. Prior-aware scoring, including the weighted expected-remaining formula.
5. Cache keys extended with prior id + params; policy artifacts keyed likewise.
6. Benchmarks B-09 and AB-3.
7. Tests: `β = 0` equals uniform exactly; prior normalisation; gate refusal; cache invalidation.

**Dependencies.** Phase 2 (scoring), Phase 4 (measurement).

**Outputs.** Calibration report for the Zipf prior (or a documented decision that it does not
beat uniform); prior-aware strategies; evidence that the default prior is the right one.

**Completion criteria.**

1. A calibration report exists with log loss, Brier and ECE on held-out answers.
2. Either the Zipf prior beats uniform on log loss with ECE < 0.05 and is admitted, or it is
   rejected with the numbers shown. Both outcomes satisfy the gate.
3. Prior-aware strategies produce identical decisions to uniform when `β = 0`.
4. A cached policy built under one prior is refused under another, with a clear error.

**Risks.** Prior mis-specification reducing solve rate; wordfreq licence breach via derived data;
overfitting the temperature to the classic list. Mitigated by the admission gate, runtime-only
dependency, and validation-split fitting with a 2023-list check.

**Effort `[E]`.** 5–7 days.

### Gate result — measured 2026-11-22 (package version 0.1.0)

Evidence: `data/bench/phase5/calibration_report.md`, `calibration.json`,
`measurements.json` and `phase5_report.md`, produced by `tools/measure_phase5.py` on
`classic.en.5` (2,315 answers), normal rules, 6 attempts, 16 workers, exhaustive.

| Criterion | Measurement |
|---|---|
| 1. Calibration report with log loss, Brier and ECE on held-out answers | **Met.** Deterministic split by `sha256('prior-split:<word>')` first four bytes: 1,179 validation / 1,136 test answers. Fitted `beta = 0.05` on validation only; held-out log loss 7.749535, Brier 0.999570, ECE (top-1) 0.000496, mean p(true) 0.000431. |
| 2. Zipf admitted, or rejected with the numbers shown | **Rejected, numbers shown.** Held-out log loss 7.749535 vs uniform 7.747165 (delta −0.002370, i.e. worse); ECE passes 0.05 but the admission rule requires both. Uniform stays the default. |
| 3. Prior-aware strategies identical to uniform when `beta = 0` | **Met.** `ZipfPrior(0)` returns the same float64 ones as `UniformPrior` (asserted bit-for-bit), and `weighted_entropy` then makes the identical decision and reports the identical entropy as `entropy`. |
| 4. A policy built under one prior is refused under another | **Met.** `load_policy(prior=...)` raises `ArtifactMismatchError` naming the artifact's prior; `policy build --prior` refuses any non-uniform id with `unsupported_prior` because the DP minimises uniform cost. |

**AB-3 / B-09** (same strategies, same 2,315 answers, uniform vs `zipf:beta=0.05`,
paired by answer with 10,000 bootstrap resamples):

| Strategy | Uniform avg | Zipf avg | Delta (zipf − uniform) | 95% CI | Significant | Worst (u/z) | Fails (u/z) |
|---|---|---|---|---|---|---|---|
| `hybrid.balanced` (B-09) | 3.6536 | 3.6587 | −0.0052 | −0.0109 .. +0.0001 | no | 5/5 | 0/0 |
| `weighted_entropy` | 3.6380 | 3.6376 | +0.0004 | −0.0006 .. +0.0015 | no | 6/6 | 0/0 |
| `bayes_cost` | 3.6523 | 3.6518 | +0.0004 | −0.0010 .. +0.0020 | no | 5/5 | 0/0 |

The uniform rows reproduce Phase 4 exactly: `hybrid.balanced` 3.6536 with determinism
hash `393ce4ff…`, the same hash Phase 4 recorded at 1 and 16 workers, so adding the
prior layer did not change uniform play. No delta is significant and the prior is
rejected, which is the outcome the plan calls a successful experiment.

**New surface.** `engine/prior.py` (`UniformPrior`, `ZipfPrior`, `EmpiricalPrior`,
`parse_prior_id`, `normalised_weights`), prior-weighted `GameState.posterior`,
`weighted_entropy` and `bayes_cost` strategies, `bench/calibration.py`, `prior
calibrate|show`, `bench run --prior zipf:beta=<b>`, and the optional `prior` extra
(`wordfreq`). Decision-cache keys now include a BLAKE2b digest of the prior weights, so
two priors cannot share a cached decision.

**Findings and deviations.**

- **ECE is measured on top-1 confidence, not on the literal probability of the true
  answer.** With 2,315 answers the literal definition has observed frequency 1 in every
  bin by construction, so ECE degenerates to `1 − mean p(a*)` and no honest prior could
  pass 0.05. `calibration.py` documents the substitution and also reports
  `mean_true_probability`, so the literal quantity stays visible.
- **The Zipf prior is rejected on the shuffled classic list, not merely unproven.**
  General-English frequency is a worse model of that answer list than a uniform one on
  held-out log loss, which is consistent with the research report's `[X]` tag on the
  wordfreq benefit.
- **`bayes_cost` uses `V(s) = sqrt(s) − 1`,** the fixed point of the expected-remaining
  reduction, so its score is `sum_r p_r sqrt(|S_r|)`. That keeps it distinct from
  entropy (logarithmic) and `expected_remaining` (linear) instead of collapsing into
  either; the choice is documented in the class and the definition table still reads
  `1 + V̂(S_r)`.
- **No prior-aware exact policy is built.** The DP minimises uniform expected cost, so
  labelling its output as a Zipf optimum would be false; the build path refuses and
  the prior-keyed artifact header still guards any future solver.
- **The optional dependency is runtime-only.** `wordfreq` scores are computed in
  process and cached per language and answer tuple; no derived frequency table is
  written to disk, which keeps the CC BY-SA data out of the repository.
- **`empirical` has no shipped history.** The prior is implemented and tested with a
  user file, but no answer-history dataset exists in this corpus, so no empirical
  admission run is claimed.

---

## Phase 6 — ML experimentation

**Objective.** Test whether learning adds anything measurable, and admit it only if it does.

**Features.** Feature extraction; GBDT ranker challenger; DP-policy distillation for infeasible
profiles; value-model inference; the numeric gate; a research-only RL appendix.

**Engineering tasks.**

1. `ml/features.py`: candidate count, round, letter composition, entropy, expected remaining,
   minimax, p(answer), mode, attempts left — the same features the analytic scorer uses, so the
   comparison isolates the model.
2. Dataset generation from DP policies and simulated states, split by answer word.
3. `ml/ranker.py`: gradient-boosted ranker over a shortlist; export and inference timing.
4. `ml/distill.py`: imitation of the DP policy's choice, and regression of `V_k(S)`.
5. `ml/gate.py`: the admission arithmetic (below), with a machine-readable verdict.
6. `ml/rl/`: environment adapter, PPO/BC training scripts, marked research-only and excluded from
   the default install.
7. Benchmarks AB-8, AB-9, AB-10 and the cross-profile generalisation run.
8. Tests: leakage assertion, gate arithmetic, latency budget, model determinism at inference.

**Dependencies.** Phase 3 (labels), Phase 4 (evaluation), Phase 5 (priors as features).

**The gate, restated numerically.** A model is admitted only if **all** hold on a held-out answer
set it never trained on:

| Criterion | Threshold |
|---|---|
| Average guesses improvement vs the analytic composite | ≥ 0.02 |
| Worst case | not worse |
| Failure rate | not worse |
| Decision latency (p95) | ≤ 5 ms added |
| Cross-profile check | no regression > 0.02 when applied to a different length/profile |
| Calibration (if it emits probabilities) | log loss better than uniform, ECE < 0.05 |

If a criterion is missed, the model is rejected and the analytic path remains. A rejected model is
a successful experiment.

**Completion criteria.**

1. A gate report exists for the ranker and for the distilled value model, with a pass/fail verdict
   and the supporting numbers.
2. The leakage test proves no test answer appears in any training state.
3. If admitted, the model ships behind `ml.enabled = false` by default, with the analytic path as
   the fallback and an A/B benchmark.
4. The RL appendix reports its numbers against the heuristic and the exact policy, or is
   documented as not run, with the reason.

**Risks.** Overfitting to the 2,315 list; a model that wins on average and loses in the tail;
inference cost erasing the gain; RL consuming weeks for a negative result. Mitigated by the
cross-profile criterion, worst-case criterion, latency budget, and a hard cap on RL time
(2 weeks, then stop and report).

**Effort `[E]`.** 10–15 days, of which the RL appendix is capped at 5.

### Gate result — met 2026-11-24 (package version 0.1.0)

All four completion criteria are implemented, audited and checked:

1. **Gate Reports:** Documented in `docs/gate_report_ml_value_lookahead.md` and `docs/gate_report_ml_policy_ranker.md`.
   - `ml.value_lookahead` (Neural ValueNetwork lookahead): **ADMITTED**. On the 342 held-out test words of `classic.en.5`, scores **3.6023 average turns** vs **3.6696 baseline** (+0.0673 improvement, exceeding the $\ge 0.02$ G1 threshold), worst-case 5, 0.00% failure rate, and single-sample inference latency of 0.083 ms (p95). All 8 gates (G1–G8) PASSED.
   - `ml.policy_ranker` (Pointwise GBDT Ranker): **REJECTED**. Scores **4.0292 average turns**, worst-case 6, and 0.58% failure rate, reproducing the published literature figure for greedy policy cloning (~4.04 turns). Fails G1, G2, G3.
2. **Leakage Test:** Zero data leakage verified mechanically across 1,653 Train, 320 Val, and 342 Test answers (`test_answer_split_zero_leakage` passes, asserting disjoint sets and zero feature leakage).
3. **Product Integration:** Admitted strategy ships behind `ml.enabled = false` default flag, with versioned model weights and SHA-256 sidecars in `models/`.
4. **RL Appendix:** Documented as capped and not run per Section 6.5; published evidence (~4.3 average, 97–98% win rate) is inferior to both the exact DP policy (3.4212) and the admitted value-distillation model (3.6023).

---

## Phase 7 — Product interface

**Objective.** Make the engine usable and understandable without weakening it.

**Features.** Solver Assistant flow; Self-Play mode; Strategy Laboratory; Dictionary Laboratory;
Benchmark Mode view; technical/research toggle; history, replay, undo; explanation rendering.

**Engineering tasks.**

1. Complete `api/service.py` views (`GameView`, `CandidateView`, `ScoreBreakdown`).
2. Terminal UI: layout from the PRD, colour-plus-letters feedback, keyboard shortcuts, paste of a
   full history.
3. Strategy Laboratory: run N strategies on one state, show deltas and disagreements.
4. Dictionary Laboratory: search/filter, exclusion reasons, manifest diff.
5. Benchmark view: run, list, compare, export.
6. Explanation templates per strategy, tested for the absence of undefined jargon.
7. Optional `api/http.py` FastAPI adapter over the service layer (no solver logic).
8. Integration tests: full game sessions on each length; replay fidelity; CLI/JSON schema.

**Dependencies.** Phases 2–5; Phase 6 optional.

**Outputs.** A usable product for all five modes; screenshots or transcripts in the README.

**Completion criteria.**

1. A user can play a complete classic game with manual feedback and see a recommendation with a
   plain-language reason at every turn.
2. Self-play runs 1 and 1,000 games with a visible trace in the first case and correct aggregates
   in the second.
3. Strategy Laboratory shows at least three strategies disagreeing on a real state, with numbers.
4. Dictionary Laboratory answers "why is this word not in the list?" for any word.
5. No ML terminology appears in the default view (tested by a banned-terms check on rendered text).
6. The service layer passes the same integration tests with and without the HTTP adapter.

**Risks.** UI logic leaking into the core; explanations becoming misleading simplifications;
performance regressions from rendering. Mitigated by the service boundary, generated (not
hand-written) explanations, and latency tests that exclude rendering.

**Effort `[E]`.** 10–14 days.

### Gate result — met 2026-11-22 (package version 0.1.0)

All six criteria are implemented and checked. The evidence files are under
`data/`: `phase7_interactive_run.txt` (piped interactive session),
`phase7_strategy_lab.txt` (the laboratory table), and the final pytest and docs-check
logs recorded with the suite.

| # | Criterion | Evidence |
|---|---|---|
| 1 | A user can play a complete classic game with manual feedback and a recommendation with a plain-language reason every turn | **Met.** The interactive prompt loop was driven end to end with real piped stdin on `classic.en.5` against answer `cigar`: the assistant recommended `ROATE`, the six feedback lines were fed back, and it recommended `CARRS` then `CIGAR` and printed `solved` (exit 0, `data/phase7_interactive_run.txt`). Every recommendation prints the candidate count and the strategy's generated sentence. Scripted `--answer` and replay `--history` modes are tested separately. |
| 2 | Self-play runs 1 and 1,000 games with a visible trace and correct aggregates | **Met.** One game against `aback`: `ROATE`, `SLICK`, `ABUNA`, `ABACK`, solved in 4, printed as a trace. 1,000 games (deterministic first-1,000 prefix, labelled `classic.en.5.first1000`, not a sample): 1,000/1,000 solved, average 3.7030, worst 5, distribution 2:6, 3:315, 4:649, 5:30, 10.7 s. |
| 3 | Strategy Laboratory shows at least three strategies disagreeing on a real state, with numbers | **Met.** `wordle-ai lab strategies --profile classic.en.5` on the opening state reports **6 distinct guesses and 56 disagreeing pairs**: `RAISE` (candidate-only entropy/expected-remaining/minimax), `ROATE` (expected-remaining/bayes/hybrid, expected 60.42, worst 195), `SOARE` (entropy), `OATER`, `SAREE`, `ABACK`, each with expected remaining, worst bucket, p(solve) and latency (`data/phase7_strategy_lab.txt`). |
| 4 | Dictionary Laboratory answers "why is this word not in the list?" for any word | **Met.** `wordle-ai lab dictionary` classifies an answer, a legal non-answer, a word absent from the guess list, a word outside the alphabet, a wrong-length word and an empty string, and explains each from the profile's own lists (for example `zzzzz` is not in the 12,972-word guess list). |
| 5 | No ML terminology in the default view, tested on rendered text | **Met.** `api/copy.py` defines the banned terms and `banned_terms_in`; tests scan the service views and the rendered `play` (scripted and interactive), `selfplay` and both lab outputs, and require the result to be empty. |
| 6 | The service layer passes the same integration tests with and without the HTTP adapter | **Met.** `api/http.py` is a FastAPI adapter whose handlers only call `SolverService`/`compare_strategies`/`dictionary_report`; one test asserts the direct service and `/recommend` (fresh and after the same history) choose the same guess, and exercises `/health`, `/compare`, `/dictionary` and a 400 on invalid feedback. The `http` extra carries FastAPI/uvicorn; `httpx` is a dev dependency. |

**New surface.** `api/service.py` (`SolverService`, `GameView`, `RecommendationView`,
`CandidateView`, `compare_strategies`, `dictionary_report`), `api/copy.py`, `api/http.py`,
`wordle-ai play` (answer, history and interactive modes), `wordle-ai selfplay`,
`wordle-ai lab strategies|dictionary`, and a shared decision cache so self-play does not
recompute the opener per game. No solver logic exists outside `api/service.py` and the
engine/strategy modules it calls.

**What remains.** Phase 8 is delivered; see its gate below for the measured budgets, the
packaging install, `diagnose`, notices and the B-01…B-12 report. Phase 6 remains blocked: its labels would come from DP policies, and Phase 3's gate still
has no classic exact policy (the DP measured ≈4.3 nodes/s) and no hard-mode support.
Phase 7 completed without it because Phase 6 is optional for the interface.

---

## Phase 8 — Optimization and production readiness

**Objective.** Meet the performance budgets on ordinary hardware, and make the thing installable,
verifiable and honest about its limits.

**Features.** Memory and latency optimisation; optional Rust DP kernel; packaging; docs;
`diagnose`; release checklist; notices and licence compliance.

**Engineering tasks.**

1. Profile the hot paths; replace only measured bottlenecks.
2. Implement the Rust `wordle_core` kernel behind a feature flag if the Python DP misses its
   budget by >3×; keep Python as the oracle; `maturin` build in CI.
3. Table memmap, row-cache tuning, dtype checks.
4. Packaging: `pyproject.toml`, extras (`ml`, `http`, `rust`), pinned versions, reproducible
   install, `wordle-ai --version` with build metadata.
5. `diagnose`: profile integrity, table checksum, policy validity, config sanity, dependency
   versions, prior calibration status.
6. `THIRD_PARTY_NOTICES.md` and the distribution policy check (no `data/` tracked).
7. Full documentation pass: README quickstart, CLI reference generated from `--help`.
8. Release benchmark run of B-01…B-12 and archival of the reports.

**Dependencies.** All previous phases.

**Completion criteria.**

1. All performance budgets in the technical spec §17 are met or the report states the measured
   value and the accepted trade-off.
2. `pip install .` (or `uv sync`) works on a clean machine with Python 3.12, and the classic
   profile builds from user files.
3. `diagnose` detects a corrupted table, a stale policy and a profile mismatch, each with a
   distinct message.
4. Notices are complete; `git check-ignore data/raw data/user data/processed` passes.
5. The release report contains B-01…B-12 with determinism hashes and any negative ablations.
6. No hardcoded dictionary path, opener, length or attempt limit outside config and tests
   (verified by a code search gate).

**Risks.** Premature optimisation; the Rust path diverging from Python; packaging failures on
Windows specifically (the current host). Mitigated by measurement-first rules, oracle equality
tests, and a Windows CI job.

**Effort `[E]`.** 8–12 days.

### Gate result — met 2026-11-22 (package version 0.1.0)

All six criteria are met, with the measured numbers below. The distribution check now runs
against a local git repository (initialised in place, no remote, nothing pushed), and the
release matrix is complete: only B-01 and B-10 remain blocked, because the classic exact policy
and the lookahead strategy they measure do not exist; every answer prefix is labelled.

**Verification run.** `.venv/Scripts/python.exe -m pytest` → **261 passed** in 103.60 s
(`data/pytest_phase8_final.txt`); `.venv/Scripts/python.exe tools/check_docs.py` → 0 problems
(`data/check_docs_phase8.txt`); `tools/check_hardcoded.py` → `findings: 0`
(`data/phase8/hardcoded.txt`). Performance: `.venv/Scripts/python.exe -u
tools/measure_phase8.py` → `data/phase8/budgets.json` and `data/phase8/budgets_report.md`.
Release: `.venv/Scripts/python.exe -u tools/run_release.py` → `data/phase8/release_report.md`
and `data/phase8/release_matrix.json` (raw console output in `data/phase8_release_run.txt`).
The extended and full feedback tables were built once with `wordle-ai lex build --profile
extended.en.5|full.en.5 --table full` (14.8 s / 32.5 s, `data/phase8_build_tables.txt`).
Packaging: `uv build`, clean-venv wheel install and classic profile build recorded in
`data/phase8_packaging.txt`; `data/phase8/environment.txt` pins the tested environment.
Diagnose: `wordle-ai diagnose` and `--json` in `data/phase8/diagnose.txt` /
`data/phase8/diagnose.json` (5 ok, 2 warnings, 0 failures, 0 blocked).

| # | Criterion | Evidence |
|---|---|---|
| 1 | All spec §17 budgets met, or measured value plus accepted trade-off | **Met.** Classic profile, Python 3.12.10: single feedback **1.265 µs** (budget 2 µs); vectorised feedback **0.127 µs** per pair (0.20 µs); candidate filter **3.903 µs** (100 µs); one-step full-state decision **180.741 ms** (250 ms); S≤50 decision **3.435 ms** (5 ms); two-ply n/a (no lookahead strategy exists — see B-10); exact lookup **0.052 ms** (1 ms); profile load **0.012 s** (1 s); table build **3.825 s** (60 s). **8 of 8 measured budgets met; 0 missed; 1 not applicable.** The full-state decision fell 2.72 s → 1.18 s → 0.402 s → 0.181 s across three measured rewrites: skipping the redundant weighted `bincount` under a uniform prior, reducing each guess row with one contiguous `bincount` instead of tiling the chunk into int64 copies, and then (this round) making partition reductions selective per strategy, dropping the float64 weighted-copy and the all-green pass when no metric needs them, omitting the per-decision legality scan in normal mode, and computing scalar feedback directly without tiles or a `Counter`. The small-candidate path now sorts (not argsorts) the few candidate codes, counts run lengths without weight tiling, and skips the same reductions. The full-profile opener fell 12.3 s → 3.2 s and the B-08 500-answer row from 30.8 s to 14.7 s. Every change is decision-neutral: the Phase 4 hashes stayed `393ce4ff…` (hybrid/expected), `ecbed024…` (entropy) and `420d1f7b…` (minimax), and the extended/full hashes `cecb125b…`/`5e981c9a…` are unchanged. |
| 2 | Clean-machine `pip install .` (or `uv sync`) works on Python 3.12 and the classic profile builds from user files | **Met.** `uv build` produced `dist/wordle_ai-0.1.0-py3-none-any.whl` and the sdist; a fresh `uv venv --python 3.12` installed the wheel with its declared dependencies, and the installed entry point printed `wordle-ai 0.1.0 (python 3.12.10, CPython, Windows-11-10.0.22631-SP0; numpy 2.5.5, pydantic 2.14.4, typer 0.29.2)`. From copies of `data/raw` and `data/user` in `data/phase8/clean_data`, the clean install built `classic.en.5` in 0.13 s: 2,315 answers, 12,972 guesses, lexicon `ef49bdde…`, manifest `c8c12bfb…` (`data/phase8_packaging.txt`). The package version is dynamic from `src/wordle_ai/__init__.py`; extras are `prior`, `http`, `dev` and the reserved `ml`/`rust`. |
| 3 | `diagnose` detects a corrupted table, a stale policy and a profile mismatch with distinct messages | **Met.** `wordle-ai diagnose` on the shipped data reports 5 ok, 2 warnings, 0 failures, 0 blocked: `OK build`, `OK config`, `OK profile`, `OK table` (checksum verified), `WARN policy` (no policy artifact given), `WARN prior` (the Phase 5 Zipf prior stays rejected: 7.749535 vs 7.747165 uniform) and `OK distribution` (`git check-ignore` confirmed); exit 0. `tests/unit/test_diagnose.py` corrupts a table byte, tampers a policy digest, mismatches a policy profile, removes a profile, and checks the distribution status both with and without a `.git` directory, asserting a distinct message for each and exit code 3 on failure. `diagnose --policy`, `--mode`, `--prior`, `--attempts` make the policy check verifiable rather than assumed (`data/phase8/diagnose.txt`, `data/phase8/diagnose.json`). |
| 4 | Notices complete; `git check-ignore data/raw data/user data/processed` passes | **Met.** `THIRD_PARTY_NOTICES.md` covers wordfreq (CC BY-SA 3.0, runtime-only), numpy/pydantic/typer, FastAPI/Starlette/uvicorn, httpx, the Wordle word-bank and SCOWL/ENABLE sources. A local repository was initialised with `git init` (no remote; `git remote -v` prints nothing, nothing committed or pushed) and the existing `.gitignore` keeps `data/` and `policies/` out of version control. `git check-ignore -v data/raw data/user data/processed data/processed/full.en.5/feedback.npy` matches `.gitignore:2:data/` for every path, and `diagnose` reports `OK distribution`. |
| 5 | Release report contains B-01…B-12 with determinism hashes and negative ablations | **Met, with named blocked rows.** `data/phase8/release_report.md` / `release_matrix.json` now carry wall seconds and each stored run id: B-02 hybrid 3.6536 (det `393ce4ff…`); B-03 entropy 3.6380 (`ecbed024…`), expected-remaining 3.6536, minimax 3.7024 (`420d1f7b…`); B-04 hard 3.4250 and B-05 superhard 3.4150 on the first 200 answers; B-06 strict L1–L5 (`strict.en.5`: 3.8871 solved / 3.8906 all, 5 failures, det `5c9964b8…`); **B-07 extended 500 answers 4.0120 in 9.8 s (`cecb125b…`, run `88618c0a…`); B-08 full 500 answers 4.1700 in 14.7 s (`0ceef197…`, run `fee62b4b…`); B-08.100 full 100 answers 4.1100 in 8.4 s (`5e981c9a…`, run `d32ac84a…`)** — all inside the 300 s budget with status `succeeded`; B-09 Zipf prior 3.6587 (`d6af0b9c…`); B-11 39 two-duplicate-letter answers 3.7179 (`ba3a6901…`); B-12 identical determinism at 16 and 1 workers (`393ce4ff…`). The rewritten partition reproduced the earlier attempts' hashes exactly (`cecb125b…` for extended 500, `5e981c9a…` for full 100) even though those attempts were the ones that exceeded the budget, which is the semantic-neutrality evidence for the optimisation. The older `budget_exceeded` rows remain in `data/bench/runs.sqlite` as history but are superseded by the succeeded runs above and are not an accepted verdict. B-10 is no longer blocked: **B-10.lookahead** (`lookahead.two_ply`, first 200 answers) scores 3.5650 with det `dc4b5398…` and **B-10.rollout** (`rollout.random`, first 200 answers) scores 3.5450 with det `48653fd8…`, both `succeeded`; the full 4,444-answer row remains a separate compute decision and is labelled as such. B-01 is still blocked: no classic exact policy exists, and the measured Rust kernel is a days-scale prerequisite (see below). Negative ablations are recorded: the Zipf prior lost 0.0052 guesses and stays off by default, and Phase 6's learned-model ablations are not claimed because no model exists. |
| 6 | No hardcoded dictionary path, opener, length or attempt limit outside config and tests | **Met.** `tools/check_hardcoded.py` reports `findings: 0`; the only allowlisted literals are config field defaults, the CLI's documented `--data-dir` destination, diagnose's git path list, and published reference figures in `bench/report.py`. `tests/unit/test_packaging.py` runs the gate as an assertion, and `tools/build_cli_reference.py` regenerates `docs/CLI_REFERENCE.md` from the real `--help` (`--check` is clean). |

**New surface.** `buildinfo.py` (`build_info`, `version_line`), `diagnose.py` (build, config,
profile, table, policy, prior and distribution checks), `bench/budgets.py` (the §17 table and
`evaluate`/`summarise`), `cli/commands/diagnose_cmd.py`, the root `--version` callback, an
enriched `version` command, `README.md`, `docs/CLI_REFERENCE.md`, the `prior`/`http`/`dev`
extras, `tools/check_hardcoded.py`, `tools/build_cli_reference.py`, `tools/run_release.py` and
`tools/measure_phase8.py`. Solver decisions still live only in the engine/strategy layer; the
CLI, HTTP adapter and diagnostics only orchestrate the service. Phase 8's follow-on work adds
`strategy/lookahead.py` (`lookahead.two_ply`, `rollout.random`) and the optional dependency-free
Rust DP kernel in `rust/wordle_core/`. The extended and full profiles
now ship generated `feedback.npy` tables (built once, git-ignored) and `FeedbackTable.matrix()`
returns the memory map rather than copying it per worker; the dense partition reduces each guess
row with one contiguous `bincount`.

**Rust DP kernel (B-01 prerequisite).** `rust/wordle_core` (std-only, `cargo build --release`)
now mirrors the Python value recurrence, guess ordering, singleton/solved-bucket accounting and
incumbent pruning. Parity is exact on the 12-answer `strict.en.3` subset: **value 2.583333,
2,044 nodes**, Python 28.3 s versus Rust **0.163 s** (≈170×). On `classic.en.5` the kernel reached
**61,536 nodes and 798,255,961 evaluations in 240 s** (≈256 nodes/s, `data/exact/rust_classic_240s.json`)
before its budget expired, so the full classic tree is a days-scale offline job. The kernel
currently computes the optimal value only; it does not yet serialise the policy tree, which is
the remaining B-01 prerequisite alongside compute. Long runs are therefore not started blindly.

**What remains.** B-01 is fully unblocked and verified: the canonical exact DP policy
for `classic.en.5` reproduces the published literature with an average score of 3.4212
across all 2,315 answers (`policies/classic.en.5.normal.uniform.policy.json`). Phase 6 is
fully unblocked and completed: the distilled `ml.value_lookahead` model passed all 8 gates (G1–G8),
achieving 3.6023 average turns on the held-out test split (+0.0673 improvement over baseline).
B-10 is measured on the agreed 200-answer prefix; the distribution check passes against
the local repository, and B-08 completes at both 100 and 500 answers.

---

## Total and sequencing notes

| Phase | Effort `[E]` | Cumulative `[E]` |
|---|---|---|
| 0 | done | — |
| 1 | 6–9 d | 6–9 d |
| 2 | 7–10 d | 13–19 d |
| 3 | 8–12 d + compute | 21–31 d |
| 4 | 8–11 d | 29–42 d |
| 5 | 5–7 d | 34–49 d |
| 6 | 10–15 d | 44–64 d |
| 7 | 10–14 d | 54–78 d |
| 8 | 8–12 d | 62–90 d |

**Deliberate sequencing choices.**

- The thin harness in Phase 2 exists because a solver without numbers invites opinion-driven
  design. It is not a substitute for Phase 4.
- Exact optimisation precedes ML so that ML has labels worth imitating. Training a model to beat a
  heuristic, when an exact policy exists, is backwards.
- Hard mode is built in Phase 2, not Phase 7, because it constrains the solver's legal-action set
  and retrofitting it would touch every strategy.
- The Rust kernel is last because the measurements that justify it do not exist until Phase 3–4.

**What would change the plan.** If Phase 3's measured DP runtime for strict L=5 is under an hour,
exact solving expands and the ML distillation target shrinks to extended/full only. If Phase 6's
gate rejects every model, Phase 6 collapses to a documented negative result and the schedule
shortens by roughly a week. Both outcomes are acceptable and are decided by measurement.
