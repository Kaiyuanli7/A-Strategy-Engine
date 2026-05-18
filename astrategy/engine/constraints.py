"""A-share market constraint helpers: price limits, lot rounding, suspension detection."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from astrategy.config import (
    BOARD_BJ,
    BOARD_CHINEXT,
    BOARD_MAIN_SH,
    BOARD_MAIN_SZ,
    BOARD_STAR,
    LOT_SIZE,
    PRICE_LIMIT_PCT,
    ST_PRICE_LIMIT_PCT,
)


@dataclass(frozen=True)
class StockStaticInfo:
    code: str
    board: str
    is_st: bool = False


def price_limit_pct(info: StockStaticInfo) -> float:
    if info.is_st:
        return ST_PRICE_LIMIT_PCT
    return PRICE_LIMIT_PCT.get(info.board, 0.10)


def _round_price(x: float) -> float:
    """Stock prices in CN markets quote at 0.01 yuan tick. Round to 2dp."""
    return round(x, 2)


def upper_limit_price(prev_close: float, info: StockStaticInfo) -> float:
    return _round_price(prev_close * (1.0 + price_limit_pct(info)))


def lower_limit_price(prev_close: float, info: StockStaticInfo) -> float:
    return _round_price(prev_close * (1.0 - price_limit_pct(info)))


def is_at_upper_limit(close: float, prev_close: float, info: StockStaticInfo, eps: float = 1e-4) -> bool:
    return abs(close - upper_limit_price(prev_close, info)) < eps


def is_at_lower_limit(close: float, prev_close: float, info: StockStaticInfo, eps: float = 1e-4) -> bool:
    return abs(close - lower_limit_price(prev_close, info)) < eps


def round_to_lot(shares: float, lot: int = LOT_SIZE) -> int:
    """Floor shares down to the nearest lot multiple."""
    if shares < lot:
        return 0
    return int(shares // lot) * lot


def is_suspended(bar: pd.Series | None) -> bool:
    """Treat zero / missing volume as a suspension day."""
    if bar is None:
        return True
    vol = bar.get("volume")
    if vol is None or pd.isna(vol):
        return True
    return float(vol) <= 0.0
