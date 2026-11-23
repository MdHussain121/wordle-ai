"""Configuration loading and validation (technical specification §16).

Every key in ``config/default.toml`` is modelled here so that an unknown key or an
out-of-range value fails with the key path, not a silent default.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .errors import ConfigError

DEFAULT_CONFIG_PATH = Path("config/default.toml")


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GeneralSettings(_Section):
    data_dir: str = "data"
    cache_dir: str = "data/processed/cache"
    deterministic: bool = True


class ProfileSettings(_Section):
    language: str = "en"
    length: int = Field(default=5, ge=1, le=5)
    alphabet: str = "abcdefghijklmnopqrstuvwxyz"

    @field_validator("alphabet")
    @classmethod
    def _distinct(cls, value: str) -> str:
        if not value or len(set(value)) != len(value):
            raise ValueError("alphabet must be non-empty with distinct symbols")
        return value


class RulesSettings(_Section):
    mode: Literal["normal", "hard", "superhard"] = "normal"
    max_attempts: int = Field(default=6, ge=1, le=12)


class PriorSettings(_Section):
    kind: Literal["uniform", "zipf", "empirical"] = "uniform"
    beta: float = 0.0
    empirical_path: str = ""


class FeedbackSettings(_Section):
    table_max_bytes: int = Field(default=268_435_456, ge=0)
    build_policy: Literal["auto", "full", "none", "hybrid"] = "auto"
    lru_rows: int = Field(default=2048, ge=0)


class StrategySettings(_Section):
    default: str = "hybrid.balanced"
    top_n_lookahead: int = Field(default=12, ge=1)
    lookahead_max_candidates: int = Field(default=50, ge=1)
    rollout_max_candidates: int = Field(default=25, ge=1)
    pairwise_limit: int = Field(default=20_000_000, ge=1)
    tie_epsilon: float = 1e-12


class ExactSettings(_Section):
    max_answers: int = Field(default=5000, ge=1)
    max_guesses: int = Field(default=20_000, ge=1)
    memo_max_entries: int = Field(default=2_000_000, ge=1)
    time_budget_s: int = Field(default=86400, ge=1)
    parallel_root: bool = True


class BenchSettings(_Section):
    answers: str = "all"
    seed: int = 20261119
    workers: int = Field(default=16, ge=1)
    bootstrap_samples: int = Field(default=10_000, ge=1)


class MLSettings(_Section):
    enabled: bool = False
    model_path: str = ""
    max_decision_ms: float = Field(default=5.0, gt=0)
    min_avg_improvement: float = 0.02


class ProfileFamily(_Section):
    scowl_size: int = Field(default=0, ge=0, le=95)
    include_enable: bool = False
    answer_policy: Literal["same", "file"] = "same"
    answers_path: str = ""
    guesses_path: str = ""


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    general: GeneralSettings = GeneralSettings()
    profile: ProfileSettings = ProfileSettings()
    rules: RulesSettings = RulesSettings()
    prior: PriorSettings = PriorSettings()
    feedback: FeedbackSettings = FeedbackSettings()
    strategy: StrategySettings = StrategySettings()
    exact: ExactSettings = ExactSettings()
    bench: BenchSettings = BenchSettings()
    ml: MLSettings = MLSettings()
    profiles: dict[str, ProfileFamily] = Field(default_factory=dict)

    def family(self, name: str) -> ProfileFamily:
        try:
            return self.profiles[name]
        except KeyError:
            raise ConfigError(
                f"unknown profile family {name!r}; configured: {sorted(self.profiles)}",
                family=name,
            ) from None


def load_config(path: str | Path | None = None) -> Settings:
    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not target.exists():
        raise ConfigError(f"configuration file not found: {target}", path=str(target))
    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{target}: invalid TOML: {exc}", path=str(target)) from exc
    try:
        return Settings.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{target}: {exc}", path=str(target)) from exc


def dump_settings(settings: Settings) -> dict:
    return settings.model_dump(mode="json")
