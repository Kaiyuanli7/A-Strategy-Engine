"""Quintile bucketing + spread tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from astrategy.evaluation.quintile import (
    assign_quintiles,
    compute_quintile_returns,
    cumulative_quintile_returns,
    quintile_summary,
    quintile_turnover,
)


def test_assign_quintiles_basic():
    scores = pd.Series({f"S{i:02d}": float(i) for i in range(50)})
    buckets = assign_quintiles(scores, n=5)
    # Top 10 codes (highest scores) → bucket 1
    top = scores.nlargest(10).index
    assert all(buckets[c] == 1 for c in top)
    # Bottom 10 → bucket 5
    bottom = scores.nsmallest(10).index
    assert all(buckets[c] == 5 for c in bottom)


def test_assign_quintiles_handles_all_identical():
    scores = pd.Series({"A": 5.0, "B": 5.0, "C": 5.0, "D": 5.0, "E": 5.0})
    buckets = assign_quintiles(scores, n=5)
    # Fallback gives middle bucket
    assert (buckets == 3).all()


def test_compute_quintile_returns_perfect_signal_positive_spread():
    """When score and return are perfectly correlated, Q1 >> Q5."""
    np.random.seed(0)
    codes = [f"S{i:03d}" for i in range(50)]
    d1 = pd.Timestamp("2024-01-05")
    scores = pd.Series({c: float(i) for i, c in enumerate(codes)})
    rets = pd.Series({c: 0.001 * i for i, c in enumerate(codes)})
    qr = compute_quintile_returns({d1: scores}, {d1: rets}, n=5)
    assert qr.loc[d1, "Q1"] > qr.loc[d1, "Q5"]
    assert qr.loc[d1, "long_short"] > 0


def test_compute_quintile_returns_zero_spread_on_random():
    np.random.seed(42)
    codes = [f"S{i:03d}" for i in range(100)]
    d1 = pd.Timestamp("2024-01-05")
    scores = pd.Series({c: np.random.randn() for c in codes})
    rets = pd.Series({c: np.random.randn() * 0.01 for c in codes})
    qr = compute_quintile_returns({d1: scores}, {d1: rets}, n=5)
    # Spread should be near zero (within a few sigma)
    assert abs(qr.loc[d1, "long_short"]) < 0.01


def test_cumulative_quintile_returns_compounds():
    df = pd.DataFrame({
        "Q1": [0.01, 0.02], "Q2": [0.0, 0.0], "Q3": [0.0, 0.0],
        "Q4": [0.0, 0.0], "Q5": [-0.01, -0.02], "long_short": [0.02, 0.04],
    })
    cum = cumulative_quintile_returns(df)
    # Q1 cumulative = (1.01)(1.02) - 1
    assert abs(cum.iloc[-1]["Q1"] - ((1.01 * 1.02) - 1)) < 1e-9


def test_quintile_summary_monotone_signal():
    """Perfect signal: Q1 > Q2 > ... > Q5 → high monotonicity."""
    df = pd.DataFrame({
        "Q1": [0.05, 0.04], "Q2": [0.03, 0.025], "Q3": [0.01, 0.008],
        "Q4": [-0.01, -0.012], "Q5": [-0.03, -0.025], "long_short": [0.08, 0.065],
    })
    s = quintile_summary(df, n=5)
    assert s["long_short_mean"] > 0
    assert s["monotonicity"] > 0.9


def test_quintile_turnover_stable_factor():
    """Same scores at each rebalance → 0 turnover."""
    codes = [f"S{i:02d}" for i in range(20)]
    scores = pd.Series({c: float(i) for i, c in enumerate(codes)})
    d1, d2 = pd.Timestamp("2024-01-05"), pd.Timestamp("2024-01-12")
    t = quintile_turnover({d1: scores, d2: scores}, n=5)
    assert t == 0.0


def test_quintile_turnover_full_churn():
    codes = [f"S{i:02d}" for i in range(20)]
    s1 = pd.Series({c: float(i) for i, c in enumerate(codes)})
    s2 = pd.Series({c: float(-i) for i, c in enumerate(codes)})
    d1, d2 = pd.Timestamp("2024-01-05"), pd.Timestamp("2024-01-12")
    t = quintile_turnover({d1: s1, d2: s2}, n=5)
    # Reversing the order moves both ends across; expect high turnover.
    assert t > 0.5
