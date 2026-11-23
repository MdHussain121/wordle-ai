# WORDLE_AI_ML_RESEARCH_AND_TRAINING_PLAN.md

**Status:** Phase 0 deliverable, revision 1.0 · **Date:** 2026-11-19
**Implements:** PRD FR-25, roadmap Phase 6
**Governing rule:** classical algorithms are the baseline, and ML is admitted only by measurement.

---

## 1. Why ML is in this project at all

Wordle is small enough to solve exactly for its flagship configuration, so a learned policy cannot
win on the flagship. There are only two honest reasons to add learning:

1. **Where exactness is infeasible.** The open extended profile has 11,411 five-letter words and
   the full profile 17,410 `[R]`; the classic 2023 configuration has 3,158 answers `[P]`. Exact
   optimisation there is a multi-day or intractable job. A model that approximates the exact
   *value* of a state can extend near-optimal decisions into that gap, which no heuristic does
   well.
2. **Where a prior is genuinely probabilistic.** "How likely is this word to be the answer" is a
   distributional question, and a calibrated model can answer it better than a hand-set
   temperature — if it passes calibration.

Everything else — ranking guesses, choosing an opener, deciding when to stop eliminating — is
already handled analytically, deterministically and explainably. The plan therefore invests in a
**word-probability model** and a **distilled value/policy model**, treats a **GBDT ranker** as a
challenger, and confines reinforcement learning to a capped appendix.

The published evidence for that ordering is blunt:

| Approach | Published result | Tag |
|---|---|---|
| Exact DP | 3.4212 average, worst 5 | `[P]` |
| Bin-count heuristic | 3.4600 | `[P]` |
| Max-entropy heuristic | 3.476 | `[P]` |
| PPO (deep RL, elimination win condition) | ~97–98% win, ~4.3 average | `[P]` |
| Behaviour cloning of a greedy policy | 99.8% win, 4.04 average | `[P]` |
| DQN | reported as not successful on full Wordle; replay buffer breaks under partial observability | `[P]` |

A learned policy that reaches ~4.04 is worse than a 30-line heuristic. That is the bar ML must
clear, and the reason the gate in §8 is numeric rather than rhetorical.

---

## 2. Three questions that must not be merged

The brief calls this out and the architecture enforces it:

| Question | Representation | Component | Test |
|---|---|---|---|
| Is `w` valid? | set membership in `G` | `lexicon` + policy | membership tests; no model involved |
| How likely is `w` as the secret? | distribution over `A` | `engine.prior` / word model | log loss, Brier, ECE |
| How useful is guessing `w`? | partition statistics over `S` | `strategy` | measured guesses |

A character LM can only inform the second. It cannot make a non-word valid, and it cannot by
itself evaluate a guess. Any code path that lets a model's score influence the valid-guess set is
a defect (tested by asserting `suggested ∈ G` regardless of model output).

---

## 3. Component 1 — word probability model

### 3.1 Candidate models

| Model | Description | Expected value here |
|---|---|---|
| Empirical answer frequency | counts from a user-supplied answer history, Laplace-smoothed | Strong if the history is real; useless without one |
| `wordfreq` Zipf | runtime lookup, `zipf ∈ [0, 8]`, 0 for unseen | Best general-purpose prior; licence-safe at runtime |
| Character n-gram (n = 3–5) | add-k smoothed, trained on the *answer* distribution | Captures orthographic plausibility; weak on rare-but-valid words |
| Character LSTM | 1–2 layers, 64–128 hidden | Marginal over n-gram at this vocabulary size `[E]` |
| Character Transformer | 2–4 layers, small heads | Overkill; no measurable headroom `[E]` |
| Pretrained subword LM | external model, tokeniser probabilities | Not useful: tokenisation fragments short words and the probabilities are not calibrated to Wordle answers |

**Decision.** Ship `uniform` (default), `zipf`, and `empirical`. Implement the character n-gram as
an offline *evaluation baseline* to test whether a learned prior beats Zipf; do not ship a neural
LM. The measured vocabulary is small (2,315 answers in the flagship profile) and the strings are
five characters; there is no semantic content for a large model to exploit.

### 3.2 The prior, formally

```
π_β(a) = exp(β · z(a)) / Σ_{a' ∈ A} exp(β · z(a'))
```

where `z(a)` is the standardised Zipf score (or a model log-probability). `β = 0` recovers uniform
and must reproduce uniform decisions bit-for-bit (tested). `β` is fit on a validation split by
minimising log loss of the true answer, never on the test split.

### 3.3 Calibration

| Metric | Definition | Admission threshold |
|---|---|---|
| Log loss | `−mean log π(a*)` at game start | strictly better than uniform |
| Brier | `mean Σ_a (π(a) − 1[a=a*])²` | reported, no threshold |
| ECE | 10 equal-mass bins of `π(a*)` | < 0.05 |
| Reliability curve | predicted vs observed per bin | exported for inspection |
| Top-k hit | `a*` in top-k of prior | reported for k = 1, 10, 100 |

