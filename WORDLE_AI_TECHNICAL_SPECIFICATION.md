# WORDLE_AI_TECHNICAL_SPECIFICATION.md

**Status:** Phase 0 deliverable, revision 1.0 · **Date:** 2026-11-19
**Depends on:** `WORDLE_AI_RESEARCH_REPORT.md` (numbers ledger), `WORDLE_AI_ARCHITECTURE.md`
**Implements:** the decisions in `WORDLE_AI_PRD.md`

---

## 1. Design principles

1. **Data over constants.** Word length, alphabet, guess set, answer set, attempt limit, mode,
   prior, budgets and strategy weights are configuration. The only hardcoded numbers are
   mathematical (3 feedback states per position) and structural (SQLite schema version).
2. **One definition of feedback.** Every component calls the same `feedback()` function or reads
   a table produced by it. No component re-implements letter logic.
3. **Exactness is a claim, not a default.** A strategy declares whether it is exact, approximate,
   or a bound. The UI and the benchmark display that declaration.
4. **Correct before fast.** A vectorised path and a reference path must agree on every
   (guess, answer) pair in a profile; the reference path is the test oracle.
5. **Deterministic by construction.** Same inputs, same outputs, byte-identical, independent of
   iteration order of dictionaries or process count.
6. **Profile-scoped identity.** A result is only meaningful as
   `(profile_id, rules, prior, attempts, strategy)`. This tuple is the primary key of benchmarks.
7. **CPU-first.** No GPU, no server, no network at solve time. Lexicon build and policy
   generation may use all cores offline.

---

## 2. Directory structure

```
wordle/
  WORDLE_AI_*.md                  # this corpus
  pyproject.toml                  # package metadata, deps, tool config
  README.md                       # quickstart (Phase 1)
  config/
    default.toml                  # shipped configuration
  data/
    raw/                          # downloaded sources; gitignored; never shipped
    processed/                    # built lexicons, tables, manifests; gitignored
    user/                         # user-supplied classic lists; gitignored
  policies/                       # generated exact policies (*.policy.json + .sha256)
  src/wordle_ai/
    __init__.py
    config.py                     # pydantic settings, TOML loading
    types.py                      # enums, dataclasses, pydantic models
    errors.py                     # error taxonomy
    lexicon/
      source.py                   # source descriptors, fetching, checksums
      normalize.py                # NFC, casefold, grapheme length, alphabet filter
      build.py                    # the 12-step pipeline
      profile.py                  # Profile runtime object, bitsets, indexing
      manifest.py                 # provenance manifest read/write
    engine/
      feedback.py                 # two-pass feedback, base-3 codec
      table.py                    # uint8 feedback matrix, memory policy
      state.py                    # GameState, invariants, replay
      filter.py                   # candidate filtering, bitsets
      prior.py                    # uniform, Zipf, calibration
    strategy/
      base.py                     # Strategy protocol, Decision, ScoreBreakdown
      random_valid.py
      first_candidate.py
      letter_frequency.py
      positional_frequency.py
      expected_remaining.py
      minimax.py
      entropy.py
      weighted_entropy.py
      bayes_cost.py
      lookahead.py                # two-ply
      rollout.py
      exact.py                    # DP + policy lookup
      hybrid.py                   # composite policy selector
    solver/
      dp.py                       # memoised recursion, pruning, canonicalisation
      policy.py                   # artifact build/load/verify
      value_model.py              # distilled value model inference (Phase 6)
    sim/
      environment.py              # gym-style environment, no dependency on gym
      runner.py                   # exhaustive / sampled game loops
      parallel.py                 # process pool, deterministic reduction
    bench/
      metrics.py                  # all metrics from the benchmark plan
      runner.py                   # profile × strategy × prior matrix
      report.py                   # markdown/CSV output
      stats.py                    # bootstrap CIs, paired tests
    ml/
      features.py
      ranker.py                   # GBDT challenger
      distill.py                  # imitation of DP policy
      gate.py                     # numeric admission gate
      rl/                         # research-only; excluded from default install
    store/
      sqlite.py                   # runs, games, decisions, artifacts
      cache.py                    # feedback-row LRU
    cli/
      main.py                     # Typer app
      commands/*.py
    api/
      service.py                  # transport-agnostic use cases
      http.py                     # optional FastAPI adapter (Phase 7)
  tests/
    unit/ integration/ property/ golden/ exhaustive/
  tools/
    measure_lexicons.py           # Phase 0 spike (kept for reproducibility)
```

**Dependency rule.** `strategy` may import `engine` and `lexicon`; `engine` may import `lexicon`
and `types`; `cli`, `api`, `bench`, `sim`, `ml` may import downward but nothing below may import
them. `engine` must not import `numpy` types into its public signatures (arrays are internal).

