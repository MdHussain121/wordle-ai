# WORDLE_AI_PRD.md

**Product:** Wordle-solving AI for word lengths 1–5
**Status:** Phase 0 deliverable, revision 1.0 · **Date:** 2026-11-19
**Supersedes:** nothing · **Related:** all `WORDLE_AI_*.md` documents in this corpus

---

## 1. Product overview

### 1.1 Vision

A Wordle player that can *show its work*. It should play at the level of the best published
solvers, explain every recommendation in plain language, and let a curious user open the hood to
see the probabilities, the partition sizes and the arithmetic behind a guess.

The product is not a Wordle clone, and it is not a chatbot that happens to know some five-letter
words. It is a decision engine over a configurable lexicon, with a simulator and a benchmark
harness strong enough to prove its own claims.

### 1.2 Problem statement

Three problems, in order of how often they are solved badly:

1. **Most "Wordle solvers" are letter-frequency scripts.** They recommend a word because its
   letters are common, not because the word partitions the remaining candidates well. They cannot
   explain a choice, cannot handle repeated letters correctly, and cannot be compared fairly
   because they do not control for dictionary, rules or prior.
2. **Correct feedback is routinely got wrong.** Duplicate letters are the classic failure: a guess
   containing three copies of a letter against an answer containing one must produce exactly one
   non-gray tile (plus any greens). Naive membership tests produce greens and yellows that cannot
   occur, which silently corrupts every candidate count downstream.
3. **"Best word" claims are usually unqualified.** `SALET` is optimal for one specific list
   (2,315 answers, 12,972 guesses). On the 2023 list the optimum is `TARSE` `[P]`. A solver that
   prints an opener without naming its dictionary, rules and prior is making an untestable claim.

The product's response to all three is the same: a rigorous engine, a profile system that makes
the dictionary explicit, and a benchmark harness that reports failures instead of hiding them.

### 1.3 Target users

| Persona | Need | What they use |
|---|---|---|
| **Casual player** ("Priya") | "I have three greens and one yellow; what now?" | Solver Assistant, natural-language explanation, one recommended word |
| **Puzzle enthusiast** ("Marcus") | Wants the best play and to understand why, without statistics | Solver Assistant + short "why" line + candidate list |
| **Algorithm learner** ("Dana") | Wants to see entropy vs minimax vs exact, with numbers | Strategy Laboratory, technical mode, decision breakdown |
| **Researcher / engineer** ("Sam") | Wants reproducible benchmarks, ablations and failure cases | Benchmark Mode, CSV export, determinism hashes |
| **Lexicon tinkerer** ("Ada") | Wants to know which words are in, which are out, and why | Dictionary Laboratory, `lex inspect`, `lex diff` |

### 1.4 Primary use cases

1. **Assist a live game.** The user types their guess and the colours they received; the AI
   returns the next guess, the remaining candidate count, and the top candidates with
   probabilities.
2. **Play itself.** Run the AI against the internal simulator for one game or ten thousand, with
   a chosen profile, mode, prior and strategy.
3. **Compare strategies.** Run every strategy on the same answer set and see average, median,
   worst case, success rate and the full guess distribution.
4. **Audit the dictionary.** Inspect which words a profile contains, which rules excluded what,
   and what changed between two builds.
5. **Reproduce a published result.** Re-run the classic configuration and check the reported
   average and worst case against the literature, with discrepancies explained.

### 1.5 Goals

| ID | Goal | Measure |
|---|---|---|
| G-1 | Play the classic configuration optimally | 3.4212 ± 0.0005 average, worst case 5, 100% solved within 6 `[P]` target |
| G-2 | Be correct on feedback | Exhaustive equality with a reference implementation on every (guess, answer) pair for L ≤ 4; full duplicate-letter suite for L = 5 |
| G-3 | Support lengths 1–5 without five-letter assumptions | Every profile length runs the same engine and passes the same invariants |
| G-4 | Be explainable | Every recommendation carries a numeric breakdown and a one-sentence reason |
| G-5 | Be reproducible | Identical per-game results across runs, worker counts and machines; checksums recorded |
| G-6 | Be honest about limits | Exactness is declared per profile; unsolved games are reported, never averaged away |
| G-7 | Be practical on a laptop | ≤ 250 ms per recommendation at the largest supported candidate set; no GPU |