A prior that fails any threshold is rejected with its numbers recorded. A rejected prior is a
successful experiment: it prevents a plausible-sounding but harmful change.

### 3.4 What frequency must never do

- It must not add or remove words from `A` or `G`.
- It must not be presented as a probability without naming the prior.
- It must not be fit on the benchmark's test answers.
- It must not be derived into a redistributable table from wordfreq (CC BY-SA 4.0 data).

---

## 4. Component 2 — guess-ranking model (challenger)

### 4.1 Features

The ranker sees exactly the information the analytic scorer sees, so any measured difference comes
from the model, not from privileged inputs.

| Group | Features |
|---|---|
| State | candidate count, `log2` candidate count, turn index, attempts remaining, mode (one-hot), length |
| Guess | is-candidate flag, distinct-letter count, repeated-letter flag, per-position letter identity (hashed), vowel count |
| Partition | entropy (bits), expected remaining, worst-case bucket, bucket count, singleton count, max bucket fraction |
| Probability | prior mass on the guess, posterior mass on the guess, `p(solve now)` |
| History | number of prior guesses, letters excluded, letters confirmed, positions fixed |
| Cost | analytic composite score, rank of the guess by that score |

### 4.2 Model families compared

| Family | Configuration | Expected outcome |
|---|---|---|
| Analytic composite | no model | baseline; already strong |
| GBDT (LightGBM or sklearn `HistGradientBoosting`) | 200–600 trees, depth 4–8, lr 0.05 | Best chance of a small win; ~1–5 MB; <1 ms |
| Small MLP | 2 × 128, ReLU, dropout 0.1 | Similar or worse than GBDT at this data size `[E]` |
| Linear pairwise ranker | logistic on features | Interpretable floor; likely underfits interactions |

### 4.3 Training target

Two formulations, both evaluated:

1. **Classification over a shortlist.** For each state, take the top-`m` (`m = 32`) guesses by the
   analytic composite; label the one the DP policy actually chose. Cross-entropy over `m` classes.
   Problem: when the DP choice is outside the shortlist, the label is "none of these" — recorded
   as a separate class, and the shortlist miss rate is reported.
2. **Pairwise ranking.** Sample pairs `(g1, g2)` from the shortlist, label by the DP's `V` value,
   optimise a pairwise logistic loss. More robust to ties and near-ties.

Report both; ship whichever passes the gate. If the DP choice is frequently outside the shortlist,
that is itself a finding: the analytic scorer's shortlist is the bottleneck, and no ranker can fix
it.

### 4.4 Size and inference budget

GBDT ≤ 5 MB serialised, ≤ 1 ms per state, loaded once. MLP ≤ 1 MB, ≤ 0.5 ms. Both must run on CPU
with no vectorised batch requirement at solve time.

---

## 5. Component 3 — distillation of the exact policy

This is the highest-value ML work in the project, and the only one with a clear theoretical story:
the exact policy is optimal but only computable on small profiles; a model can approximate its
value function where DP cannot run.

### 5.1 Two heads

| Head | Input | Output | Use |
|---|---|---|---|
| Value | state features (candidate set statistics, turn, attempts, mode) | `V̂(S, k)` ≈ expected remaining guesses | replaces the one-step surrogate inside lookahead on infeasible profiles |
| Policy | state features + candidate guess features | distribution over shortlist | direct recommendation where no analytic strategy is strong |

The value head is the important one: with a calibrated `V̂`, two-ply lookahead becomes affordable
on large profiles because the inner search is replaced by a regression rather than a full
expansion.

### 5.2 Data generation

```
for each profile in {classic, strict L=4, strict L=5, ...}:
    for each answer a in that profile (or a stratified subset):
        play the DP policy; at every state s along the path:
            emit (features(s), V(s), chosen_guess(s), candidate set digest, k)
```

States come only from answers in the training split. The DP labels are exact where the profile is
tractable; where it is not, labels come from a bounded-depth search and are marked as such, with
the label source recorded per row.

### 5.3 Splits and generalisation

| Split | Contents | Purpose |
|---|---|---|
| Train | 70% of answers per profile | fitting |
| Validation | 15% | early stopping, `β`, hyperparameters |
| Test | 15% | one evaluation per release |
| Cross-profile | a *different* length or profile entirely | the real generalisation test |

The cross-profile test is the one that matters: a model trained on 4-letter states and applied to
5-letter states (or trained on strict and applied to extended) must not regress by more than 0.02
average guesses. If it does, the model has learned profile-specific artefacts rather than the game.

### 5.4 Losses

