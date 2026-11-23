# WORDLE_AI_RESEARCH_REPORT.md

**Project:** Wordle-solving AI for word lengths 1–5
**Document status:** Phase 0 deliverable, revision 1.0
**Date:** 2026-11-19
**Companion documents:** `WORDLE_AI_PRD.md`, `WORDLE_AI_TECHNICAL_SPECIFICATION.md`,
`WORDLE_AI_DATASET_AND_LEXICON_PLAN.md`, `WORDLE_AI_ML_RESEARCH_AND_TRAINING_PLAN.md`,
`WORDLE_AI_BENCHMARK_PLAN.md`, `WORDLE_AI_IMPLEMENTATION_ROADMAP.md`,
`WORDLE_AI_RISK_REGISTER.md`, `WORDLE_AI_ARCHITECTURE.md`

**Evidence labels used throughout the corpus**

| Tag | Meaning |
|---|---|
| `[P]` | Published result, cited to a primary source |
| `[R]` | Reproduced or measured during this Phase 0 work (commands and inputs recorded) |
| `[X]` | Proposed experiment, not yet run |
| `[E]` | Engineering estimate or derivation from measured inputs |
| `[U]` | Unverified assumption, explicitly flagged |

No performance number in this corpus is presented as measured unless `[R]` or `[P]` accompanies it.
This project has not yet run a solver, so **no solver benchmark result is `[R]`**. All solver
performance figures below are `[P]`, and the benchmark plan defines how each will be reproduced.

---

## 0. Consolidated executive summary

**The recommendation.** Build a CPU-first, lexicon-driven solver whose default policy is
*exact* where exactness is affordable and *Bayesian one-step with endgame lookahead* everywhere
else. The exact solver is a dynamic program over candidate sets, memoised by (candidate set,
guesses remaining). It is affordable for the classic five-letter configuration — 2,315 answers
against 12,972 allowed guesses, a 28.64 MiB feedback table `[R]` — and it provably achieves the
published optimum of 3.4212 average guesses with a worst case of 5 `[P]`. It is *not* affordable
for the 17,410-word five-letter full-lexicon profile (289.07 MiB table `[R]`, and a state space
that grows far faster than the table). A compact, well-tested Python core plus a numpy feedback table delivers the classic optimum; a Rust inner loop is justified only for offline policy generation, and only if the measured Python runtime misses its budget.

**Why not a frequency solver.** Letter-frequency greed is not a strategy, it is a prior. It
answers "which letters are common", not "which guess partitions my remaining candidates best".
Its failure mode is structural: it cannot distinguish a guess that is likely to *be* the answer
from a guess that is likely to *eliminate* most candidates, and it degrades badly with repeated
letters, where a naive membership test mislabels feedback. On the classic configuration the
published spread is wide: an ad-hoc letter heuristic with `soare` averages 3.65 `[P]`, a maximum
entropy solver 3.476 `[P]`, a solution-word-only bin-count heuristic 3.4600 `[P]`, and the exact
optimum 3.4212 `[P]`. The gap between "reasonable heuristic" and "optimal" is about 0.23 guesses
on average, and much larger in the tail.

**The five findings that shaped the design**

1. **The optimal opening word is a property of the dictionary, not of English.** `SALET` is
   optimal for 2,315 answers / 12,972 guesses `[P]`; on the July 2023 configuration
   (3,158 answers / 14,855 guesses) the optimum moves to `TARSE` at 3.5526 `[P]`. Any hardcoded
   opener is therefore wrong for some supported profile. Openers must be computed per profile
   and cached with the profile's checksum.
2. **Maximum entropy is not the objective.** Maximising feedback entropy is a proxy for
   minimising expected *log* remaining candidates. The true objective is expected *guesses*,
   and one-step greedy on any surrogate is not optimal: a breadth-1 greedy search on total
   guesses picks `TRACE` for 7,944 total guesses, while the proven optimum is 7,920 `[P]`.
   Measured on solution-word-only guesses, the bin-count heuristic (3.4600) beats entropy
   (3.4955) `[P]`. Entropy belongs in the engine as a *baseline and tie-break*, not as the
   default claim to optimality.
3. **Exact optimisation is intractable in general, and that is a theorem, not an excuse.**
   Deciding whether a winning strategy exists within ℓ guesses is NP-complete, and the problem
   is NP-hard to approximate even for length 5 `[P]`. The published exact solutions took days on
   a 64-core machine `[P]`. The architecture therefore needs a *measured* feasibility boundary
   and a strong approximate path, not an assumption that DP always works.
4. **The classic word lists cannot be reconstructed from open lexicons.** Measured coverage of
   the 12,972 allowed guesses by the union of SCOWL (American composition) and ENABLE is
   **93.73%**; two classic answers (`admin`, `cyber`) are absent from every open source measured
   `[R]`. A "classic" profile must be user-supplied and provenance-documented, and it must never
   be silently substituted with an open list.
5. **Reinforcement learning does not beat the classical stack here.** The strongest published
   deep RL results reach roughly 97–98% win rate at 4.3 average guesses with an elimination-style
   win condition, while a trivial randomised greedy policy solves 99.8% at 4.04 `[P]`. Against
   3.4212 optimal and 3.4600 heuristic, RL is a research appendix, not a product feature. The
   defensible ML contribution is *distillation* of the exact policy into a fast value model for
   profiles where DP is infeasible.

**The stack.** Python 3.12 with numpy for vectorised candidate filtering and feedback-table
gathers; Typer for a CLI-first interface, per the standing CLI-first rule; pydantic for schemas;
pytest plus hypothesis for property tests; SQLite for caches and benchmark results; optional
Rust (maturin) for the DP inner loop. No GPU, no database server, no cloud dependency. A future
web UI or external game adapter sits behind a transport-agnostic service layer.

