"""Tests for market regime classification."""

import numpy as np
import pandas as pd
import pytest

from astrategy.engine.regime import (
    REGIME_LABELS,
    classify_regimes,
    per_regime_metrics,
)


def test_classify_empty():
    result = classify_regimes(pd.Series([], dtype=float))
    assert len(result) == 0


def test_classify_steady_uptrend_is_bull():
    """Strong uptrend (60-day return well above the 5% bull threshold) with low vol."""
    rng = np.random.default_rng(42)
    idx = pd.date_range("2023-01-01", periods=600, freq="B")
    # Daily +0.0015 with low noise → 60-day cumulative ≈ 9%, above 5% threshold
    rets = pd.Series(rng.normal(0.0015, 0.005, 600), index=idx)
    regimes = classify_regimes(rets, window=60, min_duration=10)
    post_warmup = regimes.iloc[100:]
    bull_count = (post_warmup == "bull").sum()
    bear_count = (post_warmup == "bear").sum()
    assert bull_count > 50, f"bull={bull_count}, expected > 50"
    assert bear_count == 0


def test_classify_steady_downtrend_is_bear():
    rng = np.random.default_rng(43)
    idx = pd.date_range("2023-01-01", periods=600, freq="B")
    # Daily -0.0025 → 60-day cumulative ≈ -14%, below -10% threshold
    rets = pd.Series(rng.normal(-0.0025, 0.008, 600), index=idx)
    regimes = classify_regimes(rets, window=60, min_duration=10)
    post_warmup = regimes.iloc[100:]
    bear_count = (post_warmup == "bear").sum()
    assert bear_count > 50, f"bear={bear_count}, expected > 50"


def test_min_duration_prevents_flip_flop():
    """A noisy single-day regime change should be suppressed by min_duration."""
    rng = np.random.default_rng(42)
    idx = pd.date_range("2023-01-01", periods=500, freq="B")
    rets = pd.Series(rng.normal(0.0005, 0.015, 500), index=idx)
    regimes_no_smooth = classify_regimes(rets, window=60, min_duration=1)
    regimes_smoothed = classify_regimes(rets, window=60, min_duration=20)

    def transitions(s: pd.Series) -> int:
        return int((s != s.shift(1)).sum())

    assert transitions(regimes_smoothed) <= transitions(regimes_no_smooth)


def test_per_regime_metrics_sums_to_total():
    idx = pd.date_range("2023-01-01", periods=300, freq="B")
    rets = pd.Series(np.random.default_rng(7).normal(0.0003, 0.012, 300), index=idx)
    regimes = classify_regimes(rets, window=30, min_duration=5)
    metrics = per_regime_metrics(rets, regimes)
    total_days = sum(m["n_days"] for m in metrics.values())
    assert total_days == len(regimes.dropna()) or total_days == len(rets)


def test_per_regime_metrics_handles_empty_regime():
    idx = pd.date_range("2023-01-01", periods=200, freq="B")
    rets = pd.Series([0.001] * 200, index=idx)
    regimes = classify_regimes(rets, window=20, min_duration=5)
    metrics = per_regime_metrics(rets, regimes)
    # Every regime label appears in the output (even if 0 days)
    assert set(metrics.keys()) == set(REGIME_LABELS)
    # Annualized return for empty regime is 0, not NaN
    for label in REGIME_LABELS:
        assert isinstance(metrics[label]["annualized_return"], float)
        assert isinstance(metrics[label]["sharpe"], float)


def test_high_vol_regime_dominates_when_vol_spikes():
    idx = pd.date_range("2023-01-01", periods=400, freq="B")
    base = pd.Series([0.0003] * 400, index=idx)
    # Inject a 100-day high-vol stretch in the middle
    rng = np.random.default_rng(13)
    base.iloc[200:300] = rng.normal(0.0, 0.04, 100)
    regimes = classify_regimes(base, window=30, min_duration=5)
    spike_window = regimes.iloc[230:280]
    # high_vol should appear in the spike window
    assert (spike_window == "high_vol").any()
