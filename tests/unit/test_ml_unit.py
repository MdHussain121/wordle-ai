"""Unit tests for Phase 6 Machine Learning modules."""

from __future__ import annotations

import numpy as np
import pytest

from wordle_ai.ml.dataset import AnswerSplit, split_answers_by_word, verify_leakage
from wordle_ai.ml.features import StateFeatureExtractor
from wordle_ai.ml.gate import evaluate_gate_criteria
from wordle_ai.ml.models import PolicyRanker, ValueNetwork, ValueRegressor
from wordle_ai.types import Profile


@pytest.fixture
def sample_profile() -> Profile:
    raw_answers = ("cigar", "rebut", "sissy", "humph", "awake", "blush", "focal", "evade")
    answers = tuple(sorted(raw_answers))
    guesses = tuple(sorted(raw_answers + ("salet", "roate", "tares")))
    return Profile(
        profile_id="test.en.5",
        language="en",
        dialect="test",
        length=5,
        alphabet="abcdefghijklmnopqrstuvwxyz",
        answers=answers,
        guesses=guesses,
        manifest_sha256="0" * 64,
        source_ids=("test",),
        answer_index={w: i for i, w in enumerate(answers)},
        guess_index={w: i for i, w in enumerate(guesses)},
    )


def test_answer_split_zero_leakage():
    answers = [f"word{i:04d}" for i in range(100)]
    split = split_answers_by_word(answers, train_pct=70, val_pct=15)

    assert len(split.train) > 0
    assert len(split.validation) > 0
    assert len(split.test) > 0
    assert split.total == 100

    # Assert pairwise disjoint
    assert set(split.train).isdisjoint(set(split.validation))
    assert set(split.train).isdisjoint(set(split.test))
    assert set(split.validation).isdisjoint(set(split.test))


def test_verify_leakage_raises_on_overlap():
    leaky_split = AnswerSplit(
        train=("apple", "banana"),
        validation=("cherry", "apple"),  # overlap!
        test=("date",),
    )
    with pytest.raises(ValueError, match="Data leakage detected"):
        verify_leakage(leaky_split)


def test_feature_extractor_dimensions_and_properties(sample_profile: Profile):
    extractor = StateFeatureExtractor(sample_profile)
    expected_dim = 6 + 26 + (5 * 26)  # 162
    assert extractor.feature_dim == expected_dim

    # All candidates active
    mask = np.ones(len(sample_profile.answers), dtype=bool)
    features = extractor.extract_state(mask, turn=0, attempts_left=6)

    assert features.shape == (expected_dim,)
    assert features.dtype == np.float32
    assert features[0] == len(sample_profile.answers)  # count
    assert np.all(np.isfinite(features))


def test_value_network_forward():
    net = ValueNetwork(input_dim=162, hidden_dim=64)
    x = np.random.randn(162).astype(np.float32)
    val = net.predict_one(x)
    assert isinstance(val, float)
    assert np.isfinite(val)

    batch_x = np.random.randn(10, 162).astype(np.float32)
    batch_val = net.predict_batch(batch_x)
    assert batch_val.shape == (10,)


def test_value_regressor_fit_predict():
    reg = ValueRegressor(max_iter=10)
    X = np.random.randn(20, 162).astype(np.float32)
    y = np.random.uniform(1.0, 5.0, size=20).astype(np.float32)
    reg.fit(X, y)

    pred = reg.predict_one(X[0])
    assert isinstance(pred, float)
    assert np.isfinite(pred)


def test_policy_ranker_ranking():
    ranker = PolicyRanker(max_iter=10)
    X = np.random.randn(20, 167).astype(np.float32)
    y = np.array([1.0, 0.0] * 10, dtype=np.float32)
    ranker.fit(X, y)

    state_feat = np.random.randn(162).astype(np.float32)
    guess_feats = np.random.randn(5, 5).astype(np.float32)
    candidates = ["cigar", "rebut", "sissy", "humph", "awake"]

    ranked = ranker.rank_candidates(state_feat, candidates, guess_feats)
    assert len(ranked) == 5
    assert all(isinstance(w, str) and isinstance(s, float) for w, s in ranked)


def test_gate_criteria_evaluation():
    # Test passing case
    report_pass = evaluate_gate_criteria(
        model_name="test_model",
        profile_id="classic.en.5",
        baseline_avg_guesses=3.6696,
        model_avg_guesses=3.6023,  # improvement 0.0673 >= 0.02
        baseline_worst_case=5,
        model_worst_case=5,
        baseline_failure_rate=0.0,
        model_failure_rate=0.0,
        baseline_p95_ms=10.0,
        model_p95_ms=12.0,  # +2.0 ms <= 5.0 ms
        cross_profile_delta=0.01,
        ece=0.02,
        is_deterministic=True,
        has_checksum=True,
        has_explanation=True,
    )
    assert report_pass.passed_all is True
    assert report_pass.verdict == "admitted"

    # Test failing case (insufficient improvement)
    report_fail = evaluate_gate_criteria(
        model_name="failing_model",
        profile_id="classic.en.5",
        baseline_avg_guesses=3.6696,
        model_avg_guesses=3.6600,  # only 0.0096 improvement < 0.02
        baseline_worst_case=5,
        model_worst_case=6,  # worse max turns!
        baseline_failure_rate=0.0,
        model_failure_rate=0.01,
        baseline_p95_ms=10.0,
        model_p95_ms=18.0,
    )
    assert report_fail.passed_all is False
    assert report_fail.verdict == "rejected"
