"""Northbound Acceleration factor (1.2)."""

from __future__ import annotations

import pandas as pd

from astrategy.data.cache import SQLiteCache
from astrategy.factors.base import FactorContext
from astrategy.factors.northbound import NorthboundAccelerationFactor


def _seed_universe(cache: SQLiteCache, per_code_net_buy: dict[str, list[float]]):
    """Seed northbound + valuation rows for a small universe."""
    dates = pd.bdate_range("2024-05-20", periods=20).strftime("%Y-%m-%d").tolist()
    val_df = pd.DataFrame({
        "date": ["2024-05-19"], "pe_ttm": [20.0], "pb": [2.0], "ps_ttm": [5.0],
        "mkt_cap": [1.0e10], "float_cap": [7.0e9],
    })
    for code, net_flows in per_code_net_buy.items():
        # Pad/repeat the flow series to match the date count
        f = (net_flows * ((len(dates) + len(net_flows) - 1) // len(net_flows)))[: len(dates)]
        cache.upsert_northbound(code, pd.DataFrame({
            "date": dates,
            "holding_shares": [1000] * len(dates),
            "holding_value": [10000] * len(dates),
            "holding_pct": [1.0] * len(dates),
            "net_buy_shares": [v / 25.0 for v in f],
            "net_buy_value": f,
        }))
        cache.upsert_valuation_daily(code, val_df)
        cache.upsert_stock_meta(code, code, "main_sh", False)


def test_factor_registered():
    from astrategy.factors import get_factor
    assert get_factor("northbound_acceleration") is NorthboundAccelerationFactor


def test_default_params():
    f = NorthboundAccelerationFactor()
    assert f.params["window"] == 5
    assert f.params["gap"] == 5


def test_ramping_inflow_scores_higher_than_steady(tmp_path):
    """With window=5 gap=5, the two compared windows are [N-10:N-5] (prior)
    and [N-5:N] (recent). The seed series puts a regime change between them
    so the score reflects actual acceleration."""
    cache = SQLiteCache(db_path=str(tmp_path / "ramp.db"))
    _seed_universe(cache, {
        # Steady inflow → both windows identical → acceleration = 0
        "STEADY": [5.0e7] * 20,
        # Ramping: low flow until row 15, then high → recent window catches the ramp
        "RAMP": [1.0e6] * 15 + [1.0e8] * 5,
        # Falling: high until row 15, then low → recent window is low, prior is high
        "FALL": [1.0e8] * 15 + [1.0e6] * 5,
    })
    f = NorthboundAccelerationFactor(window=5, gap=5)
    ctx = FactorContext(
        cache=cache, universe=["STEADY", "RAMP", "FALL"],
        as_of=pd.Timestamp("2024-06-17"),
    )
    scores = f.compute(ctx)
    assert scores["RAMP"] > scores["STEADY"]
    assert scores["FALL"] < scores["STEADY"]
    # Steady should be near zero
    assert abs(scores["STEADY"]) < abs(scores["RAMP"]) * 0.2


def test_normalizes_by_float_cap(tmp_path):
    """Same delta in absolute inflow, smaller float cap → larger score."""
    cache = SQLiteCache(db_path=str(tmp_path / "fc.db"))
    dates = pd.bdate_range("2024-05-20", periods=20).strftime("%Y-%m-%d").tolist()
    # Ramp at row 15 so the recent-vs-prior window comparison sees the change.
    net_flows = [1.0e6] * 15 + [5.0e7] * 5
    for code, float_cap in [("BIG", 1.0e11), ("SMALL", 1.0e9)]:
        cache.upsert_northbound(code, pd.DataFrame({
            "date": dates,
            "holding_shares": [1000] * 20, "holding_value": [10000] * 20,
            "holding_pct": [1.0] * 20,
            "net_buy_shares": [v / 25.0 for v in net_flows],
            "net_buy_value": net_flows,
        }))
        cache.upsert_valuation_daily(code, pd.DataFrame({
            "date": ["2024-05-19"], "pe_ttm": [20.0], "pb": [2.0], "ps_ttm": [5.0],
            "mkt_cap": [float_cap * 1.4], "float_cap": [float_cap],
        }))
    f = NorthboundAccelerationFactor(window=5, gap=5)
    ctx = FactorContext(
        cache=cache, universe=["BIG", "SMALL"],
        as_of=pd.Timestamp("2024-06-17"),
    )
    scores = f.compute(ctx)
    assert scores["SMALL"] > scores["BIG"] * 10


def test_abstains_with_insufficient_history(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "short.db"))
    cache.upsert_northbound("SHORT", pd.DataFrame({
        "date": pd.bdate_range("2024-06-10", periods=4).strftime("%Y-%m-%d"),
        "holding_shares": [1000] * 4, "holding_value": [10000] * 4,
        "holding_pct": [1.0] * 4,
        "net_buy_shares": [1.0] * 4, "net_buy_value": [1.0e8] * 4,
    }))
    cache.upsert_valuation_daily("SHORT", pd.DataFrame({
        "date": ["2024-06-09"], "pe_ttm": [20.0], "pb": [2.0], "ps_ttm": [5.0],
        "mkt_cap": [1.0e10], "float_cap": [7.0e9],
    }))
    f = NorthboundAccelerationFactor(window=5, gap=5)
    ctx = FactorContext(
        cache=cache, universe=["SHORT"], as_of=pd.Timestamp("2024-06-17"),
    )
    assert f.compute(ctx).empty