---

## 3. Core data model

### 3.1 Enumerations

```python
class RuleMode(str, Enum):      NORMAL, HARD, SUPERHARD
class PriorKind(str, Enum):     UNIFORM, ZIPF, EMPIRICAL
class Tile(int, Enum):          GRAY = 0; YELLOW = 1; GREEN = 2
```

### 3.2 `Profile`

```python
@dataclass(frozen=True)
class Profile:
    profile_id: str             # e.g. "classic.en.5", "strict.en.4"
    language: str               # BCP-47-ish tag, "en"
    dialect: str | None         # "american" | "british" | None
    length: int                 # 1..5 in v1 (validated, not assumed)
    alphabet: str               # "abcdefghijklmnopqrstuvwxyz"
    answers: tuple[str, ...]    # sorted, unique, ASCII
    guesses: tuple[str, ...]    # sorted, unique, superset of answers
    answer_index: dict[str, int]
    guess_index: dict[str, int]
    manifest_sha256: str
    source_ids: tuple[str, ...]
```

Invariants asserted at construction: `answers ⊆ guesses`; every word matches
`^[alphabet]{length}$`; no duplicates; `manifest_sha256` matches the loaded manifest; length
equals the configured length. Failure raises `ProfileIntegrityError` (never a silent warning).

### 3.3 `Pattern`

```python
@dataclass(frozen=True, order=True)
class Pattern:
    code: int                   # base-3 integer in [0, 3**L)
    length: int

    def tiles(self) -> tuple[Tile, ...]      # least-significant trit is position 0
    @classmethod
    def from_tiles(cls, tiles: Sequence[Tile]) -> "Pattern"
    @classmethod
    def parse(cls, text: str, alphabet: str) -> "Pattern"   # "GYBBG" / "01220"
    def render(self) -> str                                  # canonical letters G/Y/B
```

Wire format for humans: `G`/`Y`/`B` (also accept `2`/`1`/`0`, and `🟩`/`🟨`/`⬛` for pasted
output; parser strips whitespace and rejects anything else). Canonical internal form is the
integer code, so a table cell is one `uint8`.

### 3.4 `GameState`

```python
@dataclass
class GameState:
    profile_id: str
    mode: RuleMode
    max_attempts: int
    history: list[Turn]              # Turn = (guess: str, pattern: Pattern)
    candidates: np.ndarray           # uint8 mask, len == len(profile.answers)
    posterior: np.ndarray            # float64, sums to 1.0 over candidates
    prior_kind: PriorKind
    prior_params: dict[str, float]
    attempts_used: int

    @property
    def remaining(self) -> int
    @property
    def candidate_words(self) -> list[str]
    def is_solved(self) -> bool
```

`candidates` is authoritative; `posterior` is derived and cached. Both are rebuilt on load by
replaying `history`, so a persisted state can never disagree with its history.

### 3.5 `Decision`

```python
@dataclass(frozen=True)
class Decision:
    guess: str
    strategy: str
    score: float                       # lower is better, strategy-defined
    breakdown: dict[str, float]        # entropy, expected_remaining, worst_case, p_answer, ...
    candidates_before: int
    candidates_after_expected: float
    p_solve_now: float
    explanation: str                   # ≤ 2 sentences, user-facing
    exact: bool                        # whether a proven-optimal policy produced it
    elapsed_ms: float
```

`explanation` is generated from the numbers, not hand-written per strategy, e.g.
*"SALET splits 2,315 candidates into 148 groups (largest 168). It is expected to leave 61.2
candidates, and it wins immediately in 0.0% of games."*

### 3.6 `LexiconManifest`

```json
{
  "schema_version": 1,
  "profile_id": "strict.en.5",
  "created_utc": "2026-11-19T00:00:00Z",
  "generator_version": "0.1.0",
  "language": "en", "dialect": "american", "length": 5,
  "alphabet": "abcdefghijklmnopqrstuvwxyz",
  "sources": [
    {"id": "scowl", "version": "2020.12.07",
     "url": "https://wordlist.aspell.net/", "retrieved_utc": "2026-11-19T00:00:00Z",
     "sha256": "dc3435e1cb56f3394aea91b5d2ab5d10d80c98bc7dd88c3fccb7348f6ab913a0",
     "license": "SCOWL permissive (MIT/X11-style), notice required",
     "license_file": "data/raw/scowl/Copyright"}
  ],
  "transforms": [
    "decode:latin-1", "normalize:NFC", "casefold", "filter:ascii_alpha",
    "filter:length==5", "dedupe", "sort", "assert:answers_subset_guesses"
  ],
  "counts": {"answers": 4444, "guesses": 4444, "by_length": {"5": 4444}},
  "rejected": {"apostrophe": 0, "non_ascii": 0, "other": 0},
  "outputs": {"lexicon": "data/processed/strict.en.5/lexicon.npz",
              "lexicon_sha256": "…", "feedback_table": "…", "table_sha256": "…",
              "feedback_table_bytes": 19749136},
  "policy_artifacts": ["policies/strict.en.5.exact.policy.json"]
}
```