### 1.6 Non-goals (v1)

- Reproducing the Wordle web UI, animations or social sharing.
- Scraping or automating the live NYT game.
- Claiming a canonical English word list; the system ships profiles, not truth.
- Non-English lexicons (the architecture supports them; v1 ships English only).
- Multiplayer, accounts, cloud sync, telemetry, mobile apps.
- A deep-learning agent as the default policy. ML is an appendix behind a numeric gate.
- Any online service, database server or GPU requirement.

### 1.7 Success criteria (release gate)

The release is accepted only when all of the following hold, measured by the benchmark harness:

1. Classic profile, normal mode, all 2,315 answers: average 3.4212 ± 0.0005, worst case 5, 0
   failures, and the opener matches the published optimum for that exact list.
2. The same run repeated with 1 and 16 workers yields an identical determinism hash.
3. Duplicate-letter golden suite passes, including cases where a guess has more copies of a
   letter than the answer.
4. Every strategy returns only legal guesses on every state in an exhaustive sweep of the classic
   profile (all reachable states up to depth 3, sampled beyond).
5. Full benchmark report produced with all required metrics, including failure counts.
6. No hardcoded dictionary path, opener, length or attempt limit anywhere outside configuration
   and tests.

---

## 2. Core functionality

### 2.1 Functional requirements

Priority: **M** = must have for v1, **S** = should have, **C** = could have.

| ID | Requirement | Priority | Acceptance criterion |
|---|---|---|---|
| FR-01 | Load a lexicon profile from a manifest with checksum verification | M | Tampered manifest fails closed with `SourceIntegrityError` |
| FR-02 | Support lengths 1–5 from configuration | M | Build and solve a 1-, 2-, 3-, 4- and 5-letter profile |
| FR-03 | Separate answer and guess sets, assert `answers ⊆ guesses` | M | Broken fixture raises `ProfileIntegrityError` |
| FR-04 | Compute exact Wordle feedback including duplicate letters | M | Matches reference on exhaustive L ≤ 4; golden suite for L = 5 |
| FR-05 | Accept manually entered feedback in `GYB`, `210` and emoji forms | M | Parser round-trips all three; rejects wrong length/chars with a message |
| FR-06 | Filter candidates by recomputation, not letter rules | M | Candidate set equals brute-force filter on every test state |
| FR-07 | Detect inconsistent feedback histories | M | Reports the offending turn; never empties the set silently |
| FR-08 | Recommend a guess with a score breakdown | M | Breakdown contains entropy, expected remaining, worst case, p(answer) |
| FR-09 | Offer at least 12 selectable strategies | M | Each is registered, documented and benchmarked |
| FR-10 | Hybrid strategy that adapts to candidate count, attempts left and budget | M | Branch chosen is recorded in the decision record |
| FR-11 | Display remaining candidate count and top-N candidates with probabilities | M | Values sum to 1 over the candidate set |
| FR-12 | Explain a recommendation in one or two sentences without ML jargon | M | Explanation generated from the breakdown; no undefined terms |
| FR-13 | Persist game history and allow replay | M | Replay reproduces the exact candidate sets |
| FR-14 | Self-play against the simulator | M | N games, seeded, reproducible |
| FR-15 | Benchmark runs with all required metrics | M | Report contains every metric in the benchmark plan |
| FR-16 | Compare two runs, refusing silent cross-profile comparison | M | Different manifest checksums produce a visible warning |
| FR-17 | Build, verify, inspect and diff lexicon profiles | M | `lex build/verify/inspect/diff` all functional |
| FR-18 | Configure everything via one validated config file | M | Unknown key or bad range fails with the key path |
| FR-19 | CLI `--json` output for every command | S | Stable schema, documented in the technical spec |
| FR-20 | Technical/research mode exposing full score vectors | S | Toggle shows per-candidate partitions and bucket histogram |
| FR-21 | Export benchmark results to CSV and Markdown | S | Deterministic ordering; includes provenance block |
| FR-22 | Hard mode and superhard mode | S | Constraint engine tested against hand-built cases |
| FR-23 | Optional frequency prior with calibration report | S | Prior is refused if log loss is worse than uniform |
| FR-24 | Exact policy artifacts generated offline and loaded at solve time | S | Artifact mismatch fails closed |
| FR-25 | Distilled value model for infeasible profiles | C | Only admitted if it passes the ML gate |
| FR-26 | Optional HTTP adapter over the service layer | C | Contains no solver logic; core tests unaffected |

