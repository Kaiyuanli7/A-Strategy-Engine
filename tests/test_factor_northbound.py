"""Northbound Momentum factor — Factor 1.1."""

from __future__ import annotations

import pandas as pd

from astrategy.data.cache import SQLiteCache
from astrategy.factors.base import FactorContext
from astrategy.factors.northbound import NorthboundMomentumFactor


def _seed_cache(cache: SQLiteCache, codes_with_flow: dict[str, list[float]]):
    """Plant northbound rows + a valuation row for every code in `codes_with_flow`."""
    dates = pd.bdate_range("2024-05-20", periods=10).strftime("%Y-%m-%d").tolist()
    val_df = pd.DataFrame({
        "date": ["2024-05-19"],
        "pe_ttm": [20.0], "pb": [2.0], "ps_ttm": [5.0],
        "mkt_cap": [1.0e10], "float_cap": [7.0e9],
    })
    for code, flows in codes_with_flow.items():
        # Pad/trim flows to length of dates
        f = (flows * ((len(dates) + len(flows) - 1) // len(flows)))[: len(dates)]
        nb = pd.DataFrame({
            "date": dates,
            "holding_shares": [1000] * len(dates),
            "holding_value": [10000] * len(dates),
            "holding_pct": [1.0] * len(dates),
            "net_buy_shares": [v / 25.0 for v in f],
            "net_buy_value": f,
        })
        cache.upsert_northbound(code, nb)
        cache.upsert_valuation_daily(code, val_df)
        cache.upsert_stock_meta(code, code, "main_sh", False)


def test_factor_registered():
    from astrategy.factors import get_factor
    assert get_factor("northbound_momentum") is NorthboundMomentumFactor


def test_factor_default_lookback():
    f = NorthboundMomentumFactor()
    assert f.params["lookback"] == 5


def test_factor_ranks_higher_inflow_higher(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "t.db"))
    _seed_cache(cache, {
        "INFLOW": [1.0e8] * 10,
        "OUTFLOW": [-1.0e8] * 10,
        "ZERO": [0.0] * 10,
    })
    factor = NorthboundMomentumFactor(lookback=5)
    ctx = FactorContext(
        cache=cache,
        universe=["INFLOW", "OUTFLOW", "ZERO"],
        as_of=pd.Timestamp("2024-06-10"),
    )
    scores = factor.compute(ctx)
    assert set(scores.index) == {"INFLOW", "OUTFLOW", "ZERO"}
    assert scores["INFLOW"] > scores["ZERO"]
    assert scores["OUTFLOW"] < scores["ZERO"]


def test_factor_normalizes_by_float_cap(tmp_path):
    """Two stocks with same dollar inflow but different float caps should score differently."""
    cache = SQLiteCache(db_path=str(tmp_path / "t.db"))
    dates = pd.bdate_range("2024-05-20", periods=10).strftime("%Y-%m-%d").tolist()
    for code, float_cap in [("BIG", 1.0e11), ("SMALL", 1.0e9)]:
        nb = pd.DataFrame({
            "date": dates,
            "holding_shares": [1000] * len(dates),
            "holding_value": [10000] * len(dates),
            "holding_pct": [1.0] * len(dates),
            "net_buy_shares": [1.0e6] * len(dates),
            "net_buy_value": [5.0e7] * len(dates),
        })
        cache.upsert_northbound(code, nb)
        cache.upsert_valuation_daily(code, pd.DataFrame({
            "date": ["2024-05-19"], "pe_ttm": [20.0], "pb": [2.0], "ps_ttm": [5.0],
            "mkt_cap": [float_cap * 1.4], "float_cap": [float_cap],
        }))
    factor = NorthboundMomentumFactor(lookback=5)
    ctx = FactorContext(
        cache=cache, universe=["BIG", "SMALL"],
        as_of=pd.Timestamp("2024-06-10"),
    )
    scores = factor.compute(ctx)
    # Same dollar inflow / smaller float = much higher score
    assert scores["SMALL"] > scores["BIG"] * 10


def test_factor_abstains_with_no_valuation(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "t.db"))
    dates = pd.bdate_range("2024-05-20", periods=10).strftime("%Y-%m-%d").tolist()
    cache.upsert_northbound("NOVAL", pd.DataFrame({
        "date": dates,
        "holding_shares": [1000] * len(dates),
        "holding_value": [10000] * len(dates),
        "holding_pct": [1.0] * len(dates),
        "net_buy_shares": [1] * len(dates),
        "net_buy_value": [1.0e8] * len(dates),
    }))
    # No valuation_daily row → factor should abstain
    factor = NorthboundMomentumFactor(lookback=5)
    ctx = FactorContext(cache=cache, universe=["NOVAL"], as_of=pd.Timestamp("2024-06-10"))
    scores = factor.compute(ctx)
    assert scores.empty


def test_factor_abstains_with_no_northbound(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "t.db"))
    cache.upsert_valuation_daily("EMPTY", pd.DataFrame({
        "date": ["2024-05-19"], "pe_ttm": [20.0], "pb": [2.0], "ps_ttm": [5.0],
        "mkt_cap": [1.0e10], "float_cap": [7.0e9],
    }))
    factor = NorthboundMomentumFactor(lookback=5)
    ctx = FactorContext(cache=cache, universe=["EMPTY"], as_of=pd.Timestamp("2024-06-10"))
    scores = factor.compute(ctx)
    assert scores.empty