The manifest is the *only* accepted source of truth for a profile. Loading a lexicon without a
matching manifest checksum fails closed.

### 3.7 `PolicyArtifact` (exact solver output)

```json
{
  "schema_version": 1,
  "profile_id": "classic.en.5",
  "profile_sha256": "…",
  "answer_set_sha256": "…",
  "answer_set_size": 2315,
  "rules": "normal",
  "prior": "uniform",
  "attempts": 6,
  "strategy": "exact",
  "solver_version": "0.1.0",
  "proven_optimal": true,
  "expected_guesses": 3.4212,
  "max_guesses": 5,
  "tree": {"root": {"guess": "salet", "children": {"<code>": {…}}}},
  "sha256": "…"
}
```

Loading verifies `profile_sha256`, `rules`, `prior`, `attempts` and the artifact's own checksum.
A mismatch raises `ArtifactMismatchError`; it never falls back silently.

---

## 4. Feedback engine

**Reference implementation** (exact, `O(L)`):

```
def feedback(guess, answer, length, alphabet_index):
    tiles = [GRAY]*L
    remaining = Counter()                      # multiset of answer letters
    for i in range(L):
        if guess[i] == answer[i]: tiles[i] = GREEN
        else: remaining[answer[i]] += 1
    for i in range(L):
        if tiles[i] is GREEN: continue
        c = guess[i]
        if remaining[c] > 0:
            tiles[i] = YELLOW; remaining[c] -= 1
    return Pattern.from_tiles(tiles)
```

Note the two-pass structure: greens are reserved before any yellow is considered, and the counter
holds only *unmatched* answer letters. This is the whole correctness argument; the tests below
pin it.

**Vectorised implementation.** For a fixed guess `g` and a table row, the pattern for every
answer is precomputed. For on-demand computation over a candidate array, `numpy` comparison plus
a per-position trit accumulation reproduces the reference result: exact-match mask, then for
each letter a cumulative count of unmatched occurrences, then `yellow = present & (rank <
available)`. The vectorised path is validated against the reference on **every** (guess, answer)
pair of every profile in CI for lengths 1–4, and on a stratified sample plus all duplicate-letter
cases for length 5.

**Complexity.** Reference `O(L)` time, `O(L)` space. Table build `O(\|G\| · \|A\| · L)`; for the
classic profile that is 30M pattern computations, a few seconds in numpy `[E]`.

**Base-3 codec.** Position 0 is the least-significant trit. `code = Σ tiles[i] · 3^i`. This makes
`code < 3**L` and lets a table cell be `uint8`. `Pattern.parse` rejects strings whose length
differs from `L` or whose characters are outside `{G,Y,B}`.

---

## 5. Candidate filtering

```
def filter_candidates(state, guess, pattern, table):
    row = table.row(guess)                     # uint8[|A|] or computed on demand
    mask = (row == pattern.code)
    new_candidates = state.candidates & mask
    if new_candidates.sum() == 0:
        raise InconsistentFeedback(guess, pattern)   # I3, not a silent empty set
    return new_candidates
```

- **Filtering is defined by recomputation, not by rule inference.** No component maintains
  "letter is absent" flags as the source of truth.
- **Bitset representation.** Internally `numpy.uint8` masks; for cross-checks a `uint64` bitset
  view supports fast popcount. Both must agree (`tests/unit/test_filter_equivalence.py`).
- **Complexity.** `O(\|A\|)` per guess with a table, `O(\|A\| · L)` without.
- **Monotonicity.** `S_{t+1} ⊆ S_t` always; asserted in debug builds and property-tested.

---

## 6. Strategy engine

### 6.1 Interface

```python
class Strategy(Protocol):
    name: str
    exact: bool
    def score(self, state: GameState, profile: Profile,
              table: FeedbackTable, budget: Budget) -> list[ScoreBreakdown]: ...
    def choose(self, state: GameState, profile: Profile,
               table: FeedbackTable, budget: Budget) -> Decision: ...
```

