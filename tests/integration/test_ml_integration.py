"""Integration tests for Phase 6 Machine Learning pipelines and strategies."""

from __future__ import annotations

from pathlib import Path

import pytest

from wordle_ai.api.service import SolverService
from wordle_ai.lexicon.profile import load_profile
from wordle_ai.ml.dataset import extract_dp_dataset, verify_leakage
from wordle_ai.ml.strategy import LearnedRankerStrategy, LearnedValueStrategy


@pytest.fixture(scope="module")
def classic_profile():
    return load_profile(Path("data/processed/classic.en.5"))


def test_dataset_extraction_and_zero_leakage(classic_profile):
    policy_path = Path("policies/classic.en.5.normal.uniform.policy.json")
    if not policy_path.exists():
        pytest.skip("Exact DP policy artifact not present")

    dataset = extract_dp_dataset(policy_path, classic_profile)
    verify_leakage(dataset.split)

    assert len(dataset.trajectories) == 7920
    assert len(dataset.unique_train_states) > 1000
    assert len(dataset.unique_val_states) > 200
    assert len(dataset.unique_test_states) > 200


def test_learned_strategies_play_game(classic_profile):
    # Test LearnedValueStrategy on a real game
    service_val = SolverService(classic_profile, strategy="ml.value_lookahead")
    turns_val, solved_val = service_val.play("cigar")
    assert solved_val is True
    assert 1 <= len(turns_val) <= 6

    # Test LearnedRankerStrategy on a real game
    service_rank = SolverService(classic_profile, strategy="ml.policy_ranker")
    turns_rank, solved_rank = service_rank.play("cigar")
    assert solved_rank is True
    assert 1 <= len(turns_rank) <= 6
