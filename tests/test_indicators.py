"""Unit tests for the pure indicator library."""

import math

import numpy as np
import pandas as pd
import pytest

from astrategy.strategies import indicators as ind


def _series(values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.date_range("2024-01-01", periods=len(values), freq="B"))


def test_sma():
    s = _series([1, 2, 3, 4, 5])
    assert ind.sma(s, 3).tolist()[-1] == 4.0
    assert pd.isna(ind.sma(s, 3).iloc[0])


def test_ema_first_value_nan_then_converges():
    s = _series([1.0] * 30)
    result = ind.ema(s, 10)
    assert pd.isna(result.iloc[0])
    # Constant input → EMA approaches constant
    assert result.iloc[-1] == pytest.approx(1.0)


def test_rsi_golden_value():
    """
    Wilder RSI on a known sequence. Inputs from a standard textbook example;
    after ~14 bars of mixed up/down moves the RSI should land near a specific value.
    """
    closes = [
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
        45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64,
    ]
    s = _series(closes)
    r = ind.rsi(s, 14)
    # Expected RSI on bar 14 (first valid) ≈ 70.5 by Wilder
    val = r.iloc[14]
    assert 65 < val < 78, f"RSI(14) at bar 14 was {val}"


def test_rsi_constant_input():
    """Flat prices → no movement; RSI should be ~50 (avg_up = avg_dn = 0)."""
    s = _series([100.0] * 30)
    r = ind.rsi(s, 14)
    # We fill 50.0 for the degenerate avg_up = avg_dn = 0 case (where we have count >= n)
    assert r.iloc[15] == pytest.approx(50.0)


def test_bollinger_bands_widen_with_vol():
    rng = np.random.default_rng(42)
    flat = pd.Series([100.0] * 50, index=pd.date_range("2024-01-01", periods=50, freq="B"))
    volatile = flat + pd.Series(rng.normal(0, 5, 50), index=flat.index)
    _, u_flat, l_flat = ind.bollinger(flat, 20, 2.0)
    _, u_vol, l_vol = ind.bollinger(volatile, 20, 2.0)
    # Width = upper - lower; volatile should be much wider
    width_flat = (u_flat - l_flat).iloc[-1]
    width_vol = (u_vol - l_vol).iloc[-1]
    assert width_vol > width_flat


def test_macd_signal_below_macd_in_uptrend():
    s = pd.Series(np.linspace(10, 30, 60),
                  index=pd.date_range("2024-01-01", periods=60, freq="B"))
    m, sig, _ = ind.macd(s, 12, 26, 9)
    # In a steady uptrend, MACD > signal
    assert m.iloc[-1] > sig.iloc[-1]


def test_volume_ratio_spike():
    v = pd.Series([1000] * 19 + [5000], index=pd.date_range("2024-01-01", periods=20, freq="B"))
    r = ind.volume_ratio(v, 20)
    assert r.iloc[-1] == pytest.approx(5000 / 1200, rel=1e-2)


def test_cross_up_detects_only_transition():
    a = pd.Series([1, 2, 3, 4, 5], dtype=float)
    b = pd.Series([3, 3, 3, 3, 3], dtype=float)
    out = ind.cross_up(a, b)
    # Bar 3: a=4 > b=3, prev a=3 == b=3 → True
    assert out.tolist() == [False, False, False, True, False]


def test_cross_down_detects_only_transition():
    a = pd.Series([5, 4, 3, 2, 1], dtype=float)
    b = pd.Series([3, 3, 3, 3, 3], dtype=float)
    out = ind.cross_down(a, b)
    # Bar 3: a=2 < b=3, prev a=3 == b=3 → True
    assert out.tolist() == [False, False, False, True, False]


def test_realized_vol_zero_for_flat():
    s = _series([100.0] * 30)
    rv = ind.realized_vol(s, 20)
    assert rv.iloc[-1] == pytest.approx(0.0)
