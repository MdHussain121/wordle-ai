"""Machine Learning research, feature extraction, distillation and gates (Phase 6).

Governed by WORDLE_AI_ML_RESEARCH_AND_TRAINING_PLAN.md:
classical algorithms are the baseline, and ML is admitted only by measurement.
"""

from __future__ import annotations

from .dataset import (
    AnswerSplit,
    MLDataset,
    extract_dp_dataset,
    split_answers_by_word,
    verify_leakage,
)
from .features import StateFeatureExtractor, extract_state_features
from .models import ValueNetwork, ValueRegressor, PolicyRanker
from .gate import GateReport, evaluate_gate_criteria

__all__ = [
    "AnswerSplit",
    "MLDataset",
    "extract_dp_dataset",
    "split_answers_by_word",
    "verify_leakage",
    "StateFeatureExtractor",
    "extract_state_features",
    "ValueNetwork",
    "ValueRegressor",
    "PolicyRanker",
    "GateReport",
    "evaluate_gate_criteria",
]