`score` returns a breakdown for *every* legal guess so the UI and benchmark can explain choices;
`choose` is the argmin with deterministic tie-breaking. Strategies may raise
`BudgetExceeded`; the hybrid selector catches it and falls back.

### 6.2 Scoring functions (all minimised)

| Strategy | Score for guess `g` | Notes |
|---|---|---|
| `random_valid` | `rng()` | Not implemented in Phase 2 (no RNG in a production path); belongs to the Phase 4 benchmark matrix, where the seed is part of the run key |
| `first_candidate` | `0` for candidates, `1` otherwise | Sanity/fallback |
| `letter_frequency` | `-Σ_{c ∈ distinct(g)} f(c)` | `f` is the letter share of the **remaining candidates**, not the whole corpus: a corpus-wide table is state-independent and makes the strategy repeat one word until it fails (measured on classic: 5.6832 average, 67.0% unsolved) |
| `positional_frequency` | `-Σ_i f_i(g_i)` | Position-conditioned share of the remaining candidates |
| `expected_remaining` | `Σ_r p_r \|S_r\|` | Uniform: `Σ\|S_r\|²/\|S\|` |
| `minimax` | `max_r \|S_r\|` | Tie-break: second-largest, then entropy |
| `entropy` | `-Σ_r p_r log2 p_r` | Ties broken by expected remaining |
| `weighted_entropy` | `-Σ_r p_r log2 p_r` under the answer prior | Prior-aware |
| `bayes_cost` | `Σ_r p_r (1 + V̂(S_r))` with `V̂` analytic | One-step expected cost |
| `lookahead` | two-ply expansion of `bayes_cost` over a shortlist | Hottest path |
| `rollout` | mean simulated guesses under a base strategy | Endgame only |
| `exact` | `V_k(S)` from DP or a verified policy artifact | Proven optimal when `proven_optimal` |

**Forced endgame branches (Phase 2).** Every strategy, before applying its own objective, takes
two forced cases, each recorded as `Decision.breakdown["branch"]`: with one candidate it guesses
that candidate (`single_candidate`); with two turns left it guesses the highest-posterior candidate
(`endgame_candidate`), because a splitter cannot be cashed in with the single remaining turn. This
is a scoring rule, not a search: no two-ply or rollout is performed in Phase 2.

**Unit of score.** All scores are minimised; ties are broken by the strategy's declared secondary
key and then by ascending guess index. Entropy's secondary key is expected remaining;
expected-remaining's is entropy; minimax's is the second-largest bucket and then entropy.

**Composite default (`hybrid.balanced`)**

```
if policy artifact valid for (profile, rules, prior, attempts): use exact
elif |S| == 1: guess the only candidate
elif k == 1: guess argmax posterior (no elimination value left)
elif |S| <= lookahead.max_candidates and k >= 2: two-ply over top-n by expected_remaining
elif |G| * |S| <= budget.pairwise_limit: expected_remaining with entropy tie-break
else: entropy over a pruned guess shortlist
```

Every threshold is a config key (`strategy.hybrid.*`); every branch is recorded in
`Decision.breakdown["branch"]` so a decision can be audited.

### 6.3 Hard-mode constraint filter

Legal guesses under each mode:

| Mode | Constraint |
|---|---|
| `NORMAL` | `g ∈ G` |
| `HARD` (NYT) | `g ∈ G`; each green letter appears at the same position; each yellow letter appears somewhere; a letter proven absent by count is not introduced beyond its known multiplicity |
| `SUPERHARD` | `g ∈ S` (a candidate), in addition to HARD constraints |

The duplicate-letter rule is expressed as a **minimum multiplicity**, not a per-letter ban: if the
answer has two `l` and one is green at position 2, a guess may contain `l` at position 2 and one
more `l` elsewhere, but not three. Gray-only for a letter that also has green/yellow feedback
must not zero out the allowed count. This is implemented by deriving, from the history, a
`LetterConstraint` (min count, max count, fixed positions, excluded positions) via the *same*
feedback function, and testing candidate guesses against it. Where a constraint is
underdetermined (the feedback does not pin the count), the bound is a range, not a point.

### 6.4 Determinism

Ties are broken by ascending index in the profile's sorted guess list — never by dict order,
never by floating-point noise. Scores are compared with a fixed epsilon (`1e-12`) and then by
index. `random_valid` uses a seeded `numpy.random.Generator` stored in the run record.

---

## 7. Exact solver

### 7.1 Recursion

```
V(k, S):
    if |S| == 1: return 1
    if k == 1:   return INF
    key = (k, canonical(S))
    if key in memo: return memo[key]
    best = INF
    for g in ordered_guesses(S):           # candidates first, then the rest by index
        if not feasible_in_mode(g): continue
        buckets = partition(S, g)
        cost = 1 + Σ_{r != solved(g)} (|b_r|/|S|) * V(k-1, b_r)
        if cost < best - EPS: best, best_g = cost, g
    memo[key] = best
    return best
```

