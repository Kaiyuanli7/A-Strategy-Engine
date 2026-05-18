"""End-to-end factor evaluation orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from astrategy.data.cache import SQLiteCache
from astrategy.data.universes import load_universe
from astrategy.evaluation.decay import DEFAULT_HORIZONS, compute_decay_curve
from astrategy.evaluation.ic import compute_ic_series, summarize_ic
from astrategy.evaluation.quintile import (
    compute_quintile_returns,
    cumulative_quintile_returns,
    quintile_summary,
    quintile_turnover,
)
from astrategy.factors.base import Factor, FactorContext


log = logging.getLogger(__name__)


@dataclass
class EvaluationConfig:
    start: str
    end: str
    universe: str = "000300"
    horizon: int = 20
    rebalance: Literal["daily", "weekly", "monthly"] = "weekly"
    n_quintiles: int = 5
    decay_horizons: tuple[int, ...] = DEFAULT_HORIZONS

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "universe": self.universe,
            "horizon": self.horizon,
            "rebalance": self.rebalance,
            "n_quintiles": self.n_quintiles,
            "decay_horizons": list(self.decay_horizons),
        }


@dataclass
class FactorEvaluation:
    n_dates: int
    n_stocks_avg: float
    ic_series: pd.Series
    ic_summary: dict
    quintile_returns: pd.DataFrame
    quintile_cum: pd.DataFrame
    quintile_summary: dict
    decay: pd.DataFrame

    def ic_series_dicts(self) -> list[dict]:
        return [
            {"date": d.strftime("%Y-%m-%d"), "ic": float(v)}
            for d, v in self.ic_series.items()
        ]

    def quintile_cum_dicts(self) -> list[dict]:
        out = []
        for d, row in self.quintile_cum.iterrows():
            r = {"date": d.strftime("%Y-%m-%d")}
            for col in self.quintile_cum.columns:
                v = row[col]
                r[col.lower()] = float(v) if pd.notna(v) else 0.0
            # Schema expects q1..q5 + long_short
            r.setdefault("long_short", float(row.get("long_short", 0.0)) if pd.notna(row.get("long_short")) else 0.0)
            out.append(r)
        return out

    def decay_dicts(self) -> list[dict]:
        return [
            {
                "horizon": int(r["horizon"]),
                "ic_mean": float(r["ic_mean"]),
                "ic_ir": float(r["ic_ir"]),
            }
            for _, r in self.decay.iterrows()
        ]


def evaluate_factor(
    factor: Factor,
    cache: SQLiteCache,
    config: EvaluationConfig,
) -> FactorEvaluation:
    """
    Run the factor over the period, build IC + quintile + decay artifacts.

    Universe resolution: if `config.universe` looks like an index code, use
    point-in-time membership via `load_universe`. Otherwise, fall back to all
    cached codes.
    """
    rebalance_dates = _rebalance_dates(config.start, config.end, config.rebalance)
    if not rebalance_dates:
        raise ValueError(
            f"no rebalance dates between {config.start} and {config.end} "
            f"(rebalance={config.rebalance})"
        )

    # Pre-fetch all bars we need for forward returns. The longest horizon
    # determines how many trading days we need past `end`.
    max_horizon = max(max(config.decay_horizons), config.horizon)
    bars_end = _add_calendar_days(config.end, max_horizon * 2 + 14)
    bars_by_code = _load_bars(cache, config.start, bars_end)

    scores_by_date: dict[pd.Timestamp, pd.Series] = {}
    forward_h: dict[int, dict[pd.Timestamp, pd.Series]] = {h: {} for h in (config.horizon, *config.decay_horizons)}

    n_stock_sum = 0
    for date in rebalance_dates:
        universe = _resolve_universe(cache, config.universe, date.strftime("%Y-%m-%d"))
        if not universe:
            continue
        ctx = FactorContext(cache=cache, universe=universe, as_of=date)
        try:
            scores = factor.compute(ctx)
        except Exception as e:
            log.warning("factor.compute failed at %s: %s", date.strftime("%Y-%m-%d"), e)
            continue
        if scores is None or scores.empty:
            continue
        scores_by_date[date] = scores
        n_stock_sum += len(scores)

        for h in forward_h:
            fwd = _forward_returns(bars_by_code, scores.index.tolist(), date, h)
            if not fwd.empty:
                forward_h[h][date] = fwd

    n_dates = len(scores_by_date)
    n_stocks_avg = (n_stock_sum / n_dates) if n_dates else 0.0

    ic_series = compute_ic_series(scores_by_date, forward_h[config.horizon])
    ic_summary_d = summarize_ic(ic_series)

    qr = compute_quintile_returns(scores_by_date, forward_h[config.horizon], n=config.n_quintiles)
    qc = cumulative_quintile_returns(qr)
    qs = quintile_summary(qr, n=config.n_quintiles)
    qs["avg_turnover"] = quintile_turnover(scores_by_date, n=config.n_quintiles)

    decay = compute_decay_curve(scores_by_date, forward_h)

    return FactorEvaluation(
        n_dates=n_dates,
        n_stocks_avg=float(n_stocks_avg),
        ic_series=ic_series,
        ic_summary=ic_summary_d,
        quintile_returns=qr,
        quintile_cum=qc,
        quintile_summary=qs,
        decay=decay,
    )


# ----- helpers ---------------------------------------------------------------

def _rebalance_dates(start: str, end: str, freq: str) -> list[pd.Timestamp]:
    """Trading-week-friendly rebalance dates. Uses weekday bdate_range for now;
    factor evaluation tolerates a missing date by skipping it."""
    bdays = pd.bdate_range(start=start, end=end)
    if freq == "daily":
        return list(bdays)
    df = pd.DataFrame({"d": bdays})
    if freq == "weekly":
        df["bucket"] = df["d"].dt.to_period("W")
    elif freq == "monthly":
        df["bucket"] = df["d"].dt.to_period("M")
    else:
        raise ValueError(f"unknown rebalance freq '{freq}'")
    last_per_bucket = df.groupby("bucket", observed=True)["d"].max()
    return [pd.Timestamp(d) for d in last_per_bucket.sort_values().tolist()]


def _add_calendar_days(date_str: str, days: int) -> str:
    return (pd.Timestamp(date_str) + pd.Timedelta(days=days)).strftime("%Y-%m-%d")


def _load_bars(cache: SQLiteCache, start: str, end: str) -> dict[str, pd.DataFrame]:
    """Load every cached stock's bars in [start, end] for forward-return lookups."""
    out: dict[str, pd.DataFrame] = {}
    for code in cache.all_meta_codes():
        df = cache.get_daily_bars(code, start, end)
        if df.empty:
            continue
        df = df[["date", "close"]].set_index("date").sort_index()
        out[code] = df
    return out


