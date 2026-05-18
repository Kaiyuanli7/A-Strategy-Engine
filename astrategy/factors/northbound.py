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


@register_factor
class NorthboundAccelerationFactor(Factor):
    """
    Factor 1.2 — Northbound Holding Acceleration (北向资金加速度).

    Thesis: acceleration of foreign buying signals strengthening conviction
    — institutions are not just maintaining a position but ramping it.

    Score: difference between two consecutive trailing windows of net-buy
    value, normalized by free-float market cap:

        (sum(net_buy[t-window:t]) - sum(net_buy[t-window-gap:t-gap])) / float_cap

    Higher score = recent window outpacing the earlier one.
    """

    name: ClassVar[str] = "northbound_acceleration"
    category: ClassVar[str] = "flow"
    description: ClassVar[str] = (
        "Second-derivative of northbound flow: latest window's net-buy minus "
        "the prior window's, normalized by free-float market cap. Captures "
        "institutions ramping rather than maintaining a position."
    )
    lookback_days: ClassVar[int] = 60
    rebalance_freq: ClassVar[str] = "weekly"
    _param_specs: ClassVar[list[FactorParamSpec]] = [
        FactorParamSpec(name="window", type="int", default=5, min=2, max=30,
                        description="Trailing trading-day window per side."),
        FactorParamSpec(name="gap", type="int", default=5, min=1, max=20,
                        description="Gap between the two windows."),
    ]

    def compute(self, ctx: FactorContext) -> pd.Series:
        window = int(self.params["window"])
        gap = int(self.params["gap"])
        # Need window + gap trading days; pad heavily for holidays/weekends.
        calendar_window = max((window + gap) * 3, 30)

        scores: dict[str, float] = {}
        for code in ctx.universe:
            nb = ctx.northbound(code, lookback_days=calendar_window)
            if nb.empty or len(nb) < window + gap + 1:
                continue
            net_buy = nb["net_buy_value"].astype(float).to_numpy()
            # Recent: last `window` rows. Prior: `window` rows ending `gap` days earlier.
            recent = float(net_buy[-window:].sum())
            prior_end = len(net_buy) - gap
            prior_start = prior_end - window
            if prior_start < 0:
                continue
            prior = float(net_buy[prior_start:prior_end].sum())

            val = ctx.valuation(code)
            float_cap = (val or {}).get("float_cap") if val else None
            if float_cap is None or float_cap <= 0:
                float_cap = (val or {}).get("mkt_cap") if val else None
                if float_cap is None or float_cap <= 0:
                    continue
            scores[code] = (recent - prior) / float(float_cap)

        if not scores:
            return pd.Series(dtype="float64")
        return (
            pd.Series(scores, name=self.name)
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
        )
