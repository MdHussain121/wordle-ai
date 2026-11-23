# WORDLE_AI_RISK_REGISTER.md

**Status:** Phase 0 deliverable, revision 1.0 · **Date:** 2026-11-19
**Owner:** project maintainer · **Review cadence:** at every phase gate, and whenever a benchmark
disagrees with a published result

Scoring: **Severity** = combination of likelihood (L) and impact (I), each rated High/Medium/Low.
A risk with High impact and High likelihood is a blocker for its phase; High impact with Medium
likelihood requires a mitigation in place before the phase gate opens.

---

## 1. Summary matrix

| ID | Risk | L | I | Severity |
|---|---|---|---|---|
| R-01 | Dictionary licensing breach | M | H | **High** |
| R-02 | Incomplete or wrong vocabulary | H | M | **High** |
| R-03 | Invalid or obscure words in the answer set | M | M | Medium |
| R-04 | Incorrect repeated-letter feedback | M | H | **High** |
| R-05 | Mis-specified answer priors | M | H | **High** |
| R-06 | Overfitting to the original 2,315 answers | H | M | **High** |
| R-07 | Exact DP computational explosion | H | M | **High** |
| R-08 | Feedback matrix exceeds memory | M | M | Medium |
| R-09 | ML overfitting / no real gain | H | L | Medium |
| R-10 | RL sample inefficiency | H | L | Low |
| R-11 | Benchmark leakage | M | H | **High** |
| R-12 | Hardware dependence | M | M | Medium |
| R-13 | Incorrect hard-mode implementation | H | M | **High** |
| R-14 | External dictionary/rule changes | H | M | **High** |
| R-15 | SCOWL composition misread | M | H | **High** |
| R-16 | Unicode/normalisation corruption | M | H | **High** |
| R-17 | Silent sampling or metric drift in benchmarks | M | H | **High** |
| R-18 | Stale artifact or profile mismatch serving wrong answers | M | H | **High** |

---

## R-01 — Dictionary licensing breach

**Description.** Bundling or redistributing word lists whose licence does not permit it, or
failing to reproduce required notices.
**Likelihood** Medium · **Impact** High (legal exposure, forced removal of data).

**Why it is live.** The classic Wordle lists have no clear open licence. wordfreq's *data* is
CC BY-SA 4.0 even though its code is Apache-2.0, and its README explicitly refuses CSV-style
extraction. SCOWL requires its notice in supporting documentation.

**Mitigation.**
- `data/raw/`, `data/user/`, `data/processed/` are gitignored and never shipped.
- Classic lists are imported only with `--attest-license` and marked `user-supplied`.
- wordfreq is a runtime-only optional dependency; no derived frequency table is committed.
- `THIRD_PARTY_NOTICES.md` reproduces the SCOWL, ENABLE, WordNet and wordfreq notices.
- A release check greps tracked files for word-list content and fails the build on a hit.

**Detection.** CI gate on tracked paths; manual licence review before any published bundle.
**Gate.** Phase 1 (data handling) and Phase 8 (release).

**Residual.** Low, provided no built lexicon is ever published without a notices file.

---

## R-02 — Incomplete or wrong vocabulary

**Description.** A profile silently contains the wrong words: missing dialect spellings, missing
common words, or extra non-words, so results do not describe the game being played.
**Likelihood** High · **Impact** Medium.

**Why it is live and measured.** `english-words` alone omits `color`; the union of every open
source measured covers only 93.73% of the classic allowed guesses, and two classic answers
(`admin`, `cyber`) are absent entirely `[R]`.

**Mitigation.**
- Composition rules encoded in the pipeline, not in a README: incremental level union, and
  `english ∪ dialect` enforced (a neutral-only profile requires an explicit flag and warns).
- Coverage report against the classic lists printed at build time, with the missing words listed.
- Manifests record source ids, level sets and rejection counts; `lex diff` exposes churn.
- Profiles are never silently substituted when files are missing (`ProfileIntegrityError`).

