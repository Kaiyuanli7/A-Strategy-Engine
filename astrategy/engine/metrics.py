"""Performance metrics on a backtest equity curve / fills."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from astrategy.config import DEFAULT_RISK_FREE_RATE, TRADING_DAYS_PER_YEAR
from astrategy.engine.orders import Fill, OrderSide


def total_return(equity: pd.Series) -> float:
    if len(equity) < 2:
        return 0.0
    return float(equity.iloc[-1] / equity.iloc[0] - 1.0)


def annualized_return(equity: pd.Series, trading_days: int = TRADING_DAYS_PER_YEAR) -> float:
    if len(equity) < 2:
        return 0.0
    n = len(equity)
    growth = equity.iloc[-1] / equity.iloc[0]
    if growth <= 0:
        return -1.0
    return float(growth ** (trading_days / n) - 1.0)


def daily_returns(equity: pd.Series) -> pd.Series:
    return equity.pct_change().dropna()


def annualized_vol(equity: pd.Series, trading_days: int = TRADING_DAYS_PER_YEAR) -> float:
    r = daily_returns(equity)
    if len(r) < 2:
        return 0.0
    return float(r.std(ddof=1) * math.sqrt(trading_days))


def sharpe_ratio(
    equity: pd.Series,
    rf_annual: float = DEFAULT_RISK_FREE_RATE,
    trading_days: int = TRADING_DAYS_PER_YEAR,
) -> float:
    vol = annualized_vol(equity, trading_days)
    if vol == 0.0:
        return 0.0
    return (annualized_return(equity, trading_days) - rf_annual) / vol


def max_drawdown(equity: pd.Series) -> tuple[float, pd.Timestamp | None, pd.Timestamp | None]:
    if len(equity) < 2:
        return 0.0, None, None
    peak = equity.cummax()
    dd = equity / peak - 1.0
    trough_idx = dd.idxmin()
    peak_idx = equity.loc[:trough_idx].idxmax()
    return float(dd.min()), peak_idx, trough_idx


def calmar_ratio(equity: pd.Series, trading_days: int = TRADING_DAYS_PER_YEAR) -> float:
    mdd, _, _ = max_drawdown(equity)
    if mdd == 0:
        return 0.0
    return annualized_return(equity, trading_days) / abs(mdd)


def round_trips(fills: list[Fill]) -> list[dict]:
    """
    FIFO-match buys and sells to produce closed round-trip trades per stock.
    Returns list of dicts: code, entry_date, exit_date, entry_price, exit_price,
    shares, pnl, hold_days.

    Does NOT mutate the input fills — internally tracks remaining unmatched
    shares per queued buy in a separate counter.
    """
    # Per-code FIFO queue of [Fill, remaining_unmatched_shares]
    queues: dict[str, list[list]] = {}
    trips: list[dict] = []
    for f in fills:
        q = queues.setdefault(f.code, [])
        if f.side == OrderSide.BUY:
            q.append([f, f.shares])
        else:
            remaining = f.shares
            while remaining > 0 and q:
                entry, entry_remaining = q[0]
                matched = min(entry_remaining, remaining)
                pnl = (f.price - entry.price) * matched
                trips.append({
                    "code": f.code,
                    "entry_date": entry.timestamp,
                    "exit_date": f.timestamp,
                    "entry_price": entry.price,
                    "exit_price": f.price,
                    "shares": matched,
                    "pnl": pnl,
                    "hold_days": (f.timestamp - entry.timestamp).days,
                })
                q[0][1] -= matched
                remaining -= matched
                if q[0][1] == 0:
                    q.pop(0)
    return trips


def win_rate(trips: list[dict]) -> float:
    if not trips:
        return 0.0
    wins = sum(1 for t in trips if t["pnl"] > 0)
    return wins / len(trips)


def avg_hold_days(trips: list[dict]) -> float:
    if not trips:
        return 0.0
    return float(np.mean([t["hold_days"] for t in trips]))


def turnover(fills: list[Fill], equity: pd.Series, trading_days: int = TRADING_DAYS_PER_YEAR) -> float:
    if equity.empty:
        return 0.0
    gross_notional = sum(f.notional for f in fills)
    mean_eq = float(equity.mean())
    if mean_eq == 0 or len(equity) == 0:
        return 0.0
    return gross_notional / mean_eq * (trading_days / len(equity))


def summarize(
    equity: pd.Series,
    fills: list[Fill],
    rejections: list[Fill],
    rf_annual: float = DEFAULT_RISK_FREE_RATE,
) -> dict:
    trips = round_trips(fills)
    mdd, peak_dt, trough_dt = max_drawdown(equity)
    return {
        "n_bars": len(equity),
        "initial_equity": float(equity.iloc[0]) if len(equity) else 0.0,
        "final_equity": float(equity.iloc[-1]) if len(equity) else 0.0,
        "total_return": total_return(equity),
        "annualized_return": annualized_return(equity),
        "annualized_vol": annualized_vol(equity),
        "sharpe": sharpe_ratio(equity, rf_annual),
        "max_drawdown": mdd,
        "max_drawdown_peak": peak_dt,
        "max_drawdown_trough": trough_dt,
        "calmar": calmar_ratio(equity),
        "win_rate": win_rate(trips),
        "avg_hold_days": avg_hold_days(trips),
        "n_trips": len(trips),
        "n_fills": len(fills),
        "n_rejections": len(rejections),
        "turnover": turnover(fills, equity),
    }
