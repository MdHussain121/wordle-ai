# WORDLE_AI_BENCHMARK_PLAN.md

**Status:** Phase 0 deliverable, revision 1.0 · **Date:** 2026-11-19
**Implements:** PRD §7–8; research report §4–7, §14
**Consumed by:** `wordle-ai bench *` commands (technical spec §10)

---

## 1. Purpose

A benchmark whose numbers cannot be trusted is worse than no benchmark, because it launders
guesses into claims. This plan fixes four things in advance: **what** is measured, **on which
data**, **with what exclusions**, and **how two runs may be compared**. Every published figure
this project intends to reproduce is named with its source configuration, so a discrepancy can be
diagnosed rather than argued about.

Three rules govern everything below:

1. **Failures are data.** A game that exceeds the attempt limit is a failure with a recorded
   guess sequence. It is never dropped from the denominator.
2. **A number is meaningless without its tuple.** Every result carries
   `(profile_id, manifest_sha256, rules, prior, attempts, strategy_version, answer_set, seed)`.
3. **Exhaustive where feasible, sampled where not, and always labelled.** No table mixes the two
   without a column saying which.

---

## 2. Run identity and provenance

```
run_key = sha256(
    profile_id, manifest_sha256, rules, prior_kind, prior_params,
    attempts, strategy_id, strategy_version, answer_set_id, seed,
    package_version, config_digest
)
```

Stored with each run: Python and numpy versions, CPU model and core count, OS, wall-clock start
and end, peak RSS, and the artifact checksums used (feedback table, exact policy). Two runs are
**comparable** only if `profile_id`, `manifest_sha256`, `rules`, `prior`, `attempts` and
`answer_set_id` match. `bench compare` prints a hard warning and requires `--allow-mismatch` when
they do not; the report then labels the comparison as informal.

**Determinism hash.**

```
determinism_sha256 = sha256( "\n".join(sorted(f"{answer}\t{n_guesses}\t{','.join(guesses)}")) )
```

over all games in the run. This hash is the primary evidence for reproducibility across worker
counts and machines. It must match exactly for the same run key.

---

## 3. Answer sets

| Answer-set id | Contents | Use |
|---|---|---|
| `classic.all` | the 2,315 user-supplied classic answers | reference reproduction |
| `classic.nytv20230701` | the 3,158-answer list, if supplied | distribution-shift check |
| `strict.en.L.all` | the full strict answer list for length L (4,444 at L=5 `[R]`) | primary multi-length benchmark |
| `extended.en.L.all` | 11,411 at L=5 `[R]` | coverage benchmark |
| `full.en.L.all` | 17,410 at L=5 `[R]` | stress benchmark |
| `stress.duplicates` | hand-built answers maximising repeated letters (e.g. patterns with 2–3 copies) | adversarial correctness |
| `sample.<profile>.<n>.<seed>` | stratified sample, see §3.2 | when exhaustive is too expensive |

### 3.1 Exhaustive-first policy

A run is exhaustive when `\|answers\| × cost_per_game ≤ time_budget` (default 30 minutes wall-clock
at the configured worker count) **and** `\|answers\| ≤ 20,000`. Otherwise it is sampled and the
report states `sampled` in the header and in every aggregate row. Silent sampling is a defect.

### 3.2 Sampling method

Stratified by first two letters and by answer-list origin (original vs expanded, when known), with
proportional allocation and a fixed seed. Minimum 2,000 answers or 10% of the set, whichever is
larger, capped at 20,000. Report: sample size, population size, seed, strata counts, and a 95%
bootstrap interval on every headline metric. A sampled result may never be described as
"all answers".

### 3.3 Adversarial subsets

These are always run in addition to the main set, never instead of it:

- **Repeated-letter answers** (e.g. `abbey`, `sassy`, `eerie`-style patterns): all such answers in
  the profile.
- **Late-branch answers**: the 50 answers with the highest per-answer cost under the reference
  strategy, chosen on a training split only (see §8).