def _resolve_universe(cache: SQLiteCache, name: str, as_of: str) -> list[str]:
    """If `name` looks like an index, use PIT membership; else use all cached codes."""
    if name.lower() in ("all", "all_cached", "*"):
        return cache.all_meta_codes()
    if name.isdigit() and len(name) == 6:
        try:
            codes = load_universe(name, as_of=as_of, cache=cache)
            if codes:
                return codes
        except Exception as e:
            log.warning("load_universe failed for %s @ %s: %s; falling back to cached codes", name, as_of, e)
    # Fallback: all cached stocks (excludes index rows in stock_meta)
    return cache.all_meta_codes()


def _forward_returns(
    bars_by_code: dict[str, pd.DataFrame],
    codes: list[str],
    as_of: pd.Timestamp,
    horizon: int,
) -> pd.Series:
    """
    Forward total return per code: close[as_of + horizon trading days] / close[as_of].

    Uses next-day open convention indirectly: the factor sees data strictly
    before `as_of`, signals are realized at the close of `as_of`, and the
    forward window starts from `as_of`'s close. Codes with insufficient
    forward history return NaN (filtered out by the caller).
    """
    out: dict[str, float] = {}
    for code in codes:
        df = bars_by_code.get(code)
        if df is None or df.empty:
            continue
        # Position the index right at as_of, then look horizon ahead.
        try:
            loc = df.index.searchsorted(as_of)
        except Exception:
            continue
        if loc >= len(df) or loc + horizon >= len(df):
            continue
        start_price = float(df.iloc[loc]["close"])
        end_price = float(df.iloc[loc + horizon]["close"])
        if start_price <= 0:
            continue
        out[code] = end_price / start_price - 1.0
    if not out:
        return pd.Series(dtype="float64")
    return pd.Series(out).replace([np.inf, -np.inf], np.nan).dropna()