`solved(g)` is the all-green bucket `{g}` when `g` is in `S`. It contributes **zero** further
guesses: the guess that produced it is already being paid for by the leading `1`. Charging
`V({g}) = 1` on top of that counts a solved game twice — a bug this project actually had, caught
by comparing the serialised policy's measured average with the DP value, and now pinned by the
brute-force test in `tests/unit/test_exact.py`.

The last line of the pseudo-code, entropy-style `lower_bound` early exit, is not implemented. It
was replaced by the incumbent bound inside the bucket loop: as soon as a partial sum makes
`1 + Σ |b_r| V / |S|` reach the best complete guess, the candidate cannot improve and is dropped.
Guess ordering is candidates-first then index order, because heuristic ordering would itself need
the full partition pass the solver is trying to avoid.

### 7.2 Optimisations, in the order they matter

1. **Memoisation keyed by candidate-set digest** (SHA-1 of the sorted index list, truncated),
   with the full set stored to detect collisions. Bounded by an LRU of configurable size.
2. **Canonicalisation**: bucket sets are canonicalised by sorted index tuple, so identical
   subtrees share entries.
3. **Branch and bound** with `lower_bound(S) = 1` plus an entropy-derived bound on the number of
   remaining rounds: if `\|S\| > 3^(k-1) · max_bucket_capacity`, the state is infeasible.
4. **Guess ordering** by one-step expected remaining; the incumbent then prunes.
5. **Immediate-win shortcut**: if a candidate has posterior ≥ `1 - 1e-12`, its value is 1.
6. **Feasibility pruning** for hard modes (constraint filter before partitioning).
7. **Parallelism at the root**: root guesses are independent; `multiprocessing` over root moves
   with deterministic reduction (min over `(cost, guess_index)`). This is the only place
   parallelism changes wall-clock materially.
8. **Rust inner loop** (optional, Phase 8): the partition + recursion kernel behind a
   `wordle_core` module, with the Python implementation retained as the oracle and fallback.

### 7.3 Policy artifacts

For tractable profiles the solver emits a decision tree: at each node, the chosen guess and, per
feedback code, the child node. This turns an hours-long DP into microsecond lookups and makes
"why this word" answerable exactly (`policy` strategy, `exact: true`). Artifacts are checksummed
and keyed by profile digest, rules, prior and attempt limit.

**Feasibility gate** (matches the research report): attempt exact solving only when
`\|A\| ≤ exact.max_answers (5000)` and `\|G\| ≤ exact.max_guesses (20000)`; otherwise the CLI prints
the reason and recommends `rollout`. The gate is enforced in code so a user cannot accidentally
start a multi-day job without `--force`.

### 7.4 Measured boundary (2026-11-20)

The gate is necessary, not sufficient. The shipped pure-Python kernel measures ≈4.3 nodes/s on
`classic.en.5` (544 nodes in 127 s), so a full solve of that profile is out of reach without the
compiled kernel in Phase 8. `tools/measure_exact.py` records every case it attempts, with nodes,
guess evaluations and wall-clock, in `data/exact/feasibility.json`; the benchmark plan §14 carries
the table. Exact solve is implemented for **normal mode only**: hard and superhard legality depends
on the accumulated constraint, so their state is `(candidates, constraint)` and is not claimed
here. Policy lookup is unaffected by solve cost and measures p95 0.219 ms on a reloaded artifact.

---

## 8. Probability engine

```
class Prior(Protocol):
    def weights(self, profile: Profile) -> np.ndarray   # unnormalised, len == |A|
```

- `UniformPrior` → ones.
- `ZipfPrior(beta, floor)` → `exp(beta * (zipf(w) - zipf_max))`, computed at load time from the
  optional `wordfreq` dependency; words absent from wordfreq get `zipf = 0`.
- `EmpiricalPrior(path)` → counts from a user-supplied answer history, Laplace-smoothed.

Normalisation happens once per state rebuild; `posterior.sum()` is asserted to be 1 within
`1e-9`. Calibration (`ml/gate.py`) reports log loss and Brier score against held-out answers and
refuses to enable a non-uniform prior whose log loss is worse than uniform's.

---

## 9. Simulation environment

```python
class Environment:
    def reset(self, answer: str | None = None, seed: int | None = None) -> Observation
    def step(self, guess: str) -> tuple[Observation, float, bool, dict]
    def legal_actions(self) -> np.ndarray            # boolean mask over profile.guesses
```