- **Unknown-word answers**: answers present in the answer list but not in the guess list of a
  *different* profile (tests hard-mode and fallback paths).

---

## 4. Metric definitions

Let a run contain games `i = 1..N`, with `n_i` guesses used, `solved_i ∈ {0,1}`, and `K` the
attempt limit. All formulas are implemented in `src/wordle_ai/bench/metrics.py` with fixture tests
using hand-computed values.

### 4.1 Core outcome metrics

| Metric | Definition | Notes |
|---|---|---|
| `avg_guesses_solved` | `Σ n_i · solved_i / Σ solved_i` | comparable to published 3.4212 |
| `avg_guesses_all` | `Σ (n_i if solved else K+1) / N` | conservative; penalises failures |
| `median_guesses` | median of `n_i` over solved games | report with count |
| `worst_case` | `max n_i` over solved games | plus `worst_case_answer` |
| `success_rate` | `Σ solved_i / N` | denominator includes failures |
| `failure_rate` | `1 − success_rate` | failures listed by answer |
| `distribution` | counts of solved games at 1,2,…,K guesses, plus `failed` | must sum to N |
| `pct_solved_in_k` | `count(n_i ≤ k and solved) / N` for k = 1..K | N in denominator |

The report prints both `avg_guesses_solved` and `avg_guesses_all` for every strategy. Presenting
only the first is the most common way benchmarks flatter a solver; the PRD forbids it.

### 4.2 Efficiency metrics

| Metric | Definition |
|---|---|
| `decision_p50_ms`, `decision_p95_ms`, `decision_max_ms` | per recommendation, excluding I/O and reporting |
| `total_sim_time_s` | wall clock for the whole run |
| `peak_rss_mib` | peak resident memory of the process pool |
| `candidates_before/after` | per turn, from the decision record |
| `candidate_reduction_mean` | mean of `\|S_t\| / \|S_{t−1}\|` over turns and games |
| `candidate_reduction_geomean` | geometric mean, less sensitive to tiny late-game sets |
| `information_gain_bits` | mean of `log2(\|S_{t−1}\|) − log2(\|S_t\|)` under uniform prior |
| `information_gain_weighted` | mean of `H(π_{t−1}) − H(π_t)` under the run's prior |
| `per_round_reduction` | table of mean reduction by turn number (1..K) |

`information_gain_bits` and `information_gain_weighted` are reported separately because they
answer different questions: how much the candidate set shrank, versus how much uncertainty
(under the prior) was resolved.

### 4.3 Correctness metrics

| Metric | Definition | Target |
|---|---|---|
| `invalid_guess_count` | recommendations not in the allowed guess set | 0 |
| `mode_violation_count` | recommendations violating hard/superhard constraints | 0 |
| `inconsistent_history_count` | histories that emptied the candidate set during simulation | 0 |
| `answer_eliminated_count` | times the true answer left the candidate set | 0 |
| `feedback_mismatch_count` | table vs reference disagreements | 0 |
| `determinism_sha256` | §2 | stable per run key |

### 4.4 Calibration metrics (probabilistic components)

Applied to any component that emits a distribution over answers (priors, learned rankers, value
models), evaluated on held-out answers, never on training states:

| Metric | Definition |
|---|---|
| `log_loss` | `−mean(log π_i(a*_i))` at the start of each game |
| `brier` | `mean Σ_a (π_i(a) − 1[a = a*_i])²` |
| `ece` | expected calibration error over 10 equal-mass bins of predicted probability for the true answer |
| `reliability_curve` | predicted vs empirical frequency per bin, exported as CSV |
| `top_k_hit_rate` | fraction of games where the true answer is in the top-k of the prior, k = 1, 10, 100 |

A prior is **admitted** only if its log loss on held-out answers is strictly better than uniform's
and its ECE is below 0.05. Otherwise it is rejected and the run uses uniform.

### 4.5 Statistical treatment

