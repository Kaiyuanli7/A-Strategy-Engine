"""Unit tests for A-share constraint helpers."""

import pandas as pd
import pytest

from astrategy.config import classify_board, is_st_name
from astrategy.engine.constraints import (
    StockStaticInfo,
    is_at_lower_limit,
    is_at_upper_limit,
    is_suspended,
    lower_limit_price,
    price_limit_pct,
    round_to_lot,
    upper_limit_price,
)


def test_classify_board():
    assert classify_board("600519") == "main_sh"
    assert classify_board("601398") == "main_sh"
    assert classify_board("000858") == "main_sz"
    assert classify_board("002594") == "main_sz"
    assert classify_board("300750") == "chinext"
    assert classify_board("301234") == "chinext"
    assert classify_board("688981") == "star"
    assert classify_board("832000") == "beijing"
    assert classify_board("ABCDEF") == "unknown"


def test_is_st_name():
    assert is_st_name("*ST 中航") is True
    assert is_st_name("ST 华夏") is True
    assert is_st_name("XYZ退") is True
    assert is_st_name("贵州茅台") is False


def test_price_limit_pct():
    assert price_limit_pct(StockStaticInfo("600519", "main_sh", False)) == 0.10
    assert price_limit_pct(StockStaticInfo("300750", "chinext", False)) == 0.20
    assert price_limit_pct(StockStaticInfo("688981", "star", False)) == 0.20
    assert price_limit_pct(StockStaticInfo("000001", "main_sz", True)) == 0.05


def test_limit_prices_main_board():
    info = StockStaticInfo("600519", "main_sh", False)
    assert upper_limit_price(10.00, info) == 11.00
    assert lower_limit_price(10.00, info) == 9.00


def test_limit_prices_chinext():
    info = StockStaticInfo("300750", "chinext", False)
    assert upper_limit_price(10.00, info) == 12.00
    assert lower_limit_price(10.00, info) == 8.00


def test_limit_prices_st():
    info = StockStaticInfo("000001", "main_sz", True)
    assert upper_limit_price(10.00, info) == 10.50
    assert lower_limit_price(10.00, info) == 9.50


def test_is_at_upper_limit():
    info = StockStaticInfo("600519", "main_sh", False)
    assert is_at_upper_limit(11.00, 10.00, info) is True
    assert is_at_upper_limit(10.99, 10.00, info) is False


def test_is_at_lower_limit():
    info = StockStaticInfo("600519", "main_sh", False)
    assert is_at_lower_limit(9.00, 10.00, info) is True
    assert is_at_lower_limit(9.01, 10.00, info) is False


def test_round_to_lot():
    assert round_to_lot(150) == 100
    assert round_to_lot(99) == 0
    assert round_to_lot(2050) == 2000
    assert round_to_lot(100) == 100
    assert round_to_lot(0) == 0


def test_is_suspended_zero_volume():
    bar = pd.Series({"open": 10, "close": 10, "volume": 0})
    assert is_suspended(bar) is True


def test_is_suspended_nan_volume():
    bar = pd.Series({"open": 10, "close": 10, "volume": float("nan")})
    assert is_suspended(bar) is True


def test_is_suspended_normal():
    bar = pd.Series({"open": 10, "close": 10, "volume": 1_000_000})
    assert is_suspended(bar) is False


def test_is_suspended_none():
    assert is_suspended(None) is True
