"""Tests for the synthetic fundamentals / valuation / sector / northbound generators."""

import pandas as pd
import pytest

from astrategy.data.synthetic import (
    DEMO_FUNDAMENTALS,
    generate_synthetic_fundamentals,
    generate_synthetic_northbound,
    generate_synthetic_sector,
    generate_synthetic_valuation_daily,
)


def test_all_demo_codes_have_fundamentals_anchor():
    expected = {
        "600519", "601318", "300750", "601398", "000858",
        "600036", "601012", "002594", "600276", "601888",
    }
    assert set(DEMO_FUNDAMENTALS) >= expected


@pytest.mark.parametrize("code", list(DEMO_FUNDAMENTALS.keys()))
def test_synthetic_fundamentals_nonempty(code):
    df = generate_synthetic_fundamentals(code, "2023-05-18", "2026-05-18")
    assert not df.empty
    assert {"report_date", "announce_date", "pe_ttm", "pb", "roe_ttm", "revenue_yoy"} <= set(df.columns)
    # Anchor values should be in the right ballpark
    anchor = DEMO_FUNDAMENTALS[code]
    assert abs(df["roe_ttm"].mean() - anchor["roe"]) < 4.0


@pytest.mark.parametrize("code", list(DEMO_FUNDAMENTALS.keys()))
def test_synthetic_valuation_daily_nonempty(code):
    df = generate_synthetic_valuation_daily(code, "2023-05-18", "2026-05-18")
    assert not df.empty
    assert {"date", "pe_ttm", "pb", "mkt_cap", "float_cap"} <= set(df.columns)
    # Market cap is positive
    assert (df["mkt_cap"] > 0).all()


@pytest.mark.parametrize("code", list(DEMO_FUNDAMENTALS.keys()))
def test_synthetic_northbound_nonempty(code):
    df = generate_synthetic_northbound(code, "2023-05-18", "2026-05-18")
    assert not df.empty
    # holding_pct is stored as percentage (0.5 to 8.0), not fraction
    assert df["holding_pct"].between(0.0, 10.0).all()
    assert "net_buy_value" in df.columns


@pytest.mark.parametrize("code", list(DEMO_FUNDAMENTALS.keys()))
def test_synthetic_sector_matches_anchor(code):
    sec = generate_synthetic_sector(code)
    assert sec["sw_l1_name"] == DEMO_FUNDAMENTALS[code]["sector_l1"]
    assert sec["sw_l1_code"]  # non-empty stable code


def test_announce_date_after_report_date():
    """PIT correctness: announce_date should always be AFTER report_date."""
    df = generate_synthetic_fundamentals("600519", "2023-05-18", "2026-05-18")
    for _, r in df.iterrows():
        assert pd.Timestamp(r["announce_date"]) > pd.Timestamp(r["report_date"])
