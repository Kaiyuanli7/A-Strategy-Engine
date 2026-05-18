"""Tests for AKShareClient.get_quarterly_fundamentals and its normalizer.

These run without network; we mock the wide-format AKShare response and
verify the pivot, indicator-name rename, and announce_date estimation.
"""

from __future__ import annotations

import pandas as pd
import pytest

from astrategy.data.akshare_client import AKShareClient


def _sample_akshare_response() -> pd.DataFrame:
    """Mimic stock_financial_abstract output: indicator rows, quarter columns."""
    return pd.DataFrame({
        "选项": ["盈利能力", "盈利能力", "财务风险", "成长能力", "成长能力"],
        "指标": [
            "净资产收益率(摊薄)",
            "摊薄每股收益",
            "经营活动产生的现金流量净额",
            "营业总收入同比增长",
            "归属于母公司股东的净利润同比增长",
        ],
        "20240331": [3.2, 0.8, 1.2e9, 12.5, 18.0],
        "20231231": [12.5, 3.0, 4.8e9, 10.0, 15.0],
        "20230930": [9.0, 2.2, 3.5e9, 11.0, 16.5],
        "20230630": [6.0, 1.4, 2.0e9, 9.5, 13.0],
    })


def test_normalizer_basic_shape():
    raw = _sample_akshare_response()
    out = AKShareClient._normalize_quarterly_fundamentals(raw)
    assert not out.empty
    # 4 quarters in the input
    assert len(out) == 4
    # All schema columns present
    for col in ("report_date", "announce_date", "roe_ttm", "eps_ttm",
                "operating_cash_flow_ttm", "net_income_ttm",
                "revenue_yoy", "net_profit_yoy"):
        assert col in out.columns


def test_normalizer_renames_indicators():
    raw = _sample_akshare_response()
    out = AKShareClient._normalize_quarterly_fundamentals(raw)
    # Q1 2024 row — verify values mapped correctly
    q1 = out[out["report_date"] == "2024-03-31"].iloc[0]
    assert q1["roe_ttm"] == 3.2
    assert q1["eps_ttm"] == 0.8
    assert q1["operating_cash_flow_ttm"] == 1.2e9
    assert q1["revenue_yoy"] == 12.5
    assert q1["net_profit_yoy"] == 18.0
    # net_income_ttm wasn't in the sample — should be NaN
    assert pd.isna(q1["net_income_ttm"])


def test_normalizer_announce_date_is_45_days_after_report():
    raw = _sample_akshare_response()
    out = AKShareClient._normalize_quarterly_fundamentals(raw)
    for _, row in out.iterrows():
        rep = pd.Timestamp(row["report_date"])
        ann = pd.Timestamp(row["announce_date"])
        assert (ann - rep).days == 45


def test_normalizer_accepts_weighted_roe_variant():
    """Some AKShare versions report '净资产收益率(加权)' instead of '(摊薄)'."""
    raw = pd.DataFrame({
        "选项": ["盈利能力"],
        "指标": ["净资产收益率(加权)"],
        "20240331": [11.5],
    })
    out = AKShareClient._normalize_quarterly_fundamentals(raw)
    assert len(out) == 1
    assert out.iloc[0]["roe_ttm"] == 11.5


def test_normalizer_returns_empty_when_no_matching_indicators():
    raw = pd.DataFrame({
        "选项": ["foo"],
        "指标": ["some_unknown_indicator"],
        "20240331": [42.0],
    })
    out = AKShareClient._normalize_quarterly_fundamentals(raw)
    assert out.empty


def test_normalizer_returns_empty_on_unrecognized_schema():
    """Response without the 指标 column should be rejected cleanly."""
    raw = pd.DataFrame({"foo": [1], "bar": [2]})
    out = AKShareClient._normalize_quarterly_fundamentals(raw)
    assert out.empty


def test_normalizer_skips_non_date_columns():
    """Columns that don't match YYYYMMDD should be ignored."""
    raw = pd.DataFrame({
        "选项": ["盈利能力", "盈利能力"],
        "指标": ["净资产收益率(摊薄)", "摊薄每股收益"],
        "单位": ["%", "元"],          # extra non-date column — should be skipped
        "20240331": [11.5, 1.2],
        "20231231": [14.8, 3.0],
    })
    out = AKShareClient._normalize_quarterly_fundamentals(raw)
    # 2 quarter columns → 2 output rows
    assert len(out) == 2


def test_normalizer_deduplicates_indicator_aliases():
    """If both '(摊薄)' and '(加权)' ROE appear, take the first match only."""
    raw = pd.DataFrame({
        "选项": ["盈利能力", "盈利能力"],
        "指标": ["净资产收益率(摊薄)", "净资产收益率(加权)"],
        "20240331": [11.5, 14.0],
    })
    out = AKShareClient._normalize_quarterly_fundamentals(raw)
    assert len(out) == 1
    # Whichever matched first; the dict iteration order preserves insertion
    assert out.iloc[0]["roe_ttm"] in (11.5, 14.0)


def test_normalizer_parses_yyyymmdd_dates():
    raw = _sample_akshare_response()
    out = AKShareClient._normalize_quarterly_fundamentals(raw)
    # Dates ascending
    dates = list(out["report_date"])
    assert dates == sorted(dates)
    assert dates[0] == "2023-06-30"
    assert dates[-1] == "2024-03-31"
