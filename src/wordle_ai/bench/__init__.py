"""Benchmark aggregation, statistics, orchestration and reporting (Phase 4)."""

from .metrics import (
    RunResult,
    brier,
    determinism_hash,
    ece,
    log_loss,
    reliability_curve,
    summarise,
    top_k_hit_rate,
)
from .report import (
    aggregates_from_csv,
    compare_to_published,
    csv_rows,
    csv_text,
    format_table,
    markdown,
    parse_csv,
    payload,
    result_from_dict,
)
from .runner import RunSpec, execute, expand_matrix, run_key, run_matrix

__all__ = [
    "RunResult",
    "RunSpec",
    "aggregates_from_csv",
    "brier",
    "compare_to_published",
    "csv_rows",
    "csv_text",
    "determinism_hash",
    "ece",
    "execute",
    "expand_matrix",
    "format_table",
    "log_loss",
    "markdown",
    "parse_csv",
    "payload",
    "reliability_curve",
    "result_from_dict",
    "run_key",
    "run_matrix",
    "summarise",
    "top_k_hit_rate",
]