**What "better" means, measurably.** On the classic profile the system must reproduce
3.4212 ± 0.0005 average and a worst case of 5 over all 2,315 answers, bit-identical across runs.
On profiles where DP is infeasible, the target is within 0.05 average guesses of the best
available one-step strategy on the same answer set, with 100% of games solved within the limit.
ML is admitted only if it improves average guesses by at least 0.02 with no worst-case
regression and ≤5 ms per decision. These gates are defined numerically in
`WORDLE_AI_ML_RESEARCH_AND_TRAINING_PLAN.md` §7 and `WORDLE_AI_BENCHMARK_PLAN.md` §6.

---

## 1. Method, scope and evidence grading

**What was done.** Primary literature was read directly (journal and conference versions, arXiv
preprints, author write-ups with code). Lexicon sources were downloaded and measured on this
machine. Every quantitative claim is tagged. Where a figure comes from a secondary summary
rather than the paper itself, that is stated.

**What was measured `[R]`.** The Phase 0 spike downloaded SCOWL 2020.12.07, ENABLE 2K, and the
classic Wordle lists, recorded SHA-256 checksums, and counted words per length under several
composition rules. Commands and outputs are in `data/processed/measurements.json`, produced by
`tools/measure_lexicons.py` (exit 0). Numbers used in this corpus are listed in Appendix A.

**What was not done.** No solver was implemented or benchmarked. No ML model was trained. No
licence was accepted on the user's behalf; licensing conclusions are engineering guidance, not
legal advice.

**Scope.** English, lengths 1–5, normal and hard modes, uniform and frequency-weighted priors,
five lexicon profiles, five application modes. Out of scope for v1: non-English lexicons
(architecture supports them via a configurable alphabet), multiplayer, and any hosted service.

**Non-goals.** Reproducing Wordle's UI, scraping the live NYT game, or claiming that a single
word list is "the" English vocabulary. There is no canonical complete English word list; the
system's answer to that is an explicit, versioned, checksummed profile.

---

## 2. The game, formally

Let `L` be the word length, `A` the answer set (possible secrets), `G` the allowed guess set,
with `A ⊆ G` enforced as an invariant — otherwise a game can become unwinnable through no fault
of the solver. A game state is

```
s = (S, h, k, m)
  S : current candidate set, S ⊆ A, S ≠ ∅
  h : feedback history, a sequence of (guess, pattern) pairs
  k : guesses remaining, 1..K
  m : rule mode ∈ {normal, hard, superhard}
```

The secret `a* ∈ A` is unknown. A guess `g ∈ G` produces a pattern `p = F(g, a*) ∈ P_L`, where
`P_L` is the set of feedback patterns.

**Why |P_L| = 3^L.** Each position is independently in one of three states — exact match
(green), present elsewhere (yellow), absent (gray). Encoding green = 2, yellow = 1, gray = 0
gives a base-3 numeral with `L` digits, so `\|P_L\| = 3^L`: 3, 9, 27, 81, 243 for L = 1..5 `[E]`.
All five fit in one byte (243 ≤ 255), which is why a feedback table is a `uint8` matrix `[E]`.

**Feedback is a multiset problem, not a membership problem.** The correct algorithm is a
two-pass reservation:

```
F(g, a):
  p ← [GRAY] * L
  remaining ← multiset(a)                 # letters of the secret still unassigned
  for i in 0..L-1:                        # pass 1: reserve exact matches
      if g[i] == a[i]:
          p[i] ← GREEN
          remaining.remove(g[i])
  for i in 0..L-1:                        # pass 2: assign yellows while copies remain
      if p[i] == GRAY and g[i] in remaining:
          p[i] ← YELLOW
          remaining.remove(g[i])
  return p
```

Pass 1 must complete before pass 2 begins. A single-pass implementation that consumes letters
left-to-right awards a yellow to a duplicated guess letter that the answer does not contain,
and mislabels a case such as guess `sassy` against answer `assay`. This is the single most
common correctness defect in hobby solvers and the reason `WORDLE_AI_TECHNICAL_SPECIFICATION.md`
§4 specifies the two-pass algorithm with adversarial golden tests.

**Candidate elimination.** After observing `(g, p)`, the posterior support is
`S' = {a ∈ S : F(g, a) = p}`. Filtering by recomputing `F` for every candidate is
`O(\|S\| · L)` — trivial at these sizes, and *mathematically* correct in a way that hand-written
per-letter rules are not. Incremental letter-constraint engines are an optimisation over this
definition, and must be validated against it, not the other way round.

**Invariants.** (I1) `a* ∈ S` whenever the feedback history is realisable; (I2) a solved game
has `S = {a*}` and the last guess equals `a*`; (I3) an unrealisable history is reported as an
error rather than silently emptying `S`; (I4) posterior probabilities sum to 1 within floating
tolerance; (I5) every recommended guess is in `G` and, in hard modes, satisfies the mode's
constraint; (I6) no feedback in `h` is ignored. These are enforced in code and tested by
property tests (`WORDLE_AI_TECHNICAL_SPECIFICATION.md` §12).

---

## 3. Family A — frequency-based approaches

**Variants.** Global letter frequency; positional frequency; distinct-letter frequency;
character co-occurrence; candidate ranking by summed letter scores; vowel/consonant balance;
position-dependent probability from a corpus.

**The mathematics.** A frequency scorer is a linear model over letter indicators. If
`score(g) = Σ_i w_{i, g_i}` with `w` estimated from corpus counts, then the guess ordering is
induced by a fixed additive utility. Wordle's payoff, however, is not additive in letters: the
value of a guess is the *partition* it induces on `S`, and that partition is defined by a
multiset comparison with each candidate. Two words with identical letter sets can induce very
different partitions. Additivity is therefore a mis-specified model of the objective, and no
reweighting fixes that.

**Why naive frequency fails, concretely.**

- It cannot exploit the current candidate set. After `S` shrinks to 40 words sharing a prefix,
  global letter frequency still recommends the same opener-family word.
- It double-counts duplicated letters: `eerie` looks letter-rich but contains only three
  distinct letters, and its informational value is lower than its score suggests.
- It ignores position: `_ _ _ _ y` and `y _ _ _ _` are not the same evidence.
- It has no notion of a guess being *disproportionately* likely to be the answer, and no notion
  of hard-mode consistency.