- `answer=None` samples from the answer prior (seeded).
- `step` validates the guess against `G` (and the mode), computes feedback, updates state, and
  returns `(obs, reward, done, info)` with `reward = -1` per guess, `+1` bonus on solve, `0` on
  failure — the benchmark uses guesses, not reward, so shaping never contaminates results.
- Illegal guess → `InvalidGuessError`, never silently coerced.
- Exhaustive mode iterates answers in profile order; parallel mode shards by index and reduces
  with `(sum, count, histogram, max)` — order-independent, hence deterministic.

---

## 10. Benchmark engine

Contract: given `(profile, strategy, rules, prior, attempts, answer_set, seed)`, produce a
`RunRecord` with every metric in the benchmark plan, plus provenance (git-free: package version,
config digest, profile manifest checksum, artifact checksums, Python/numpy versions, CPU count,
wall-clock). Results are written to SQLite and exported to CSV/Markdown. Re-running the same
tuple must produce identical per-game guess counts; the report includes a `determinism_sha256`
over the per-game tuple list.

Full metric definitions, sampling rules and ablations live in `WORDLE_AI_BENCHMARK_PLAN.md`;
this document only fixes the interfaces.

---

## 11. Persistence and cache

SQLite (single file, WAL, no server), as implemented in Phase 4. `PRAGMA user_version` records the
schema version and migrations are applied forward one version at a time; a store newer than the
build is refused rather than reinterpreted.

```sql
CREATE TABLE dataset (profile_id TEXT PRIMARY KEY, manifest_sha256 TEXT NOT NULL,
                      built_utc TEXT NOT NULL, counts_json TEXT NOT NULL);
CREATE TABLE run (run_id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, rules TEXT NOT NULL,
                  prior TEXT NOT NULL, attempts INT NOT NULL, strategy TEXT NOT NULL,
                  answer_set TEXT NOT NULL, seed INT, config_sha256 TEXT NOT NULL,
                  created_utc TEXT NOT NULL, metrics_json TEXT NOT NULL,
                  determinism_sha256 TEXT NOT NULL);
CREATE TABLE game (run_id TEXT, answer TEXT, guesses_json TEXT, solved INT, n_guesses INT,
                   elapsed_ms REAL, final_candidates INT, opener TEXT, candidates_json TEXT,
                   PRIMARY KEY (run_id, answer));
CREATE TABLE artifact (kind TEXT, profile_id TEXT, rules TEXT, prior TEXT, attempts INT,
                       path TEXT, sha256 TEXT, created_utc TEXT,
                       PRIMARY KEY (kind, profile_id, rules, prior, attempts));
CREATE TABLE cache_meta (key TEXT PRIMARY KEY, sha256 TEXT, bytes INT, created_utc TEXT);
CREATE INDEX run_profile_strategy ON run(profile_id, strategy);
```

Two deliberate differences from the Phase 0 sketch. Per-turn data lives in `game.candidates_json`
(the candidate counts before and after each turn) rather than in a `decision` row: every §4 metric
needs those counts, nothing in the benchmark needs a separate decision row, and a row per turn would
multiply the store by six for no measurable gain. Per-decision records belong to the service API
(Phase 7), which also owns `breakdown_json`. `run.metrics_json` holds the whole `RunResult` plus the
provenance block and a `status` (`succeeded` or `budget_exceeded`), which is what resume reads.

Feedback tables are `.npy` files with a sidecar `.sha256`, not BLOBs — memory-mapping beats
SQLite for a 30 MB array. Row caches are LRU in RAM only; nothing is written on the hot path.

---

## 12. CLI and API

### 12.1 CLI (Typer; every operation is reachable from it)

```
wordle-ai config show|validate
wordle-ai lex fetch   --source scowl|enable|user --dest data/raw
wordle-ai lex build   --profile strict.en.5 [--dialect american] [--dry-run]
wordle-ai lex inspect --profile strict.en.5 [--length 5] [--json]
wordle-ai lex verify  --all
wordle-ai table build --profile classic.en.5 [--max-bytes 268435456]
wordle-ai policy build --profile classic.en.5 [--mode normal] [--attempts 6]
                       [--guess-set all|candidates] [--time-budget S] [--force]
wordle-ai policy verify --path policies/classic.en.5.normal.uniform.a6.policy.json
wordle-ai policy show   --path policies/…
wordle-ai play        --profile classic.en.5 [--strategy hybrid.balanced] [--mode hard]
wordle-ai suggest     --profile classic.en.5 --history history.json [--json]
wordle-ai selfplay    --profile strict.en.5 --games 2000 [--strategy entropy]
wordle-ai bench run     --profile classic.en.5 --strategies all [--mode normal] [--prior uniform]
                        [--limit N] [--workers 16] [--policy PATH] [--store PATH]
                        [--time-budget S] [--no-store] [--json]
wordle-ai bench report  --run A[,B] --format markdown|csv|json [--out PATH]
wordle-ai bench compare --run A --other B [--metric avg_guesses_solved]
                        [--allow-mismatch] [--check-determinism] [--json]
wordle-ai ml train|eval|gate --config ml/ranker.toml
wordle-ai diagnose    --profile classic.en.5
```