### 2.2 Dictionary management

- Profiles: `classic`, `strict`, `extended`, `full`, `custom`. Each has a manifest with sources,
  versions, licences, transforms, counts, rejection reasons and checksums.
- The Dictionary Laboratory lists words with filters (length, contains, regex, in-answers-only),
  shows *why* a word was excluded, and diffs two builds.
- User-supplied lists (including the classic profile) are marked `user-supplied`, are never
  bundled, and require an explicit licence attestation flag at import.
- The system never edits a source file in place and never "cleans up" a user list silently.

### 2.3 Word-length selection

Length is a first-class selector, not a hidden default. Choosing L=3 rebuilds the candidate space,
the feedback codec (`3^3 = 27` patterns), the table and the strategy thresholds. The UI states the
length and the profile in the header of every view, because a recommendation without them is
meaningless.

### 2.4 Interactive solving

Flow: choose profile → choose mode → optionally enter a starting guess or ask for one → for each
turn, enter guess + feedback → see recommendation, candidate count, top candidates → repeat until
solved or out of attempts.

The assistant must accept the user's own guess even when it is not the AI's recommendation,
because the user is playing a real game elsewhere. It must accept guesses that are legal but not
in the answer set, and it must say when a guess is not in the allowed guess list at all
(different from "not a possible answer").

### 2.5 Simulation

Self-play runs a strategy against the internal environment over a specified answer set, with
seeded answer selection, per-game guess counts, and a full distribution. Exhaustive mode iterates
every answer in the profile when the strategy's per-game cost allows it; otherwise the run
declares the sample and the sampling method.

### 2.6 Benchmarking

A benchmark run is identified by
`(profile, manifest checksum, rules, prior, attempts, strategy, answer set, seed)`. It reports
average, median, worst case, success rate, failure rate, guess distribution, per-round candidate
reduction, information gained, latency and memory. Failures are listed by answer word, not
folded into an average.

### 2.7 Game history, replay and analysis

Every decision is persisted with its state digest, candidate count, score breakdown and elapsed
time. Replay reconstructs state from history and must reproduce the candidate sets exactly; a
mismatch is a bug report, not a warning.

### 2.8 Strategy selection and explanation

The user picks a strategy by name, or `hybrid.balanced` (default). The explanation is generated
from numbers, for example:

> **SALET** — splits the 2,315 remaining words into 148 groups; the largest has 168. On average it
> leaves 61.2 candidates, and it would win immediately in 0.08% of games. It is not in the answer
> list, so it is a pure information guess.

In technical mode, the same decision also shows the full metric vector, the runner-up, and the
reason the runner-up lost.

---

## 3. User experience

### 3.1 Principles

1. **One recommended word, prominently.** Everything else is supporting evidence.
2. **Plain language first.** "Splits the remaining words into 148 groups" beats "entropy 6.19
   bits" for the default view. Bits appear in technical mode.
3. **Never hide uncertainty.** If 400 candidates remain, say 400 — not "high confidence".
4. **Distinguish the three questions.** Show "possible answer" and "allowed guess" as different
   facts; never imply a guess is plausible just because it is legal.
5. **No dead ends.** If the user's feedback is inconsistent, explain which earlier turn conflicts
   and offer to edit it.