- Value head: Huber loss on `V` (robust to the long tail of hard states), plus a monotonicity
  penalty encouraging `V(S) ≥ V(S')` when `S' ⊂ S` on sampled pairs (`[X]`, optional).
- Policy head: cross-entropy against the DP choice over the shortlist, with label smoothing 0.05.

### 5.5 What would make this fail

- The DP value is not smooth in the features (it is a step function with large jumps at bucket
  boundaries), so regression may be systematically off by ±0.5 guesses.
- Distribution shift: DP paths are optimal paths; a model used inside a heuristic policy will see
  states the DP would never visit. Mitigation: generate states from *both* DP and heuristic play,
  and label each with its DP value where computable.

Both risks are measured, not assumed away. If the value head's mean absolute error exceeds 0.5
guesses, it is not used for lookahead.

---

## 6. Component 4 — reinforcement learning (research appendix, capped)

### 6.1 Environment

| Element | Specification |
|---|---|
| Episode | one game, `K` attempts, profile fixed |
| Hidden secret | sampled from `A` under the run's prior, seeded |
| Observation | candidate mask (bitset or top-k summary), `k`, mode flags, aggregate counts; **not** the answer |
| Action | index into `G`, with a legality mask (and a mode mask in hard modes) |
| Reward | `−1` per guess; `+(K − t)` on solve at turn `t`; `−K` on failure |
| Termination | solve, or `k = 0` |
| Info | candidate count after each step, whether the true answer survived |

Reward shaping is **off by default**. An optional information-gain shaping term may be tested, but
it must be ablated, because rewarding candidate reduction can reward elimination that does not
shorten the game — the exact confusion the research report warns about.

### 6.2 Observation representation

Two options, both tested:

- **Structured features** (as in §4.1), dimension ~40. Cheap, interpretable, generalises across
  lengths.
- **Candidate bitset** (|A| booleans). Stronger signal, but length- and profile-specific; a 2,315-
  bit vector does not transfer to 4,444 or 11,411. Use only for a per-profile experiment.

A shared encoder with a length embedding is the only design that plausibly generalises across
lengths, and it is tested explicitly rather than assumed.

### 6.3 Algorithms

| Algorithm | Role | Notes |
|---|---|---|
| DQN | do not pursue | published failure under partial observability; replay buffer mixes inconsistent value targets `[P]` |
| A2C / PPO | primary RL experiment | on-policy, entropy regularisation; small MLP policy |
| Behaviour cloning (BC) | baseline and warm start | imitate the DP policy or the heuristic; published BC of a simple greedy policy reaches 4.04 `[P]` |
| Actor-critic with a learned value head | secondary | reuse the distillation value model as a critic |

### 6.4 Training protocol

- 1M–10M environment steps, 16–64 parallel environments, batch 256, lr 3e-4 → 1e-4, entropy
  coefficient swept in {0, 0.001, 0.01}, gradient clip 0.5.
- Action masking applied at the logits, not by resampling; illegal actions get `−inf`.
- Evaluation every 100k steps on a fixed held-out answer set, greedy policy, with the full metric
  set (average, worst case, failure rate) — not just win rate.
- Early stop on validation average guesses, not on reward.

### 6.5 What counts as a result

RL is compared against the heuristic and the exact policy, on the same answer set, with the same
attempt limit. A win requires beating the hybrid composite by ≥ 0.02 average with no worst-case
regression — the same gate as any other ML component. Given the published numbers, the expected
outcome is a negative result, which is worth documenting precisely because it is usually omitted.

**Cap.** Two weeks of wall-clock and compute. At the cap, stop and publish whatever the numbers
say.

---

## 7. Leakage prevention (applies to all of §3–6)

1. **Split by answer word**, never by state, seed or date. A test asserts the intersection of
   train/test answer sets is empty.
2. **States are generated from training answers only.** A model must never see a state derived
   from a test answer, even as an unlabelled feature.
3. **The test split is evaluated once per release.** The count of evaluations is logged; repeated
   peeking converts the test set into a validation set and must be declared.
4. **The 2,315 list is public and heavily optimised.** Generalisation is also measured on the 3,158
   list and the open extended profile.
5. **Feature audit.** No feature may encode the answer, the answer index, or any function that is
   injective on answers (e.g. a hash of the candidate set is fine; a hash of the secret is not).
6. **Dataset checksums.** Each training set records the profile manifest checksums it was built
   from, so a rebuilt lexicon invalidates the dataset explicitly.

---

## 8. The decision gate

A model is admitted to the product only if **all** of the following hold on a held-out answer set,
with the analytic composite as the baseline, measured by the benchmark harness:

