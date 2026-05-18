"""Schema additions (OCF / NI on fundamentals) and idempotent ALTER TABLE."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from astrategy.data.cache import SQLiteCache


def test_fresh_cache_has_new_fundamentals_columns(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "fresh.db"))
    with sqlite3.connect(cache.db_path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(fundamentals)")}
    assert "operating_cash_flow_ttm" in cols
    assert "net_income_ttm" in cols


def test_migration_is_idempotent_on_second_init(tmp_path):
    db_path = str(tmp_path / "twice.db")
    SQLiteCache(db_path=db_path)
    # Re-instantiate; _init_schema runs again with ALTER TABLE.
    SQLiteCache(db_path=db_path)
    # Both columns still present, no errors raised.
    with sqlite3.connect(db_path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(fundamentals)")}
    assert "operating_cash_flow_ttm" in cols
    assert "net_income_ttm" in cols


def test_migration_backfills_legacy_db_without_columns(tmp_path):
    """Simulate a DB created before the schema bump: drop the new columns,
    re-instantiate, and verify the migration adds them back."""
    db_path = str(tmp_path / "legacy.db")
    SQLiteCache(db_path=db_path)
    # Recreate the table without the new columns (simulate pre-bump schema).
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE fundamentals")
        conn.execute("""
            CREATE TABLE fundamentals (
                code           TEXT NOT NULL,
                report_date    TEXT NOT NULL,
                announce_date  TEXT NOT NULL,
                pe_ttm         REAL,
                pb             REAL,
                ps_ttm         REAL,
                roe_ttm        REAL,
                revenue_yoy    REAL,
                net_profit_yoy REAL,
                eps_ttm        REAL,
                PRIMARY KEY (code, report_date)
            )
        """)
    # Now open via SQLiteCache — _init_schema's ALTER TABLE backfills the cols.
    SQLiteCache(db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(fundamentals)")}
    assert "operating_cash_flow_ttm" in cols
    assert "net_income_ttm" in cols


def test_upsert_and_get_round_trip_includes_new_columns(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "rt.db"))
    df = pd.DataFrame({
        "report_date": ["2024-03-31"],
        "announce_date": ["2024-05-15"],
        "pe_ttm": [12.0], "pb": [1.5], "ps_ttm": [3.0], "roe_ttm": [15.0],
        "revenue_yoy": [10.0], "net_profit_yoy": [12.0], "eps_ttm": [2.5],
        "operating_cash_flow_ttm": [1.2e9],
        "net_income_ttm": [1.0e9],
    })
    cache.upsert_fundamentals("600519", df)
    got = cache.get_fundamentals("600519")
    assert "operating_cash_flow_ttm" in got.columns
    assert "net_income_ttm" in got.columns
    assert got.iloc[0]["operating_cash_flow_ttm"] == 1.2e9
    assert got.iloc[0]["net_income_ttm"] == 1.0e9


def test_fundamentals_as_of_returns_latest_pre_date(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "pit.db"))
    df = pd.DataFrame({
        "report_date": ["2023-12-31", "2024-03-31"],
        "announce_date": ["2024-02-15", "2024-05-15"],
        "pe_ttm": [10.0, 12.0], "pb": [1.4, 1.5], "ps_ttm": [2.5, 3.0],
        "roe_ttm": [14.0, 15.0],
        "revenue_yoy": [8.0, 10.0], "net_profit_yoy": [9.0, 12.0],
        "eps_ttm": [2.0, 2.5],
        "operating_cash_flow_ttm": [1.0e9, 1.2e9],
        "net_income_ttm": [0.9e9, 1.0e9],
    })
    cache.upsert_fundamentals("600519", df)

    # Before Q1 announcement: should return Q4 only.
    got = cache.fundamentals_as_of("600519", "2024-04-01")
    assert got is not None
    assert pd.Timestamp(got["announce_date"]).strftime("%Y-%m-%d") == "2024-02-15"

    # After Q1 announcement: should return Q1.
    got = cache.fundamentals_as_of("600519", "2024-06-01")
    assert got is not None
    assert pd.Timestamp(got["announce_date"]).strftime("%Y-%m-%d") == "2024-05-15"

    # Before any announcement: None.
    assert cache.fundamentals_as_of("600519", "2024-01-01") is None


def test_recent_fundamentals_as_of_returns_k_quarters(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "k.db"))
    df = pd.DataFrame({
        "report_date": ["2023-09-30", "2023-12-31", "2024-03-31"],
        "announce_date": ["2023-11-15", "2024-02-15", "2024-05-15"],
        "pe_ttm": [9.0, 10.0, 12.0], "pb": [1.3, 1.4, 1.5],
        "ps_ttm": [2.2, 2.5, 3.0], "roe_ttm": [13.0, 14.0, 15.0],
        "revenue_yoy": [7.0, 8.0, 10.0], "net_profit_yoy": [8.0, 9.0, 12.0],
        "eps_ttm": [1.8, 2.0, 2.5],
        "operating_cash_flow_ttm": [0.9e9, 1.0e9, 1.2e9],
        "net_income_ttm": [0.8e9, 0.9e9, 1.0e9],
    })
    cache.upsert_fundamentals("600519", df)
    got = cache.recent_fundamentals_as_of("600519", "2024-06-01", k=2)
    assert len(got) == 2
    # DESC order — newest first
    assert got.iloc[0]["roe_ttm"] == 15.0
    assert got.iloc[1]["roe_ttm"] == 14.0


def test_bars_as_of_excludes_as_of_date(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "bars.db"))
    df = pd.DataFrame({
        "date": ["2024-06-10", "2024-06-11", "2024-06-12", "2024-06-13"],
        "open": [10, 11, 12, 13], "high": [11, 12, 13, 14],
        "low": [9, 10, 11, 12], "close": [10.5, 11.5, 12.5, 13.5],
        "volume": [1e6, 1e6, 1e6, 1e6],
    })
    cache.upsert_daily_bars("600519", df)
    got = cache.bars_as_of("600519", "2024-06-12", lookback_days=10)
    assert (got["date"] < pd.Timestamp("2024-06-12")).all()
    assert len(got) == 2  # 06-10 and 06-11


def test_valuation_history_as_of_respects_lookback(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "val.db"))
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=10, freq="D").strftime("%Y-%m-%d"),
        "pe_ttm": [10.0] * 10, "pb": [1.5] * 10, "ps_ttm": [3.0] * 10,
        "mkt_cap": [1.0e10] * 10, "float_cap": [7.0e9] * 10,
    })
    cache.upsert_valuation_daily("600519", df)
    # Pull a 5-day window before 2024-01-08.
    got = cache.valuation_history_as_of("600519", "2024-01-08", lookback_days=5)
    assert (got["date"] < pd.Timestamp("2024-01-08")).all()
    assert (got["date"] >= pd.Timestamp("2024-01-03")).all()
