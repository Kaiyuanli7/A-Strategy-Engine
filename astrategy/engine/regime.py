"""
Market regime classification: tag each date as bull / bear / range / high_vol
based on the 沪深300 trailing return + realized vol percentile.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from astrategy.config import DEFAULT_RISK_FREE_RATE, TRADING_DAYS_PER_YEAR


REGIME_LABELS = ("bull", "bear", "range", "high_vol")


def classify_regimes(
    market_returns: pd.Series,
    window: int = 60,
    bull_return: float = 0.05,
    bear_return: float = -0.10,
    vol_low_pct: float = 0.60,
    vol_high_pct: float = 0.80,
    min_duration: int = 10,
) -> pd.Series:
    """
    Classify each date in `market_returns.index` into one of REGIME_LABELS.

    Rules (evaluated in order — first match wins):
      high_vol: realized vol > vol_high_pct percentile
      bear:     window-return < bear_return
      bull:     window-return > bull_return AND realized vol < vol_low_pct pct
      range:    everything else

    `min_duration` enforces hysteresis: a regime must persist at least
    `min_duration` consecutive bars before the classifier can transition.
    """
    if market_returns.empty:
        return pd.Series([], dtype="object")

    cum = (1 + market_returns).cumprod()
    rolling_ret = cum / cum.shift(window) - 1.0
    rolling_vol = market_returns.rolling(window, min_periods=window).std() * math.sqrt(TRADING_DAYS_PER_YEAR)

    if rolling_vol.dropna().empty:
        vol_low_thr = vol_high_thr = float("inf")
    else:
        vol_low_thr = float(rolling_vol.dropna().quantile(vol_low_pct))
        vol_high_thr = float(rolling_vol.dropna().quantile(vol_high_pct))

    raw = pd.Series(index=market_returns.index, dtype="object")
    for ts, ret, vol in zip(market_returns.index, rolling_ret, rolling_vol):
        if pd.isna(ret) or pd.isna(vol):
            raw[ts] = "range"
        elif vol > vol_high_thr:
            raw[ts] = "high_vol"
        elif ret < bear_return:
            raw[ts] = "bear"
        elif ret > bull_return and vol < vol_low_thr:
            raw[ts] = "bull"
        else:
            raw[ts] = "range"

    # Apply min_duration hysteresis
    if min_duration <= 1:
        return raw

    smoothed = raw.copy()
    current = raw.iloc[0]
    run_start = 0
    for i in range(1, len(raw)):
        if raw.iloc[i] == current:
            continue
        run_length = i - run_start
        if run_length < min_duration:
            # Roll back this run to the previous regime
            prior = smoothed.iloc[run_start - 1] if run_start > 0 else current
            smoothed.iloc[run_start:i] = prior
        current = raw.iloc[i]
        run_start = i
    return smoothed


def per_regime_metrics(
    strategy_returns: pd.Series,
    regimes: pd.Series,
    rf_annual: float = DEFAULT_RISK_FREE_RATE,
) -> dict[str, dict]:
    """Per-regime: n_days, annualized_return, sharpe, max_drawdown."""
    out: dict[str, dict] = {}
    joined = pd.concat([strategy_returns.rename("r"), regimes.rename("regime")], axis=1, join="inner").dropna()
    daily_rf = rf_annual / TRADING_DAYS_PER_YEAR
    for regime in REGIME_LABELS:
        slice_df = joined[joined["regime"] == regime]
        if slice_df.empty:
            out[regime] = {
                "n_days": 0,
                "annualized_return": 0.0,
                "sharpe": 0.0,
                "max_drawdown": 0.0,
            }
            continue
        rets = slice_df["r"]
        excess = rets - daily_rf
        ann_ret = float((1 + rets.mean()) ** TRADING_DAYS_PER_YEAR - 1)
        sigma = rets.std(ddof=1)
        sharpe = float(excess.mean() / sigma * math.sqrt(TRADING_DAYS_PER_YEAR)) if sigma and not pd.isna(sigma) and sigma > 0 else 0.0
        equity = (1 + rets).cumprod()
        mdd = float((equity / equity.cummax() - 1).min()) if not equity.empty else 0.0
        out[regime] = {
            "n_days": int(len(rets)),
            "annualized_return": ann_ret,
            "sharpe": sharpe,
            "max_drawdown": mdd,
        }
    return out