- It is blind to the answer/guess distinction: the best elimination word is often not a
  plausible answer at all.

**Where frequency genuinely helps.** As a *prior* over answers, not as a guess scorer. Corpus
frequency is a reasonable model of "how likely is this word to be chosen as today's secret",
and that prior enters the expected-cost objective. The measured distinction matters: coverage
and validity are set membership, plausibility is a probability, and guess value is a partition
statistic. Conflating them is the core error the PRD is written to prevent.

**Published performance.** An ad-hoc heuristic with `soare` averages 3.65 with worst case 6 `[P]`.
That is the realistic ceiling of a pure letter-scoring approach, and it is 0.23 worse than
optimal on average, and materially worse in the tail.

---

## 4. Family B — information theory

**Derivation.** For a candidate set `S` with prior `p(a)`, guess `g` and pattern `r`, let

```
S_r = {a ∈ S : F(g, a) = r},      p_r = Σ_{a ∈ S_r} p(a) = P(R = r | g, S)
```

The feedback random variable `R` has entropy

```
H(g) = -Σ_r p_r log2 p_r
```

which equals the mutual information `I(A; R \| g, S)` because `R` is a deterministic function of
`(g, A)`. Entropy is therefore *expected information gain in bits*, and maximising it is
equivalent to minimising the conditional entropy `H(A \| g, R)`.

**Expected remaining candidates.** Under a uniform prior over `S`:

```
E[|S_R|] = Σ_r p_r |S_r| = Σ_r (|S_r|/|S|) |S_r| = (1/|S|) Σ_r |S_r|²
```

This is the `L²` norm of the bucket-size vector, normalised. Under a non-uniform prior the same
expression holds with `p_r` in place of `\|S_r\|/\|S\|`.

**Why entropy and expected remaining differ.** Entropy is `E[-log p_R]`; expected remaining is
`E[\|S_R\|]`. By Jensen, `E[log X] ≤ log E[X]`, so entropy is a concave, scale-free surrogate for
a quantity the game measures linearly in guesses. Two guesses can have equal entropy and
different expected bucket mass; equal expected mass and different tail shape. Neither ordering
implies the other, and neither is the true objective.

**The true objective is expected guesses, and greedy on a surrogate is not optimal.** For state
`S` with `k` guesses left:

```
V_k(S) = 1 + min_{g ∈ G} Σ_r p_r V_{k-1}(S_r),     V_0(S) = 0,  V_k({a}) = 1
```

Minimising `E[\|S_R\|]` is a one-step approximation to this recursion with `V_{k-1}(S') ≈ \|S'\|`.
Published evidence quantifies the gap: a breadth-1 greedy on total guesses selects `TRACE` for
7,944 total; the proven optimum is 7,920 `[P]`. On the 2,315-answer set that is 3.4318 versus
3.4212 — a 0.3% relative gap, small but real and reproducible.

**Published comparisons on the classic configuration `[P]`.**

| Strategy | Avg guesses | Worst case | Notes |
|---|---|---|---|
| Exact optimum (`salet`) | 3.4212 | 5 | Bertsimas–Paskov; Cunanan–Thielscher proof |
| Bin-count heuristic, solution-word-only guesses (`trace`) | 3.4600 | 6 | Greenberg 2024 |
| Maximum entropy (`soare`) | 3.476 | 6 | Luebeck, as tabulated by Greenberg |
| Max entropy, solution-word-only (`raise`) | 3.4955 | 6 | Greenberg 2024 |
| Expected-bin-size, solution-word-only (`raise`) | 3.5210 | 5 | Greenberg 2024 |
| Minimax (max bucket size), solution-word-only (`arise`) | 3.5844 | 5 | Greenberg 2024 |
| Ad-hoc letter heuristic (`soare`) | 3.65 | 6 | Das, as tabulated by Greenberg |

**Interpretation.** Entropy is an excellent *cheap* default and a bad *optimality claim*.
Bucket-count (maximising the number of distinct feedback outcomes) beat entropy in the
solution-word-only regime `[P]`, which is a useful warning against treating any single scalar
as canonical. The engine therefore exposes entropy, expected-remaining, bucket-count and minimax
as separately scored objectives, and the default composite is defined in
`WORDLE_AI_TECHNICAL_SPECIFICATION.md` §6.

---

## 5. Family C — minimax

**Definitions.** For guess `g`:

```
worst_case(g)  = max_r |S_r|
expected(g)    = Σ_r p_r |S_r|
```

Minimax selects `argmin_g worst_case(g)`. The related game-theoretic question — an adversary
choosing the answer after seeing the guess, as in Absurdle-style variants — is a different
problem and is not what Wordle does; the answer is fixed in advance. Minimax here is a
*risk-control heuristic* on a fixed hidden answer, not a saddle-point solution.

**When minimax is preferable.** When the tail is what you are paid on: a hard 6-guess limit, a
leaderboard scored on worst case, or a profile where a single unlucky branch loses the game.
Minimax buys tail insurance at the cost of average performance. The measured trade-off on the
classic list is visible: `maxbinsize` reaches a worst case of 5 with a 3.5844 average, while
entropy reaches a 3.476 average with a worst case of 6 `[P]`.

**When it is not.** Minimising the largest bucket can select a guess that is useless for
actually *winning* — it may never be the answer and may leave many small buckets that each take
another guess. It also ignores the remaining-guess budget: with five guesses left, a 30-word
bucket is fine; with one guess left, it is fatal.

**The strong published facts.** No strategy guarantees 4 guesses; the optimal worst case is 5 in
normal mode `[P]`. In NYT hard mode, no strategy guarantees 6, and the best max-5 opener is
`PALET` `[P]`. Under the stricter "guess must be consistent with all information" (superhard)
rule, the optimum is `SCAMP` at 3.7162 average with a worst case of 5 `[P]` — and greedy
heuristics in that mode can exceed 6 guesses and fail outright `[P]`. This is why hard mode gets
its own solver path rather than a flag on the normal one.