- Paired comparison by answer word (same answer set, same seed) with 10,000 bootstrap resamples
  for the mean difference in guesses; report the 95% interval.
- Two strategies' solve/fail outcomes compared with McNemar's test when both have failures.
- Guess-count differences compared with the Wilcoxon signed-rank test; report effect size (median
  difference and rank-biserial correlation).
- Never report a difference smaller than the bootstrap interval as an improvement, regardless of
  its sign.

---

## 5. Benchmark profiles and matrix

### 5.1 Strategy matrix (all against the same answer set)

`random_valid`, `first_candidate`, `letter_frequency`, `positional_frequency`,
`expected_remaining`, `minimax`, `entropy`, `weighted_entropy`, `bayes_cost`, `lookahead`,
`rollout`, `exact`, `hybrid.balanced`.

### 5.2 Configuration matrix

| Dimension | Values | Notes |
|---|---|---|
| Profile | classic, strict, extended, full | each at L = 1..5 where defined |
| Rules | normal, hard, superhard | hard modes on classic + strict at minimum |
| Prior | uniform, zipf (β calibrated) | zipf requires the calibration gate to pass |
| Attempts | 6 for L = 5; 4 for L = 3–4; 3 for L = 1–2 | configurable; recorded |
| Answer set | exhaustive or sampled per §3 | labelled in every row |
| Workers | 1 and 16 | determinism proof |

Not every cell is run for every release; the required set is in §9. The matrix exists so that a
missing cell is a visible decision rather than an accident.

### 5.3 Expected cost `[E]`

Classic exhaustive with the exact policy: 2,315 games × ~1 ms per lookup ≈ seconds. Classic with
`entropy` and full-table scoring: estimated 12 minutes single-core `[E]`; **measured 2026-11-20 at
21.5 s** with the vectorised partition statistics (§13), because the estimate assumed one Python
scoring call per guess per turn rather than one chunked numpy pass over the whole table.
Rollout in the endgame dominates; early-game rollout is disabled by the hybrid policy. The full
L=5 extended matrix (11,411 answers × 13 strategies) is a multi-hour job and is scheduled, not
interactive.

---

## 6. Published reproduction protocol

Each row is reproduced with the exact configuration named in the source, then compared.

| Target | Configuration | Expected | Source |
|---|---|---|---|
| Normal-mode optimum | 2,315 answers, 12,972 guesses, uniform, 6 attempts, exact | 3.4212, max 5, opener `salet` | Selby 2022; Bertsimas & Paskov 2025 `[P]` |
| Independent optimality | same | total 7,920 | Cunanan & Thielscher 2023 `[P]` |
| Hard-mode optimum | same lists, NYT hard rules | 3.5084 | Selby 2022 `[P]` |
| Superhard optimum | guesses restricted to candidates, 2,315 | `scamp`, 3.7162, max 5 | Greenberg 2024 `[P]` |
| Bin-count heuristic | guesses restricted to 2,315 answers | 3.4600, max 6 | Greenberg 2024 `[P]` |
| Entropy heuristic | same restriction, `raise` | 3.4955, max 6 | Greenberg 2024 `[P]` |
| Max-entropy solver | full 12,972 guess list, `soare` | 3.476, max 6 | Luebeck, as tabulated `[P]` |
| Ad-hoc letter heuristic | full guess list, `soare` | 3.65, max 6 | Das, as tabulated `[P]` |
| 2023 configuration | 3,158 answers, 14,855 guesses, exact | 3.5526, opener `tarse` | Selby part 3; wordle-opt `[P]` |

**Discrepancy protocol.** If a reproduced number differs, the report must state, in order:

1. the observed value and its bootstrap interval;
2. the profile manifest checksum and whether the lists match the source's (most discrepancies are
   list differences — see the 2,315 vs 2,309 vs 3,158 churn);
3. the rule interpretation (hard vs superhard; whether a guess must be a candidate);
4. the tie-breaking and prior;
5. whether the strategy is exact or approximate, and which bound applies.