Exit codes: `0` success, `1` usage error, `2` missing input, `3` integrity/invariant failure,
`4` budget exceeded, `5` artifact mismatch. Every command supports `--json` for machine use and
prints a stable human summary otherwise.

### 12.2 Service API (transport-agnostic)

```python
class SolverService:
    def profiles(self) -> list[ProfileInfo]
    def new_game(self, profile_id: str, mode: RuleMode, attempts: int,
                 prior: PriorKind) -> GameView
    def apply_feedback(self, game_id: str, guess: str, pattern: str) -> GameView
    def suggest(self, game_id: str, strategy: str | None = None) -> Decision
    def candidates(self, game_id: str, top: int = 10) -> list[CandidateView]
    def replay(self, history: list[Turn]) -> GameView
    def explain(self, game_id: str, guess: str) -> ScoreBreakdown
```

`GameView` is a plain dataclass with candidate count, top candidates with probabilities, last
decision and a rendered explanation — enough for any front end, including a future external game
adapter, without exposing numpy arrays.

---

## 13. Data flows

**Lexicon build**

```
sources → verify sha256 → decode (utf-8, fallback latin-1, recorded)
        → NFC + casefold → alphabet filter → length filter → policy filters
        → dedupe → sort → assert answers ⊆ guesses
        → write lexicon.npz + manifest.json (counts, rejects, transforms, checksums)
        → build feedback table (if within memory budget) + .sha256
```

**Solve turn**

```
history ──► replay ──► candidates (bitset) ──► posterior ──► strategy.score(all guesses)
                                                        │
                                                        ├─► hybrid branch choice
                                                        └─► Decision (guess, breakdown, explanation)
                                                                 │
                                                                 └─► persist decision row
```

**Exact policy generation**

```
profile + rules + prior ──► feasibility gate ──► DP with memo+pruning (parallel at root)
                        ──► tree + metrics ──► policy.json + sha256 ──► artifacts table
```

**ML distillation (Phase 6)**

```
DP policies (many profiles) → state features + optimal value/label
    → train/val split by ANSWER WORD → model → export (ONNX or joblib)
    → gate: Δ avg guesses, worst case, latency, cross-profile generalization → admit/reject
```

---

## 14. Solver decision flow

```
                    ┌──────────────────────────┐
                    │ state built from history │
                    └────────────┬─────────────┘
                                 ▼
                 |S| == 1 ? ──yes──► return the candidate (solved)
                                 │no
                                 ▼
                 k == 1 ? ─────yes──► argmax posterior
                                 │no
                                 ▼
        verified exact policy exists ? ──yes──► policy lookup (exact: true)
                                 │no
                                 ▼
          |S| ≤ lookahead.max ? ──yes──► two-ply over top-n
                                 │no      (budget-guarded; on timeout → next branch)
                                 ▼
        |G|·|S| ≤ pairwise_limit ? ──yes──► expected_remaining + entropy tie-break
                                 │no
                                 ▼
                     entropy over pruned shortlist
```

---

## 15. Error taxonomy

| Error | Raised when | Handling |
|---|---|---|
| `ConfigError` | invalid TOML, unknown key, bad range | exit 1, print key path |
| `SourceIntegrityError` | checksum mismatch, missing file | exit 3, refuse to build |
| `ProfileIntegrityError` | answers ⊄ guesses, bad alphabet, duplicate, wrong length | exit 3 |
| `InvalidGuess` | guess not in `G`, or violates hard mode | exit 1; API returns 400-style result |
| `InconsistentFeedback` | history eliminates all candidates (I3) | exit 3; report the offending turn |
| `ArtifactMismatchError` | profile/rules/prior/checksum mismatch | exit 5; never silently fall back |
| `BudgetExceeded` | time or memory cap hit mid-search | caller falls back to a cheaper strategy, recorded |
| `UnsupportedProfile` | length outside 1..5 or alphabet mismatch | exit 2 |
| `PriorCalibrationError` | prior log loss worse than uniform | refuse to enable prior |

All errors carry a machine-readable `code`, a human message, and (where relevant) the state hash.

