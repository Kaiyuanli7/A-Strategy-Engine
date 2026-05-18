"""Technical indicator computation tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from astrategy.charts.indicators import (
    compute_ema,
    compute_ma,
    compute_macd,
    compute_rsi,
)


def _closes(values: list[float]) -> pd.Series:
    dates = pd.date_range("2024-01-02", periods=len(values), freq="B")
    return pd.Series(values, index=dates, name="close")


def test_ma_basic():
    closes = _closes([1, 2, 3, 4, 5, 6])
    ma3 = compute_ma(closes, period=3)
    # First two values lack enough history → NaN
    assert pd.isna(ma3.iloc[0])
    assert pd.isna(ma3.iloc[1])
    # MA(3) at idx 2 = (1+2+3)/3 = 2
    assert ma3.iloc[2] == pytest.approx(2.0)
    # MA(3) at idx 5 = (4+5+6)/3 = 5
    assert ma3.iloc[5] == pytest.approx(5.0)


def test_ema_decays_toward_recent():
    closes = _closes([1, 1, 1, 1, 1, 5])
    ema = compute_ema(closes, period=3)
    # EMA(3): alpha = 2/4 = 0.5. Starts at 1, last bar at 5 pulls ema up.
    assert ema.iloc[-1] > 1.0
    assert ema.iloc[-1] < 5.0


def test_rsi_constant_series_undefined():
    """RSI on flat prices: numerator + denominator both 0 → NaN."""
    closes = _closes([10] * 30)
    rsi = compute_rsi(closes, period=14)
    # All-flat → NaN (avg_loss = 0 division)
    assert rsi.iloc[-1] is pd.NA or pd.isna(rsi.iloc[-1])


def test_rsi_all_up_approaches_100():
    closes = _closes(list(range(1, 50)))   # strictly increasing
    rsi = compute_rsi(closes, period=14)
    # Strictly rising → no losses → RSI saturates at 100
    assert rsi.iloc[-1] > 99.0


def test_rsi_all_down_approaches_0():
    closes = _closes(list(range(50, 0, -1)))
    rsi = compute_rsi(closes, period=14)
    assert rsi.iloc[-1] < 1.0


def test_macd_columns_present():
    closes = _closes(list(np.linspace(10, 50, 100)))
    macd = compute_macd(closes)
    assert list(macd.columns) == ["macd", "signal", "histogram"]
    # histogram = macd - signal exactly
    assert (macd["histogram"] == (macd["macd"] - macd["signal"])).all()


def test_macd_rising_prices_positive_macd():
    closes = _closes(list(range(1, 80)))
    macd = compute_macd(closes)
    # On a strong uptrend, MACD should end positive
    assert macd["macd"].iloc[-1] > 0