Only after those are excluded may the implementation be suspected. "Our number is better" is not
an acceptable entry in this section.

---

## 7. Ablation studies

Each ablation changes exactly one thing and holds profile, rules, prior and answer set fixed.

| ID | Ablation | What varies | What is fixed | Metric |
|---|---|---|---|---|
| AB-1 | Objective | entropy vs expected-remaining vs bin-count vs minimax | guesses = candidates only | avg, max, distribution |
| AB-2 | Entropy term | composite with vs without entropy tie-break | same primary objective | avg (expect small, report honestly) |
| AB-3 | Frequency prior | uniform vs calibrated Zipf | same strategy | avg, log loss, ECE |
| AB-4 | Bayesian weighting | unweighted vs posterior-weighted scores | same candidate set | avg, max |
| AB-5 | Lookahead depth | one-step vs two-ply vs rollout | same shortlist and budget | avg, latency |
| AB-6 | Escalation threshold | lookahead at `\|S\| ≤ 25/50/100` | same strategy | avg vs p95 latency curve |
| AB-7 | Guess-set breadth | candidates-only vs full guess list | same answer set | avg, max, and "obscure word rate" |
| AB-8 | ML ranker | analytic vs GBDT-ranked shortlist | same features available | avg, latency, gate pass/fail |
| AB-9 | Distilled value model | no model vs model for infeasible profile | same profile | avg, max, cross-profile generalisation |
| AB-10 | RL policy (research) | heuristic vs PPO vs BC | same environment | avg, success, sample cost |
| AB-11 | Hard-mode engine | constraint filter on/off | same answers | invalid-guess count, avg |
| AB-12 | Table strategy | full vs hybrid vs on-demand | same strategy | latency, RSS, identical decisions |

**Reporting rule.** An ablation that shows no improvement is reported as a negative result. AB-2
in particular is expected to be small; the honest outcome may be "entropy tie-break made no
measurable difference on this profile", and that is a valid finding, not a failure.

---

## 8. Leakage prevention

Benchmarks of adaptive systems leak in four ways. Each has a mechanical guard:

1. **Answer leakage into ML training.** Training states are generated only from answers in the
   training split; the split is by *answer word*, never by game state, seed or date. A test
   asserts the intersection of answer sets is empty.
2. **Hyperparameter tuning on test.** Tuning uses a validation split; the test split is evaluated
   once per release, and the number of evaluations is logged.
3. **Threshold fitting to the benchmark.** Escalation thresholds and shortlist sizes are chosen on
   the validation profile (strict) and then applied unchanged to classic. A run that re-tunes per
   answer set is labelled `tuned` and cannot be compared to `untuned` without that label.
4. **Public-list overfitting.** The classic 2,315-answer list is public and has been optimised
   against for years. Generalisation is therefore also measured on the 2023 3,158-answer list and
   on the open `extended` profile, where the answers were not the target of published tuning.

---

## 9. Required benchmark set per release

| # | Run | Answers | Purpose |
|---|---|---|---|
| B-01 | classic / normal / uniform / exact | 2,315 | RG-2 optimum reproduction |
| B-02 | classic / normal / uniform / hybrid | 2,315 | default-policy quality |
| B-03 | classic / normal / uniform / entropy + expected_remaining + minimax | 2,315 | primary ablations AB-1 |
| B-04 | classic / hard / uniform / hybrid | 2,315 | hard-mode behaviour |
| B-05 | classic / superhard / uniform / hybrid | 2,315 | constraint engine |
| B-06 | strict.en.{1..5} / normal / uniform / hybrid | all | multi-length gate RG-4 |
| B-07 | extended.en.5 / normal / uniform / hybrid | sampled | coverage and latency |
| B-08 | full.en.5 / normal / uniform / hybrid | sampled | stress |
| B-09 | classic / normal / zipf / hybrid | 2,315 | AB-3, with calibration report |
| B-10 | strict.en.5 / normal / uniform / lookahead, rollout | all | AB-5/AB-6 |
| B-11 | duplicate-letter adversarial subsets | all such | correctness |
| B-12 | determinism re-run at 1 and 16 workers | B-01, B-02 | RG-3 |

