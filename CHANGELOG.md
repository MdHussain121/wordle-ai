# Changelog

All notable changes to the Wordle AI project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-24

### Added
- **Exact Dynamic Programming Solver**:
  - Provably optimal policy solver reproducing the canonical 3.4212 turn benchmark on `classic.en.5`.
  - Zero-failure, 100% win-rate guarantee across all 2,315 target words with maximum depth of 5 guesses.
  - Accelerated Rust kernel fallback (`wordle_core`) with SIMD and Rayon concurrency.
- **Information Entropy & Heuristic Solvers**:
  - Fast information-theoretic entropy solver with candidate reduction metrics.
  - Minimax worst-case partition size minimizer.
  - Hybrid balanced heuristic combining entropy and candidate likelihood.
- **Interactive Web Studio**:
  - Full-featured React/StyleX/Vite web application (`wordle-ai web`).
  - Interactive 6×5 grid with cycling tile states (Gray &rarr; Yellow &rarr; Green).
  - Live AI Copilot providing step-by-step suggestions, probability estimates, and candidate count trees.
  - Step-by-step AI simulation mode with real-time visual solve playback.
- **Strategy Benchmark Arena**:
  - Head-to-head comparison panel across exact DP, entropy, minimax, and neural surrogate models.
  - Disagreement audit highlighting strategy divergence on identical game states.
- **Benchmark Suite & Lexicon Management**:
  - CLI commands for lexing, building CSR pattern tables, and verifying checksums.
  - Unified benchmarking harness with execution timing, turn distributions, and literature parity verification.
