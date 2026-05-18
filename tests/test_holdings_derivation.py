"""Derive final holdings + sector exposure from a fills timeline."""

from __future__ import annotations

import pandas as pd
import pytest

from astrategy.strategies.holdings import (
    HoldingRecord,
    SectorWeight,
    derive_final_holdings,
    derive_sector_exposure,
)


def _bars(code: str, last_close: float) -> pd.DataFrame:
    return pd.DataFrame({
        "date": [pd.Timestamp("2024-12-31")],
        "open": [last_close], "high": [last_close], "low": [last_close],
        "close": [last_close], "volume": [1e6],
    }).set_index("date")


def test_buy_then_no_sell_leaves_full_position():
    fills = [
        {"date": "2024-01-05", "code": "AAA", "side": "buy",
         "shares": 1000, "price": 10.0, "cost": 2.50, "seq": 0},
    ]
    holdings = derive_final_holdings(
        fills,
        bars_by_code={"AAA": _bars("AAA", 12.0)},
        sector_map={"AAA": "tech"},
    )
    assert len(holdings) == 1
    h = holdings[0]
    assert h.code == "AAA"
    assert h.shares == 1000
    # avg_cost = (1000 * 10 + 2.50) / 1000 = 10.0025
    assert h.avg_cost == pytest.approx(10.0025, abs=1e-6)
    assert h.last_price == 12.0
    assert h.market_value == pytest.approx(12000.0)
    assert h.pnl == pytest.approx(12000.0 - 1000 * 10.0025)
    assert h.pnl_pct > 0
    assert h.sector == "tech"


def test_buy_then_partial_sell_reduces_shares_proportionally():
    fills = [
        {"date": "2024-01-05", "code": "AAA", "side": "buy",
         "shares": 1000, "price": 10.0, "cost": 5.0, "seq": 0},
        {"date": "2024-06-15", "code": "AAA", "side": "sell",
         "shares": 400, "price": 12.0, "cost": 6.0, "seq": 1},
    ]
    holdings = derive_final_holdings(fills, bars_by_code={"AAA": _bars("AAA", 13.0)})
    assert len(holdings) == 1
    h = holdings[0]
    assert h.shares == 600
    # Original cost basis: 10005 / 1000 = 10.005 per share
    # After selling 400, remaining cost = 600 * 10.005 = 6003
    assert h.avg_cost == pytest.approx(10.005, abs=1e-6)


def test_buy_then_full_sell_then_buy_resets_entry_date():
    """Round-trip then re-enter — entry_date should be the SECOND buy."""
    fills = [
        {"date": "2024-01-05", "code": "AAA", "side": "buy",
         "shares": 1000, "price": 10.0, "cost": 5.0, "seq": 0},
        {"date": "2024-04-10", "code": "AAA", "side": "sell",
         "shares": 1000, "price": 11.0, "cost": 6.0, "seq": 1},
        {"date": "2024-09-20", "code": "AAA", "side": "buy",
         "shares": 500, "price": 9.0, "cost": 4.0, "seq": 2},
    ]
    holdings = derive_final_holdings(fills, bars_by_code={"AAA": _bars("AAA", 10.0)})
    assert len(holdings) == 1
    h = holdings[0]
    assert h.shares == 500
    assert h.entry_date == "2024-09-20"


def test_buy_then_full_sell_drops_position():
    fills = [
        {"date": "2024-01-05", "code": "AAA", "side": "buy",
         "shares": 1000, "price": 10.0, "cost": 5.0, "seq": 0},
        {"date": "2024-04-10", "code": "AAA", "side": "sell",
         "shares": 1000, "price": 11.0, "cost": 6.0, "seq": 1},
    ]
    holdings = derive_final_holdings(fills, bars_by_code={"AAA": _bars("AAA", 12.0)})
    assert holdings == []


def test_multiple_codes_sorted_by_market_value():
    fills = [
        {"date": "2024-01-05", "code": "BIG", "side": "buy",
         "shares": 1000, "price": 100.0, "cost": 25.0, "seq": 0},
        {"date": "2024-01-05", "code": "SMALL", "side": "buy",
         "shares": 100, "price": 20.0, "cost": 5.0, "seq": 1},
        {"date": "2024-01-05", "code": "MID", "side": "buy",
         "shares": 500, "price": 50.0, "cost": 12.50, "seq": 2},
    ]
    bars = {
        "BIG": _bars("BIG", 100.0),
        "SMALL": _bars("SMALL", 20.0),
        "MID": _bars("MID", 50.0),
    }
    holdings = derive_final_holdings(fills, bars_by_code=bars)
    assert [h.code for h in holdings] == ["BIG", "MID", "SMALL"]


def test_no_fills_returns_empty():
    assert derive_final_holdings([]) == []


def test_unknown_code_uses_avg_cost_as_last_price():
    """Last-price fallback when bars cache doesn't have the code."""
    fills = [
        {"date": "2024-01-05", "code": "UNKNOWN", "side": "buy",
         "shares": 100, "price": 10.0, "cost": 1.0, "seq": 0},
    ]
    holdings = derive_final_holdings(fills, bars_by_code={})
    assert len(holdings) == 1
    h = holdings[0]
    # PnL pct should be ~0 since last_price = avg_cost when no bars
    assert h.pnl_pct == pytest.approx(0.0, abs=1e-6)


def test_sector_exposure_aggregates_weights():
    holdings = [
        HoldingRecord(code="A", shares=100, avg_cost=10.0, market_value=1000.0,
                      pnl=0.0, pnl_pct=0.0, last_price=10.0, entry_date="2024-01-05",
                      sector="tech"),
        HoldingRecord(code="B", shares=100, avg_cost=10.0, market_value=2000.0,
                      pnl=0.0, pnl_pct=0.0, last_price=20.0, entry_date="2024-01-05",
                      sector="tech"),
        HoldingRecord(code="C", shares=100, avg_cost=10.0, market_value=1000.0,
                      pnl=0.0, pnl_pct=0.0, last_price=10.0, entry_date="2024-01-05",
                      sector="finance"),
    ]
    exposure = derive_sector_exposure(holdings)
    assert len(exposure) == 2
    tech = next(s for s in exposure if s.sector == "tech")
    assert tech.weight == pytest.approx(3000 / 4000)
    assert tech.n_stocks == 2
    fin = next(s for s in exposure if s.sector == "finance")
    assert fin.weight == pytest.approx(1000 / 4000)
    # Sorted descending by weight
    assert exposure[0].weight >= exposure[1].weight


def test_sector_exposure_buckets_missing_sector():
    holdings = [
        HoldingRecord(code="A", shares=100, avg_cost=10.0, market_value=1000.0,
                      pnl=0.0, pnl_pct=0.0, last_price=10.0, entry_date="2024-01-05",
                      sector=None),
    ]
    exposure = derive_sector_exposure(holdings)
    assert len(exposure) == 1
    assert exposure[0].sector == "(unknown)"


def test_sector_exposure_empty_holdings():
    assert derive_sector_exposure([]) == []
