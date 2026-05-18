"""Earnings Quality factor (2.1)."""

from __future__ import annotations

import pandas as pd

from astrategy.data.cache import SQLiteCache
from astrategy.factors.base import FactorContext
from astrategy.factors.fundamental import EarningsQualityFactor


def _seed_two_quarters(
    cache: SQLiteCache, code: str,
    roe_prev: float, roe_now: float,
    ocf_now: float, ni_now: float,
):
    df = pd.DataFrame({
        "report_date": ["2023-12-31", "2024-03-31"],
        "announce_date": ["2024-02-15", "2024-05-15"],
        "pe_ttm": [10.0, 12.0], "pb": [1.4, 1.5], "ps_ttm": [2.5, 3.0],
        "roe_ttm": [roe_prev, roe_now],
        "revenue_yoy": [8.0, 10.0], "net_profit_yoy": [9.0, 12.0],
        "eps_ttm": [2.0, 2.5],
        # OCF / NI only matter for the newest row; backfill the older with sane values.
        "operating_cash_flow_ttm": [1.0e9, ocf_now],
        "net_income_ttm": [0.9e9, ni_now],
    })
    cache.upsert_fundamentals(code, df)


def test_factor_registered():
    from astrategy.factors import get_factor
    assert get_factor("earnings_quality") is EarningsQualityFactor


def test_default_min_ocf_ratio():
    f = EarningsQualityFactor()
    assert f.params["min_ocf_ratio"] == 0.7


def test_rising_roe_high_quality_scores_positive(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "good.db"))
    _seed_two_quarters(cache, "GOOD",
                       roe_prev=12.0, roe_now=15.0,
                       ocf_now=1.0e9, ni_now=1.0e9)  # ratio = 1.0, passes 0.7 gate
    f = EarningsQualityFactor()
    ctx = FactorContext(cache=cache, universe=["GOOD"], as_of=pd.Timestamp("2024-06-01"))
    scores = f.compute(ctx)
    assert scores["GOOD"] == 3.0   # 15 - 12


def test_rising_roe_low_quality_abstains(tmp_path):
    """High accruals: NI=1B but OCF=300M → ratio 0.3, below the 0.7 gate."""
    cache = SQLiteCache(db_path=str(tmp_path / "accr.db"))
    _seed_two_quarters(cache, "ACCRUALS",
                       roe_prev=12.0, roe_now=15.0,
                       ocf_now=3.0e8, ni_now=1.0e9)
    f = EarningsQualityFactor()
    ctx = FactorContext(cache=cache, universe=["ACCRUALS"], as_of=pd.Timestamp("2024-06-01"))
    scores = f.compute(ctx)
    assert "ACCRUALS" not in scores or pd.isna(scores.get("ACCRUALS", float("nan")))


def test_falling_roe_scores_negative(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "fall.db"))
    _seed_two_quarters(cache, "DECLINE",
                       roe_prev=15.0, roe_now=10.0,
                       ocf_now=1.0e9, ni_now=1.0e9)
    f = EarningsQualityFactor()
    ctx = FactorContext(cache=cache, universe=["DECLINE"], as_of=pd.Timestamp("2024-06-01"))
    scores = f.compute(ctx)
    assert scores["DECLINE"] == -5.0


def test_only_one_quarter_available_abstains(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "one.db"))
    df = pd.DataFrame({
        "report_date": ["2024-03-31"],
        "announce_date": ["2024-05-15"],
        "pe_ttm": [12.0], "pb": [1.5], "ps_ttm": [3.0],
        "roe_ttm": [15.0],
        "revenue_yoy": [10.0], "net_profit_yoy": [12.0], "eps_ttm": [2.5],
        "operating_cash_flow_ttm": [1.0e9],
        "net_income_ttm": [1.0e9],
    })
    cache.upsert_fundamentals("ONE", df)
    f = EarningsQualityFactor()
    ctx = FactorContext(cache=cache, universe=["ONE"], as_of=pd.Timestamp("2024-06-01"))
    scores = f.compute(ctx)
    assert scores.empty


def test_negative_ni_abstains(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "loss.db"))
    _seed_two_quarters(cache, "LOSS",
                       roe_prev=12.0, roe_now=15.0,
                       ocf_now=1.0e9, ni_now=-1.0e8)
    f = EarningsQualityFactor()
    ctx = FactorContext(cache=cache, universe=["LOSS"], as_of=pd.Timestamp("2024-06-01"))
    scores = f.compute(ctx)
    assert "LOSS" not in scores


def test_pit_discipline_excludes_future_announcements(tmp_path):
    """If the second-quarter announcement is still in the future, abstain."""
    cache = SQLiteCache(db_path=str(tmp_path / "pit.db"))
    _seed_two_quarters(cache, "PIT",
                       roe_prev=12.0, roe_now=15.0,
                       ocf_now=1.0e9, ni_now=1.0e9)
    f = EarningsQualityFactor()
    # 2024-04-01 is before 2024-05-15 (Q1 announce); only one row visible.
    ctx = FactorContext(cache=cache, universe=["PIT"], as_of=pd.Timestamp("2024-04-01"))
    assert f.compute(ctx).empty