---

## 6. Family D — exact dynamic programming

**Formulation.** With `V_k` as in §4, the DP is exact when the state is the full candidate set.
The Bellman equation above is the whole algorithm; everything else is engineering:

- **State canonicalisation.** States that induce identical future behaviour can be merged.
  Two candidate sets with the same partition structure under every guess are equivalent; in
  practice memoise on `frozenset(S)` plus `k`.
- **Base cases.** `V_k({a}) = 1` (guess it); `V_1(S) = 1` iff `\|S\| = 1`, else ∞ (cannot win).
- **Pruning.** A lower bound `LB(S) ≥ 1` and an incumbent upper bound from a heuristic give
  branch-and-bound: skip a guess whose optimistic continuation cannot beat the incumbent.
  Cunanan and Thielscher's `V_i` filters are a formal version of this and reduced 12,972
  starting guesses to a single proven optimum `[P]`.
- **Ordering.** Evaluate promising guesses first; the incumbent then prunes hard.
- **Memoisation.** The dominant cost is repeated evaluation of the same `S_r` buckets across
  parent states; a global table keyed by candidate-set hash is essential.

**Published results.** Normal mode 3.4212 with `SALET`, worst case 5 `[P]`. Hard mode 3.5084
`[P]`. Total 7,920 guesses over 2,315 answers, independently proven optimal `[P]`. The DP took
days on a 64-core machine per the RL paper's account `[P]`. A 2023 configuration with 3,158
answers and 14,855 guesses was also solved exactly, at 3.5526 with `TARSE` `[P]`; that is the
current practical ceiling of exhaustive optimisation for five-letter English.

**Why exactness does not generalise.** The problem is NP-hard even at length 5, and hard to
approximate `[P]`. Intuitively the state space is a subset lattice: the number of distinct
reachable candidate sets grows combinatorially with `\|A\|`, and each state requires a scan over
`\|G\|` guesses. Doubling the answer set does far more than double the work.

**The feasibility boundary this project will use.** Measured profile sizes `[R]` give the
footprint; feasibility is a policy, not a fact:

| Profile | L | Answers | Guesses | Feedback table | Exact DP |
|---|---|---|---|---|---|
| classic | 5 | 2,315 | 12,972 | 28.64 MiB | **Yes**, cached artifact |
| strict (SCOWL ≤50) | 5 | 4,444 | 4,444 | 18.83 MiB | Plausible `[E]`, measure |
| extended (SCOWL ≤80 ∪ ENABLE) | 5 | 11,411 | 11,411 | 124.18 MiB | **No** |
| full (SCOWL ≤95 ∪ ENABLE) | 5 | 17,410 | 17,410 | 289.07 MiB | **No** |
| strict | 4 | 2,303 | 2,303 | 5.06 MiB | Plausible `[E]`, measure |
| extended | 4 | 5,059 | 5,059 | 24.41 MiB | Borderline `[E]` |
| full | 4 | 7,441 | 7,441 | 52.80 MiB | **No** |
| strict | 3 | 588 | 588 | 0.33 MiB | **Yes** |
| extended | 3 | 1,223 | 1,223 | 1.43 MiB | **Yes** |
| full | 3 | 2,000 | 2,000 | 3.81 MiB | **Yes** |
| full | 2 | 276 | 276 | 0.07 MiB | **Yes** |
| full | 1 | 2 | 2 | 4 B | **Yes** (and trivial) |

Threshold policy: exact DP is attempted when `\|A\| ≤ 5,000` **and** `\|G\| ≤ 20,000`, with an
offline budget; the decision is recorded per profile with the measured wall-clock time, not
assumed. Lengths 1–3 are exact for every profile. Lengths 4–5 are exact for the classic and
strict profiles only. Everywhere else the system uses the approximate stack, and the documents
say so rather than pretending DP is universal.

**A subtlety for small `L`.** At `L = 1` the game is degenerate: with `\|A\| ≤ 6` a single
candidate is always reachable, and with `\|A\| = 2` (`a`, `i`) the worst case is 2 guesses. The
architecture must nonetheless route it through the same engine, because a length-specific
special case is exactly the kind of hardcoded assumption the brief forbids.

---

## 7. Family E — lookahead and rollout

**One-step** evaluates `g` by an immediate statistic (§4). **Two-ply** evaluates
`g`, then for each observed pattern evaluates the best `g'` on `S_r`, and averages:

```
V_2(S) = 1 + min_g Σ_r p_r min_{g'} Σ_{r'} p_{r'|r} V_1(S_{r,r'})
```

Cost is `O(\|G\| · \|S\| · \|G\| · L)` feedback lookups in the worst case, which is why it must be
restricted: to a shortlist of top-`n` first guesses, to late-game states where `\|S\|` is small,
or both.

**Rollout** replaces the inner minimisation with a fixed base policy `H` simulated to the end:

```
Q(g) = (1/|S|) Σ_{a ∈ S} guesses_to_solve(a | first guess g, then policy H)
```

and selects `argmin_g Q(g)`. Bhambri, Bhattacharjee and Bertsekas show rollout over an entropy
base heuristic is "very close to optimal at relatively modest computational cost", and that it
substantially improves even weak base heuristics `[P]`. That is the strongest published case for
adding computation to a heuristic without paying for full DP.

**Cost in this project's terms.** For `\|S\| = 40` candidates and a 13k-word guess list, a full
rollout is 520k base-policy simulations, each a handful of matrix gathers `[E]`. That is
milliseconds in numpy and unacceptable per keystroke at `\|S\| = 1,000`. The engine therefore
escalates: one-step while `\|S\| > 50`; two-ply or rollout when `\|S\| ≤ 50` and `k ≥ 2`. The exact
threshold is a benchmark parameter, not a constant in code.

---

## 8. Family F — Bayesian inference

**Model.** Treat `A` as a random variable with prior `π`. After feedback `(g, r)`:

```
π'(a) ∝ π(a) · 1[F(g, a) = r]
```

