"""Northbound flow factors (北向资金)."""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pandas as pd

from astrategy.factors.base import Factor, FactorContext, FactorParamSpec
from astrategy.factors.registry import register_factor


@register_factor
class NorthboundMomentumFactor(Factor):
    """
    Factor 1.1 — Northbound Momentum (北向资金动量).

    Thesis: institutional foreign capital flowing through Hong Kong → Stock
    Connect leads retail by 2-3 weeks. Persistent accumulation signals
    fundamental conviction that retail hasn't priced in yet.

    Score: sum of trailing `lookback` daily northbound net-buy values, divided
    by the stock's free-float market cap (latest pre-as_of valuation). Higher
    score = stronger persistent foreign accumulation relative to size.
    """

    name: ClassVar[str] = "northbound_momentum"
    category: ClassVar[str] = "flow"
    description: ClassVar[str] = (
        "Trailing northbound net-buy value normalized by free-float market cap. "
        "Captures persistent Stock Connect accumulation."
    )
    lookback_days: ClassVar[int] = 30  # default trailing window the runner reserves
    rebalance_freq: ClassVar[str] = "weekly"
    _param_specs: ClassVar[list[FactorParamSpec]] = [
        FactorParamSpec(
            name="lookback",
            type="int",
            default=5,
            description="Trailing trading-day window for cumulative net-buy.",
            min=2,
            max=60,
        ),
    ]

    def compute(self, ctx: FactorContext) -> pd.Series:
        lookback = int(self.params["lookback"])
        # We pull a slightly larger calendar-day window so the lookback in
        # trading-days is satisfied even across holidays.
        calendar_window = max(lookback + 10, lookback * 2)

        scores: dict[str, float] = {}
        for code in ctx.universe:
            nb = ctx.northbound(code, lookback_days=calendar_window)
            if nb.empty:
                continue
            # Take the last `lookback` trading days available.
            recent = nb.tail(lookback)
            if len(recent) < max(2, lookback // 2):
                continue
            net_sum = float(recent["net_buy_value"].sum())
            val = ctx.valuation(code)
            float_cap = (val or {}).get("float_cap") if val else None
            if float_cap is None or float_cap <= 0:
                # Fall back to total mkt_cap; otherwise abstain.
                float_cap = (val or {}).get("mkt_cap") if val else None
                if float_cap is None or float_cap <= 0:
                    continue
            scores[code] = net_sum / float(float_cap)

        if not scores:
            return pd.Series(dtype="float64")
        return pd.Series(scores, name=self.name).replace([np.inf, -np.inf], np.nan).dropna()
