"""Training and distillation pipelines for Phase 6 machine learning models.

Implements M-3, M-4, and M-5 from WORDLE_AI_ML_RESEARCH_AND_TRAINING_PLAN.md:
- Trains ValueRegressor (HistGradientBoosting) on exact DP values V(s).
- Trains ValueNetwork (PyTorch MLP) using Huber loss.
- Trains PolicyRanker on optimal DP decisions g*(s).
- Evaluates out-of-sample MAE, RMSE, and Top-1 accuracy on held-out validation/test splits.
- Exports versioned model checkpoints and SHA-256 sidecars.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from ..lexicon.profile import load_profile
from ..types import Profile
from .dataset import MLDataset, extract_dp_dataset, unpack_mask
from .features import StateFeatureExtractor
from .models import PolicyRanker, ValueNetwork, ValueRegressor


@dataclass
class DistillMetrics:
    model_name: str
    target: str
    train_mae: float
    val_mae: float
    test_mae: float
    train_rmse: float
    val_rmse: float
    test_rmse: float
    top1_accuracy: float | None = None
    top3_accuracy: float | None = None
    training_time_s: float = 0.0
    inference_p95_ms: float = 0.0


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float]:
    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    return mae, rmse


def measure_inference_p95(model, X_sample: np.ndarray, n_trials: int = 500) -> float:
    """Measure single-sample inference latency at p95."""
    latencies: list[float] = []
    sample = X_sample[0]
    for _ in range(n_trials):
        t0 = time.perf_counter()
        _ = model.predict_one(sample)
        latencies.append((time.perf_counter() - t0) * 1000.0)
    return float(np.percentile(latencies, 95))


def prepare_feature_arrays(
    dataset: MLDataset,
    extractor: StateFeatureExtractor,
) -> tuple[
    np.ndarray, np.ndarray, list[dict],
    np.ndarray, np.ndarray, list[dict],
    np.ndarray, np.ndarray, list[dict],
]:
    """Extract dense feature matrices and state records for train, val, and test splits."""
    def _extract_split(states_list: list[dict]):
        X_list = []
        y_val_list = []
        for s in states_list:
            mask = unpack_mask(s["state_sig"], extractor.num_answers)
            feat = extractor.extract_state(mask, s["turn"], s["attempts_left"])
            X_list.append(feat)
            y_val_list.append(s["expected_cost"])
        return (
            np.array(X_list, dtype=np.float32),
            np.array(y_val_list, dtype=np.float32),
            states_list,
        )

    X_train, y_v_train, states_train = _extract_split(dataset.unique_train_states)
    X_val, y_v_val, states_val = _extract_split(dataset.unique_val_states)
    X_test, y_v_test, states_test = _extract_split(dataset.unique_test_states)

    return (
        X_train, y_v_train, states_train,
        X_val, y_v_val, states_val,
        X_test, y_v_test, states_test,
    )


def prepare_ranking_data(
    states_list: list[dict],
    extractor: StateFeatureExtractor,
    answers: Sequence[str],
    guesses: Sequence[str],
    num_negatives: int = 4,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Build pairwise/pointwise training data for PolicyRanker.

    Positive examples (y=1.0): optimal guess chosen by DP.
    Negative examples (y=0.0): suboptimal candidate words.
    """
    rng = np.random.default_rng(seed)
    pairs_X: list[np.ndarray] = []
    pairs_y: list[float] = []

    for s in states_list:
        mask = unpack_mask(s["state_sig"], extractor.num_answers)
        state_feat = extractor.extract_state(mask, s["turn"], s["attempts_left"])
        cand_indices = np.flatnonzero(mask)
        cand_words = [answers[i] for i in cand_indices]
        cand_set = set(cand_words)

        opt_guess = s["optimal_guess"]
        unpos_freq = state_feat[6 : 6 + extractor.spec.unpositioned_dim]

        # Positive sample
        g_opt_feat = extractor.extract_guess_features(
            opt_guess, is_candidate=(opt_guess in cand_set), unpositioned_freq=unpos_freq
        )
        pairs_X.append(np.concatenate([state_feat, g_opt_feat]))
        pairs_y.append(1.0)

        # Negative samples from candidates
        non_opt = [w for w in cand_words if w != opt_guess]
        if non_opt:
            chosen_neg = rng.choice(non_opt, size=min(num_negatives, len(non_opt)), replace=False)
            for neg_w in chosen_neg:
                g_neg_feat = extractor.extract_guess_features(
                    neg_w, is_candidate=True, unpositioned_freq=unpos_freq
                )
                pairs_X.append(np.concatenate([state_feat, g_neg_feat]))
                pairs_y.append(0.0)

    return np.array(pairs_X, dtype=np.float32), np.array(pairs_y, dtype=np.float32)


def evaluate_ranker_accuracy(
    ranker: PolicyRanker,
    states_list: list[dict],
    extractor: StateFeatureExtractor,
    answers: Sequence[str],
) -> tuple[float, float]:
    """Evaluate Top-1 and Top-3 ranking accuracy on candidate sets."""
    top1 = 0
    top3 = 0
    evaluated = 0

    for s in states_list:
        opt_guess = s["optimal_guess"]
        mask = unpack_mask(s["state_sig"], extractor.num_answers)
        cand_indices = np.flatnonzero(mask)
        cand_words = [answers[i] for i in cand_indices]
        if not cand_words:
            continue

        state_feat = extractor.extract_state(mask, s["turn"], s["attempts_left"])
        unpos_freq = state_feat[6 : 6 + extractor.spec.unpositioned_dim]

        # Candidate words + optimal guess if outside
        pool = list(cand_words)
        if opt_guess not in pool:
            pool.append(opt_guess)

        cand_set = set(cand_words)
        guess_feats = np.array(
            [
                extractor.extract_guess_features(w, is_candidate=(w in cand_set), unpositioned_freq=unpos_freq)
                for w in pool
            ],
            dtype=np.float32,
        )

        ranked = ranker.rank_candidates(state_feat, pool, guess_feats)
        ranked_words = [w for w, _ in ranked]

        if ranked_words[0] == opt_guess:
            top1 += 1
        if opt_guess in ranked_words[:3]:
            top3 += 1
        evaluated += 1

    acc1 = top1 / max(evaluated, 1)
    acc3 = top3 / max(evaluated, 1)
    return acc1, acc3