---

## 16. Configuration

`config/default.toml`, validated by pydantic; every key has a documented default.

```toml
[general]
data_dir = "data"
cache_dir = "data/processed/cache"
deterministic = true

[profile]
id = "classic.en.5"
language = "en"
length = 5
alphabet = "abcdefghijklmnopqrstuvwxyz"
answers_path = "data/user/classic_answers.txt"
guesses_path = "data/user/classic_guesses.txt"

[rules]
mode = "normal"            # normal | hard | superhard
max_attempts = 6

[prior]
kind = "uniform"           # uniform | zipf | empirical
beta = 0.0
empirical_path = ""

[feedback]
table_max_bytes = 268435456   # 256 MiB
build_policy = "auto"         # auto | full | none | hybrid
lru_rows = 2048

[strategy]
default = "hybrid.balanced"
top_n_lookahead = 12
lookahead_max_candidates = 50
rollout_max_candidates = 25
pairwise_limit = 20000000
tie_epsilon = 1e-12

[exact]
max_answers = 5000
max_guesses = 20000
memo_max_entries = 2000000
time_budget_s = 86400
parallel_root = true

[bench]
answers = "all"
seed = 20261119
workers = 16
bootstrap_samples = 10000

[ml]
enabled = false
model_path = ""
max_decision_ms = 5.0
min_avg_improvement = 0.02
```

---

## 17. Performance budgets

| Operation | Budget | Basis |
|---|---|---|
| Single feedback | ≤ 2 µs (Python), ≤ 200 ns (vectorised) | `[E]` |
| Candidate filter, A = 12,972 | ≤ 100 µs | table row compare `[E]` |
| One-step decision, all guesses, S = 2,315 | ≤ 250 ms | 30M byte compares in numpy `[E]` |
| One-step decision, S ≤ 50 | ≤ 5 ms | shortlist `[E]` |
| Two-ply, S = 50, top 12 | ≤ 2 s | 12·50·50 partitions `[E]` |
| Exact policy lookup | ≤ 1 ms | tree walk `[E]` |
| Profile load (classic) | ≤ 1 s | memmap + manifest verify `[E]` |
| Table build (classic) | ≤ 60 s | 30M patterns `[E]` |

These are engineering budgets to be replaced by measurements in Phase 2; the benchmark plan
records actuals and the roadmap gates on them.

---

## 18. Testing requirements per component

| Component | Required tests |
|---|---|
| `normalize` | NFC idempotence; grapheme length vs code-point length; casefold edge cases; reject non-alphabet; no silent truncation |
| `feedback` | golden duplicate-letter suite; all 3^L patterns reachable; vectorised == reference on exhaustive L ≤ 4 and sampled L = 5 |
| `table` | every cell equals reference; checksum stability; memory policy honours budget; on-demand path agrees |
| `filter` | monotonicity; true answer retained; inconsistent history raises; bitset == mask |
| `state` | replay determinism; invariant assertions; solved-state detection |
| `prior` | normalisation; beta=0 equals uniform; calibration refusal |
| each strategy | legality of every returned guess; score consistency; deterministic ties; budget behaviour |
| `exact` | artifact verify; policy value equals DP value on sampled states; infeasibility gate |
| `sim` | reward semantics; exhaustive iteration covers all answers exactly once; parallel == serial |
| `bench` | metric formulas against hand-computed fixtures; determinism hash stable |
| `store` | schema migration; concurrent readers during run |
| `cli` | exit codes; `--json` schema; helpful errors on missing files |
| `ml` | leakage test (no test answer appears in training states); gate arithmetic |

---

## 19. Extension points

- **New language:** supply a profile with a different alphabet and word lists; nothing in the
  engine assumes Latin letters. Feedback uses per-position character equality and multiset
  counts, both alphabet-agnostic. Normalisation rules are per-language config.
- **New length:** `3**L ≤ 256` governs the `uint8` table; for `L ≥ 6` the codec widens to
  `uint16`. v1 validates `L ∈ 1..5` and rejects others with `UnsupportedProfile`, but the codec
  is written parameterically so widening is a config change plus a table dtype change.
- **New mode:** implement a constraint predicate `legal(g, history) -> bool` and register it;
  the solver already takes feasibility as a predicate.
- **External game adapter:** implement `GamePort` (`read_board()`, `submit_guess()`) over the
  service API; the solver core is untouched.

---

## 20. Deliberate exclusions

No web framework in v1, no authentication, no database server, no telemetry, no GPU path, no
network calls during solving. The optional HTTP adapter in Phase 7 is a thin layer over
`SolverService` and must not contain solver logic.
