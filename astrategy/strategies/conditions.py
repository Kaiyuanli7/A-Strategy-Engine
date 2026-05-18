"""
Composable condition specs + evaluator for ComposableStrategy.

Each ConditionSpec variant is a Pydantic discriminated-union model. Given a
CondData bundle (OHLCV + PIT-joined fundamentals + valuation + northbound),
`precompute_condition(spec, data)` returns a boolean pd.Series indexed by
ohlcv.index — True where the condition holds.

The strategy AND-reduces multiple conditions into a single entry signal at
initialize time, then on_bar is just a date-keyed lookup.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, Union

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from astrategy.strategies import indicators as ind


# ---------- ConditionSpec variants ------------------------------------------

class _SpecBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MACrossCond(_SpecBase):
    type: Literal["ma_cross"]
    fast: int = 5
    slow: int = 20
    direction: Literal["up", "down"] = "up"


class PriceVsMACond(_SpecBase):
    type: Literal["price_vs_ma"]
    period: int = 20
    op: Literal[">", "<"] = ">"


class RSICond(_SpecBase):
    type: Literal["rsi"]
    period: int = 14
    threshold: float = 30.0
    direction: Literal["above", "below", "cross_up", "cross_down"] = "below"


class BollingerBreakoutCond(_SpecBase):
    type: Literal["bollinger_breakout"]
    period: int = 20
    k: float = 2.0
    band: Literal["upper", "lower"] = "upper"


class MACDCond(_SpecBase):
    type: Literal["macd"]
    fast: int = 12
    slow: int = 26
    signal: int = 9
    event: Literal[
        "hist_cross_up", "hist_cross_down", "macd_above_signal", "macd_below_signal"
    ] = "hist_cross_up"


class VolumeSpikeCond(_SpecBase):
    type: Literal["volume_spike"]
    period: int = 20
    multiple: float = 2.0


class PEBoundCond(_SpecBase):
    type: Literal["pe_bound"]
    min: float | None = None
    max: float | None = None


class PBBoundCond(_SpecBase):
    type: Literal["pb_bound"]
    min: float | None = None
    max: float | None = None


class PSBoundCond(_SpecBase):
    type: Literal["ps_bound"]
    min: float | None = None
    max: float | None = None


class ROEBoundCond(_SpecBase):
    type: Literal["roe_bound"]
    min: float | None = None
    max: float | None = None


class RevenueGrowthCond(_SpecBase):
    type: Literal["revenue_growth"]
    min: float | None = None
    max: float | None = None


class NorthboundNetInflowCond(_SpecBase):
    type: Literal["nb_net_inflow"]
    window: int = 5
    min_value: float = 0.0


class NorthboundHoldingPctCond(_SpecBase):
    type: Literal["nb_holding_pct"]
    min: float | None = None
    max: float | None = None


ConditionSpec = Annotated[
    Union[
        MACrossCond, PriceVsMACond, RSICond, BollingerBreakoutCond, MACDCond,
        VolumeSpikeCond, PEBoundCond, PBBoundCond, PSBoundCond, ROEBoundCond,
        RevenueGrowthCond, NorthboundNetInflowCond, NorthboundHoldingPctCond,
    ],
    Field(discriminator="type"),
]


CONDITION_TYPES: list[dict] = [
    {"type": "ma_cross", "label": "MA crossover",
     "params": {"fast": "int", "slow": "int", "direction": ["up", "down"]}},
    {"type": "price_vs_ma", "label": "Price vs MA",
     "params": {"period": "int", "op": [">", "<"]}},
    {"type": "rsi", "label": "RSI threshold",
     "params": {"period": "int", "threshold": "float",
                "direction": ["above", "below", "cross_up", "cross_down"]}},
    {"type": "bollinger_breakout", "label": "Bollinger breakout",
     "params": {"period": "int", "k": "float", "band": ["upper", "lower"]}},
    {"type": "macd", "label": "MACD signal",
     "params": {"fast": "int", "slow": "int", "signal": "int",
                "event": ["hist_cross_up", "hist_cross_down",
                          "macd_above_signal", "macd_below_signal"]}},
    {"type": "volume_spike", "label": "Volume spike",
     "params": {"period": "int", "multiple": "float"}},
    {"type": "pe_bound", "label": "PE bound",
     "params": {"min": "float?", "max": "float?"}},
    {"type": "pb_bound", "label": "PB bound",
     "params": {"min": "float?", "max": "float?"}},
    {"type": "ps_bound", "label": "PS bound",
     "params": {"min": "float?", "max": "float?"}},
    {"type": "roe_bound", "label": "ROE bound (%)",
     "params": {"min": "float?", "max": "float?"}},
    {"type": "revenue_growth", "label": "Revenue YoY (%)",
     "params": {"min": "float?", "max": "float?"}},
    {"type": "nb_net_inflow", "label": "Northbound net inflow",
     "params": {"window": "int", "min_value": "float"}},
    {"type": "nb_holding_pct", "label": "Northbound holding %",
     "params": {"min": "float?", "max": "float?"}},
]


# ---------- Data bundle ------------------------------------------------------

@dataclass
class CondData:
    """
    All per-stock data needed to evaluate conditions, pre-aligned to the
    OHLCV trading-day index. Fundamentals are PIT forward-filled
    (announce_date <= bar date), then reindexed to ohlcv.index.
    """
    ohlcv: pd.DataFrame                       # date-indexed
    fundamentals: pd.DataFrame | None = None  # reindexed to ohlcv.index
    valuation: pd.DataFrame | None = None     # reindexed to ohlcv.index
    northbound: pd.DataFrame | None = None    # reindexed to ohlcv.index


def build_cond_data(
    ohlcv: pd.DataFrame,
    fundamentals: pd.DataFrame | None = None,
    valuation: pd.DataFrame | None = None,
    northbound: pd.DataFrame | None = None,
) -> CondData:
    """
    Construct CondData with PIT-safe forward-fill for fundamentals and
    daily-aligned valuation / northbound.

    PIT rule for fundamentals: for each bar date D, use the most recent row
    whose announce_date <= D. Never use a row whose announce_date > D.
    """
    if not isinstance(ohlcv.index, pd.DatetimeIndex):
        ohlcv = ohlcv.set_index(pd.to_datetime(ohlcv.index))

    fund_aligned = None
    if fundamentals is not None and not fundamentals.empty:
        f = fundamentals.copy()
        f["announce_date"] = pd.to_datetime(f["announce_date"])
        f = f.sort_values("announce_date").set_index("announce_date")
        # reindex with method=ffill aligns each bar date with the most recent
        # row whose announce_date <= bar date
        fund_aligned = f.reindex(ohlcv.index, method="ffill")

    val_aligned = None
    if valuation is not None and not valuation.empty:
        v = valuation.copy()
        v["date"] = pd.to_datetime(v["date"])
        v = v.set_index("date").sort_index()
        val_aligned = v.reindex(ohlcv.index, method="ffill")

    nb_aligned = None
    if northbound is not None and not northbound.empty:
        n = northbound.copy()
        n["date"] = pd.to_datetime(n["date"])
        n = n.set_index("date").sort_index()
        nb_aligned = n.reindex(ohlcv.index, method="ffill")

    return CondData(
        ohlcv=ohlcv,
        fundamentals=fund_aligned,
        valuation=val_aligned,
        northbound=nb_aligned,
    )


# ---------- Evaluator --------------------------------------------------------

def precompute_condition(spec, data: CondData) -> pd.Series:
    """
    Parse `spec` (dict or BaseModel) into the discriminated union and dispatch
    to the right evaluator. Returns a bool Series aligned to data.ohlcv.index.
    """
    parsed = _parse_spec(spec)
    t = parsed.type
    if t == "ma_cross":
        return _eval_ma_cross(parsed, data)
    if t == "price_vs_ma":
        return _eval_price_vs_ma(parsed, data)
    if t == "rsi":
        return _eval_rsi(parsed, data)
    if t == "bollinger_breakout":
        return _eval_bollinger(parsed, data)
    if t == "macd":
        return _eval_macd(parsed, data)
    if t == "volume_spike":
        return _eval_volume_spike(parsed, data)
    if t == "pe_bound":
        return _eval_bound(data.valuation, "pe_ttm", parsed.min, parsed.max, data.ohlcv.index)
    if t == "pb_bound":
        return _eval_bound(data.valuation, "pb", parsed.min, parsed.max, data.ohlcv.index)
    if t == "ps_bound":
        return _eval_bound(data.valuation, "ps_ttm", parsed.min, parsed.max, data.ohlcv.index)
    if t == "roe_bound":
        return _eval_bound(data.fundamentals, "roe_ttm", parsed.min, parsed.max, data.ohlcv.index)
    if t == "revenue_growth":
        return _eval_bound(data.fundamentals, "revenue_yoy", parsed.min, parsed.max, data.ohlcv.index)
    if t == "nb_net_inflow":
        return _eval_nb_net_inflow(parsed, data)
    if t == "nb_holding_pct":
        return _eval_bound(data.northbound, "holding_pct", parsed.min, parsed.max, data.ohlcv.index)
    raise ValueError(f"unknown condition type: {t}")


def _parse_spec(spec):
    """Accept either a Pydantic model instance or a dict."""
    if isinstance(spec, _SpecBase):
        return spec

    class _Wrapper(BaseModel):
        s: ConditionSpec

    return _Wrapper.model_validate({"s": spec}).s


def _bool_index(idx: pd.DatetimeIndex, source: pd.Series) -> pd.Series:
    """Reindex source onto idx, fill NaN with False."""
    return source.reindex(idx).fillna(False).astype(bool)


# ----- technical -----

def _eval_ma_cross(spec: MACrossCond, data: CondData) -> pd.Series:
    close = data.ohlcv["close"].astype(float)
    fast_ma = ind.sma(close, spec.fast)
    slow_ma = ind.sma(close, spec.slow)
    if spec.direction == "up":
        return _bool_index(data.ohlcv.index, ind.cross_up(fast_ma, slow_ma))
    return _bool_index(data.ohlcv.index, ind.cross_down(fast_ma, slow_ma))


def _eval_price_vs_ma(spec: PriceVsMACond, data: CondData) -> pd.Series:
    close = data.ohlcv["close"].astype(float)
    ma = ind.sma(close, spec.period)
    if spec.op == ">":
        return _bool_index(data.ohlcv.index, close > ma)
    return _bool_index(data.ohlcv.index, close < ma)


def _eval_rsi(spec: RSICond, data: CondData) -> pd.Series:
    close = data.ohlcv["close"].astype(float)
    r = ind.rsi(close, spec.period)
    if spec.direction == "above":
        return _bool_index(data.ohlcv.index, r > spec.threshold)
    if spec.direction == "below":
        return _bool_index(data.ohlcv.index, r < spec.threshold)
    threshold = pd.Series(spec.threshold, index=close.index)
    if spec.direction == "cross_up":
        return _bool_index(data.ohlcv.index, ind.cross_up(r, threshold))
    return _bool_index(data.ohlcv.index, ind.cross_down(r, threshold))


def _eval_bollinger(spec: BollingerBreakoutCond, data: CondData) -> pd.Series:
    close = data.ohlcv["close"].astype(float)
    _, upper, lower = ind.bollinger(close, spec.period, spec.k)
    if spec.band == "upper":
        return _bool_index(data.ohlcv.index, close > upper)
    return _bool_index(data.ohlcv.index, close < lower)


def _eval_macd(spec: MACDCond, data: CondData) -> pd.Series:
    close = data.ohlcv["close"].astype(float)
    macd_line, signal_line, hist = ind.macd(close, spec.fast, spec.slow, spec.signal)
    zero = pd.Series(0.0, index=close.index)
    if spec.event == "hist_cross_up":
        return _bool_index(data.ohlcv.index, ind.cross_up(hist, zero))
    if spec.event == "hist_cross_down":
        return _bool_index(data.ohlcv.index, ind.cross_down(hist, zero))
    if spec.event == "macd_above_signal":
        return _bool_index(data.ohlcv.index, macd_line > signal_line)
    return _bool_index(data.ohlcv.index, macd_line < signal_line)


def _eval_volume_spike(spec: VolumeSpikeCond, data: CondData) -> pd.Series:
    vol = data.ohlcv["volume"].astype(float)
    ratio = ind.volume_ratio(vol, spec.period)
    return _bool_index(data.ohlcv.index, ratio >= spec.multiple)


# ----- bound / fundamentals / valuation / northbound -----

def _eval_bound(
    src: pd.DataFrame | None,
    col: str,
    lo: float | None,
    hi: float | None,
    idx: pd.DatetimeIndex,
) -> pd.Series:
    if src is None or col not in src.columns:
        return pd.Series(False, index=idx)
    s = src[col].reindex(idx)
    mask = s.notna()
    if lo is not None:
        mask &= s >= lo
    if hi is not None:
        mask &= s <= hi
    return mask.fillna(False).astype(bool)


def _eval_nb_net_inflow(spec: NorthboundNetInflowCond, data: CondData) -> pd.Series:
    if data.northbound is None or "net_buy_value" not in data.northbound.columns:
        return pd.Series(False, index=data.ohlcv.index)
    nb = data.northbound["net_buy_value"].reindex(data.ohlcv.index)
    rolling = nb.rolling(spec.window, min_periods=spec.window).sum()
    return (rolling >= spec.min_value).fillna(False).astype(bool)