**Detection.** Build-time coverage table; `lex verify`; benchmark header shows the manifest hash.
**Gate.** Phase 1.

**Residual.** Medium for `classic` only, because that list is supplied, not derived.

---

## R-03 — Invalid or obscure words in the answer set

**Description.** The answer set includes archaic, offensive, proper-noun or non-word entries, so
benchmarks reward guessing obscure strings and the assistant recommends words a human would never
use.
**Likelihood** Medium · **Impact** Medium.

**Why it is live.** SCOWL at size 95 is deliberately exhaustive; it includes entries most speakers
would not recognise, and the `full` profile inherits them.

**Mitigation.**
- Answer policy is separate from validity policy (strict/extended/full/classic/custom).
- Default answer policy is `strict`; `full` is opt-in for stress tests only.
- Proper nouns, abbreviations, possessives and non-ASCII are excluded by named rules with counts.
- Benchmark reports state the answer policy, and an "obscure guess rate" metric is recorded when
  the full guess list is used (AB-7), so the cost of obscure play is quantified rather than
  hidden.

**Detection.** AB-7; review of the top recommended words per profile.
**Gate.** Phase 1 and Phase 4.

**Residual.** Low for strict; accepted and disclosed for full.

---

## R-04 — Incorrect repeated-letter feedback

**Description.** Feedback mislabels duplicated letters: too many greens/yellows when the answer has
fewer copies, or a yellow awarded to a copy that should be gray.
**Likelihood** Medium · **Impact** High (every downstream candidate count is wrong; the solver can
eliminate the true answer).

**Why it is live.** It is the most common defect in Wordle implementations, and it is invisible on
most words because duplicates are a minority of cases.

**Mitigation.**
- Two-pass reservation algorithm (greens first, then yellows while unmatched copies remain), with
  the reference implementation as the single definition.
- Golden suite covering: guess with 3 copies vs answer with 1; guess with 1 copy vs answer with 3;
  greens and yellows of the same letter in one guess; all-distinct control cases.
- Exhaustive equality against the reference for L ≤ 4; stratified + duplicate-focused sample for
  L = 5.
- Property test: for valid feedback, the true answer is never eliminated (I1).

**Detection.** CI; any `answer_eliminated_count > 0` in a benchmark is a release blocker.
**Gate.** Phase 1; re-verified in Phase 2 and Phase 4 (RG-1).

**Residual.** Very low.

---

## R-05 — Mis-specified answer priors

**Description.** A frequency prior is treated as the answer distribution without validation, so the
solver optimises for the wrong objective, sometimes lowering the solve rate and always
misstating confidence.
**Likelihood** Medium · **Impact** High.

**Why it is live.** WordleBot uses NYT appearance frequencies `[P]`, and the NYT draws from the
original list more often than from 2023 additions `[P]`; copying that assumption without checking
it against the user's actual play context is easy.

**Mitigation.**
- Uniform is the default; `β = 0` is tested to reproduce uniform decisions exactly.
- A prior is admitted only with a calibration report (log loss better than uniform, ECE < 0.05).
- Prior id and parameters are part of the cache key, the policy artifact key and the run key.
- Calibration uses held-out answers; temperature is fit on validation only.
- The UI never displays a probability without stating the prior behind it.

**Detection.** Calibration report; AB-3; a regression in solve rate under a new prior.
**Gate.** Phase 5.

**Residual.** Low.

---

## R-06 — Overfitting to the original 2,315 answers

**Description.** Design decisions, thresholds, openers and models are tuned against the most
famous, most-optimised word list in the world, producing results that do not transfer.
**Likelihood** High · **Impact** Medium.

**Why it is live.** Nearly all published Wordle analysis uses that list; the project's own
reproduction target is defined on it.

**Mitigation.**
- Multi-profile by construction: strict/extended/full, lengths 1–5.
- The 2023 3,158-answer list and the open `extended` profile are mandatory generalisation checks.
- Thresholds are tuned on the validation profile (strict) and applied unchanged to classic.
- ML splits are by answer word; cross-profile generalisation is an admission criterion.
- No opener, threshold or length is hardcoded (release gate RG-8).

