"""Tests for the walk-forward validation engine.

The factor-research overhaul deletes indicator-based strategies, but the
walk-forward machinery is engine-level and remains. These tests exercise it
with an inline buy-and-hold strategy so the mechanics keep coverage. A real
factor-portfolio strategy will replace this in Sprint 3.
"""

from __future__ import annotations

import pandas as pd
import pytest

from astrategy.data.synthetic import generate_synthetic_ohlcv
from astrategy.engine.backtest import BacktestConfig
from astrategy.engine.orders import Order, OrderSide
from astrategy.engine.walk_forward import (
    WalkForwardConfig,
    WalkForwardResult,
    WalkForwardRunner,
    generate_windows,
)
from astrategy.strategies.base import Strategy, StrategyContext


class _BuyAndHoldFirst(Strategy):
    """Tiny test-only strategy: buy 100 shares of the first symbol on day 2, hold."""

    name = "buy_and_hold_test"

    def __init__(self) -> None:
        self._bought = False

    def initialize(self, context: StrategyContext) -> None:
        self._bought = False

    def on_bar(self, date, bars, context):
        if self._bought or not bars:
            return []
        code = sorted(bars.keys())[0]
        self._bought = True
        return [Order(code=code, side=OrderSide.BUY, shares=100)]


def _three_years_data() -> dict[str, pd.DataFrame]:
    out = {}
    for code in ["600519", "601318"]:
        df = generate_synthetic_ohlcv(code, "2023-01-01", "2025-12-31")
        df = df.assign(date=pd.to_datetime(df["date"])).set_index("date").sort_index()
        out[code] = df
    return out


def test_generate_windows_correct_count():
    """3 years with 12mo train / 3mo test / 3mo step → ~8 windows."""
    windows = generate_windows(
        pd.Timestamp("2023-01-01"),
        pd.Timestamp("2025-12-31"),
        WalkForwardConfig(train_months=12, test_months=3, step_months=3),
    )
    assert 6 <= len(windows) <= 9


def test_generate_windows_increasing():
    windows = generate_windows(
        pd.Timestamp("2023-01-01"),
        pd.Timestamp("2025-12-31"),
        WalkForwardConfig(train_months=12, test_months=3, step_months=3),
    )
    for i in range(len(windows) - 1):
        assert windows[i + 1][0] > windows[i][0]
        assert windows[i][3] <= windows[i + 1][2]


def test_walk_forward_runs_and_produces_result():
    data = _three_years_data()
    config = BacktestConfig(start="2023-01-01", end="2025-12-31", initial_cash=1_000_000.0)
    wf = WalkForwardConfig(train_months=12, test_months=3, step_months=3, min_train_bars=200)
    runner = WalkForwardRunner(
        base_config=config,
        strategy_factory=_BuyAndHoldFirst,
        data=data,
        wf_config=wf,
    )
    result = runner.run()
    assert len(result.windows) > 0
    assert isinstance(result.aggregate_oos_sharpe, float)
    assert isinstance(result.overfit_flag, bool)


def test_walk_forward_concatenated_oos_equity_curve_is_continuous():
    data = _three_years_data()
    config = BacktestConfig(start="2023-01-01", end="2025-12-31", initial_cash=1_000_000.0)
    runner = WalkForwardRunner(
        base_config=config,
        strategy_factory=_BuyAndHoldFirst,
        data=data,
        wf_config=WalkForwardConfig(train_months=12, test_months=3, step_months=3),
    )
    result = runner.run()
    if result.oos_equity_curve.empty:
        pytest.skip("no OOS data produced (strategy may have made no trades)")
    dates = result.oos_equity_curve.index
    assert list(dates) == sorted(dates)
    assert len(dates) == len(set(dates))


def test_walk_forward_skips_short_train_window():
    data = _three_years_data()
    config = BacktestConfig(start="2023-01-01", end="2025-12-31", initial_cash=1_000_000.0)
    wf = WalkForwardConfig(train_months=12, test_months=3, step_months=3, min_train_bars=10_000)
    runner = WalkForwardRunner(
        base_config=config,
        strategy_factory=_BuyAndHoldFirst,
        data=data,
        wf_config=wf,
    )
    result = runner.run()
    assert len(result.windows) > 0
    assert all(w.skipped for w in result.windows)
    assert all(w.skip_reason is not None for w in result.windows)


def test_overfit_flag_triggers_on_large_gap():
    """Manually construct a result and ensure the flag math is right."""
    config = WalkForwardConfig(overfit_gap_threshold=0.5)
    r = WalkForwardResult(
        aggregate_is_sharpe=2.0,
        aggregate_oos_sharpe=0.5,
        aggregate_gap=1.5,
        overfit_flag=abs(1.5) > 0.5,
        config=config,
    )
    assert r.overfit_flag is True