---

## 10. Report format

Every report begins with a provenance block and then a results table. Failures appear as their own
section, never inside an average.

```
RUN 2026-11-19T12:00:00Z  profile=classic.en.5  manifest=sha256:…  rules=normal
prior=uniform attempts=6  strategy=exact  answers=classic.all (2,315, exhaustive)
python=3.12.10 numpy=…  cpu=…x16  peak_rss=…  wall=…

strategy            avg_solved  avg_all  median  worst  success  p95_ms  det_hash
exact               3.4212      3.4212   3       5      100.0%   …
hybrid.balanced     …           …        …       …      …        …
entropy             …           …        …       …      …        …

distribution       1     2      3      4      5      6    failed
exact              0     …      …      …      …      0    0

failures
  (none)

comparison vs published
  exact: 3.4212 vs 3.4212 (Δ 0.0000, CI [−0.0000, +0.0000]) — reproduced
```

CSV export contains one row per game: `run_id, answer, guesses, n_guesses, solved, elapsed_ms,
final_candidates, opener`. This is the artifact reviewers should ask for, because it makes every
aggregate recomputable.

---

## 11. Reproducibility commands

Phase 2 implemented the harness form of the first `bench run`; Phase 4 completed the surface. `bench
run` now takes `--strategies`, `--mode`, `--max-attempts`, `--prior`, `--limit`, `--feedback`,
`--policy`, `--workers`, `--seed`, `--store`, `--time-budget`, `--no-store` and `--json`; `bench
report` renders Markdown, CSV or JSON from the store; `bench compare` refuses mismatched provenance
and can assert determinism. The matrix as a whole is driven by `tools/measure_phase4.py`, which owns
matrix expansion, resume and the budget guard through `bench/runner.py`.

```bash
# environment and config
wordle-ai config validate --config config/default.toml

# data
wordle-ai lex fetch --source scowl --dest data/raw
wordle-ai lex fetch --source enable --dest data/raw
wordle-ai lex build --profile classic.en.5 --answers data/user/classic_answers.txt \
                    --guesses data/user/classic_guesses.txt --attest-license
wordle-ai lex verify --all

# tables and policies
wordle-ai table build --profile classic.en.5
wordle-ai policy build --profile classic.en.5 --strategy exact
wordle-ai policy verify --profile classic.en.5

# benchmarks
wordle-ai bench run --profile classic.en.5 --rules normal --prior uniform \
                    --strategy exact --answers all --workers 16 --seed 20261119
wordle-ai bench run --profile classic.en.5 --rules normal --prior uniform \
                    --strategy all --answers all --workers 16
wordle-ai bench report --run <run_id> --format markdown
wordle-ai bench compare --run <A> --run <B> --metric avg_guesses_solved

# determinism
wordle-ai bench run --profile classic.en.5 --strategy exact --answers all --workers 1
wordle-ai bench compare --run <16w> --run <1w> --check-determinism
```

Every command prints a one-line machine-readable summary with `--json`, including the run key and
determinism hash.

---

## 12. Benchmark acceptance criteria

1. B-01 reproduces 3.4212 ± 0.0005 with worst case 5 and zero failures, and the opener matches the
   list-specific published optimum.
2. B-12 produces identical determinism hashes at 1 and 16 workers.
3. Every report contains both `avg_guesses_solved` and `avg_guesses_all`, a distribution, and a
   failure section (possibly empty, explicitly marked).
4. No aggregate row is printed without its answer-set id and exhaustive/sampled label.
5. AB-1 through AB-6 are run for the release and reported, including negative results.
6. The CSV export can regenerate every aggregate in the Markdown report to within rounding; a test
   asserts this.
7. Any discrepancy against §6 names the manifest checksum and the rule interpretation before
   blaming the implementation.

---