Because feedback is deterministic and noiseless, the likelihood is 0/1 and the posterior is
simply the prior restricted to `S_r` and renormalised. This is why "Bayesian updating" here is
cheap and exact, and why a complex inference engine is unjustified.

**When uniform is correct.** For the original game the daily answer was drawn from a fixed
shuffled list, so a player who does not know the date has a uniform prior over all answers
`[P]`. Uniform is the default, and it is the prior under which the published 3.4212 optimum is
defined `[P]`.

**When non-uniform helps.** WordleBot models answer likelihood from the frequency with which
words have actually appeared `[P]`; the NYT draws from the original list more often than from
the 2023 additions `[P]`. If the goal is "win today's puzzle", a prior weighted toward the
editorial distribution is better calibrated than uniform. Two cautions: the prior changes which
guess is optimal (so cached exact policies are prior-specific and must be keyed by prior id),
and a mis-specified prior is actively harmful — it can make a rare answer unreachable within the
guess budget while looking confident.

**Calibration.** Priors must be validated, not asserted. The plan uses held-out log loss and
Brier score over historical answers, plus a reliability curve, and a temperature parameter
`β` in `π(a) ∝ exp(β · z(a))` where `z` is a Zipf-frequency score `[X]`. `β = 0` recovers
uniform and is the shipped default.