**Detection.** Cross-profile benchmark table; a large gap between classic and extended performance
triggers review.
**Gate.** Phase 4 and Phase 6.

**Residual.** Medium; disclosed rather than eliminated.

---

## R-07 — Exact DP computational explosion

**Description.** The DP does not finish in the planned budget, or exhausts memory, on a profile that
was assumed tractable.
**Likelihood** High · **Impact** Medium (schedule, not correctness).

**Why it is live.** The published exact solution took days on 64 cores `[P]`, and the problem is
NP-hard `[P]`.

**Mitigation.**
- Feasibility gate (`|A| ≤ 5,000`, `|G| ≤ 20,000`, explicit time budget) enforced in code.
- Resumable progress files, checkpointed memo table, LRU cap with eviction.
- Root-level parallelism with deterministic reduction.
- Approximate path (rollout/hybrid) always available, so an unfinished DP blocks a feature, not
  the product.
- Expected-value framing: exactness is a bonus where affordable, not a promise everywhere.

**Detection.** Measured runtime table from Phase 3; a job exceeding 24 h triggers the gate review.
**Gate.** Phase 3.

**Residual.** Medium for untested profiles; explicitly marked infeasible rather than attempted
blindly.

---

## R-08 — Feedback matrix exceeds memory

**Description.** Precomputing a `|G| × |A|` `uint8` table for a large profile exhausts RAM or
thrashes.
**Likelihood** Medium · **Impact** Medium.

**Why it is live and measured.** Classic is 28.64 MiB, extended L=5 is 124.18 MiB, full L=5 is
289.07 MiB `[R]`; a naive "precompute everything" policy scales quadratically and will not hold on
a small machine.

**Mitigation.**
- Three policies: full, hybrid (rows on demand + LRU), none; chosen by `table_max_bytes`.
- memmap for large tables; row cache sized in config.
- Profile load reports the planned footprint before building.
- Benchmark records peak RSS, so regressions are visible.

**Detection.** Peak RSS metric; a build that exceeds the budget aborts with a clear message.
**Gate.** Phase 1 and Phase 8.

**Residual.** Low.

---

## R-09 — ML overfitting / no real gain

**Description.** A learned ranker or distilled value model improves the training distribution and
degrades elsewhere, or improves nothing while adding latency and complexity.
**Likelihood** High · **Impact** Low–Medium (a rejected model costs time, not correctness).

**Mitigation.**
- Numeric admission gate: ≥ 0.02 average improvement, no worst-case or failure regression,
  ≤ 5 ms added latency, no cross-profile regression, calibration required for probabilities.
- Splits by answer word; leakage test.
- Analytic path remains the default; ML is `ml.enabled = false` unless admitted.
- A rejected model is reported as a successful experiment.

**Detection.** Gate report; AB-8/AB-9; cross-profile run.
**Gate.** Phase 6.

**Residual.** Low, because rejection is cheap and expected.

---

## R-10 — RL sample inefficiency

**Description.** RL consumes large compute for a policy worse than the heuristic, delaying the
project.
**Likelihood** High · **Impact** Low (research-only, capped).

**Why it is live.** Published PPO reaches ~97–98% at 4.3 average under a weaker win condition,
while behaviour cloning of a greedy policy reaches 99.8% at 4.04, and the exact optimum is 3.4212
`[P]`.

**Mitigation.**
- RL is explicitly out of the product path and capped at two weeks (Phase 6).
- Baselines are the heuristic and the exact policy, never random play.
- The environment and reward are specified in advance so the experiment is reproducible.
- Stop rule: if no improvement over the heuristic by the cap, publish the negative result.

**Detection.** Phase 6 gate report.
**Gate.** Phase 6.

**Residual.** None to the product; schedule risk only, bounded.

---

## R-11 — Benchmark leakage

**Description.** Test answers appear in training data, thresholds are tuned on the test set, or
sampled results are reported as exhaustive — inflating results.
**Likelihood** Medium · **Impact** High (invalidates every claim).