def train_and_evaluate_all(
    dataset: MLDataset,
    profile: Profile,
    output_dir: Path = Path("models"),
) -> dict[str, DistillMetrics]:
    """Train all models, evaluate out-of-sample performance, and export artifacts."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    extractor = StateFeatureExtractor(profile)
    (
        X_train, y_v_train, states_train,
        X_val, y_v_val, states_val,
        X_test, y_v_test, states_test,
    ) = prepare_feature_arrays(dataset, extractor)

    results: dict[str, DistillMetrics] = {}

    # 1. Train ValueRegressor (HistGBDT)
    t0 = time.perf_counter()
    regressor = ValueRegressor(max_iter=200, max_depth=5, learning_rate=0.05)
    regressor.fit(X_train, y_v_train)
    reg_train_time = time.perf_counter() - t0

    reg_train_pred = regressor.predict_batch(X_train)
    reg_val_pred = regressor.predict_batch(X_val)
    reg_test_pred = regressor.predict_batch(X_test)

    r_train_mae, r_train_rmse = compute_metrics(y_v_train, reg_train_pred)
    r_val_mae, r_val_rmse = compute_metrics(y_v_val, reg_val_pred)
    r_test_mae, r_test_rmse = compute_metrics(y_v_test, reg_test_pred)
    r_p95 = measure_inference_p95(regressor, X_test)

    reg_path = output_dir / "value_regressor.joblib"
    regressor.save(reg_path)
    reg_sha = hashlib.sha256(reg_path.read_bytes()).hexdigest()
    reg_path.with_suffix(".joblib.sha256").write_text(reg_sha + "\n", encoding="utf-8")

    results["value_regressor"] = DistillMetrics(
        model_name="ValueRegressor (HistGBDT)",
        target="expected_remaining_turns",
        train_mae=r_train_mae,
        val_mae=r_val_mae,
        test_mae=r_test_mae,
        train_rmse=r_train_rmse,
        val_rmse=r_val_rmse,
        test_rmse=r_test_rmse,
        training_time_s=reg_train_time,
        inference_p95_ms=r_p95,
    )

    # 2. Train ValueNetwork (PyTorch MLP)
    t0 = time.perf_counter()
    net = ValueNetwork(input_dim=extractor.feature_dim, hidden_dim=128)
    net.train_epoch(X_train, y_v_train, epochs=150, batch_size=64, lr=1e-3, seed=42)
    net_train_time = time.perf_counter() - t0

    net_train_pred = net.predict_batch(X_train)
    net_val_pred = net.predict_batch(X_val)
    net_test_pred = net.predict_batch(X_test)

    n_train_mae, n_train_rmse = compute_metrics(y_v_train, net_train_pred)
    n_val_mae, n_val_rmse = compute_metrics(y_v_val, net_val_pred)
    n_test_mae, n_test_rmse = compute_metrics(y_v_test, net_test_pred)
    n_p95 = measure_inference_p95(net, X_test)

    net_path = output_dir / "value_network.pt"
    net.save(net_path)
    net_sha = hashlib.sha256(net_path.read_bytes()).hexdigest()
    net_path.with_suffix(".pt.sha256").write_text(net_sha + "\n", encoding="utf-8")

    results["value_network"] = DistillMetrics(
        model_name="ValueNetwork (PyTorch MLP)",
        target="expected_remaining_turns",
        train_mae=n_train_mae,
        val_mae=n_val_mae,
        test_mae=n_test_mae,
        train_rmse=n_train_rmse,
        val_rmse=n_val_rmse,
        test_rmse=n_test_rmse,
        training_time_s=net_train_time,
        inference_p95_ms=n_p95,
    )

    # 3. Train PolicyRanker (Pairwise/Pointwise GBDT)
    t0 = time.perf_counter()
    X_rank_train, y_rank_train = prepare_ranking_data(
        states_train, extractor, profile.answers, profile.guesses
    )
    ranker = PolicyRanker(max_iter=150, max_depth=5, learning_rate=0.05)
    ranker.fit(X_rank_train, y_rank_train)
    ranker_train_time = time.perf_counter() - t0

    acc1_test, acc3_test = evaluate_ranker_accuracy(
        ranker, states_test, extractor, profile.answers
    )
    ranker_p95 = measure_inference_p95(ranker, X_rank_train)

    ranker_path = output_dir / "policy_ranker.joblib"
    ranker.save(ranker_path)
    ranker_sha = hashlib.sha256(ranker_path.read_bytes()).hexdigest()
    ranker_path.with_suffix(".joblib.sha256").write_text(ranker_sha + "\n", encoding="utf-8")

    results["policy_ranker"] = DistillMetrics(
        model_name="PolicyRanker (HistGBDT)",
        target="optimal_guess",
        train_mae=0.0,
        val_mae=0.0,
        test_mae=0.0,
        train_rmse=0.0,
        val_rmse=0.0,
        test_rmse=0.0,
        top1_accuracy=acc1_test,
        top3_accuracy=acc3_test,
        training_time_s=ranker_train_time,
        inference_p95_ms=ranker_p95,
    )

    summary = {name: asdict(m) for name, m in results.items()}
    (output_dir / "training_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    return results