**A distinction the PRD makes explicit.** Validity ("is this a word?") is a set membership
question; plausibility ("is this likely to be the answer?") is a probability; guess value ("does
this partition my candidates?") is neither. The engine keeps them in three separate components
with three separate tests.

---

## 9. Family G — reinforcement learning

**Why it is tempting.** Wordle is a finite-horizon POMDP with a small action space (12,972) and
a clean reward. That is exactly the shape of problem where RL is usually applied.

**Why it loses here.** The optimal policy is computable for the flagship configuration, so RL's
advantage — no model, no enumeration — buys nothing. Empirically:

| Approach | Result | Source |
|---|---|---|
| Exact DP | 3.4212 avg, max 5 | `[P]` |
| Bin-count heuristic | 3.4600 avg | `[P]` |
| PPO, elimination win condition | ~97–98% win, 4.3 avg | `[P]` |
| Behaviour cloning of a greedy heuristic | 99.8% win, 4.04 avg | `[P]` |
| DQN | "not successful" on full Wordle; replay buffer breaks under partial observability | `[P]` |

The DQN failure is instructive and architectural: the same observation can correspond to
different hidden answers, so value targets from a replay buffer are inconsistent. Policy-gradient
methods dodge this only by being on-policy, which is sample-hungry. The reported deep RL result
is also measured under a weaker win condition (reduce the candidate set to one, then take a free
guess), so its 4.3 is not comparable to 3.4212 without adjustment `[P]`.

**Design, if it is ever run.** State: candidate-set bitset plus `k` and mode. Action: guess
index with a validity mask (and a mode mask in hard modes). Reward: `-1` per guess, `+ (K - t)`
on solve, `-K` on failure; optional shaping on candidate reduction, which must be ablated
because it can reward information that does not shorten the game. Training across lengths via a
shared encoder with a length embedding; evaluation against DP and against the analytic stack,
never against random play. This is specified in full in the ML plan, and labelled research-only.

**Verdict.** RL is not justified for the product. Sample cost, instability and a weaker ceiling
than DP make it a poor use of complexity. It stays as a labelled appendix with a numeric gate.

---

## 10. Family H — language models and lexical probability

**The three questions, again.** (1) Is `w` a valid word? (2) How likely is `w` as the secret?
(3) How much information does guessing `w` yield? A character LM can inform (2) at best; it says
nothing about (1) (validity is a curated set, and an LM will happily generate non-words) and
nothing directly about (3).

**Model comparison for this problem.**

| Model | Fit for 1–5 letter English | Note |
|---|---|---|
| Character unigram/bigram | Weak but cheap | Collapses positional structure; near-useless for 3–5 letters |
| Character n-gram (n=3–5) | Reasonable prior | Effectively a soft lexicon; must be trained on the answer distribution, not the guess list |
| Character LSTM | Marginal gain over n-gram | Adds dependency, no measured benefit at this vocabulary size `[E]` |
| Character Transformer | Overkill | 17k-word vocabulary does not need attention |
| Pretrained subword LM | Not useful | Tokenisers fragment 5-letter words; probabilities are not calibrated to Wordle answers |
| wordfreq Zipf values | Best available prior | Runtime dependency only; licence constrains redistribution `[R]` |

**Why big models do not help.** The vocabulary is small, the strings are short, and the decision
problem is combinatorial rather than semantic. A model's job here is to rank candidates, and a
5-point Zipf score already captures most of the signal. The measured evidence that a strong
prior is not the bottleneck: on the classic list, uniform-prior exact play is 3.4212 `[P]`, and
WordleBot's frequency-informed play is not better in expectation because the prior mostly
reorders near-equivalent guesses.

**What a small learned model *is* good for.** Distilling the DP value function so that
near-exact decisions survive on profiles where DP is infeasible. That is the ML plan's central
idea, and it is a ranking/regression problem, not a language-modelling problem.

---

## 11. Lexicon and licence research (measured)

**Sources evaluated.** SCOWL 2020.12.07 (Spell Checker Oriented Word Lists, Kevin Atkinson);
ENABLE 2K; Princeton WordNet 3.0; Open English WordNet; wordfreq; the classic Wordle lists;
12Dicts (public domain, subsumed by SCOWL); UKACD and YAWL (referenced by SCOWL's composition
notes, not separately usable here).

**Licences.**

| Source | Licence | Redistribution | Notes |
|---|---|---|---|
| SCOWL 2020.12.07 | MIT/X11-style permissive, notice required | Yes, commercial included | Derived mostly from public-domain 12Dicts and ENABLE; COCA 3-gram data used under NDA and not redistributed |
| ENABLE 2K | Public domain | Yes | 173,528 lines in the master list; 172,823 unique after casefold+NFC `[R]` |
| WordNet 3.0 | Princeton WordNet licence, permissive, commercial allowed | Yes, with notice | Used here for lexical metadata, not as the guess list |
| Open English WordNet | CC BY 4.0, and derived from WordNet under the WordNet licence (verified in `LICENSE.md`) | Yes, with attribution to both Princeton WordNet and the OEWN team | Not required for v1 |
| wordfreq | Apache-2.0 code, **CC BY-SA 4.0 data** | Constrained | README explicitly refuses CSV-style redistribution; usable as a runtime dependency with attribution |
| Classic Wordle lists | No clear open licence | **Do not redistribute** | User-supplied, provenance recorded, excluded from any shipped artifact |

**Composition traps found by measurement `[R]`.**

- SCOWL's per-size files are **incremental**; a dictionary of size N is the union of levels
  10..N. Naively reading `english-words.80` undercounts badly.
- `english-words.*` is the **neutral base list**, not "all English". It contains only one
  spelling per word, so `color` is in `american-words.10` and `colour` in `british-words.10`,
  and neither is in `english-words`. A correct American profile is `english ∪ american`.
  Measured: English-only 490,233 entries versus English+American 502,141 `[R]`.
- American and British compositions differ by a symmetric difference of **23,753** entries `[R]`.
  Dialect is therefore part of the profile identity, not a cosmetic option.
- SCOWL is ISO-8859-1, not UTF-8; 948 entries under the broad union are non-ASCII `[R]`.
  A UTF-8-only loader crashes on it (observed during this spike).
- **76,390 of 507,556 entries in the broad open union are possessives** containing an apostrophe
  `[R]`. A policy that does not strip them inflates the 5-letter list and pollutes the guess
  space.
- SCOWL contains all 26 single letters; English has two one-letter words (`a`, `i`). The L=1
  profile therefore needs an explicit policy rule, not a length filter `[R]`.

**Measured profile sizes `[R]` (ASCII `[a-z]` only, per length).**

| Profile | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|
| strict: SCOWL ≤50, American | 26 | 65 | 588 | 2,303 | 4,444 |
| extended: SCOWL ≤80 ∪ ENABLE | 26 | 148 | 1,223 | 5,059 | 11,411 |
| full: SCOWL ≤95 ∪ ENABLE | 26 | 276 | 2,000 | 7,441 | 17,410 |
| classic (5 only) | — | — | — | — | 2,315 answers / 12,972 guesses |

**Coverage of the classic game vocabulary `[R]`.**

| Open source | Answers covered | Allowed guesses covered |
|---|---|---|
| SCOWL ≤35 American | 1,914 / 2,315 (82.68%) | 3,461 / 12,972 (26.68%) |
| SCOWL ≤50 American | 2,205 / 2,315 (95.25%) | 4,440 / 12,972 (34.23%) |
| SCOWL ≤80 American | 2,282 / 2,315 (98.57%) | 10,901 / 12,972 (84.03%) |
| ENABLE | 2,306 / 2,315 (99.61%) | 8,635 / 12,972 (66.57%) |
| SCOWL ≤80 ∪ ENABLE | 2,313 / 2,315 (99.91%) | 11,223 / 12,972 (86.52%) |
| full open (SCOWL ≤95 ∪ ENABLE) | 2,313 / 2,315 (99.91%) | 12,159 / 12,972 (93.73%) |

**Conclusion.** No open lexicon reproduces Wordle's guess list, and the missing words are not
only obscure: `admin` and `cyber` are absent from every source measured. A classic profile that
silently substitutes an open list changes the game — different valid guesses, different opener,
different optimum. The profile system must therefore treat the classic lists as *user-supplied
data with recorded provenance*, and the benchmark must report which profile produced a number.

---

## 12. Performance and computational engineering

**Feedback representation.** `uint8` per (guess, answer) pair, one of 243 values at L=5 `[E]`.
Measured table sizes: classic 30,030,180 bytes = 28.64 MiB; strict L5 18.83 MiB; extended L5
124.18 MiB; full L5 289.07 MiB `[R]`.

**Memory policy.** Full precomputation for any profile whose table is under a configurable
budget (default 256 MiB) and whose dimensions are fixed; otherwise a hybrid: precompute the
`\|G\| × \|A\|` table only when `\|G\| · \|A\|` is under budget, else compute patterns on demand and
memoise an LRU of rows. A 512 MiB machine must still run the strict profile; the policy is a
documented knob, not a hardcoded assumption.

**Filtering.** Candidate sets as bitsets (`uint64` words: 203 words for 12,972 candidates `[E]`).
Given a guess row of the feedback table, filtering is a vectorised equality test plus popcount.
This is the hot loop; it is why numpy is a hard dependency rather than an optional one.

**Complexity.** Feedback computation `O(L)`; candidate filter `O(\|S\|)`; one-step scoring over all
guesses `O(\|G\| · \|S\|)` pattern comparisons, which the precomputed table turns into
`O(\|G\| · \|S\|)` byte comparisons in vectorised form; two-ply `O(\|G\| · \|S\|²)`; exact DP exponential
in the worst case.

**Parallelism.** Benchmark and policy generation are embarrassingly parallel over answers; a
`multiprocessing` pool with 16 workers on this machine `[R]` is the intended default. Python
threads do not help (GIL); numpy releases the GIL only for some operations, so process-level
parallelism is the deliberate choice.

**Why not C++ or Rust as the primary language.** The heavy inner loop is a vectorised table
gather, which numpy does at near-native speed. DP policy *generation* is the one place where a
native inner loop plausibly pays: it runs for hours to days `[P]`, so a 10× constant-factor win
matters. Rust is available on this machine `[R]` and is the recommended target for a single
optional crate, compiled through maturin, with a pure-Python fallback so the project never
depends on a toolchain the user may not have.

**GPU.** Not justified. The workload is memory-bound table lookups and branch-heavy recursion,
neither of which maps well; the measured tables fit in RAM and the published exact solver was
CPU-only `[P]`. No GPU dependency in v1.

---

## 13. Findings that change the design

1. **Openers are profile data.** Compute and cache per profile; never hardcode `SALET`.
2. **Entropy is a baseline.** The default composite must include expected remaining candidates,
   with entropy as a tie-break, and the benchmark must show which wins on each profile.
3. **Hard mode is three modes.** NYT-hard (reuse revealed letters, guess need not be a
   candidate), superhard (guess must be a candidate), and normal. They have different optima and
   different guarantee structures.
4. **Exactness needs an explicit boundary.** `\|A\| ≤ 5,000`, `\|G\| ≤ 20,000`, offline budget,
   recorded per profile with measured runtime.
5. **The classic profile cannot be inferred.** Coverage tops out at 93.73% of allowed guesses
   `[R]`; the lists must be supplied and versioned.
6. **Possessives, dialects and non-ASCII are first-class policy questions**, not cleanup
   details: 76,390 apostrophe entries and 23,753 dialect differences `[R]`.
7. **RL is out; distillation is in.** The ML budget goes to a value/policy model trained on DP
   output for infeasible profiles.
8. **Every result must name its profile, rules and prior.** A number without those three is not
   comparable to the published literature.

---

## 14. Final recommendation

| # | Decision | Rationale |
|---|---|---|
| 1 | **Primary algorithm:** exact DP policy for tractable profiles, shipped as a cached artifact | Proven optimal 3.4212 / max 5 `[P]`; deterministic and explainable |
| 2 | **Fallback:** one-step Bayesian expected-cost with entropy tie-break, escalating to 2-ply/rollout at `\|S\| ≤ 50` | Best measured cheap strategies are within ~0.04–0.08 of optimal `[P]` |
| 3 | **Exact DP scope:** classic and strict 5-letter, all profiles at L ≤ 3, plus L=4 strict if measured affordable | Measured table sizes and state growth `[R]`, `[E]` |
| 4 | **Default objective:** expected remaining candidates; entropy as tie-break; minimax selectable and used as a worst-case guard | Bin-count beat entropy in measurement `[P]`; minimax is tail insurance |
| 5 | **Prior:** uniform default; optional Zipf prior with temperature, calibrated and never used for validity | Uniform is correct for the shuffled classic list `[P]`; frequency priors need validation `[X]` |
| 6 | **ML:** distillation of DP policy/value into a small model for infeasible profiles; GBDT ranker as challenger | Only ML use with a plausible measured win; everything behind the numeric gate |
| 7 | **RL:** not justified for product; research appendix only | PPO ~4.3 avg at 97–98% vs 3.4212 optimal and 3.4600 heuristic `[P]` |
| 8 | **Dictionaries:** SCOWL + ENABLE as open foundation; classic lists user-supplied and never bundled; American default, British selectable; possessives and non-ASCII excluded by policy | Measured coverage and licence constraints `[R]` |
| 9 | **Stack:** Python 3.12 + numpy + Typer + pydantic + pytest/hypothesis + SQLite; optional Rust DP crate; no GPU, no server, no cloud | CPU-first, CLI-first, minimal infrastructure |
| 10 | **Sequence:** docs → lexicon+engine → classical solver → exact DP → simulator/bench → priors → ML → UI → hardening | Each phase gated on measured evidence, never on promise |

**Why this beats a letter-frequency solver, in numbers.** A letter heuristic averages 3.65 `[P]`;
this design targets 3.4212 on the classic profile (0.23 fewer guesses per game, ~6.3% relative)
and never exceeds 5 guesses, whereas the heuristic can need 6 `[P]`. In the tail the difference
is starker: the exact policy has no 6-guess games at all, and no failures. On a 365-puzzle year
that is roughly 84 fewer guesses and zero lost games. Those are the numbers the benchmark plan
requires the implementation to reproduce before release.

---

## Appendix A — Numbers ledger

| ID | Value | Tag | Source |
|---|---|---|---|
| N-01 | 2,315 classic answers, 12,972 allowed guesses, answers ⊆ guesses | `[R]` | measured, `data/processed/measurements.json` |
| N-02 | Classic feedback table 30,030,180 B = 28.64 MiB | `[R]` | N-01 arithmetic |
| N-03 | Optimal classic: 3.4212 avg, max 5, opener `salet` | `[P]` | Selby 2022; Bertsimas & Paskov 2025; Cunanan & Thielscher 2023 |
| N-04 | Hard-mode optimum 3.5084, opener `salet`; no 6-guarantee | `[P]` | Selby 2022 |
| N-05 | Superhard optimum `scamp` 3.7162 avg, max 5 | `[P]` | Greenberg 2024 |
| N-06 | 2023 config 3,158 answers / 14,855 guesses, optimum 3.5526, opener `tarse` | `[P]` | Selby part 3; wordle-opt reproduction |
| N-07 | No 4-guess strategy exists in normal mode | `[P]` | Selby 2022; Poirrier notes |
| N-08 | Bin-count heuristic 3.4600; entropy 3.4955; expected-bin 3.5210; maxbinsize 3.5844 (solution-word-only) | `[P]` | Greenberg 2024 |
| N-09 | Max-entropy with full guess list (`soare`) 3.476; ad-hoc 3.65 | `[P]` | Luebeck and Das, as tabulated in Greenberg 2024 |
| N-10 | Greedy breadth-1 total 7,944 (`trace`) vs optimal 7,920 (`salet`) | `[P]` | Cunanan & Thielscher 2023 |
| N-11 | NP-hard even at k=5; hard to approximate | `[P]` | Lokshtanov & Subercaseaux 2022 |
| N-12 | Winning-strategy decision NP-complete; `N^O(g)` algorithm | `[P]` | Rosenbaum 2022 |
| N-13 | Exact DP cost "days" on 64 cores | `[P]` | Bhambri et al. 2022, describing Bertsimas & Paskov |
| N-14 | PPO 97–98% / 4.3 avg under elimination win; BC 99.8% / 4.04; DQN fails | `[P]` | deep RL report (icwhite.github.io) |
| N-15 | 3^L = 3, 9, 27, 81, 243; all fit `uint8` | `[R]` | exact combinatorics |
| N-16 | SCOWL 2020.12.07 English-only 490,233; English+American 502,141; English+British 502,206 | `[R]` | measured |
| N-17 | American vs British symmetric difference 23,753 | `[R]` | measured |
| N-18 | SCOWL American ladder totals: 49,704 / 56,324 / 80,919 / 87,379 / 101,367 / 135,951 / 279,729 / 502,141 for sizes 35/40/50/55/60/70/80/95 | `[R]` | measured |
| N-19 | ENABLE 172,823 unique (L2 96, L3 972, L4 3,903, L5 8,636) | `[R]` | measured |
| N-20 | Broad open union 507,556 entries; 76,390 with apostrophes; 948 non-ASCII; 430,474 ASCII-alpha; 27,153 of length 1–5 | `[R]` | measured |
| N-21 | Profile L5 sizes: strict 4,444 / extended 11,411 / full 17,410 | `[R]` | measured |
| N-22 | Coverage of classic guesses: 93.73% (full open), 86.52% (SCOWL80∪ENABLE); 2 answers absent (`admin`, `cyber`) | `[R]` | measured |
| N-23 | Strict L5 table 18.83 MiB; extended 124.18 MiB; full 289.07 MiB | `[R]` | N-21 arithmetic |
| N-24 | WordleBot uses NYT answer-frequency priors | `[P]` | Katz & Conlen, NYT Upshot |
| N-25 | Intended DP boundary: `\|A\| ≤ 5,000`, `\|G\| ≤ 20,000` | `[E]` | engineering policy, to be validated |

## Appendix B — References

1. Selby, A. (2022). *The best strategies for Wordle.*
   https://sonorouschocolate.com/notes/index.php/The_best_strategies_for_Wordle ;
   part 2 (2022) and part 3, July 2023 (enlarged word list).
2. Bertsimas, D., Paskov, A. (2025). *An Exact Solution to Wordle.* Operations Research
   73(3):1384–1394. https://doi.org/10.1287/opre.2022.0434 . Preprint: *An Exact and
   Interpretable Solution to Wordle* (2022).
3. Cunanan, M., Thielscher, M. (2023). *On Optimal Strategies for Wordle and General Guessing
   Games.* IJCAI-23, pp. 5541–5548. https://doi.org/10.24963/ijcai.2023/615 ; arXiv:2305.09111.
4. Lokshtanov, D., Subercaseaux, B. (2022). *Wordle Is NP-Hard.* FUN 2022, LIPIcs 226.
   https://doi.org/10.4230/LIPIcs.FUN.2022.19 ; arXiv:2203.16713.
5. Rosenbaum, W. (2022). *Finding a Winning Strategy for Wordle is NP-complete.*
   arXiv:2204.04104. https://arxiv.org/abs/2204.04104
6. Bhambri, S., Bhattacharjee, A., Bertsekas, D. (2022). *Reinforcement Learning Methods for
   Wordle: A POMDP/Adaptive Control Approach.* arXiv:2211.10298.
   https://arxiv.org/abs/2211.10298
7. Greenberg, R. I. (2024, rev. 2026). *Effective Wordle Heuristics.* arXiv:2408.11730.
   https://arxiv.org/abs/2408.11730
8. *Reward and Exploration Strategies for Solving Wordle with Deep Reinforcement Learning*
   (2023). https://icwhite.github.io/website/papers/deep_woRdLe.pdf
9. Katz, J., Conlen, M. (2022). *Introducing WordleBot* and *Introducing WordleBot 2.0.*
   NYT Upshot. https://www.nytimes.com/2022/04/07/upshot/wordle-bot-introduction.html ;
   https://www.nytimes.com/2022/08/17/upshot/wordle-wordlebot-new.html
10. Poirrier, L. (2022). *Wordle-solving state of the art: all optimality results so far.*
    https://www.poirrier.ca/notes/wordle-optimal
11. wordle-opt, published word-list provenance and reproduction notes.
    https://github.com/rbmr/wordle-opt/blob/main/words/published/README.md
12. Atkinson, K. *SCOWL: Spell Checker Oriented Word Lists*, version 2020.12.07.
    https://wordlist.aspell.net/ ; https://github.com/en-wl/wordlist ; licence text in
    `data/raw/scowl/Copyright`.
13. *ENABLE 2K master word list* (public domain). README-enable2k.
14. Princeton University. *WordNet 3.0 licence and commercial use.*
    https://wordnet.princeton.edu/license-and-commercial-use
15. Speer, R. *wordfreq* (Apache-2.0 code; CC BY-SA 4.0 data). https://github.com/rspeer/wordfreq ;
    NOTICE.md; Zenodo DOI 10.5281/zenodo.7199437.
16. Shannon, C. E. (1948). *A Mathematical Theory of Communication.* Bell System Technical
    Journal 27:379–423, 623–656.
17. Bellman, R. (1957). *Dynamic Programming.* Princeton University Press.

## Appendix C — Evidence audit (what is not verified)

| Item | Status | Why |
|---|---|---|
| Bertsimas & Paskov full text | Abstract + preprint read | Journal version is paywalled; numbers cross-checked against Selby and Greenberg |
| Exact DP wall-clock on this machine | `[E]` only | No solver implemented in Phase 0 |
| Feasibility of L=4 extended exact DP | `[E]` | Threshold is a policy; must be measured in Phase 3 |
| wordfreq prior benefit | `[X]` | Requires calibration experiment with historical answers |
| ML distillation gain | `[X]` | Gate defined; not yet run |
| Open English WordNet licence | Verified | `LICENSE.md` confirms CC BY 4.0 plus the underlying Princeton WordNet licence, with attribution to both |
| Hard-mode numbers for the 3,158-answer list | Not published as far as located | Treat as unknown, not as an estimate |
| Any claim that entropy is "optimal" | Rejected | Contradicted by N-08 and N-10 |