**Mitigation.**
- Split by answer word, asserted in a test.
- Validation/test separation; number of test evaluations logged.
- Every report row labelled `exhaustive` or `sampled`; sampling never silent.
- `tuned` runs labelled and not compared to `untuned` without disclosure.
- Determinism hash and per-game CSV make aggregates recomputable by a reviewer.

**Detection.** `tests/ml/test_leakage.py`; report audit; CSV regeneration test.
**Gate.** Phase 4 and Phase 6.

**Residual.** Low.

---

## R-12 — Hardware dependence

**Description.** Results or runtime depend on core count, memory or a specific machine, so published
numbers cannot be reproduced.
**Likelihood** Medium · **Impact** Medium.

**Mitigation.**
- Decision results must be hardware-independent; only latency varies.
- Determinism hash required to match across worker counts.
- Runtime reported with CPU model, core count and memory; estimates labelled `[E]`.
- Memory budgets enforced so a 512 MiB machine can run the strict profile.
- No GPU, no vectorisation that changes results (vectorised and reference paths are tested equal).

**Detection.** 1-vs-16-worker determinism run (B-12); RSS metric.
**Gate.** Phase 4 and Phase 8.

**Residual.** Low.

---

## R-13 — Incorrect hard-mode implementation

**Description.** Hard mode is implemented as "must contain green and yellow letters", which is
wrong for duplicates and can make the game unwinnable or illegally restrictive; or the three
rule interpretations are conflated.
**Likelihood** High · **Impact** Medium.

**Why it is live.** Even the published literature distinguishes NYT hard mode from "superhard"
(guess must be a candidate) and shows different optima for each `[P]`; a naive gray-letter ban also
breaks when a letter has both green and gray feedback.

**Mitigation.**
- Three explicit modes (`normal`, `hard`, `superhard`) with distinct constraint predicates.
- Duplicates expressed as minimum/maximum multiplicity derived from history through the feedback
  function, not as per-letter bans.
- Constraint derivation tested against hand-built duplicate cases and exhaustively at depth 2.
- Published hard-mode targets (3.5084; `palet` max-5; `scamp` 3.7162 superhard) used as checks.
- Invalid-guess and mode-violation counts are benchmark metrics that must be zero.

**Detection.** `mode_violation_count`; constraint unit tests; AB-11.
**Gate.** Phase 2 and Phase 4.

**Residual.** Low after testing; Medium if only one mode were implemented, which is why all three
ship.

---

## R-14 — External dictionary and rule changes

**Description.** The reference game changes its answer list, guess list, attempt rules or hard-mode
definition; the project's "classic" profile drifts from the live game.
**Likelihood** High · **Impact** Medium.

**Why it is live.** Documented churn: 2,315 → 2,309 answers, guess list 12,972 → 14,855, answers
3,158, optimal opener `salet` → `tarse` `[P]`.

**Mitigation.**
- Profiles are versioned by manifest checksum; every result names its profile.
- Sources are pinned in `sources.lock`; `lex diff` reports churn explicitly.
- No claim of "current Wordle" anywhere in the product; claims are scoped to a profile.
- New lists become new profiles; old benchmarks remain reproducible.
- The assistant labels the profile in its header, always.

**Detection.** `lex diff`; coverage report at build time.
**Gate.** Continuous; re-checked each phase.

**Residual.** Accepted by design.

---

## R-15 — SCOWL composition misread

**Description.** The build treats per-size SCOWL files as complete lists, or uses `english-words`
without a dialect, producing a profile that is missing thousands of ordinary words.
**Likelihood** Medium · **Impact** High.

**Why it is live and measured.** Level files are incremental (level 80 contains 139,207 new
entries, not the whole list) and `english-words` omits `color` entirely; the neutral-only reading
undercounts 5-letter words by 176 entries and loses dialect spellings wholesale `[R]`.

**Mitigation.**
- The union and dialect rules are encoded in `scowl_union(categories, upto)`, documented in the
  dataset plan, and covered by a test asserting `color` is present in an American profile and
  absent from a neutral one.
