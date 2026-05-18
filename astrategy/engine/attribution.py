"""
Post-hoc portfolio attribution: OLS regression of strategy daily returns
against a small set of constructed factor portfolios (mkt, val, mom, size,
vol).

This is the **portfolio-level** layer. It answers: "what kind of bets is
this strategy taking, decomposed against canonical factors?"

It is complementary to `astrategy/evaluation/` (Sprint 1), which is the
**individual-factor predictive-power** layer (IC / quintile / decay /
correlation). Sprint 3 wires the top-N portfolio strategy and uses both:
`evaluation/` to validate each factor pre-deployment; `attribution.py` to
decompose realized P&L after backtests.

The factor portfolios here are not perfect academic factor mimics, but
they're good enough for the "where did the return come from?" question.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from astrategy.config import TRADING_DAYS_PER_YEAR
from astrategy.data.cache import SQLiteCache

log = logging.getLogger(__name__)

FACTOR_NAMES = ["mkt", "val", "mom", "size", "vol"]


@dataclass
class AttributionResult:
    alpha_daily: float
    alpha_annualized: float
    loadings: dict[str, float]
    t_stats: dict[str, float]
    r_squared: float
    residual_vol_annualized: float
    n_obs: int


def _market_returns(cache: SQLiteCache, index_code: str, start: str, end: str) -> pd.Series:
    bars = cache.get_daily_bars(index_code, start, end)
    if bars.empty:
        return pd.Series(dtype=float)
    bars = bars.set_index("date").sort_index()
    return bars["close"].pct_change().dropna()


def _long_short_returns(
    cache: SQLiteCache,
    universe: list[str],
    start: str,
    end: str,
    score_fn: "callable[[str, pd.Timestamp], float | None]",
    top_pct: float = 0.2,
    rebalance: str = "ME",
) -> pd.Series:
    """
    Build a long-short factor portfolio: long the top quintile by `score_fn`,
    short the bottom quintile, rebalanced monthly.
    """
    # Determine rebalance dates
    rebal_dates = pd.date_range(start=start, end=end, freq=rebalance)
    if len(rebal_dates) < 2:
        return pd.Series(dtype=float)

    # Build a daily-return panel for the universe
    daily_returns_per_stock = {}
    for code in universe:
        bars = cache.get_daily_bars(code, start, end)
        if bars.empty:
            continue
        bars = bars.set_index("date").sort_index()
        daily_returns_per_stock[code] = bars["close"].pct_change()

    if not daily_returns_per_stock:
        return pd.Series(dtype=float)

    panel = pd.DataFrame(daily_returns_per_stock)

    portfolio_returns = pd.Series(0.0, index=panel.index)
    current_long: set[str] = set()
    current_short: set[str] = set()

    for i, rebal_date in enumerate(rebal_dates[:-1]):
        next_rebal = rebal_dates[i + 1]
        scores: dict[str, float] = {}
        for code in universe:
            s = score_fn(code, rebal_date)
            if s is not None and not pd.isna(s):
                scores[code] = float(s)
        if len(scores) < 10:
            continue
        sorted_codes = sorted(scores.items(), key=lambda x: x[1])
        n = len(sorted_codes)
        bottom_cut = max(1, int(n * top_pct))
        top_cut = max(1, int(n * top_pct))
        current_short = {c for c, _ in sorted_codes[:bottom_cut]}
        current_long = {c for c, _ in sorted_codes[-top_cut:]}

        mask = (panel.index >= rebal_date) & (panel.index < next_rebal)
        slice_df = panel.loc[mask]
        if slice_df.empty:
            continue
        long_codes = [c for c in current_long if c in slice_df.columns]
        short_codes = [c for c in current_short if c in slice_df.columns]
        if not long_codes or not short_codes:
            continue
        long_ret = slice_df[long_codes].mean(axis=1)
        short_ret = slice_df[short_codes].mean(axis=1)
        portfolio_returns.loc[mask] = (long_ret - short_ret).reindex(slice_df.index, fill_value=0.0)

    return portfolio_returns.dropna()


def build_factor_returns(
    cache: SQLiteCache,
    universe: list[str],
    start: str,
    end: str,
    market_index: str = "000300",
) -> pd.DataFrame:
    """
    Build daily-return DataFrame for factors: mkt, val, mom, size, vol.

    Each factor is best-effort — if underlying data is missing, the
    column is dropped (the regression handles missing factors gracefully).
    """
    out: dict[str, pd.Series] = {}

    mkt = _market_returns(cache, market_index, start, end)
    if not mkt.empty:
        out["mkt"] = mkt

    # Pre-cache PB and 12-1 month return data per stock
    # Value: low PB = value. Score is -PB (so top quintile = lowest PB = "most value").
    # PB comes from valuation_daily snapshot closest to (and before) the rebalance date.
    val_cache: dict[str, pd.DataFrame] = {}
    mom_cache: dict[str, pd.DataFrame] = {}
    size_cache: dict[str, pd.DataFrame] = {}
    vol_cache: dict[str, pd.DataFrame] = {}
    for code in universe:
        val_cache[code] = cache.get_valuation_daily(code, start, end)
        bars = cache.get_daily_bars(code, start, end)
        if not bars.empty:
            bars = bars.set_index("date").sort_index()
            mom_cache[code] = bars
            vol_cache[code] = bars
        else:
            mom_cache[code] = pd.DataFrame()
            vol_cache[code] = pd.DataFrame()

    def val_score(code: str, dt: pd.Timestamp) -> float | None:
        v = val_cache.get(code)
        if v is None or v.empty:
            return None
        idx = v[v["date"] <= dt]
        if idx.empty:
            return None
        pb = idx.iloc[-1]["pb"]
        return -float(pb) if pb and not pd.isna(pb) else None

    def mom_score(code: str, dt: pd.Timestamp) -> float | None:
        bars = mom_cache.get(code)
        if bars is None or bars.empty:
            return None
        window = bars.loc[bars.index <= dt]
        if len(window) < 252:
            return None
        end_p = float(window["close"].iloc[-21])  # ~1 month ago
        start_p = float(window["close"].iloc[-252])  # ~12 months ago
        if start_p <= 0:
            return None
        return (end_p / start_p) - 1.0

    def size_score(code: str, dt: pd.Timestamp) -> float | None:
        v = val_cache.get(code)
        if v is None or v.empty:
            return None
        idx = v[v["date"] <= dt]
        if idx.empty:
            return None
        mc = idx.iloc[-1]["mkt_cap"]
        return -float(mc) if mc and not pd.isna(mc) else None  # small minus big → negate mkt cap

    def vol_score(code: str, dt: pd.Timestamp) -> float | None:
        bars = vol_cache.get(code)
        if bars is None or bars.empty:
            return None
        window = bars.loc[bars.index <= dt].tail(20)
        if len(window) < 20:
            return None
        rets = window["close"].pct_change().dropna()
        if rets.empty:
            return None
        return -float(rets.std())  # low vol minus high vol → negate

    val_ret = _long_short_returns(cache, universe, start, end, val_score)
    if not val_ret.empty:
        out["val"] = val_ret
    mom_ret = _long_short_returns(cache, universe, start, end, mom_score)
    if not mom_ret.empty:
        out["mom"] = mom_ret
    size_ret = _long_short_returns(cache, universe, start, end, size_score)
    if not size_ret.empty:
        out["size"] = size_ret
    vol_ret = _long_short_returns(cache, universe, start, end, vol_score)
    if not vol_ret.empty:
        out["vol"] = vol_ret

    if not out:
        return pd.DataFrame()
    return pd.DataFrame(out).sort_index()


def attribute_returns(
    strategy_returns: pd.Series,
    factor_returns: pd.DataFrame,
) -> AttributionResult | None:
    """
    OLS: strategy_returns = alpha + sum(beta_i * factor_i) + epsilon

    Returns None if there's insufficient data to fit (< 30 aligned observations).
    """
    if strategy_returns.empty or factor_returns.empty:
        return None
    df = pd.concat([strategy_returns.rename("y"), factor_returns], axis=1, join="inner").dropna()
    if len(df) < 30:
        return None

    y = df["y"].to_numpy()
    X_cols = [c for c in factor_returns.columns if c in df.columns]
    if not X_cols:
        return None
    X = np.column_stack([np.ones(len(df))] + [df[c].to_numpy() for c in X_cols])

    # OLS solution + standard errors
    try:
        beta, residuals, rank, _ = np.linalg.lstsq(X, y, rcond=None)
    except np.linalg.LinAlgError:
        return None
    y_hat = X @ beta
    resid = y - y_hat
    n, k = X.shape
    dof = max(n - k, 1)
    sigma2 = (resid @ resid) / dof
    try:
        cov = sigma2 * np.linalg.inv(X.T @ X)
    except np.linalg.LinAlgError:
        cov = np.full((k, k), np.nan)
    se = np.sqrt(np.diag(cov))

    alpha = float(beta[0])
    loadings = {c: float(b) for c, b in zip(X_cols, beta[1:])}
    t_stats = {c: float(b / s) if s > 0 else 0.0 for c, b, s in zip(X_cols, beta[1:], se[1:])}
    ss_tot = float(((y - y.mean()) ** 2).sum())
    ss_res = float((resid ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return AttributionResult(
        alpha_daily=alpha,
        alpha_annualized=alpha * TRADING_DAYS_PER_YEAR,
        loadings=loadings,
        t_stats=t_stats,
        r_squared=float(r2),
        residual_vol_annualized=float(math.sqrt(sigma2 * TRADING_DAYS_PER_YEAR)),
        n_obs=n,
    )


def summarize_attribution(result: AttributionResult | None) -> dict:
    if result is None:
        return {}
    return {
        "alpha_annualized": result.alpha_annualized,
        "loadings": result.loadings,
        "t_stats": result.t_stats,
        "r_squared": result.r_squared,
        "residual_vol_annualized": result.residual_vol_annualized,
        "n_obs": result.n_obs,
    }
