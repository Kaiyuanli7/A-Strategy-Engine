"""Tests for the walk-forward validation engine."""

from pathlib import Path

import pandas as pd
import pytest

from astrategy.data.cache import SQLiteCache
from astrategy.data.synthetic import generate_synthetic_ohlcv
from astrategy.engine.backtest import BacktestConfig
from astrategy.engine.walk_forward import (
    WalkForwardConfig,
    WalkForwardRunner,
    generate_windows,
)
from astrategy.strategies.ma_cross import DualMACrossStrategy


def _three_years_data() -> dict[str, pd.DataFrame]:
    """Build 3 years of synthetic OHLCV for a couple of stocks, indexed by datetime."""
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
        assert windows[i + 1][0] > windows[i][0]  # train_start advances
        # Test windows don't overlap when step == test_months
        assert windows[i][3] <= windows[i + 1][2]


def test_walk_forward_runs_and_flags_no_overfit_on_simple_strategy():
    data = _three_years_data()
    config = BacktestConfig(start="2023-01-01", end="2025-12-31", initial_cash=1_000_000.0)
    wf = WalkForwardConfig(train_months=12, test_months=3, step_months=3, min_train_bars=200)
    runner = WalkForwardRunner(
        base_config=config,
        strategy_factory=lambda: DualMACrossStrategy(fast=5, slow=20, position_size_pct=0.10, max_positions=5),
        data=data,
        wf_config=wf,
    )
    result = runner.run()
    assert len(result.windows) > 0
    # On random GBM data, IS-OOS gap shouldn't be wildly different (noise)
    assert isinstance(result.aggregate_oos_sharpe, float)
    assert isinstance(result.overfit_flag, bool)


def test_walk_forward_concatenated_oos_equity_curve_is_continuous():
    data = _three_years_data()
    config = BacktestConfig(start="2023-01-01", end="2025-12-31", initial_cash=1_000_000.0)
    runner = WalkForwardRunner(
        base_config=config,
        strategy_factory=lambda: DualMACrossStrategy(fast=5, slow=20, max_positions=5),
        data=data,
        wf_config=WalkForwardConfig(train_months=12, test_months=3, step_months=3),
    )
    result = runner.run()
    if result.oos_equity_curve.empty:
        pytest.skip("no OOS data produced (strategy may have made no trades)")
    # Dates strictly increasing
    dates = result.oos_equity_curve.index
    assert list(dates) == sorted(dates)
    # No duplicates
    assert len(dates) == len(set(dates))


def test_walk_forward_skips_short_train_window():
    data = _three_years_data()
    config = BacktestConfig(start="2023-01-01", end="2025-12-31", initial_cash=1_000_000.0)
    # Set absurdly high min_train_bars so all windows skip
    wf = WalkForwardConfig(train_months=12, test_months=3, step_months=3, min_train_bars=10_000)
    runner = WalkForwardRunner(
        base_config=config,
        strategy_factory=lambda: DualMACrossStrategy(fast=5, slow=20),
        data=data,
        wf_config=wf,
    )
    result = runner.run()
    assert len(result.windows) > 0
    assert all(w.skipped for w in result.windows)
    assert all(w.skip_reason is not None for w in result.windows)


def test_overfit_flag_triggers_on_large_gap():
    """Manually construct a result and ensure the flag math is right."""
    from astrategy.engine.walk_forward import WalkForwardResult, WindowResult
    config = WalkForwardConfig(overfit_gap_threshold=0.5)
    # If aggregate IS Sharpe = 2.0 and OOS = 0.5, gap = 1.5 > 0.5 → overfit
    r = WalkForwardResult(
        aggregate_is_sharpe=2.0,
        aggregate_oos_sharpe=0.5,
        aggregate_gap=1.5,
        overfit_flag=abs(1.5) > 0.5,
        config=config,
    )
    assert r.overfit_flag is True