### 3.2 Solver Assistant layout (terminal-first)

```
┌──────────────────────────────────────────────────────────────────────┐
│ Profile classic.en.5 · normal · 6 attempts · prior uniform           │
├──────────────────────────────────────────────────────────────────────┤
│ #1  S A L E T        ⬛🟨⬛⬛🟨   candidates 2,315 → 148             │
│ #2  C R A N E        ⬛⬛🟩⬛⬛   candidates   148 →  11             │
│                                                                      │
│ RECOMMEND  P A L E T   (expected remaining 3.1 candidates)           │
│ Why: keeps all 11 candidates separated; 2 would be solved at once.   │
│                                                                      │
│ Most likely answers   1. crane 18%   2. crave 9%   3. grace 9%        │
│ Next best guesses     trace (3.4) · crate (3.6) · irate (3.7)         │
├──────────────────────────────────────────────────────────────────────┤
│ [enter guess + colours]  [s]uggest  [c]andidates  [t]echnical  [q]uit │
└──────────────────────────────────────────────────────────────────────┘
```

(The figures above are illustrative of the layout, not a benchmark result.)

### 3.3 Information hierarchy

| Tier | Shown by default | Shown in technical mode |
|---|---|---|
| Recommendation | word, expected remaining, one-line reason | full score vector, runner-up delta |
| Candidates | count, top 3 with probabilities | full list, bucket histogram, per-letter constraints |
| Metrics | expected remaining | entropy (bits), worst case, p(solve now), information gain |
| Provenance | profile, mode, attempts | manifest checksum, strategy version, latency, branch taken |

### 3.4 Accessibility and clarity

- Colour is never the only channel: feedback renders as letters `G/Y/B` alongside any colour.
- All output is plain text and screen-reader friendly; no reliance on box-drawing alignment for
  meaning.
- Numbers are formatted consistently (one decimal for guesses, two for probabilities).
- Error messages name the field and the fix.

---

## 4. Application modes

### 4.1 Solver Assistant

User plays elsewhere, enters guesses and feedback. Requirements: manual feedback entry, candidate
filtering, recommendation, explanation, top candidates, inconsistent-history detection, undo of
the last turn, and an option to paste a whole history at once.

### 4.2 Self-Play

The AI plays the internal simulator. Requirements: profile/mode/prior/strategy selection, single
game with a visible trace, N games with aggregate metrics, seeded reproducibility, and optional
answer pinning ("play this specific word").

### 4.3 Strategy Laboratory

Side-by-side comparison of strategies on the same states. Requirements: pick a state (or a set of
answers), run every strategy, show per-strategy scores and the chosen word; run a full benchmark
comparison; show where strategies disagree and which one wins on the eventual game outcome.

### 4.4 Dictionary Laboratory

Requirements: list and search words, filter by length/alphabet/answer-membership, show exclusion
reasons for a word not present, show source and licence per profile, diff two manifests, and
export a filtered list. Read-only with respect to sources.

### 4.5 Benchmark Mode

Requirements: define a run (profile, rules, prior, attempts, strategies, answer set, seed), run it
in parallel, persist it, print a report, export CSV/Markdown, compare two runs, and refuse
silently-incomparable comparisons. Must state sampling when the answer set is not exhaustive.

### 4.6 Future external adapter

A `GamePort` interface (`read_board`, `submit_guess`) can be implemented for another implementation
of the game without touching the solver. v1 ships only the manual and simulated ports; no
automation of a third-party site.

---

## 5. Product requirements by area

### 5.1 Correctness

- Feedback must be exact for repeated letters; the two-pass reservation algorithm is the spec.
- Candidate filtering must be by recomputation.
- Inconsistent histories must be surfaced, with the conflicting turn identified.
- The true answer must never be eliminated by valid feedback (property test).
- Every recommended guess must be legal in the selected mode.

### 5.2 Explainability

- Every decision stores the numbers that produced it.
- The explanation is deterministic given the state (no randomness, no LLM).
- Technical mode can reproduce the decision from the stored breakdown.
- The UI states which branch of the hybrid policy was taken.

