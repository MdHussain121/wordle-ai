"""Machine learning model architectures for Wordle value distillation and policy ranking.

Implements WORDLE_AI_ML_RESEARCH_AND_TRAINING_PLAN.md:
- ValueNetwork: PyTorch MLP estimating expected remaining turns V(s) with Huber loss.
- ValueRegressor: Scikit-learn HistGradientBoostingRegressor baseline.
- PolicyRanker: Fast ranking model over candidate guesses using state+guess features.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Sequence

import joblib
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.ensemble import HistGradientBoostingRegressor

from ..errors import ArtifactMismatchError


class ValueMLP(nn.Module):
    """PyTorch MLP mapping state features to expected remaining turns V(s)."""

    def __init__(self, input_dim: int, hidden_dim: int = 128) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


class ValueNetwork:
    """Wrapper around PyTorch ValueMLP supporting training, saving, loading and numpy inference."""

    def __init__(self, input_dim: int = 162, hidden_dim: int = 128) -> None:
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.model = ValueMLP(input_dim, hidden_dim)
        self.model.eval()

    def predict_one(self, feature_vec: np.ndarray) -> float:
        """Single-sample CPU prediction with minimal tensor overhead."""
        with torch.no_grad():
            tensor = torch.from_numpy(np.ascontiguousarray(feature_vec, dtype=np.float32)).unsqueeze(0)
            val = self.model(tensor).item()
            return float(val)

    def predict_batch(self, feature_matrix: np.ndarray) -> np.ndarray:
        """Batch prediction over 2D array (N, input_dim)."""
        with torch.no_grad():
            tensor = torch.from_numpy(np.ascontiguousarray(feature_matrix, dtype=np.float32))
            return self.model(tensor).cpu().numpy()

    def train_epoch(
        self,
        X: np.ndarray,
        y: np.ndarray,
        *,
        epochs: int = 100,
        batch_size: int = 64,
        lr: float = 1e-3,
        weight_decay: float = 1e-4,
        seed: int = 42,
    ) -> list[float]:
        """Fit with Huber loss and Adam optimizer."""
        torch.manual_seed(seed)
        np.random.seed(seed)

        self.model.train()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr, weight_decay=weight_decay)

        X_t = torch.from_numpy(np.ascontiguousarray(X, dtype=np.float32))
        y_t = torch.from_numpy(np.ascontiguousarray(y, dtype=np.float32))
        n_samples = len(X)
        losses: list[float] = []

        for _ in range(epochs):
            indices = np.random.permutation(n_samples)
            epoch_loss = 0.0
            steps = 0

            for start in range(0, n_samples, batch_size):
                end = min(start + batch_size, n_samples)
                batch_idx = indices[start:end]

                batch_x = X_t[batch_idx]
                batch_y = y_t[batch_idx]

                optimizer.zero_grad()
                pred = self.model(batch_x)
                loss = F.huber_loss(pred, batch_y, delta=1.0)
                loss.backward()
                optimizer.step()

                epoch_loss += loss.item()
                steps += 1

            losses.append(epoch_loss / max(steps, 1))

        self.model.eval()
        return losses

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "input_dim": self.input_dim,
            "hidden_dim": self.hidden_dim,
            "state_dict": {k: v.cpu() for k, v in self.model.state_dict().items()},
        }
        torch.save(payload, path)

    @classmethod
    def load(cls, path: Path) -> ValueNetwork:
        path = Path(path)
        payload = torch.load(path, map_location="cpu")
        net = cls(input_dim=payload["input_dim"], hidden_dim=payload["hidden_dim"])
        net.model.load_state_dict(payload["state_dict"])
        net.model.eval()
        return net


class ValueRegressor:
    """Fast Scikit-learn HistGradientBoostingRegressor baseline for V(s)."""

    def __init__(self, max_iter: int = 200, max_depth: int = 5, learning_rate: float = 0.05) -> None:
        self.model = HistGradientBoostingRegressor(
            max_iter=max_iter,
            max_depth=max_depth,
            learning_rate=learning_rate,
            random_state=42,
        )
        self.is_fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        self.model.fit(X, y)
        self.is_fitted = True

    def predict_one(self, feature_vec: np.ndarray) -> float:
        if not self.is_fitted:
            raise ValueError("Model is not fitted yet.")
        pred = self.model.predict(feature_vec.reshape(1, -1))[0]
        return float(pred)

    def predict_batch(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            raise ValueError("Model is not fitted yet.")
        return self.model.predict(X)

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, path)

    @classmethod
    def load(cls, path: Path) -> ValueRegressor:
        reg = cls()
        reg.model = joblib.load(path)
        reg.is_fitted = True
        return reg


class PolicyRanker:
    """Pointwise/shortlist GBDT ranker scoring candidate guesses."""

    def __init__(self, max_iter: int = 150, max_depth: int = 5, learning_rate: float = 0.05) -> None:
        self.model = HistGradientBoostingRegressor(
            max_iter=max_iter,
            max_depth=max_depth,
            learning_rate=learning_rate,
            random_state=42,
        )
        self.is_fitted = False

    def fit(self, X_pairs: np.ndarray, y_scores: np.ndarray) -> None:
        """Fit ranker on concatenated [state_features, guess_features]."""
        self.model.fit(X_pairs, y_scores)
        self.is_fitted = True

    def score_candidates(
        self,
        state_features: np.ndarray,
        guess_features_batch: np.ndarray,
    ) -> np.ndarray:
        """Score a batch of candidates for a single state."""
        if not self.is_fitted:
            raise ValueError("Ranker is not fitted.")
        n_cands = len(guess_features_batch)
        tiled_state = np.tile(state_features, (n_cands, 1))
        X_combined = np.hstack([tiled_state, guess_features_batch])
        return self.model.predict(X_combined)

    def rank_candidates(
        self,
        state_features: np.ndarray,
        candidates: Sequence[str],
        guess_features_batch: np.ndarray,
    ) -> list[tuple[str, float]]:
        """Return candidates sorted descending by predicted preference score."""
        scores = self.score_candidates(state_features, guess_features_batch)
        scored = list(zip(candidates, (float(s) for s in scores)))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored

    def predict_one(self, feature_vec: np.ndarray) -> float:
        if not self.is_fitted:
            raise ValueError("Ranker is not fitted.")
        return float(self.model.predict(feature_vec.reshape(1, -1))[0])

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, path)

    @classmethod
    def load(cls, path: Path) -> PolicyRanker:
        ranker = cls()
        ranker.model = joblib.load(path)
        ranker.is_fitted = True
        return ranker
