"""Unit tests for AKShare client normalizers on the new alt-data endpoints.

These test the column-renaming + filter logic without hitting the network.
"""

from __future__ import annotations

import pandas as pd

from astrategy.data.akshare_client import AKShareClient


def test_normalize_northbound_renames_and_filters():
    raw = pd.DataFrame({
        "日期": ["2024-01-05", "2024-01-12", "2024-01-19"],
        "持股数量": [100, 110, 120],
        "持股市值": [1000, 1100, 1200],
        "持股比例": [1.0, 1.1, 1.2],
        "净买入金额": [5e6, -2e6, 3e6],
    })
    out = AKShareClient._normalize_northbound(raw, start="2024-01-10", end="2024-01-20")
    assert list(out.columns) == [
        "date", "holding_shares", "holding_value", "holding_pct",
        "net_buy_shares", "net_buy_value",
    ]
    # Filter trimmed the first row
    assert len(out) == 2
    assert out.iloc[0]["date"] == "2024-01-12"


def test_normalize_northbound_returns_empty_on_missing_date_col():
    raw = pd.DataFrame({"foo": [1, 2, 3]})
    out = AKShareClient._normalize_northbound(raw, start="2024-01-01", end="2024-12-31")
    assert out.empty


def test_normalize_margin_filters_to_code_and_dates():
    raw = pd.DataFrame({
        "信用交易日期": ["2024-01-05", "2024-01-12", "2024-01-19"],
        "证券代码": ["600519", "600519", "601318"],
        "融资余额": [1e9, 1.1e9, 5e8],
        "融券余额": [1e7, 1.2e7, 4e6],
        "融资买入额": [2e7, 3e7, 1e7],
        "融资偿还额": [1.5e7, 2.5e7, 0.8e7],
    })
    out = AKShareClient._normalize_margin(raw, code="600519",
                                          start="2024-01-01", end="2024-12-31")
    assert len(out) == 2
    assert (out["financing_balance"] > 1e9 - 1).all()
    # net = buy - repay
    assert out.iloc[0]["net_financing_change"] == 2e7 - 1.5e7


def test_normalize_lhb_classifies_seat_types():
    raw = pd.DataFrame({
        "代码": ["600519", "600519", "600519"],
        "上榜日": ["2024-06-01", "2024-06-01", "2024-06-01"],
        "营业部名称": ["机构专用", "申万宏源证券", "中信证券"],
        "买入金额": [1e8, 2e7, 1.5e7],
        "卖出金额": [5e7, 1e7, 1.2e7],
        "净买额": [5e7, 1e7, 3e6],
    })
    out = AKShareClient._normalize_lhb(raw)
    types = set(out["seat_type"])
    assert "institutional" in types
    assert "hot_money" in types
    assert (out["seq"] == [0, 1, 2]).all()


def test_normalize_limit_pool_marks_first_seal():
    raw = pd.DataFrame({
        "代码": ["600519", "601318", "300750"],
        "连板数": [1, 3, 2],
        "换手率": [5.2, 12.0, 3.1],
    })
    out = AKShareClient._normalize_limit_pool(raw, date="2024-06-15", direction="up")
    assert (out["direction"] == "up").all()
    assert list(out["is_first"]) == [1, 0, 0]
    assert (out["date"] == "2024-06-15").all()
