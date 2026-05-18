"""Pure technical indicators. Stateless functions returning Series."""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(close: pd.Series, n: int) -> pd.Series:
    return close.rolling(n, min_periods=n).mean()


def ema(close: pd.Series, n: int) -> pd.Series:
    return close.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """
    Wilder's RSI. The first valid value at bar n is computed from a SIMPLE mean
    of the first n gains/losses; from there Wilder smoothing applies:
        avg_t = (avg_{t-1} * (n-1) + x_t) / n
    Output range [0, 100]. NaN for the first n bars.
    """
    delta = close.diff()
    up = delta.clip(lower=0.0).fillna(0.0)
    down = (-delta).clip(lower=0.0).fillna(0.0)

    avg_up_arr = np.full(len(close), np.nan)
    avg_dn_arr = np.full(len(close), np.nan)
    if len(close) >= n + 1:
        # First valid average uses bars 1..n (bar 0's diff is NaN → treated as 0)
        avg_up_arr[n] = up.iloc[1 : n + 1].mean()
        avg_dn_arr[n] = down.iloc[1 : n + 1].mean()
        # Wilder smoothing onward
        for i in range(n + 1, len(close)):
            avg_up_arr[i] = (avg_up_arr[i - 1] * (n - 1) + up.iloc[i]) / n
            avg_dn_arr[i] = (avg_dn_arr[i - 1] * (n - 1) + down.iloc[i]) / n

    avg_up = pd.Series(avg_up_arr, index=close.index)
    avg_dn = pd.Series(avg_dn_arr, index=close.index)
    rs = avg_up / avg_dn.replace(0, np.nan)
    rsi_val = 100.0 - (100.0 / (1.0 + rs))
    # When avg_dn is 0 and there have been gains → RSI = 100; when both are 0 → 50.
    rsi_val = rsi_val.where(~((avg_dn == 0) & (avg_up > 0)), 100.0)
    rsi_val = rsi_val.where(~((avg_dn == 0) & (avg_up == 0)), 50.0)
    return rsi_val


def bollinger(
    close: pd.Series, n: int = 20, k: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (middle, upper, lower) bands."""
    mid = close.rolling(n, min_periods=n).mean()
    std = close.rolling(n, min_periods=n).std(ddof=0)
    return mid, mid + k * std, mid - k * std


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (macd_line, signal_line, histogram)."""
    fast_ema = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    slow_ema = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def volume_ratio(volume: pd.Series, n: int = 20) -> pd.Series:
    """Today's volume / N-bar average."""
    avg = volume.rolling(n, min_periods=n).mean()
    return volume / avg.replace(0, np.nan)


def realized_vol(close: pd.Series, n: int = 20) -> pd.Series:
    """Annualized stdev of log returns over n bars."""
    logret = np.log(close / close.shift(1))
    return logret.rolling(n, min_periods=n).std(ddof=1) * np.sqrt(252)


def cross_up(a: pd.Series, b: pd.Series) -> pd.Series:
    """Boolean Series: True where a crosses ABOVE b (yesterday a<=b, today a>b)."""
    a, b = a.align(b)
    prev_a = a.shift(1)
    prev_b = b.shift(1)
    cur = a > b
    prev_below_or_eq = prev_a <= prev_b
    return (cur & prev_below_or_eq).fillna(False)


def cross_down(a: pd.Series, b: pd.Series) -> pd.Series:
    a, b = a.align(b)
    prev_a = a.shift(1)
    prev_b = b.shift(1)
    cur = a < b
    prev_above_or_eq = prev_a >= prev_b
    return (cur & prev_above_or_eq).fillna(False)
