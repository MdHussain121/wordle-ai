# WORDLE_AI_ARCHITECTURE.md

**Status:** Phase 0 deliverable, revision 1.0 · **Date:** 2026-11-19
**Companions:** `WORDLE_AI_TECHNICAL_SPECIFICATION.md` (contracts), `WORDLE_AI_RESEARCH_REPORT.md`
(rationale), `WORDLE_AI_IMPLEMENTATION_ROADMAP.md` (order)

---

## 1. Architectural position in one paragraph

A single-process, CPU-only Python application with a strict layering: immutable lexicon and
feedback data at the bottom, a state machine and strategy engine above it, then use-case services,
then a terminal UI and an optional HTTP adapter. Exact policies and feedback tables are *artifacts*
— generated offline, checksummed, verified on load — not runtime computations where avoidable. The
UI never contains puzzle logic; the engine never imports a UI. Everything that varies (dictionary,
length, rules, prior, budgets) enters through validated configuration or a profile manifest.

---

## 2. System context

```
                    ┌──────────────────────────────────────────────┐
                    │                 User (person)                │
                    │  casual player · researcher · tinkerer       │
                    └───────────────┬──────────────────────────────┘
                                    │ terminal / optional HTTP
┌───────────────────────────────────▼───────────────────────────────┐
│                        wordle-ai application                       │
│   CLI (Typer)  ·  optional FastAPI adapter  ·  no network at solve │
└───────┬───────────────────────────────┬───────────────────────────┘
        │ reads                          │ reads (offline)
┌───────▼─────────────┐        ┌─────────▼──────────────────────────┐
│ profile manifests   │        │ policy + feedback artifacts         │
│ + lexicon npz       │        │ (checksummed, versioned by profile) │
└───────▲─────────────┘        └─────────▲──────────────────────────┘
        │ produced by                     │ produced by
┌───────┴─────────────┐        ┌─────────┴──────────────────────────┐
│ lexicon pipeline    │        │ exact solver / distillation         │
│ (offline, network)  │        │ (offline, CPU-heavy, parallel)      │
└───────▲─────────────┘        └─────────▲──────────────────────────┘
        │                                 │
┌───────┴─────────────┐        ┌─────────┴──────────────────────────┐
│ SCOWL · ENABLE ·    │        │ simulated games / DP labels         │
│ user-supplied lists │        │                                     │
└─────────────────────┘        └────────────────────────────────────┘
```

Network access exists only in `lex fetch`. Solving, benchmarking and policy lookup are offline.

---

