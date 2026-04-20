"""TPOT predictor package."""

from .tpot_predictor import (
    collect_tpot_matrix,
    run_default_benchmark,
    summarize_results,
)

__all__ = [
    "collect_tpot_matrix",
    "run_default_benchmark",
    "summarize_results",
]
