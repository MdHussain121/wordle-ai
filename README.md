# wordle-ai

[![CI](https://github.com/wordle-ai/wordle-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/wordle-ai/wordle-ai/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)

A Wordle solver with a measured engine: deterministic strategies, an optional calibrated
answer prior, an exhaustive benchmark harness, a playable assistant and a thin HTTP
adapter. Solver decisions live in one service layer; the CLI, labs and HTTP surface only
orchestrate it.

The design documents (`WORDLE_AI_*.md`) are the source of truth for behaviour and gates.
This README is the quickstart and the recorded status.

## Install

Python 3.12 is required.

```bash
uv venv .venv
# Activate environment or use python directly
uv pip install -e ".[dev]"
```

Optional extras:

| Extra | Adds | Needed for |
|---|---|---|
| `prior` | `wordfreq` | the Zipf prior and its calibration |
| `http` | `fastapi`, `uvicorn` | `wordle_ai.api.http` |
| `dev` | `pytest`, `hypothesis`, `httpx` | the test suite |
| `ml` | `torch`, `scikit-learn`, `pyarrow` | Phase 6 ML distillation models & gates |

`rust` is a reserved extra (the standalone Rust DP kernel lives in `rust/wordle_core`).
Phase 6 machine learning models are available under the `ml` extra; the admitted neural value lookahead
strategy (`ml.value_lookahead`) ships behind `ml.enabled = false` by default.

## Data

Word lists are built locally from promoted sources pinned by SHA-256 in `sources.lock`.
Nothing derived is committed: `data/` and `policies/` are ignored.

```bash
wordle-ai lex fetch --source scowl --dest data/raw
wordle-ai lex fetch --source enable --dest data/raw
wordle-ai lex build --all --table auto
wordle-ai lex verify --all
```

The classic Wordle lists are user-supplied and never downloaded or redistributed:

```bash
wordle-ai lex fetch --source user \
  --answers data/user/classic_answers.txt \
  --guesses data/user/classic_guesses.txt --attest-license
```

## Web Studio & Interactive Copilot

For players and researchers who prefer an intuitive graphical interface over the terminal:

```bash
# Launch the local Web GUI Studio (automatically opens in your browser at http://localhost:8000)
wordle-ai web
```

Features included in the Web GUI:
- **Interactive Wordle Grid**: 6×5 board with click-to-cycle tile feedback (Gray &rarr; Yellow &rarr; Green) and on-screen keyboard.
- **Live AI Copilot**: Real-time recommendations powered by the provably optimal Exact DP policy or neural surrogate models, displaying candidate counts, win probabilities, and plain-language explanations.
- **Strategy Arena**: Real-time head-to-head comparison of all algorithms (Exact DP, Neural Value Lookahead, Information Entropy, Minimax, Policy Ranker) on the current board state with disagreement auditing.
- **AI Simulation**: Enter any secret word (or pick a random one) and watch the AI solve it step-by-step with full visual feedback and metrics.
- **Phase 6 ML Hub**: Interactive scorecard of G1–G8 admission gates, model parameter inspectability, and distillation metrics.
- **Dictionary Inspector**: Instant validation and lexicon status lookup for any 5-letter word.

## Play

```bash
# one game against a known answer, with a reason at every turn
wordle-ai play --profile classic.en.5 --answer cigar

# replay a real game and get the next recommendation
wordle-ai play --profile classic.en.5 --history "salet:BBYBB,horse:GBYBG"

# interactive: the assistant recommends, you paste the feedback
wordle-ai play --profile classic.en.5

# self-play: a trace for one game, aggregates for many
wordle-ai selfplay --profile classic.en.5 --games 1
wordle-ai selfplay --profile classic.en.5 --games 1000
```

`play` and `selfplay` share `SolverService` with the labs and the HTTP adapter, so a
decision is the same whichever surface asks for it.

## Labs and HTTP

```bash
wordle-ai lab strategies --profile classic.en.5 --strategies all
wordle-ai lab dictionary zzzzz --profile classic.en.5
wordle-ai diagnose --profile classic.en.5 --policy data/exact/subset12.policy.json
wordle-ai --version
```

The HTTP adapter is optional and importable without the CLI:

```python
from wordle_ai.api.http import create_app
from wordle_ai.api.service import SolverService
from wordle_ai.lexicon.profile import load_profile

profile = load_profile("data/processed/classic.en.5")
app = create_app(SolverService(profile))
```

It exposes `GET /health`, `GET /profile`, `POST /recommend`, `POST /compare` and
`POST /dictionary`; handlers only call the service layer.

## Machine Learning

Phase 6 implements zero-leakage DP distillation and G1–G8 admission gates:

```bash
# extract (state, guess, value) pairs from verified exact policy
wordle-ai ml extract --policy policies/classic.en.5.normal.uniform.policy.json

# train ValueNetwork, ValueRegressor, and PolicyRanker
wordle-ai ml train

# audit models against G1–G8 admission criteria
wordle-ai ml gate
```

## Benchmarks

```bash
wordle-ai bench run --profile classic.en.5 --strategies hybrid.balanced --workers 16
wordle-ai bench report --run <run_id> --format markdown
wordle-ai bench compare --run <A> --run <B>

python tools/measure_phase4.py   # Phase 4 matrix
python tools/measure_phase5.py   # prior calibration + AB-3
python tools/measure_phase8.py   # §17 performance budgets
python tools/run_release.py      # B-01…B-12 release set
```

Every number carries its provenance: profile digest, rules, prior, attempts, answer set,
package version and determinism hash.

## Verification

```bash
python -m pytest -q
python tools/check_docs.py
python tools/check_hardcoded.py
python tools/build_cli_reference.py --check
```

## Status

| Phase | State |
|---|---|
| 1 Lexicon and engine | done |
| 2 Classical solver | done |
| 3 Exact optimization | done; canonical exact DP policy published (B-01: 3.4212 avg) |
| 4 Simulator and benchmark | done |
| 5 Probabilistic intelligence | done; Zipf prior calibrated and rejected |
| 6 ML experimentation | done; distillation dataset extracted, models trained & gated |
| 7 Product interface | done (service, CLI, labs, HTTP, web studio) |
| 8 Optimization and readiness | packaging, `diagnose`, notices, docs and release set |

Performance budgets that are missed rather than met are recorded with their measured
values in `data/phase8/budgets_report.md`; the roadmap states the accepted trade-off.

## Contributing and Community

We welcome contributions! Please review our community guidelines:
- [Contributing Guide](CONTRIBUTING.md) — instructions for setting up the environment, testing, and pull requests.
- [Code of Conduct](CODE_OF_CONDUCT.md) — community standards and pledge.
- [Security Policy](SECURITY.md) — vulnerability reporting and disclosure policy.
- [Changelog](CHANGELOG.md) — release notes and version history.

## Licence and notices

The engine is distributed without word lists. See `THIRD_PARTY_NOTICES.md` for SCOWL,
ENABLE, wordfreq, FastAPI and the other dependencies, and for the rule that the classic
lists are never redistributed.