- The size ladder and both compositions are recorded in the manifest and printed at build time.
- A coverage check against the classic answer list runs on every build.

**Detection.** Build-time coverage table; `tests/lexicon/test_scowl_composition.py`.
**Gate.** Phase 1.

**Residual.** Low.

---

## R-16 — Unicode/normalisation corruption

**Description.** Accented words are transliterated silently, combining marks change length, or
multi-code-point graphemes are counted as multiple characters — corrupting the lexicon or the
length rule.
**Likelihood** Medium · **Impact** High (silent data corruption, and a broken premise for any
future language).

**Why it is live.** SCOWL is Latin-1 with 948 non-ASCII entries `[R]`; a UTF-8-only loader crashes
on it (observed during the spike), and a naive `len()` counts code points, not user-perceived
characters.

**Mitigation.**
- Explicit policy: decode with recorded fallback, NFC, casefold, grapheme-cluster length, alphabet
  filter, **no silent transliteration** (opt-in transform, recorded in the manifest).
- `café` is rejected for English L=4, not rewritten to `cafe`.
- Tests for combining marks, emoji, ZWJ sequences, BOM, CRLF and lone surrogates.
- The length rule is parameterised by alphabet, so a future non-Latin profile is not broken.

**Detection.** `tests/unit/test_normalize.py`; manifest rejection counts.
**Gate.** Phase 1.

**Residual.** Low.

---

## R-17 — Silent sampling or metric drift

**Description.** A benchmark reports sampled results as exhaustive, or the code's metric definition
diverges from the documented one, so two reports are not comparable.
**Likelihood** Medium · **Impact** High (invalidates comparisons and release gates).

**Mitigation.**
- `exhaustive|sampled` is a mandatory column and a mandatory field in every aggregate.
- Metric formulas are specified in the benchmark plan and implemented once, with hand-computed
  fixture tests.
- The CSV export must regenerate every aggregate within rounding (tested).
- Reports carry the run key and determinism hash; `bench compare` refuses mismatched profiles
  without a flag.

**Detection.** Fixture tests; CSV regeneration test; report review at each gate.
**Gate.** Phase 4.

**Residual.** Low.

---

## R-18 — Stale artifact or profile mismatch

**Description.** A cached policy, feedback table or lexicon from an older profile is loaded and
produces confident but wrong recommendations.
**Likelihood** Medium · **Impact** High.

**Mitigation.**
- Every artifact stores and verifies `profile_sha256`, `rules`, `prior`, `attempts` and its own
  checksum; mismatch raises `ArtifactMismatchError` and never falls back silently.
- Cache keys include all of those dimensions.
- `diagnose` reports stale artifacts with a distinct message.
- A tamper test deliberately corrupts an artifact and asserts the failure.

**Detection.** `diagnose`; tamper tests; benchmark header mismatch.
**Gate.** Phase 3 and Phase 8.

**Residual.** Low.

---

## 2. Cross-cutting controls

| Control | Guards |
|---|---|
| Profile manifest checksum in every run key | R-02, R-14, R-18 |
| Two-pass feedback + exhaustive equality | R-04 |
| `answers ⊆ guesses` assertion | R-02, R-04 |
| Numeric gates (calibration, ML) | R-05, R-09 |
| Determinism hash across worker counts | R-12, R-17 |
| Mandatory exhaustive/sampled label | R-11, R-17 |
| Gitignore + notices + tracked-file scan | R-01 |
| Feasibility gate + budget | R-07, R-08 |
| Three explicit rule modes | R-13 |

## 3. Review procedure

1. At every phase gate, each risk's likelihood is re-scored against what the phase actually
   measured, and any new risk discovered is appended with an id.
2. A risk whose severity rises to High blocks the gate until its mitigation is implemented and
   demonstrated.
3. Closed risks stay in the register with a "closed by" note and the evidence; they are not
   deleted, because the conditions can return (R-14 in particular).
4. The release report includes the register's open High risks and the evidence that each
   mitigation is in place.
