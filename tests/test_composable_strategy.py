"""Integration tests for ComposableStrategy via the Backtester."""

from pathlib import Path

import pandas as pd
import pytest

from astrategy.config import classify_board, is_st_name
from astrategy.data.cache import SQLiteCache
from astrategy.data.synthetic import (
    generate_synthetic_fundamentals,
    generate_synthetic_northbound,
    generate_synthetic_ohlcv,
    generate_synthetic_sector,
    generate_synthetic_valuation_daily,
)
from astrategy.engine.backtest import Backtester, BacktestConfig
from astrategy.strategies.composable import ComposableStrategy


@pytest.fixture
def cache_with_data(tmp_path: Path) -> SQLiteCache:
    """Seed a tmp cache with synthetic OHLCV + fundamentals/valuation/northbound."""
    db = str(tmp_path / "test.db")
    cache = SQLiteCache(db)
    code = "600519"
    cache.upsert_stock_meta(code, "贵州茅台", classify_board(code), is_st_name("贵州茅台"))
    start, end = "2023-05-18", "2026-05-18"
    ohlcv = generate_synthetic_ohlcv(code, start, end)
    cache.upsert_daily_bars(code, ohlcv)
    cache.upsert_fundamentals(code, generate_synthetic_fundamentals(code, start, end))
    ohlcv_for_val = ohlcv.assign(date=ohlcv["date"].astype(str))
    cache.upsert_valuation_daily(code, generate_synthetic_valuation_daily(code, start, end, ohlcv_for_val))
    cache.upsert_northbound(code, generate_synthetic_northbound(code, start, end))
    sec = generate_synthetic_sector(code)
    cache.upsert_sector(code, sw_l1_name=sec["sw_l1_name"], sw_l1_code=sec["sw_l1_code"])
    return cache


def _load_data(cache: SQLiteCache, code: str, start: str, end: str) -> dict[str, pd.DataFrame]:
    df = cache.get_daily_bars(code, start, end)
    df = df.set_index("date").sort_index()
    return {code: df}


def test_composable_with_one_condition_completes(cache_with_data: SQLiteCache):
    code = "600519"
    data = _load_data(cache_with_data, code, "2023-05-18", "2026-05-18")
    strategy = ComposableStrategy(
        entry_conditions=[{"type": "ma_cross", "fast": 5, "slow": 20, "direction": "up"}],
        exit_rules={"signal_reversal": True, "max_hold_days": 60},
        sizing={"method": "equal_weight", "position_size_pct": 0.10},
        max_positions=5,
        cache=cache_with_data,
    )
    bt = Backtester(BacktestConfig(start="2023-05-18", end="2026-05-18"), strategy, data)
    result = bt.run()
    # Should at minimum produce some fills since it's a permissive single signal
    assert result.summary["n_fills"] > 0


def test_composable_respects_pe_bound(cache_with_data: SQLiteCache):
    """An impossibly-restrictive PE bound should result in zero entries (and no crash)."""
    code = "600519"
    data = _load_data(cache_with_data, code, "2023-05-18", "2026-05-18")
    strategy = ComposableStrategy(
        entry_conditions=[
            {"type": "ma_cross", "fast": 5, "slow": 20, "direction": "up"},
            {"type": "pe_bound", "max": 0.01},   # nothing has PE < 0.01
        ],
        exit_rules={"max_hold_days": 30},
        sizing={"method": "equal_weight", "position_size_pct": 0.10},
        cache=cache_with_data,
    )
    bt = Backtester(BacktestConfig(start="2023-05-18", end="2026-05-18"), strategy, data)
    result = bt.run()
    assert result.summary["n_fills"] == 0
    # Equity should be exactly the initial cash since no trades happened
    assert result.summary["final_equity"] == pytest.approx(result.summary["initial_equity"])


def test_composable_stop_loss_triggers(cache_with_data: SQLiteCache):
    """A tight stop-loss should produce at least one rapid exit if any entry occurs."""
    code = "600519"
    data = _load_data(cache_with_data, code, "2023-05-18", "2026-05-18")
    strategy = ComposableStrategy(
        entry_conditions=[{"type": "ma_cross", "fast": 5, "slow": 20, "direction": "up"}],
        exit_rules={"stop_loss_pct": 0.01},  # 1% stop is very tight
        sizing={"method": "equal_weight", "position_size_pct": 0.10},
        cache=cache_with_data,
    )
    bt = Backtester(BacktestConfig(start="2023-05-18", end="2026-05-18"), strategy, data)
    result = bt.run()
    # If entries happened, there should be SELL fills too (stop-loss exits)
    buys = sum(1 for f in result.fills if f.side.value == "buy")
    sells = sum(1 for f in result.fills if f.side.value == "sell")
    if buys > 0:
        assert sells > 0


def test_composable_max_positions_cap(cache_with_data: SQLiteCache):
    """Even with N stocks all signaling, no more than max_positions concurrent."""
    # Seed 3 codes
    cache = cache_with_data
    for code in ["601318", "300750"]:
        cache.upsert_stock_meta(code, "test", classify_board(code), False)
        ohlcv = generate_synthetic_ohlcv(code, "2023-05-18", "2026-05-18")
        cache.upsert_daily_bars(code, ohlcv)
        cache.upsert_fundamentals(code, generate_synthetic_fundamentals(code, "2023-05-18", "2026-05-18"))
        ohlcv_str = ohlcv.assign(date=ohlcv["date"].astype(str))
        cache.upsert_valuation_daily(code, generate_synthetic_valuation_daily(code, "2023-05-18", "2026-05-18", ohlcv_str))
        cache.upsert_northbound(code, generate_synthetic_northbound(code, "2023-05-18", "2026-05-18"))
        sec = generate_synthetic_sector(code)
        cache.upsert_sector(code, sw_l1_name=sec["sw_l1_name"], sw_l1_code=sec["sw_l1_code"])

    data: dict[str, pd.DataFrame] = {}
    for code in ["600519", "601318", "300750"]:
        df = cache.get_daily_bars(code, "2023-05-18", "2026-05-18")
        data[code] = df.set_index("date").sort_index()

    strategy = ComposableStrategy(
        entry_conditions=[{"type": "ma_cross", "fast": 5, "slow": 20, "direction": "up"}],
        exit_rules={"max_hold_days": 365},
        sizing={"method": "equal_weight", "position_size_pct": 0.10},
        max_positions=1,
        cache=cache,
    )
    bt = Backtester(BacktestConfig(start="2023-05-18", end="2026-05-18"), strategy, data)
    bt.run()
    # max 1 concurrent position — track via on_fill tracker
    assert len(strategy._entries) <= 1
