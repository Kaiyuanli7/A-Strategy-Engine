"""
Synthetic OHLCV generator for environments without AKShare network access.

The shapes/columns mirror the real AKShare output exactly so downstream code
can't tell the difference. Use only for engine demos / CI — NEVER treat the
returned numbers as a real backtest signal.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd


def _seed_from_code(code: str, salt: int = 0) -> int:
    h = hashlib.sha256(f"{code}:{salt}".encode()).hexdigest()
    return int(h[:8], 16)


def _trading_days(start: str, end: str) -> pd.DatetimeIndex:
    """Approximate A-share trading calendar: weekdays minus a fixed holiday list."""
    bdays = pd.bdate_range(start=start, end=end)
    # Rough A-share holiday windows (Spring Festival, Qingming, May Day, Dragon Boat,
    # Mid-Autumn, National Day). Approximate, good enough for synthetic demo.
    holidays_md = {
        (1, 1), (1, 2), (1, 3),
        (2, 9), (2, 10), (2, 11), (2, 12), (2, 13), (2, 14), (2, 15),
        (4, 4), (4, 5),
        (5, 1), (5, 2), (5, 3),
        (6, 10), (6, 11),
        (9, 15), (9, 16), (9, 17),
        (10, 1), (10, 2), (10, 3), (10, 4), (10, 5), (10, 6), (10, 7),
    }
    return pd.DatetimeIndex([d for d in bdays if (d.month, d.day) not in holidays_md])


def generate_synthetic_ohlcv(
    code: str,
    start: str,
    end: str,
    start_price: float = 50.0,
    annual_drift: float = 0.05,
    annual_vol: float = 0.30,
    intraday_vol: float = 0.012,
    salt: int = 0,
) -> pd.DataFrame:
    """
    Generate a synthetic forward-adjusted OHLCV series via geometric Brownian motion.

    Parameters chosen to look A-share-y: ~30% annualized vol (high), 5% drift.

    Returns DataFrame with columns:
        date (str YYYY-MM-DD), open, high, low, close, volume, amount, pct_change, turnover
    """
    rng = np.random.default_rng(_seed_from_code(code, salt))
    dates = _trading_days(start, end)
    n = len(dates)
    if n == 0:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume",
                                      "amount", "pct_change", "turnover"])

    dt = 1.0 / 252
    daily_drift = (annual_drift - 0.5 * annual_vol ** 2) * dt
    daily_vol = annual_vol * np.sqrt(dt)

    log_returns = rng.normal(daily_drift, daily_vol, size=n)
    log_returns[0] = 0.0
    close = start_price * np.exp(np.cumsum(log_returns))

    # Open: prior close + small overnight gap
    overnight = rng.normal(0.0, 0.005, size=n)
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1] * (1.0 + overnight[1:])

    # High/low: max/min of open and close, plus a small intraday wick
    wick_up = np.abs(rng.normal(0.0, intraday_vol, size=n))
    wick_dn = np.abs(rng.normal(0.0, intraday_vol, size=n))
    high = np.maximum(open_, close) * (1.0 + wick_up)
    low = np.minimum(open_, close) * (1.0 - wick_dn)

    # Volume: lognormal centered around ~10M shares
    volume = rng.lognormal(mean=16.0, sigma=0.5, size=n)
    amount = volume * close

    pct_change = np.zeros(n)
    pct_change[1:] = (close[1:] / close[:-1] - 1.0) * 100
    # Realistic turnover proxy: 0.5-3% per day
    turnover = rng.uniform(0.5, 3.0, size=n)

    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": np.round(open_, 2),
        "high": np.round(high, 2),
        "low": np.round(low, 2),
        "close": np.round(close, 2),
        "volume": np.round(volume, 0),
        "amount": np.round(amount, 2),
        "pct_change": np.round(pct_change, 2),
        "turnover": np.round(turnover, 2),
    })