## 3. Layered component view

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Presentation        cli/ (Typer)          api/http.py (optional, Phase 7) │
├──────────────────────────────────────────────────────────────────────────┤
│ Use cases           api/service.py   → new_game, apply_feedback, suggest,  │
│                                        candidates, replay, explain        │
├──────────────────────────────────────────────────────────────────────────┤
│ Orchestration       strategy/hybrid.py   bench/runner.py   sim/runner.py   │
├──────────────────────────────────────────────────────────────────────────┤
│ Domain              strategy/*  ·  solver/dp.py  ·  solver/policy.py  ·    │
│                     engine/state.py  ·  engine/prior.py  ·  engine/filter  │
├──────────────────────────────────────────────────────────────────────────┤
│ Foundation          engine/feedback.py  ·  engine/table.py  ·              │
│                     lexicon/profile.py  ·  lexicon/build.py  ·  types.py   │
├──────────────────────────────────────────────────────────────────────────┤
│ Infrastructure      store/sqlite.py  ·  store/cache.py  ·  config.py       │
└──────────────────────────────────────────────────────────────────────────┘
```

**Dependency law.** Arrows point downward only. A violation is a build failure (import-linter
rule, Phase 1). `engine` does not import `numpy` types into public signatures; arrays are internal
implementation detail, so the domain can be tested without numpy in principle.

---

## 4. Component responsibilities

| Component | Owns | Must not |
|---|---|---|
| `lexicon` | sourcing, normalisation, validity policy, manifests, profile identity | decide strategy, hold game state |
| `engine.feedback` | the single definition of feedback, codec, parsing | know about guesses' desirability |
| `engine.table` | precomputation, memory policy, checksums | mutate the lexicon |
| `engine.state` | history replay, candidates, invariants | choose guesses |
| `engine.filter` | candidate elimination | infer letter rules independently |
| `engine.prior` | answer distributions, calibration input | decide validity |
| `strategy.*` | scoring and choice for one objective | mutate state; persist |
| `solver.dp` | exact values and policy trees | render, or read user input |
| `sim` | environment, episodes | compute metrics |
| `bench` | metrics, statistics, reports | change strategies at runtime |
| `store` | persistence, schema | contain domain logic |
| `cli`/`api` | input parsing, presentation, orchestration | contain puzzle logic |

---

## 5. Data-flow diagrams

### 5.1 Lexicon build (offline)

```
sources.lock ──► fetch ──► verify sha256 ──► decode (utf-8 → latin-1, recorded)
      │                                              │
      └────────────── manifest provenance ◄──────────┘
                              │
              normalize (NFC, casefold, grapheme length)
                              │
              validity policy (alphabet, possessives, proper nouns, …)
                              │
                 dedupe → sort → answers ⊆ guesses
                              │
            ┌─────────────────┴──────────────────┐
      lexicon.npz + manifest.json          feedback table (.npy + sha256)
            │                                    │
            └──────────► profile (immutable) ◄───┘
```

### 5.2 Solve turn (interactive)

```
user guess + colours
        │
        ▼
 Pattern.parse ──► state.apply(guess, pattern)
                        │
                        ├─ filter candidates (table row compare)
                        ├─ assert non-empty (else InconsistentFeedback)
                        └─ rebuild posterior from prior
                                 │
                                 ▼
                     hybrid.select_branch(state, config)
                                 │
             ┌───────────────────┼────────────────────┐
             ▼                   ▼                    ▼
      policy lookup        two-ply shortlist      one-step scoring
      (exact)              (|S| ≤ threshold)      (expected_remaining /
             │                   │                 entropy / minimax)
             └───────────────────┴────────────────────┘
                                 │
                                 ▼
                    Decision(guess, breakdown, explanation)
                                 │
                     persist decision row + render
```

### 5.3 Benchmark run

```
run spec ──► expand matrix (profile × rules × prior × strategy × answer set)
                 │
                 ├─► shard answers across workers
                 │        │
                 │        └─► per game: reset → loop(suggest → step) → GameResult
                 │
                 ├─► deterministic reduction (sum, count, histogram, max)
                 ├─► metrics + bootstrap CIs + determinism hash
                 └─► SQLite run/game/decision rows → Markdown + CSV
```

### 5.4 Policy generation and ML distillation

```
profile + rules + prior ──► feasibility gate ──► DP (memo, pruning, root parallel)
                                                     │
                              ┌──────────────────────┴───────────────────┐
                              ▼                                          ▼
                    policy tree artifact                    (state, optimal value/choice) rows
                    (verify, checksum)                                  │
                              │                                         ▼
                              │                              train ranker / value model
                              │                              (split by answer word)
                              │                                         │
                              └──────────────► solve time ◄───── gate: Δavg, worst case,
                                                                 latency, cross-profile
```

---

## 6. Runtime sequence: one recommendation

```
CLI            Service           State            Hybrid          Strategy        Table/Policy
 │  suggest ────►│                 │                │                │                │
 │              │  load state ────►│                │                │                │
 │              │                 │  branch? ─────►│                │                │
 │              │                 │                │  score(S) ────►│  rows ────────►│
 │              │                 │                │                │◄── uint8 ──────│
 │              │                 │                │◄── breakdown ──│                │
 │              │                 │◄── choose ─────│                │                │
 │              │◄── Decision ────│                │                │                │
 │◄── render ───│                 │                │                │                │
```

Latency budget: 250 ms at the largest candidate set, dominated by table row gathers and the
scoring reduction. Rendering is excluded from the budget and measured separately.

---

## 7. Deployment and runtime topology

- **Single machine, single process** for solving; a process pool only for benchmarks and DP.
- **No server, no container requirement, no database service.** SQLite file + `.npy`/`.npz`
  artifacts.
- **Storage layout:** `data/processed/<profile>/` for lexicons and tables, `policies/` for policy
  trees, `store/wordle.sqlite` for runs.
- **Optional extras:** `ml` (scikit-learn/onnx), `http` (FastAPI/uvicorn), `rust` (maturin-built
  kernel). Base install is numpy + typer + pydantic only.
- **Windows is a first-class target** (the current host), so path handling uses `pathlib`, no
  POSIX-only assumptions, and CI runs on Windows as well as Linux.

---

## 8. Quality attributes and how they are achieved

| Attribute | Mechanism | Evidence |
|---|---|---|
| **Correctness** | single feedback definition; recomputation-based filtering; invariants asserted | exhaustive equality tests; `answer_eliminated_count = 0` |
| **Determinism** | sorted iteration, index tie-breaks, seeded RNG, order-independent reductions | determinism hash across worker counts |
| **Explainability** | `Decision.breakdown` is data, explanations are generated from it | decision table audit; no hand-written per-word text |
| **Performance** | `uint8` tables, numpy gathers, policy lookup, escalation thresholds | latency metrics vs budgets |
| **Memory discipline** | memory-aware table policy, memmap, LRU, `uint8`/bitset representation | peak RSS metric |
| **Modifiability** | strategy protocol, profile manifests, config keys, constraint predicate | adding a strategy touches one file + registry |
| **Testability** | domain has no I/O; oracle reference path retained | unit tests run without files |
| **Portability** | pure Python base, optional native kernel, `pathlib`, no POSIX-only calls | Windows + Linux CI |
| **Honesty** | exactness declared per strategy; failures reported; profile named everywhere | release gates RG-5 |

---

## 9. Architecture decision records

### ADR-001 — Python core with an optional Rust kernel, not Rust-first

**Context.** The DP inner loop is the one genuinely compute-bound part (published: days on 64
cores `[P]`). Everything else is table gathers that numpy handles at native speed.
**Decision.** Python 3.12 + numpy is the implementation; a single Rust `wordle_core` kernel is
added only if measured DP runtime misses budget by >3×, behind the `rust` extra, with the Python
implementation retained as the test oracle.
**Consequences.** Faster iteration, easier ML integration, one toolchain for most users. Accepted
risk: DP policy generation may be slower than a C++/Rust-first design; mitigated by offline
generation and caching. Rejected alternatives: full Rust (ML and CLI ecosystem cost), C++ (build
friction on Windows), Node (weaker numeric ecosystem for this workload).

### ADR-002 — Exact DP where tractable, approximate elsewhere, with an enforced gate

**Context.** Optimal play is computable for 2,315/12,972 `[P]` but the problem is NP-hard and the
full open L=5 profile is 17,410 words with a 289.07 MiB table `[R]`.
**Decision.** Ship a verified policy artifact for tractable profiles; elsewhere use the hybrid
approximate stack. Enforce `|A| ≤ 5,000`, `|G| ≤ 20,000` and a time budget in code.
**Consequences.** The flagship number is exact and explainable; other profiles are honestly
approximate. Users cannot accidentally start a multi-day job without `--force`.

### ADR-003 — Expected remaining candidates is the default objective; entropy is a tie-break

**Context.** Max-entropy is widely described as "the" Wordle strategy, but measured
solution-word-only results put bin-count (3.4600) ahead of entropy (3.4955) `[P]`, and greedy on
total guesses is provably suboptimal (7,944 vs 7,920) `[P]`.
**Decision.** Primary score is expected remaining candidates (equivalently the normalised `L²`
norm of bucket sizes); entropy breaks ties; minimax is selectable and used as a worst-case guard.
**Consequences.** Slightly better average than pure entropy in the measured regime; one more concept
to explain. The UI explains it as "expected words left", which is intuitive.

### ADR-004 — Uniform prior by default, frequency prior only through a calibration gate

**Context.** The original answer order is a shuffled fixed list, so uniform is correct for a player
who does not know the date `[P]`; WordleBot uses appearance frequencies `[P]`, and priors change
the optimal guess.
**Decision.** `uniform` is the default; `zipf` is optional, fit with a temperature on validation
data, admitted only if log loss beats uniform and ECE < 0.05; prior id is part of every cache and
artifact key.
**Consequences.** Reproducible default; priors cannot silently degrade play; wordfreq stays a
runtime dependency, respecting its data licence.

### ADR-005 — Profiles with content-addressed manifests, not a single dictionary

**Context.** Word lists differ by licence, dialect and version; the open union covers 93.73% of the
classic allowed guesses and misses two answers `[R]`.
**Decision.** A profile is `(id, language, dialect, length, answers, guesses, manifest_sha256)`.
Nothing is loaded without a matching manifest; caches and benchmarks key on the checksum.
**Consequences.** Slightly more ceremony at build time; in exchange, no result is ambiguous about
which game it describes. This is the single most important architectural choice for honesty.

### ADR-006 — One `uint8` per (guess, answer) with a memory-aware policy

**Context.** `3^L ≤ 243` at L=5, so a byte suffices `[E]`. Measured tables: 28.64 / 124.18 /
289.07 MiB for classic / extended / full L=5 `[R]`.
**Decision.** Precompute when within `table_max_bytes` (default 256 MiB), else hybrid rows with LRU,
else on demand. Tables are `.npy` + sidecar checksum, memmapped.
**Consequences.** Fast decisions on normal machines; full-lexicon profiles work without a
supercomputer; the memory policy is a visible config decision rather than an OOM surprise.

### ADR-007 — CLI-first, one entry point, `--json` everywhere

**Context.** Standing project rule: every repeatable operation is reachable from the CLI, with
discoverable options and a documented inventory.
**Decision.** Typer app with subcommands for lex, table, policy, play, suggest, selfplay, bench, ml
and diagnose; every command supports `--json` and stable exit codes.
**Consequences.** No orphan scripts; benchmarks are reproducible from a shell; a future UI is a
client of the same service layer.

### ADR-008 — Three rule modes, not a boolean flag

**Context.** Published hard-mode and superhard-mode optima differ (`salet` 3.5084 vs `scamp`
3.7162) `[P]`, and hard-mode heuristics can exceed six guesses `[P]`.
**Decision.** `NORMAL`, `HARD` (NYT letter-reuse), `SUPERHARD` (guess must be a candidate), each a
constraint predicate derived from history through the feedback function.
**Consequences.** More configuration, correct semantics, and testable guarantees. A boolean would
have conflated two games with different optima.

### ADR-009 — No RL in the product path; distillation only

**Context.** Published RL reaches ~97–98% at 4.3 average under a weaker win condition, while
behaviour cloning of a simple heuristic reaches 99.8% at 4.04 and the exact optimum is 3.4212
`[P]`.
**Decision.** RL is a research appendix with a two-week cap. The ML investment is imitation of the
exact policy and a value model for infeasible profiles, behind a numeric gate.
**Consequences.** Effort goes where a measurable win is plausible; RL can still be evaluated, but
cannot delay the product.

### ADR-010 — SQLite plus array files, no database server

**Context.** The data is a few million rows of run/game/decision records and a handful of large
arrays.
**Decision.** SQLite for relational records (WAL mode), `.npy`/`.npz` for arrays, JSON for
manifests and policies.
**Consequences.** Zero-install persistence, trivially inspectable, backup is a file copy. Rejected
alternatives: Postgres (operational cost for no benefit), BLOBs for tables (slower than memmap),
DuckDB (nice for analytics, unnecessary dependency at this scale).

### ADR-011 — Constraint derivation must go through `feedback()`

**Context.** Hand-maintained letter rules are the standard source of duplicate-letter bugs.
**Decision.** Hard-mode legality is computed by deriving `(min_count, max_count, fixed_positions,
excluded_positions)` per letter *from the history using the same feedback function*, then testing
guesses against it. No component keeps an independent "letter is absent" model.
**Consequences.** One algorithm to test; constraints can be underdetermined and are represented as
ranges; correctness follows from the feedback definition rather than from a second implementation.

### ADR-012 — A numeric gate admits ML, not a judgement call

**Context.** ML is easy to add and hard to justify; the brief explicitly forbids deep learning for
its own sake.
**Decision.** Admission requires ≥ 0.02 average-guess improvement, no worst-case or failure
regression, ≤ 5 ms added latency, no cross-profile regression > 0.02, and calibration if the model
emits probabilities.
**Consequences.** Most models will be rejected, which is the intended outcome; the analytic path
remains the default and the product never depends on a model artifact.

---

## 10. Concurrency and memory model

- **Solving:** single-threaded. Determinism is worth more than throughput at human interaction
  rates.
- **Benchmarking:** process pool, shard by answer index, reduce with order-independent
  accumulators. Worker count must not change results (tested).
- **DP:** process pool at the root only; each worker owns a subtree and a private memo shard;
  reduction is `min` over `(cost, guess_index)`.
- **Shared state:** none. Tables are read-only memmaps; SQLite uses WAL with one writer at a time.
- **Memory:** tables memmapped; row caches bounded; memo tables capped with LRU eviction and
  checkpointing to disk for long runs.

---

## 11. Extensibility map

| Extension | Touch points | Untouched |
|---|---|---|
| New language | profile + normalisation rules + alphabet | engine, strategies, solver |
| Length 6+ | codec widening to `uint16`, table dtype, profile validation | strategy logic |
| New rule mode | one constraint predicate + registry entry | scoring, DP recursion |
| New strategy | one module implementing the protocol + registry | state, filters, UI shell |
| New UI | consume `SolverService` views | everything below the service |
| External game adapter | implement `GamePort` | solver core |
| New lexicon source | source descriptor + lock + build stage | profiles, solver |

---

## 12. What this architecture deliberately does not have

No microservices, no message queue, no container orchestration, no cloud storage, no GPU path, no
authentication, no telemetry, no plugin runtime, no dynamic code loading. Each was considered and
rejected as complexity that does not buy a measured improvement for a single-user, CPU-bound,
offline puzzle solver.