## 13. Phase 2 measured baseline — 2026-11-20

First honest internal leaderboard, produced by the Phase 2 harness on the shipped classic profile
(manifest `5127f7ba9eac90acfb371fc87f50e06c84d6afc20bfeadcf1c9c046f3e5786cf`, 2,315 answers /
12,972 guesses, normal mode, 6 attempts, uniform prior). Exhaustive over all answers; no sampling.

```
python -m wordle_ai.cli.main bench run --profile classic.en.5 --strategies all
```

| Strategy | Objective | avg solved | avg all | max | fail % | histogram 1–6 |
|---|---|---|---|---|---|---|
| `entropy` | maximise information gain | 3.6380 | 3.6380 | 6 | 0.00 | 0/22/896/1296/100/1 |
| `entropy_candidates` | information gain, answers as guesses | 3.5810 | 3.5987 | 6 | 0.52 | 1/131/999/919/207/46 |
| `expected_remaining` | minimise Σ p_r·\|S_r\| | 3.6536 | 3.6536 | 5 | 0.00 | 0/27/819/1398/71/0 |
| `expected_remaining_candidates` | Σ p_r·\|S_r\|, answers as guesses | 3.6017 | 3.6238 | 6 | 0.65 | 1/131/957/946/224/41 |
| `first_candidate` | lowest-index candidate | 4.2747 | 4.3430 | 6 | 2.51 | 1/56/407/861/722/210 |
| `hybrid.balanced` | expected cost + endgame branches | 3.6536 | 3.6536 | 5 | 0.00 | 0/27/819/1398/71/0 |
| `letter_frequency` | candidate letter share | 4.0114 | 4.0462 | 6 | 1.17 | 0/59/555/1064/521/89 |
| `minimax` | minimise largest bucket | 3.7024 | 3.7024 | 5 | 0.00 | 1/32/734/1436/112/0 |
| `minimax_candidates` | largest bucket, answers as guesses | 3.6262 | 3.6467 | 6 | 0.60 | 1/131/910/990/223/46 |
| `positional_frequency` | candidate position share | 3.8514 | 3.8976 | 6 | 1.47 | 0/96/682/1039/393/71 |

**Cost.** 4 m 24 s wall clock for all ten strategies (sum of the printed per-strategy times),
single process, 16-core Windows host; per strategy 15.6–36.0 s. The candidate-only strategies are
cheaper because they score 2,315 rows instead of 12,972.

**Reproducibility.** The printed table was captured twice and diffed byte-identically. Every
strategy's determinism hash (`sha256` over sorted `answer\tn\tguesses` lines) matched across runs;
`--json` reproduces the same numbers, differing only in timing fields. No strategy uses an RNG, so
worker count — when Phase 4 adds it — cannot change outcomes.

**Comparison with §6 targets, and the honest gaps.**

| Target | Corpus | Measured | Difference |
|---|---|---|---|
| Max-entropy, full guess list | 3.476 | **3.6380** | +0.1620 |
| Entropy, answers as guesses | 3.4955 | **3.5810** | +0.0855 |
| Bins, answers as guesses | 3.4600 | **3.6017** | +0.1417 |

All three are listed with their manifest checksum in the roadmap's Phase 2 gate. The lists and
rules match the sources, so the gap is policy: this phase breaks entropy ties by expected remaining
and switches to a candidate only with two turns left, with no two-ply or rollout endgame. The
corpus ordering (bins better than entropy) is **not** reproduced here — entropy is better by 0.0156
full-list and 0.0207 candidates-only. That is a negative result for this policy, not a revision of
the published figures; AB-1 is therefore only partially answered until Phase 3–4 add the exact
policy and the lookahead escalation.

**Hard-mode check (B-04 analogue).** The same harness with `--mode hard` over all 2,315 answers:
`entropy` 3.6652 solved (max 6, 0.52% unsolved), `hybrid.balanced` 3.6674 (max 6, 0.39%),
`minimax` 3.7104 (max 6, 0.65%). Every recommendation was checked against the constraint derived
from that game's own feedback, with zero violations raised by the harness. Hard mode costs about
0.03 guesses over normal for the same strategy; the published hard optimum is 3.5084, which needs
the Phase 3 exact policy.