| # | Criterion | Threshold | Rationale |
|---|---|---|---|
| G1 | Average guesses | improvement ≥ 0.02 | below this, noise and maintenance cost dominate |
| G2 | Worst case | not worse than baseline | tail regressions are what players notice |
| G3 | Failure rate | not worse | a model that loses games is unusable |
| G4 | Decision latency | added p95 ≤ 5 ms | must not be felt interactively |
| G5 | Cross-profile | no regression > 0.02 on a different profile/length | prevents profile-specific overfitting |
| G6 | Calibration (if probabilistic) | log loss better than uniform; ECE < 0.05 | confidence must mean something |
| G7 | Reproducibility | deterministic inference, versioned model artifact with checksum | the rest of the system is reproducible |
| G8 | Explainability | model output can be rendered as a reason without inventing one | the product's core promise |

**Outcomes.**

- **All pass:** ship behind `ml.enabled = false`, document the measured delta, keep the analytic
  path as fallback, and A/B both in the release benchmark.
- **Any fail:** reject, record the numbers, keep the analytic path. The gate report is committed as
  evidence.

**What the gate is protecting against.** The most likely failure is a model that improves the
classic average by 0.01–0.03 while degrading the worst case and adding a dependency. That is not a
win; it is complexity with a rounding error attached.

---

## 9. Training pipeline diagram

```
profiles + manifests
        │
        ▼
┌───────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│ state generator   │────►│ labeler              │────►│ dataset (parquet)   │
│ DP paths +        │     │ exact V / choice,    │     │ split by answer word│
│ heuristic paths   │     │ or bounded-depth est.│     │ train/val/test +    │
└───────────────────┘     └──────────────────────┘     │ cross-profile holdout│
                                                        └──────────┬──────────┘
                                                                   │
                    ┌──────────────────────────────────────────────┴─────────┐
                    ▼                          ▼                             ▼
            ┌───────────────┐        ┌─────────────────┐          ┌──────────────────┐
            │ prior model   │        │ value/policy    │          │ GBDT ranker      │
            │ (n-gram/Zipf) │        │ distillation    │          │ (challenger)     │
            └───────┬───────┘        └────────┬────────┘          └────────┬─────────┘
                    │                         │                            │
                    └─────────────┬───────────┴────────────────────────────┘
                                  ▼
                        ┌───────────────────┐
                        │ calibration + gate│  ── fail ──► reject, record numbers
                        └─────────┬─────────┘
                                  │ pass
                                  ▼
                     versioned artifact + checksum + A/B benchmark
```

---

## 10. Experiment schedule (Phase 6)

| # | Experiment | Input | Output | Time `[E]` |
|---|---|---|---|---|
| M-1 | Zipf prior vs uniform | classic + strict answers | log loss, ECE, avg-guess delta | 1 d |
| M-2 | Character n-gram prior vs Zipf | answers per profile | log loss comparison | 2 d |
| M-3 | GBDT ranker over analytic shortlist | DP states from classic + strict | gate report G1–G8 | 3 d |
| M-4 | Value-head distillation | DP states, cross-profile holdout | MAE, lookahead quality, gate | 4 d |
| M-5 | Policy-head distillation | same | shortlist accuracy, avg guesses | 2 d |
| M-6 | BC of the DP policy | DP trajectories | baseline for RL | 1 d |
| M-7 | PPO | environment | avg, worst, failure, sample cost | capped 5 d |
| M-8 | RL across lengths (shared encoder) | mixed profiles | transfer table | only if M-7 is promising |

Order matters: M-4 is the one most likely to justify the ML budget, and M-3 is the cheapest test of
whether the analytic shortlist is the real bottleneck.

---

## 11. Risks specific to ML

| Risk | Mitigation |
|---|---|
| Overfitting the public 2,315 list | cross-profile holdout; 3,158-list check; split by answer |
| Value function too jagged to regress | report MAE; do not use the model if MAE > 0.5; fall back to rollout |
| Model improves average, worsens tail | G2/G3 gate |
| Inference cost eats the gain | G4 latency budget, CPU-only, batched-free inference |
| Leakage through features | feature audit; candidate-set digests allowed, secret hashes not |
| Non-determinism at inference | fixed seeds, single-threaded inference, versioned artifact |
| RL consuming the schedule | two-week cap, pre-registered evaluation |
| Licence contamination via model training data | train only on generated states and open lexicons; no wordfreq-derived tables |

---

## 12. Acceptance criteria for Phase 6

1. A gate report exists for M-1, M-3, M-4 and M-7, each with a pass/fail verdict and the numbers
   behind it.
2. The leakage test passes: no test answer appears in any training state, verified mechanically.
3. If any model passes, it is versioned, checksummed, deterministic, disabled by default, and
   A/B-benchmarked against the analytic composite in the release report.
4. If none passes, the negative results are recorded with the same rigour, and the product ships
   with the analytic path only.
5. The RL appendix reports sample cost, wall-clock and comparison against both baselines, or an
   explicit "not run, with reason".
6. No model artifact exceeds 5 MB, and no inference path requires a GPU or a network call.
