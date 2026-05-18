"""Factor evaluation framework — IC, quintiles, decay, correlations."""

from astrategy.evaluation.ic import compute_ic_series, summarize_ic
from astrategy.evaluation.quintile import (
    compute_quintile_returns,
    quintile_summary,
    quintile_turnover,
)
from astrategy.evaluation.decay import compute_decay_curve
from astrategy.evaluation.correlation import pairwise_factor_correlation
from astrategy.evaluation.runner import (
    EvaluationConfig,
    FactorEvaluation,
    evaluate_factor,
)


__all__ = [
    "compute_ic_series",
    "summarize_ic",
    "compute_quintile_returns",
    "quintile_summary",
    "quintile_turnover",
    "compute_decay_curve",
    "pairwise_factor_correlation",
    "EvaluationConfig",
    "FactorEvaluation",
    "evaluate_factor",
]
