# Phase 6 ML Admission Gate Report: ml.policy_ranker

**Profile:** `classic.en.5`  
**Verdict:** `REJECTED`  
**Summary:** Gate check FAILED on: G1, G2, G3. Per Phase 6 governing rules, classical algorithm remains primary and model is REJECTED.

## Gate Criteria Results (G1–G8)

| Gate | Metric | Baseline | Model | Delta | Threshold | Pass? |
|---|---|---|---|---|---|---|
| G1 | Average Guesses | 3.6696 | 4.0292 | -0.3596 | improvement >= 0.02 | FAIL |
| G2 | Worst-Case Turns | 5 | 6 | +1 | <= baseline | FAIL |
| G3 | Failure Rate | 0.00% | 0.58% | +0.58% | <= baseline (0%) | FAIL |
| G4 | Decision Latency (p95) | 18085.24 ms | 18029.05 ms | -56.19 ms | added p95 <= 5.0 ms | PASS |
| G5 | Cross-Profile Check | 0.0000 | 0.0000 | +0.0000 | regression <= 0.02 | PASS |
| G6 | Calibration (ECE) | < 0.05 | 0.0150 | 0.0150 | < 0.05 | PASS |
| G7 | Reproducibility | true | det=True, sha=True | ok | deterministic + checksum | PASS |
| G8 | Explainability | true | True | ok | renderable breakdown | PASS |

### Detailed Rationales
- **G1 (Average Guesses):** Delta is -0.3596; requires >= +0.02 improvement.
- **G2 (Worst-Case Turns):** Model worst-case is 6 vs baseline 5.
- **G3 (Failure Rate):** Model failure rate is 0.58%.
- **G4 (Decision Latency (p95)):** Added latency is -56.19 ms (budget 5.0 ms).
- **G5 (Cross-Profile Check):** Cross-profile delta is +0.0000 (threshold <= 0.02).
- **G6 (Calibration (ECE)):** Expected calibration error is 0.0150.
- **G7 (Reproducibility):** Deterministic inference with versioned weights and SHA-256 sidecar.
- **G8 (Explainability):** Model decisions include breakdown features and confidence values.
