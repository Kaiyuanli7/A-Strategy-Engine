"""Derive daily PE / PB / PS from real fundamentals + close prices."""

from __future__ import annotations

import pandas as pd
import pytest

from astrategy.data.cache import SQLiteCache
from astrategy.data.loader import DataLoader


def _seed_bars(cache: SQLiteCache, code: str, closes_per_date: dict[str, float]):
    df = pd.DataFrame({
        "date": list(closes_per_date.keys()),
        "open": list(closes_per_date.values()),
        "high": list(closes_per_date.values()),
        "low": list(closes_per_date.values()),
        "close": list(closes_per_date.values()),
        "volume": [1e6] * len(closes_per_date),
    })
    cache.upsert_daily_bars(code, df)


def _seed_fundamentals(
    cache: SQLiteCache, code: str,
    rows: list[dict],
):
    df = pd.DataFrame(rows)
    cache.upsert_fundamentals(code, df)


def test_backfill_derives_pe_from_eps(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "t.db"))
    # 5 trading days, all close=100
    closes = {f"2024-03-{d:02d}": 100.0 for d in range(1, 6)}
    _seed_bars(cache, "TEST", closes)
    _seed_fundamentals(cache, "TEST", [
        {
            "report_date": "2023-12-31", "announce_date": "2024-02-15",
            "pe_ttm": None, "pb": None, "ps_ttm": None,
            "roe_ttm": 15.0, "revenue_yoy": 10.0, "net_profit_yoy": 12.0,
            "eps_ttm": 4.0, "operating_cash_flow_ttm": 1e9, "net_income_ttm": 1e9,
            "book_value_per_share": 20.0, "revenue_per_share": 50.0,
        },
    ])
    loader = DataLoader(cache=cache)
    n_results = loader.backfill_valuation_daily_from_fundamentals(
        ["TEST"], "2024-03-01", "2024-03-31",
    )
    assert n_results["TEST"] == 5
    got = cache.get_valuation_daily("TEST", "2024-03-01", "2024-03-31")
    assert len(got) == 5
    # PE = 100 / 4 = 25
    assert (got["pe_ttm"] == 25.0).all()
    # PB = 100 / 20 = 5
    assert (got["pb"] == 5.0).all()
    # PS = 100 / 50 = 2
    assert (got["ps_ttm"] == 2.0).all()


def test_backfill_uses_pit_fundamentals(tmp_path):
    """Different fundamentals before vs after an earnings announcement."""
    cache = SQLiteCache(db_path=str(tmp_path / "t.db"))
    closes = {f"2024-{m:02d}-15": 100.0 for m in (1, 2, 3, 4, 5)}
    _seed_bars(cache, "TEST", closes)
    _seed_fundamentals(cache, "TEST", [
        # Q3 2023 announced 2023-11-15
        {"report_date": "2023-09-30", "announce_date": "2023-11-15",
         "pe_ttm": None, "pb": None, "ps_ttm": None,
         "roe_ttm": 12.0, "revenue_yoy": 8.0, "net_profit_yoy": 9.0,
         "eps_ttm": 4.0, "operating_cash_flow_ttm": 0.9e9, "net_income_ttm": 0.9e9,
         "book_value_per_share": 20.0, "revenue_per_share": 50.0},
        # Q4 2023 announced 2024-03-30 (mid-period)
        {"report_date": "2023-12-31", "announce_date": "2024-03-30",
         "pe_ttm": None, "pb": None, "ps_ttm": None,
         "roe_ttm": 14.0, "revenue_yoy": 10.0, "net_profit_yoy": 12.0,
         "eps_ttm": 5.0, "operating_cash_flow_ttm": 1.0e9, "net_income_ttm": 1.0e9,
         "book_value_per_share": 25.0, "revenue_per_share": 60.0},
    ])
    loader = DataLoader(cache=cache)
    loader.backfill_valuation_daily_from_fundamentals(
        ["TEST"], "2024-01-01", "2024-05-31",
    )
    got = cache.get_valuation_daily("TEST", "2024-01-01", "2024-05-31").sort_values("date")
    # Before 2024-03-30 announce: uses Q3 2023 → PE = 100 / 4 = 25
    pre = got[got["date"] < "2024-03-30"]
    assert (pre["pe_ttm"] == 25.0).all()
    # After 2024-03-30 announce: uses Q4 2023 → PE = 100 / 5 = 20
    post = got[got["date"] >= "2024-03-30"]
    assert (post["pe_ttm"] == 20.0).all()


def test_backfill_skips_when_no_fundamentals(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "t.db"))
    _seed_bars(cache, "TEST", {"2024-03-01": 100.0})
    loader = DataLoader(cache=cache)
    result = loader.backfill_valuation_daily_from_fundamentals(
        ["TEST"], "2024-03-01", "2024-03-31",
    )
    assert result["TEST"] == 0


def test_backfill_handles_zero_eps_gracefully(tmp_path):
    """If EPS is 0 (loss-making quarter), PE_TTM should be NaN, not crash."""
    cache = SQLiteCache(db_path=str(tmp_path / "t.db"))
    _seed_bars(cache, "TEST", {"2024-03-15": 100.0})
    _seed_fundamentals(cache, "TEST", [
        {"report_date": "2023-12-31", "announce_date": "2024-02-15",
         "pe_ttm": None, "pb": None, "ps_ttm": None,
         "roe_ttm": -5.0, "revenue_yoy": -10.0, "net_profit_yoy": -50.0,
         "eps_ttm": 0.0, "operating_cash_flow_ttm": -1e9, "net_income_ttm": -1e9,
         "book_value_per_share": 20.0, "revenue_per_share": 50.0},
    ])
    loader = DataLoader(cache=cache)
    loader.backfill_valuation_daily_from_fundamentals(
        ["TEST"], "2024-03-01", "2024-03-31",
    )
    got = cache.get_valuation_daily("TEST", "2024-03-01", "2024-03-31")
    assert len(got) == 1
    assert pd.isna(got.iloc[0]["pe_ttm"])
    # BVPS / RPS still valid
    assert got.iloc[0]["pb"] == 5.0
