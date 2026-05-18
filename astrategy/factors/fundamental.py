"""Fundamental factors (基本面)."""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pandas as pd

from astrategy.factors.base import Factor, FactorContext, FactorParamSpec
from astrategy.factors.registry import register_factor


@register_factor
class EarningsQualityFactor(Factor):
    """
    Factor 2.1 — Earnings Quality (盈利质量).

    Thesis: improving profitability backed by real cash flows predicts
    future outperformance. Earnings "growth" without cash flow is often
    accounting tricks (revenue recognition, accrual buildup) that mean-revert.

    Score: `(ROE_q - ROE_q-1) * I(OCF_q / NI_q >= min_ocf_ratio)`.

    - `recent_fundamentals(code, k=2)` returns the two latest quarters with
      `announce_date < as_of` (DESC).
    - Indicator gates on OCF / NI; if NI <= 0 or OCF is missing, the factor
      abstains.
    """

    name: ClassVar[str] = "earnings_quality"
    category: ClassVar[str] = "fundamental"
    description: ClassVar[str] = (
        "QoQ ROE improvement gated by OCF / NI quality. Stocks with rising "
        "ROE backed by real cash flow score positive; accruals-driven 'growth' "
        "abstains."
    )
    lookback_days: ClassVar[int] = 200  # ~2 quarters of pre-announce lag
    rebalance_freq: ClassVar[str] = "monthly"
    _param_specs: ClassVar[list[FactorParamSpec]] = [
        FactorParamSpec(name="min_ocf_ratio", type="float", default=0.7, min=0.0, max=2.0,
                        description="Minimum OCF / NI ratio to clear the quality gate."),
    ]

    def compute(self, ctx: FactorContext) -> pd.Series:
        min_ratio = float(self.params["min_ocf_ratio"])
        scores: dict[str, float] = {}
        for code in ctx.universe:
            recent = ctx.recent_fundamentals(code, k=2)
            if len(recent) < 2:
                continue
            # `recent` is DESC by announce_date: row 0 = newest, row 1 = prior.
            new = recent.iloc[0]
            old = recent.iloc[1]
            roe_now = new.get("roe_ttm")
            roe_prev = old.get("roe_ttm")
            ocf = new.get("operating_cash_flow_ttm")
            ni = new.get("net_income_ttm")
            if (pd.isna(roe_now) or pd.isna(roe_prev) or pd.isna(ocf) or pd.isna(ni)
                    or ni <= 0):
                continue
            ratio = float(ocf) / float(ni)
            if ratio < min_ratio:
                continue
            scores[code] = float(roe_now) - float(roe_prev)

        if not scores:
            return pd.Series(dtype="float64")
        return (
            pd.Series(scores, name=self.name)
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
        )


@register_factor
class ValuationCompositeFactor(Factor):
    """
    Factor 2.4 — Valuation Composite (估值复合因子).

    Thesis: stocks cheap on multiple valuation metrics outperform over
    medium-term horizons in A-shares.

    Score (per stock): negative of the mean rank-percentile of each metric
    against its own trailing `history_days` history. Higher score = cheaper
    on PE, PB, PS combined.

    NaN if there's no valuation history or all three metrics are missing.
    """

    name: ClassVar[str] = "valuation_composite"
    category: ClassVar[str] = "fundamental"
    description: ClassVar[str] = (
        "Composite of trailing PE / PB / PS percentile vs the stock's own "
        "history. Lower percentile = cheaper = higher score."
    )
    lookback_days: ClassVar[int] = 756
    rebalance_freq: ClassVar[str] = "monthly"
    _param_specs: ClassVar[list[FactorParamSpec]] = [
        FactorParamSpec(name="history_days", type="int", default=756, min=126, max=1500,
                        description="Trailing calendar-day window for percentile "
                                    "(default ~3 trading years)."),
    ]

    def compute(self, ctx: FactorContext) -> pd.Series:
        history_days = int(self.params["history_days"])
        scores: dict[str, float] = {}
        for code in ctx.universe:
            hist = ctx.valuation_history(code, lookback_days=history_days)
            if hist.empty or len(hist) < 20:
                continue
            latest = hist.iloc[-1]
            metric_percentiles: list[float] = []
            for col in ("pe_ttm", "pb", "ps_ttm"):
                series = hist[col].dropna()
                if len(series) < 20:
                    continue
                latest_v = latest.get(col)
                if pd.isna(latest_v) or latest_v <= 0:
                    continue
                # Percentile rank of `latest_v` within `series` (0..1).
                pct = float((series < latest_v).sum()) / float(len(series))
                metric_percentiles.append(pct)
            if not metric_percentiles:
                continue
            # Higher percentile = more expensive → lower score.
            scores[code] = -float(np.mean(metric_percentiles))

        if not scores:
            return pd.Series(dtype="float64")
        return (
            pd.Series(scores, name=self.name)
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
        )
