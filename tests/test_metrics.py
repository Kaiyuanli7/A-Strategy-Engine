"""Performance metrics tests against known-value series."""

import math

import pandas as pd
import pytest

from astrategy.engine.metrics import (
    annualized_return,
    annualized_vol,
    max_drawdown,
    sharpe_ratio,
    total_return,
)


def _series(values: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=idx)


def test_total_return():
    eq = _series([100, 110, 121])
    assert total_return(eq) == pytest.approx(0.21)


def test_annualized_return_one_year():
    # 252 business days, doubles
    eq = pd.Series(
        [100 * (2 ** (i / 252)) for i in range(253)],
        index=pd.date_range("2024-01-01", periods=253, freq="B"),
    )
    assert annualized_return(eq) == pytest.approx(1.0, rel=0.01)


def test_annualized_vol_flat():
    eq = _series([100] * 100)
    assert annualized_vol(eq) == 0.0


def test_sharpe_zero_when_flat():
    eq = _series([100] * 100)
    assert sharpe_ratio(eq) == 0.0


def test_max_drawdown_simple():
    eq = _series([100, 120, 90, 110, 80, 100])
    # Peak 120 → trough 80 → -33.33%
    mdd, peak_dt, trough_dt = max_drawdown(eq)
    assert mdd == pytest.approx(-1/3, rel=0.01)
    assert eq.loc[peak_dt] == 120
    assert eq.loc[trough_dt] == 80


def test_max_drawdown_monotonic_up():
    eq = _series([100, 110, 120, 130])
    mdd, _, _ = max_drawdown(eq)
    assert mdd == 0.0


def test_round_trips_does_not_mutate_fills():
    from astrategy.engine.metrics import round_trips
    from astrategy.engine.orders import Fill, OrderSide

    t = pd.Timestamp("2024-01-02")
    buy = Fill(code="600519", side=OrderSide.BUY, shares=200, price=100.0,
               cost=5.0, timestamp=t)
    sell = Fill(code="600519", side=OrderSide.SELL, shares=200, price=110.0,
                cost=5.5, timestamp=t + pd.Timedelta(days=10))
    fills = [buy, sell]
    trips = round_trips(fills)
    # Inputs untouched
    assert buy.shares == 200
    assert sell.shares == 200
    # One round trip recorded with the right P&L
    assert len(trips) == 1
    assert trips[0]["shares"] == 200
    assert trips[0]["pnl"] == pytest.approx(200 * (110 - 100))


def test_round_trips_idempotent():
    """Running round_trips twice on the same fills returns the same answer."""
    from astrategy.engine.metrics import round_trips
    from astrategy.engine.orders import Fill, OrderSide

    fills = [
        Fill("A", OrderSide.BUY, 100, 10.0, 5.0, pd.Timestamp("2024-01-01")),
        Fill("A", OrderSide.BUY, 200, 12.0, 5.0, pd.Timestamp("2024-01-02")),
        Fill("A", OrderSide.SELL, 250, 15.0, 5.0, pd.Timestamp("2024-01-10")),
    ]
    first = round_trips(fills)
    second = round_trips(fills)
    assert [t["shares"] for t in first] == [t["shares"] for t in second]
    assert [t["pnl"] for t in first] == [t["pnl"] for t in second]