The JSON artifact for this run is `data/bench/baseline_classic.json` (not tracked; `data/` is
ignored), and the two captured text tables are `data/bench/baseline_run{1,2}.txt`.

---

## 14. Phase 3 measured exact-solver boundary — 2026-11-20

The exact kernel is measured, not assumed. Reproduce with:

```
python tools/measure_exact.py --budget-seconds 120
# or, for the one solved case, through the product surface:
python -m wordle_ai.cli.main policy build --profile strict.en.3 --limit 12 \
    --out data/exact/subset12.policy.json
python -m wordle_ai.cli.main policy verify --path data/exact/subset12.policy.json \
    --profile strict.en.3 --limit 12
```

Every row is the outcome of a real solve attempt on the 16-core Windows host; `budget` means the
wall-clock budget expired and the node count is what was reached, not an extrapolation.

| Case | Answers | Guesses | K | Outcome | Nodes | Guess evaluations | Time |
|---|---|---|---|---|---|---|---|
| `strict.en.2` | 65 | 65 | 6 | budget; no 6-guess guarantee (proved separately in ~128 s) | 79,840 | 5,189,749 | 120 s |
| `strict.en.3` first 12 answers | 12 | 588 | 6 | solved: 2.5833 avg, max 4 | 2,044 | 1,201,872 | 28.3 s |
| `strict.en.3` first 40 answers | 40 | 588 | 6 | budget | 8,864 | 5,212,327 | 120 s |
| `strict.en.3`, candidates only | 588 | 588 | 6 | budget | 99,840 | 4,123,824 | 120 s |
| `strict.en.3`, all guesses | 588 | 588 | 6 | budget | 8,288 | 4,873,916 | 120 s |
| `classic.en.5` | 2,315 | 12,972 | 6 | budget | 544 | 7,056,993 | 127 s |

The classic row is the one that matters for B-01: at ≈4.3 nodes/s the pure-Python kernel cannot
reach a full solve in a session, so **3.4212 is not reproduced and is not claimed**. The
`|A| ≤ 5000, |G| ≤ 20000` feasibility gate is a necessary condition only; it does not predict
runtime. A compiled kernel (Phase 8's Rust option) or an external exact solver is required before
B-01 can produce a number.

Policy lookup itself is well inside budget. A 12-answer artifact (2,370 bytes, 17 nodes) was
reloaded, verified against its profile and played 5,000 times: p50 0.161 ms, p95 0.219 ms, max
1.136 ms, against the ≤ 1 ms target at p95.

The `strict.en.2` result is a real property of that profile, not a solver failure: with only its 65
two-letter words as guesses, the `a*` family can only be identified one word at a time, so no
6-guess strategy exists. The heuristics agree by failing: `entropy` solves 84.6% and
`entropy_candidates` 78.5% on that profile. That is why a guarantee, not an average, is what a
finite DP value certifies.

---

## 15. Phase 4 measured harness — 2026-11-20

The full harness is measured on the same shipped classic profile (manifest `5127f7ba…`, 2,315 answers /
12,972 guesses, normal, uniform, 6 attempts) and written to `data/bench/phase4/`. Reproduce with:

```
.venv/Scripts/python.exe -u tools/measure_phase4.py --workers 16
.venv/Scripts/python.exe -u tools/measure_phase4.py --report-only   # re-render, no replay
```

Every row is exhaustive over its answer set; nothing here is sampled. Times are measured run times at
16 workers on the 16-core host, and the seven runs together took 200.4 s in this pass.

| Run | Strategy | avg solved | avg all | median | worst | success | p95 decision ms |
|---|---|---|---|---|---|---|---|
| B-03 | `entropy` | 3.6380 | 3.6380 | 4 | 6 | 100.00% | 13,865 |
| B-03 | `expected_remaining` | 3.6536 | 3.6536 | 4 | 5 | 100.00% | 20,354 |
| B-03 | `minimax` | 3.7024 | 3.7024 | 4 | 5 | 100.00% | 9,879 |
| B-02 | `hybrid.balanced` | 3.6536 | 3.6536 | 4 | 5 | 100.00% | 8,269 |
| B-12 | `hybrid.balanced`, 1 worker | 3.6536 | 3.6536 | 4 | 5 | 100.00% | 1,459 |
| B-01 proxy | `exact`, `strict.en.3` first 12 | 2.5833 | 2.5833 | 2.5 | 4 | 100.00% | 0.18 |
| failures | `entropy`, K = 3 | 2.8442 | 3.5931 | 3 | 3 | 35.21% | 5,738 |

**Outcome metrics.** Distributions are `entropy` 0/22/896/1296/100/1, `expected_remaining` and
`hybrid.balanced` 0/27/819/1398/71/0, `minimax` 1/32/734/1436/112/0 over turns 1–6. They match §13
and Phase 2 exactly, which is the evidence that the Phase 4 report path did not change play.
`pct_solved_in_k` and `total_guesses` are in `measurements.json`.

**Efficiency.** Candidate reduction is a geometric mean of 0.1189 (`entropy`), 0.1200
(`expected_remaining`), 0.1234 (`minimax`) per turn, with 3.07–3.10 bits of information gained per turn.
The p95 decision latency is dominated by one decision: the first guess scores all 12,972 guesses against
2,315 candidates. The exact policy's p95 is 0.18 ms in this run (0.219 ms in the Phase 3 lookup
measurement), four orders of magnitude cheaper, because it is a tree lookup rather than a scoring pass.

