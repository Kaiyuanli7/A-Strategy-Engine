"""Technical / behavioral factors."""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pandas as pd

from astrategy.factors.base import Factor, FactorContext, FactorParamSpec
from astrategy.factors.registry import register_factor


@register_factor
class MomentumSkipFactor(Factor):
    """
    Factor 3.2 — Momentum (skip-5).

    Thesis: intermediate momentum is one of the most robust factors in A-shares
    (Liu, Stambaugh, Yuan 2019). Skipping the most recent `skip` days avoids
    contamination by short-term reversal.

    Score: `close[t-skip] / close[t-skip-lookback] - 1`. Higher score = stronger
    trailing momentum. All prices are strictly before `as_of` (PIT discipline).
    """

    name: ClassVar[str] = "momentum_skip"
    category: ClassVar[str] = "technical"
    description: ClassVar[str] = (
        "Trailing lookback-day return skipping the most recent `skip` trading "
        "days. Captures intermediate-horizon momentum, filtered for short-term "
        "reversal contamination."
    )
    lookback_days: ClassVar[int] = 60   # cache window the runner reserves
    rebalance_freq: ClassVar[str] = "weekly"
    _param_specs: ClassVar[list[FactorParamSpec]] = [
        FactorParamSpec(name="lookback", type="int", default=20, min=5, max=120,
                        description="Length of the momentum window in trading days."),
        FactorParamSpec(name="skip", type="int", default=5, min=0, max=30,
                        description="Trading days to skip at the most-recent end."),
    ]

    def compute(self, ctx: FactorContext) -> pd.Series:
        lookback = int(self.params["lookback"])
        skip = int(self.params["skip"])
        # Calendar-day window padded for holidays/weekends
        calendar_window = (lookback + skip + 14) * 2

        scores: dict[str, float] = {}
        for code in ctx.universe:
            bars = ctx.bars(code, lookback_days=calendar_window)
            if bars.empty or len(bars) < lookback + skip + 1:
                continue
            # `bars` is strictly before as_of, ASC. Last row is the most recent.
            closes = bars["close"].to_numpy(dtype=float)
            end_close = closes[-(skip + 1)]   # close[t-skip-1] (skip=0 → last row)
            start_close = closes[-(skip + lookback + 1)]
            if start_close <= 0:
                continue
            scores[code] = float(end_close / start_close - 1.0)

        if not scores:
            return pd.Series(dtype="float64")
        return (
            pd.Series(scores, name=self.name)
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
        )
