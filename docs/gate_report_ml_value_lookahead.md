# Phase 6 ML Admission Gate Report: ml.value_lookahead

**Profile:** `classic.en.5`  
**Verdict:** `ADMITTED`  
**Summary:** All 8 admission gates PASSED. Model 'ml.value_lookahead' qualifies for product admission under flag ml.enabled = false.

## Gate Criteria Results (G1–G8)

| Gate | Metric | Baseline | Model | Delta | Threshold | Pass? |
|---|---|---|---|---|---|---|
| G1 | Average Guesses | 3.6696 | 3.6023 | +0.0673 | improvement >= 0.02 | PASS |
| G2 | Worst-Case Turns | 5 | 5 | +0 | <= baseline | PASS |
| G3 | Failure Rate | 0.00% | 0.00% | +0.00% | <= baseline (0%) | PASS |
| G4 | Decision Latency (p95) | 18085.24 ms | 17929.42 ms | -155.81 ms | added p95 <= 5.0 ms | PASS |
| G5 | Cross-Profile Check | 0.0000 | 0.0000 | +0.0000 | regression <= 0.02 | PASS |
| G6 | Calibration (ECE) | < 0.05 | 0.0150 | 0.0150 | < 0.05 | PASS |
| G7 | Reproducibility | true | det=True, sha=True | ok | deterministic + checksum | PASS |
| G8 | Explainability | true | True | ok | renderable breakdown | PASS |

### Detailed Rationales
- **G1 (Average Guesses):** Delta is +0.0673; requires >= +0.02 improvement.
- **G2 (Worst-Case Turns):** Model worst-case is 5 vs baseline 5.
- **G3 (Failure Rate):** Model failure rate is 0.00%.
- **G4 (Decision Latency (p95)):** Added latency is -155.81 ms (budget 5.0 ms).
- **G5 (Cross-Profile Check):** Cross-profile delta is +0.0000 (threshold <= 0.02).
- **G6 (Calibration (ECE)):** Expected calibration error is 0.0150.
- **G7 (Reproducibility):** Deterministic inference with versioned weights and SHA-256 sidecar.
- **G8 (Explainability):** Model decisions include breakdown features and confidence values.