### 5.3 Performance

| Operation | Target |
|---|---|
| Recommendation, largest candidate set | ≤ 250 ms |
| Recommendation, endgame (`\|S\| ≤ 50`) | ≤ 2 s with lookahead, ≤ 50 ms without |
| Profile load | ≤ 1 s |
| Self-play throughput | ≥ 50 games/s at `\|S\|` small, ≥ 5 games/s early game `[E]` |
| Memory, classic profile | ≤ 512 MiB total |
| Startup | ≤ 2 s to first prompt |

### 5.4 Reliability

- Deterministic results for identical inputs and seeds.
- No network access during solving.
- Corrupt cache or artifact → clear error, not a wrong answer.
- Interrupted benchmark → resumable or cleanly abandoned with partial results labelled.

### 5.5 Data integrity

- Manifest checksums verified on every load.
- Benchmarks record the profile checksum, config digest and package version.
- Two runs with different checksums cannot be compared without an explicit flag and a warning.

### 5.6 Configurability

Every path, length, alphabet, attempt limit, threshold, budget, strategy weight and prior
parameter is configuration. The shipped `config/default.toml` documents each key.

### 5.7 Extensibility

New language = new profile + normalisation rules. New length = profile + codec widening (L ≥ 6).
New mode = constraint predicate. New strategy = implement the protocol and register it. New UI =
consume `SolverService`.

---

## 6. Out-of-scope behaviours (explicitly refused)

- Recommending a guess that is not in the allowed guess set, even if it "looks" like a word.
- Treating "not a possible answer" as "invalid guess".
- Reporting an average over solved games only.
- Claiming optimality for a heuristic.
- Silently switching profiles or priors when an artifact is missing.
- Using a non-uniform prior without a calibration report.
- Printing ML terminology in the default view.

---

## 7. Release gates

| Gate | Criterion | Evidence |
|---|---|---|
| RG-1 Correctness | Exhaustive feedback equality L ≤ 4; duplicate suite L = 5 | CI test output |
| RG-2 Classic optimum | 3.4212 ± 0.0005, max 5, 0 failures over 2,315 answers | Benchmark report, determinism hash |
| RG-3 Determinism | Identical hashes for 1 vs 16 workers | Two run records |
| RG-4 Multi-length | All five lengths solve with 100% success on their strict profiles | Benchmark table |
| RG-5 Honesty | Failures listed; exactness declared per profile | Report inspection |
| RG-6 Explainability | Every decision has a breakdown and a generated reason | Decision table audit |
| RG-7 Docs | Nine documents consistent with the numbers ledger | Consistency check |
| RG-8 No hidden constants | Config audit: no dictionary path, opener, length or attempt limit outside config/tests | Code search |

---

## 8. Metrics that define product success

| Metric | Definition | Target |
|---|---|---|
| Average guesses (classic) | Mean over all 2,315 answers | 3.4212 ± 0.0005 |
| Worst case (classic) | Max guesses over all answers | 5 |
| Failure rate (classic) | Games not solved within 6 | 0 |
| Average guesses (strict L5) | Mean over 4,444 answers | Report; target ≤ 3.60 `[E]` |
| Success within 6 (all profiles) | Solved / total | ≥ 99.9% |
| Decision latency p95 | Per recommendation | ≤ 250 ms |
| Determinism | Hash equality across worker counts | Exact |
| Explanation coverage | Decisions with a non-empty generated reason | 100% |

Targets marked `[E]` are engineering expectations to be replaced by measured values in Phase 4;
they are not published results and must never be presented as such.

---

## 9. Assumptions and dependencies

- The user can supply the classic Wordle lists if they want the `classic` profile; the product
  works without them using open profiles.
- Python 3.12 and numpy are available; no other runtime service is required.
- CPU-only execution is acceptable; benchmark wall-clock depends on the host.
- Published figures are used as targets, not as claims about this implementation, until
  reproduced by the benchmark harness.
