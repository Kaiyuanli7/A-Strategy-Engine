"""Information Coefficient: cross-sectional rank correlation of factor with forward returns."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats


def spearman_ic(scores: pd.Series, forward_returns: pd.Series) -> float:
    """
    Spearman rank correlation between aligned factor scores and forward returns.

    Drops NaNs from both sides. Returns NaN if < 3 paired observations remain.
    """
    df = pd.concat([scores.rename("score"), forward_returns.rename("ret")], axis=1).dropna()
    if len(df) < 3:
        return float("nan")
    result = stats.spearmanr(df["score"], df["ret"])
    rho = getattr(result, "statistic", None)
    if rho is None:
        rho = getattr(result, "correlation", None)
    if rho is None:
        return float("nan")
    rho = float(rho)
    if math.isnan(rho):
        return float("nan")
    return rho


def compute_ic_series(
    scores_by_date: dict[pd.Timestamp, pd.Series],
    forward_returns_by_date: dict[pd.Timestamp, pd.Series],
) -> pd.Series:
    """
    IC per rebalance date. Dates with no pairwise data are dropped.

    `scores_by_date[d]` and `forward_returns_by_date[d]` are both Series
    indexed by stock code. Mismatches are dropped pairwise.
    """
    out: dict[pd.Timestamp, float] = {}
    for date, scores in scores_by_date.items():
        fwd = forward_returns_by_date.get(date)
        if fwd is None or scores is None:
            continue
        ic = spearman_ic(scores, fwd)
        if not math.isnan(ic):
            out[date] = ic
    if not out:
        return pd.Series(dtype="float64", name="ic")
    series = pd.Series(out, name="ic").sort_index()
    return series


def summarize_ic(ic_series: pd.Series) -> dict:
    """Mean / std / IR / hit rate / t-stat of an IC series."""
    if ic_series.empty:
        return {
            "mean": 0.0, "std": 0.0, "ir": 0.0,
            "hit_rate": 0.0, "t_stat": 0.0, "n": 0,
        }
    arr = ic_series.dropna().values
    n = int(arr.size)
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    ir = mean / std if std > 0 else 0.0
    hit_rate = float(np.mean(arr > 0))
    t_stat = mean / (std / math.sqrt(n)) if std > 0 and n > 1 else 0.0
    return {
        "mean": mean,
        "std": std,
        "ir": float(ir),
        "hit_rate": hit_rate,
        "t_stat": float(t_stat),
        "n": n,
    }
