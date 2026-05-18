"""Tests for the condition evaluator, including PIT-safety for fundamentals."""

import numpy as np
import pandas as pd
import pytest

from astrategy.strategies.conditions import (
    build_cond_data,
    precompute_condition,
)


def _ohlcv(closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame({
        "open": closes, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes,
        "volume": [1_000_000] * n,
    }, index=idx)


def test_ma_cross_up():
    # Down then sharp recovery — produces one clear MA(3) over MA(5) crossover
    closes = list(range(20, 10, -1)) + list(range(10, 25))
    data = build_cond_data(_ohlcv(closes))
    sig = precompute_condition({"type": "ma_cross", "fast": 3, "slow": 5, "direction": "up"}, data)
    assert sig.sum() >= 1, f"Expected at least one cross_up; got {sig.sum()}"


def test_price_vs_ma_above():
    closes = list(range(1, 31))
    data = build_cond_data(_ohlcv(closes))
    sig = precompute_condition({"type": "price_vs_ma", "period": 5, "op": ">"}, data)
    # In a uptrend, close > SMA(5) is consistently true after warmup
    assert sig.iloc[-5:].all()


def test_rsi_below_in_downtrend():
    closes = list(range(50, 20, -1))
    data = build_cond_data(_ohlcv(closes))
    sig = precompute_condition({"type": "rsi", "period": 14, "threshold": 40, "direction": "below"}, data)
    assert sig.iloc[-5:].any()


def test_volume_spike():
    n = 25
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    closes = [100.0] * n
    vols = [1_000_000] * (n - 1) + [3_500_000]
    df = pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes,
                       "volume": vols}, index=idx)
    data = build_cond_data(df)
    sig = precompute_condition({"type": "volume_spike", "period": 20, "multiple": 2.0}, data)
    assert sig.iloc[-1] is True or bool(sig.iloc[-1])


def test_pe_bound_upper_only():
    closes = [100.0] * 25
    val = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=25, freq="B").astype(str),
        "pe_ttm": [10, 15, 20, 25, 30] * 5,
        "pb": [1.0] * 25, "ps_ttm": [1.0] * 25,
        "mkt_cap": [1e10] * 25, "float_cap": [7e9] * 25,
    })
    data = build_cond_data(_ohlcv(closes), valuation=val)
    sig = precompute_condition({"type": "pe_bound", "max": 22}, data)
    # PE values: 10,15,20,25,30, repeating. True where <= 22 (and notna)
    assert sig.sum() == 15   # 10, 15, 20 in each of 5 cycles


def test_roe_bound_pit_does_not_leak():
    """
    Fundamentals announce_date is later than report_date. Condition must
    only see the row AFTER its announce_date — not after report_date.
    """
    closes = [100.0] * 60
    ohlcv = _ohlcv(closes)
    fundamentals = pd.DataFrame({
        # Report_date = first bar; announce_date = 30 days later
        "report_date": ["2024-01-01"],
        "announce_date": [str(ohlcv.index[30].date())],
        "pe_ttm": [20.0], "pb": [3.0], "ps_ttm": [2.0],
        "roe_ttm": [25.0],
        "revenue_yoy": [10.0], "net_profit_yoy": [10.0], "eps_ttm": [3.0],
    })
    data = build_cond_data(ohlcv, fundamentals=fundamentals)
    sig = precompute_condition({"type": "roe_bound", "min": 20}, data)
    # PIT: ROE bound True ONLY from announce_date onward (bar 30+)
    assert sig.iloc[:30].sum() == 0, "PIT leakage: ROE seen before announce_date"
    assert sig.iloc[30:].all()


def test_nb_net_inflow_window_aggregates():
    closes = [100.0] * 30
    ohlcv = _ohlcv(closes)
    # Daily inflows: 5 days at 10M, then negative days
    inflows = [10_000_000] * 5 + [-5_000_000] * 25
    nb = pd.DataFrame({
        "date": ohlcv.index.astype(str),
        "holding_shares": [0] * 30, "holding_value": [0] * 30,
        "holding_pct": [1.0] * 30,
        "net_buy_shares": [0] * 30, "net_buy_value": inflows,
    })
    data = build_cond_data(ohlcv, northbound=nb)
    sig = precompute_condition(
        {"type": "nb_net_inflow", "window": 5, "min_value": 40_000_000}, data
    )
    # Rolling 5-day sum hits 50M on bar 4, then falls
    assert sig.iloc[4] == True  # noqa: E712
    assert sig.iloc[-1] == False  # noqa: E712


def test_nb_holding_pct_bound():
    closes = [100.0] * 10
    ohlcv = _ohlcv(closes)
    nb = pd.DataFrame({
        "date": ohlcv.index.astype(str),
        "holding_shares": [0] * 10, "holding_value": [0] * 10,
        "holding_pct": [0.5, 1.0, 2.0, 3.5, 5.0, 6.0, 7.5, 8.0, 9.0, 10.0],
        "net_buy_shares": [0] * 10, "net_buy_value": [0] * 10,
    })
    data = build_cond_data(ohlcv, northbound=nb)
    sig = precompute_condition({"type": "nb_holding_pct", "min": 3.0, "max": 7.0}, data)
    # Values in [3.0, 7.0]: 3.5, 5.0, 6.0 → 3 hits
    assert sig.sum() == 3


def test_unknown_condition_type_raises():
    closes = [100.0] * 5
    data = build_cond_data(_ohlcv(closes))
    with pytest.raises(Exception):
        precompute_condition({"type": "made_up", "foo": 1}, data)
