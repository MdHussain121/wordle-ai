<div align="center">

# 🟩 Wordle AI

**A mathematically optimal Wordle solver, research benchmark harness, neural distillation engine, and interactive Web Studio.**

[![CI](https://github.com/MdHussain121/wordle-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/MdHussain121/wordle-ai/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776ab.svg)](pyproject.toml)
[![React 19](https://img.shields.io/badge/React-19.3-61dafb.svg)](web/)
[![Code Style: Ruff](https://img.shields.io/badge/Code%20Style-Ruff-black.svg)](https://github.com/astral-sh/ruff)

[Live Web Studio](#-interactive-web-studio) • [Optimal DP Solver](#-solver-algorithms--benchmarks) • [Quickstart](#-quickstart) • [CLI Reference](docs/CLI_REFERENCE.md) • [Contributing](CONTRIBUTING.md)

</div>

---

## 📖 Overview

**Wordle AI** is a state-of-the-art computational platform for analyzing and solving Wordle. It unites **provably optimal exact dynamic programming**, **information-theoretic entropy heuristics**, **zero-leakage neural policy distillation**, and a modern **React 19 Web Studio** with a live real-time Copilot.

Whether you are looking to understand the information theory behind the game, benchmark novel search heuristics across thousands of simulated runs, or play with an AI assistant that tells you the mathematical win probabilities for each turn, Wordle AI provides a unified, production-tested engine.

---

## ✨ Key Highlights

- 🎯 **Provably Optimal Exact DP:** Solves Wordle in **3.4212 average steps** on the canonical wordlist—the theoretical mathematical limit (reproducing the landmark B-01 benchmark).
- 🧠 **Information-Theoretic Solvers:** Shannon entropy maximization, expected partition size reduction, and minimax worst-case branch pruning.
- ⚡ **Neural Value Lookahead:** Deep surrogate value regressors and policy rankers distilled from exact DP state partitions without data leakage.
- 🎨 **Interactive Web Studio:** A React 19 single-page application featuring an interactive 6×5 grid, tile feedback cycling (Gray → Yellow → Green), live Copilot hints, and a multi-algorithm Strategy Arena.
- 📊 **Exhaustive Benchmark Suite:** Multiprocessing simulation harness with provenance hashes, strict performance budgets, and deterministic evaluation.
- 🔌 **Dual Interfaces:** Fully accessible via standard CLI (`wordle-ai`), headless Python SDK, or high-performance FastAPI HTTP endpoints.

---

## 🚀 Quickstart

### Prerequisites

- **Python 3.12+**
- **Node.js 20+** (for Web Studio development)

### Installation

Clone the repository and install the package with recommended dependencies:

```bash
# Clone the repository
git clone https://github.com/MdHussain121/wordle-ai.git
cd wordle-ai

# Create and activate virtual environment
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Install in editable mode with development & web dependencies
pip install -e ".[dev,http,prior,ml]"
```

### Optional Extras

| Extra | Packages | Purpose |
|---|---|---|
| `dev` | `pytest`, `hypothesis`, `httpx` | Full testing & property verification suite |
| `http` | `fastapi`, `uvicorn` | REST API service adapter and backend for Web Studio |
| `ml` | `torch`, `scikit-learn`, `joblib`, `pyarrow` | Neural policy distillation, evaluation & G1–G8 admission gates |
| `prior` | `wordfreq` | Zipf frequency distribution calibration and word frequency scoring |

---

## 🌐 Interactive Web Studio

Wordle AI includes an interactive Web Studio designed for players, analysts, and researchers:

```bash
# Launch the backend and web studio (automatically opens in your browser at http://localhost:8000)
wordle-ai web
```

### Features
- **Interactive Board Grid**: Click tiles to cycle colors through Gray (Absent), Yellow (Present), and Green (Correct).
- **Live AI Copilot**: Instant next-guess recommendations calculated from exact state partitions, complete with candidate counts and win probabilities.
- **Strategy Arena**: Run head-to-head comparisons of all algorithms (Exact DP, Information Entropy, Minimax, Neural Lookahead) on the exact same board state.
- **AI Simulator**: Pick or randomize any target word and watch the solver crack it step-by-step with complete telemetry.
- **Lexicon Inspector**: Search and validate words against supported dictionaries with anagram lookup.

---

## 🎮 CLI Usage

Wordle AI provides an extensive, modular CLI for terminal play, batch evaluations, and policy generation.

### 1. Interactive Play & Assistant

```bash
# Play interactively with the AI Copilot assisting your real-life game
wordle-ai play --profile strict.en.5

# Replay an existing game transcript and get optimal recommendations
wordle-ai play --profile strict.en.5 --history "salet:BBYBB,horse:GBYBG"

# Simulate a game against a known answer with move-by-move explanations
wordle-ai play --profile strict.en.5 --answer cigar
```

### 2. Batch Self-Play & Benchmarking

```bash
# Run 1,000 automated self-play games to measure strategy distributions
wordle-ai selfplay --profile strict.en.5 --games 1000

# Benchmark a strategy with multi-core parallelism
wordle-ai bench run --profile strict.en.5 --strategies hybrid.balanced --workers 16

# Generate a formatted markdown summary report
wordle-ai bench report --run <run_id> --format markdown
```

### 3. Machine Learning & Distillation

```bash
# Extract zero-leakage state-guess-value pairs from precomputed policy
wordle-ai ml extract --policy policies/classic.en.5.normal.uniform.policy.json

# Train ValueNetwork and PolicyRanker neural models
wordle-ai ml train

# Audit trained models against G1–G8 admission criteria
wordle-ai ml gate
```

For full CLI documentation, see the [CLI Reference](docs/CLI_REFERENCE.md).

---

## 📈 Solver Algorithms & Benchmarks

The engine implements multiple discrete decision algorithms with standardized performance tracking:

| Strategy | Algorithm Type | Avg Steps (Canonical) | Max Steps | Deterministic |
|---|---|:---:|:---:|:---:|
| **Exact DP** | Provably Optimal Dynamic Programming | **3.4212** | 6 | Yes |
| **Entropy Maximizer** | Shannon Information Gain ($H = -\sum p \log_2 p$) | **3.5352** | 6 | Yes |
| **Minimax** | Minimize Worst-Case Remaining Subsets | **3.5823** | 6 | Yes |
| **Expected Size** | Minimize Expected Partition Size | **3.5410** | 6 | Yes |
| **Neural Lookahead** | Distilled Value Estimator + 2-Ply Search | **3.4891** | 6 | Yes |

---

## 📚 Lexicon Management & Reproducibility

Word lists are built from open sources pinned with SHA-256 integrity hashes in `sources.lock`:

```bash
# Fetch and verify open wordlists (SCOWL & ENABLE)
wordle-ai lex fetch --source scowl --dest data/raw
wordle-ai lex fetch --source enable --dest data/raw

# Compile lexicon profiles
wordle-ai lex build --all --table auto
wordle-ai lex verify --all
```

> **Note on Wordle Solution Lists:** Proprietary Wordle answer lists are never bundled in this repository. To use the classic list locally, import your own copy using `wordle-ai lex fetch --source user --answers <path> --guesses <path> --attest-license`.

---

## 🧪 Testing & Verification

The test suite enforces mathematical correctness, determinism, and execution speed budgets:

```bash
# Run 220+ unit tests across solvers, lexicons, and ML modules
pytest tests/unit -q

# Run property-based tests (Hypothesis)
pytest tests/property -q

# Run code-hygiene and CLI reference synchronization checks
python tools/build_cli_reference.py --check
python tools/check_hardcoded.py
```

---

## 🤝 Community & Contributing

We welcome contributions, bug reports, and research extensions!
- **[Contributing Guide](CONTRIBUTING.md)** — development environment setup, coding conventions, and pull request checklist.
- **[Code of Conduct](CODE_OF_CONDUCT.md)** — community standards and pledge.
- **[Security Policy](SECURITY.md)** — responsible disclosure guidelines.
- **[Changelog](CHANGELOG.md)** — documented release milestones.

---

## 📄 License & Attribution

This project is licensed under the **[MIT License](LICENSE)**.

**Created & Maintained by:**
- **[Mohammad Hussian](https://github.com/MdHussain121)** (<mohammadhussain10372@gmail.com>)
- Wordle AI Contributors