**Correctness.** Zero invalid guesses, zero mode violations and zero eliminated answers in all seven runs.
Hard-mode legality is counted by the harness (`strict_legality=False` lets a violation be recorded
instead of aborting), so the column is measured, not assumed. Determinism hashes are identical at 1 and
16 workers: `393ce4ff9fb9b4e2ac281290f46c4b1f897eb563d928b789007105872952967d` for `hybrid.balanced`.

**Failures.** The K = 3 run is deliberate: 1,500 of 2,315 games exceed three guesses, and the report
prints both `avg_guesses_solved` (2.8442) and `avg_guesses_all` (3.5931) with the failures listed by
answer. No aggregate in any report is printed without its answer-set id and exhaustive/sampled label.

**Budget guard.** A run over `strict.en.3` with `--time-budget` set to a microsecond finishes, is stored
with `status = budget_exceeded`, and then raises: nothing is truncated, and `has_completed` is false so a
resumed matrix re-runs it.

**CSV.** `data/bench/phase4/b03_entropy_games.csv` has 2,315 rows and regenerates every aggregate in the
Markdown report (`bench report --format csv` refuses to export if it does not).

**Parallelism, measured honestly.** The pool does not speed these strategies up: `entropy` took 47.3 s
at 16 workers against 21.3 s at one worker (a serial `wordle-ai bench run --workers 1 --no-store`
re-run), and `hybrid.balanced` 28.7 s against 26.3 s. Each worker
starts with an empty decision cache, so shared early-game states are recomputed and 16 profile loads are
paid once. The pool is kept for B-12 (worker-count invariance) and for state-disjoint work; no speedup
is claimed. `peak_rss_mib` is the parent's peak (60.7–63.9 MiB in pool mode, 227.0 MiB serial) and
worker peaks are not summed.

**B-01 remains blocked.** Classic still has no exact policy — Phase 3's measured boundary did not reach
one — so B-01 is reported as a 12-answer `strict.en.3` proxy: the full exact surface (artifact load,
verification, play, report) reproduces 2.5833 with worst case 4 and no failures. The published 3.4212 is
not claimed anywhere, and §6's discrepancy protocol does not apply to a configuration that was never run.
