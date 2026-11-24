# Wordle AI Studio

The interactive web frontend and AI copilot interface for **Wordle AI**.

Wordle AI Studio provides an accessible, responsive graphical studio for players, researchers, and algorithm developers to play Wordle with AI assistance, run live simulations, and compare solver heuristics in real time.

## Key Features

- **Interactive 6×5 Wordle Grid**:
  - Full keyboard and mouse input with physical or on-screen keyboard.
  - Click-to-cycle tile feedback (Gray / Absent &rarr; Yellow / Present &rarr; Green / Correct) for replaying past games or testing hypothetical boards.
- **Live AI Copilot**:
  - Instant move recommendations powered by the provably optimal Exact DP decision policy or neural surrogate models.
  - Candidate remaining count, win probability estimates, and plain-language reasoning.
- **Strategy Arena**:
  - Head-to-head comparative analysis of algorithms: Exact DP, Neural Value Lookahead, Information Entropy, and Minimax.
  - Disagreement audit highlighting where and why strategies diverge on the current board.
- **AI Step-by-Step Simulation**:
  - Enter any secret word (or pick a random solution) and watch the AI solve it step-by-step with real-time tile animation and latency stats.
- **Phase 6 ML Diagnostics**:
  - Admission gate inspectability (G1–G8), model parameter inspectability, and training metrics.
- **Dictionary & Lexicon Inspector**:
  - Fast validation and status lookup across 12,972 allowable words and 2,315 solutions.

## Technology Stack

- **Framework**: React 19 + TypeScript
- **Styling**: StyleX (`@stylexjs/stylex`) with Astryx Design tokens (`@astryxdesign/core`, `@astryxdesign/theme-neutral`)
- **Icons**: Lucide React (`lucide-react`)
- **Bundler & Tooling**: Vite 8, TypeScript 7, Oxlint

## Development & Build

### Running Locally

```bash
# 1. Install dependencies
npm install

# 2. Start Vite development server
npm run dev
```

The Vite dev server runs at `http://localhost:5173` and proxies API requests to the Python FastAPI backend (`http://localhost:8000`).

### Production Build

```bash
# Type check and bundle for production
npm run build
```

Assets are built into `web/dist/`, which can be served directly by the Python CLI via `wordle-ai web`.

### Linting

```bash
npm run lint
```
