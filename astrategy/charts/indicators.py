"""Technical indicator computation — pure pandas, NaN-safe.

Kept minimal in this first cut: MA, EMA, RSI, MACD. Each function takes a
pd.Series of closes (indexed by date) and returns either a Series (single
output) or DataFrame (multiple outputs). All NaN-tolerant — leading periods
where there isn't enough history return NaN.
"""

from __future__ import annotations

import pandas as pd


def compute_ma(close: pd.Series, period: int) -> pd.Series:
    """Simple moving average over `period` bars."""
    return close.rolling(window=period, min_periods=period).mean()


def compute_ema(close: pd.Series, period: int) -> pd.Series:
    """Exponential moving average using pandas' standard alpha = 2/(N+1)."""
    return close.ewm(span=period, adjust=False).mean()


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index, Wilder's smoothing variant.

    Returns values in 0..100. Periods before `period+1` bars have RSI = NaN.
    Flat series (no gains AND no losses) return NaN — undefined.
    Strictly rising series saturate at 100; strictly falling at 0.
    """
    import numpy as np
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    # When avg_loss is 0 but avg_gain > 0, RSI = 100 (saturated up move).
    # When both are 0 (flat series), RSI = NaN (undefined).
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    saturated_up = (avg_loss == 0) & (avg_gain > 0)
    rsi = rsi.where(~saturated_up, 100.0)
    return rsi.astype(float)


def compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """
    MACD line, signal line, histogram.

    Returns DataFrame with columns: macd, signal, histogram.
    """
    fast_ema = close.ewm(span=fast, adjust=False).mean()
    slow_ema = close.ewm(span=slow, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({
        "macd": macd_line,
        "signal": signal_line,
        "histogram": hist,
    })
