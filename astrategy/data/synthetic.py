"""
Synthetic OHLCV + fundamentals + sector + northbound generators for
environments without AKShare network access.

The shapes/columns mirror the real AKShare output exactly so downstream code
can't tell the difference. Use only for engine demos / CI — NEVER treat the
returned numbers as a real backtest signal.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd


# Real sector + plausible PE/PB/ROE anchors for the 10 demo CSI 300 names.
# These keep synthetic-mode demos somewhat realistic — e.g. banks have low PE/PB,
# Moutai has high ROE, ICBC has near-zero revenue growth.
DEMO_FUNDAMENTALS: dict[str, dict] = {
    "600519": {"sector_l1": "食品饮料", "pe": 28.0, "pb": 9.00, "roe": 30.0, "rev_yoy": 18.0, "mkt_cap": 2.10e12},
    "601318": {"sector_l1": "非银金融", "pe": 8.5,  "pb": 0.90, "roe": 11.0, "rev_yoy": 4.0,  "mkt_cap": 8.50e11},
    "300750": {"sector_l1": "电力设备", "pe": 22.0, "pb": 4.50, "roe": 21.0, "rev_yoy": 25.0, "mkt_cap": 1.10e12},
    "601398": {"sector_l1": "银行",     "pe": 5.5,  "pb": 0.55, "roe": 11.0, "rev_yoy": 2.0,  "mkt_cap": 2.30e12},
    "000858": {"sector_l1": "食品饮料", "pe": 21.0, "pb": 5.50, "roe": 25.0, "rev_yoy": 12.0, "mkt_cap": 5.50e11},
    "600036": {"sector_l1": "银行",     "pe": 6.5,  "pb": 0.85, "roe": 14.0, "rev_yoy": 3.0,  "mkt_cap": 9.00e11},
    "601012": {"sector_l1": "电力设备", "pe": 14.0, "pb": 1.80, "roe": 12.0, "rev_yoy": -8.0, "mkt_cap": 1.50e11},
    "002594": {"sector_l1": "汽车",     "pe": 19.0, "pb": 3.40, "roe": 18.0, "rev_yoy": 30.0, "mkt_cap": 8.00e11},
    "600276": {"sector_l1": "医药生物", "pe": 35.0, "pb": 5.00, "roe": 14.0, "rev_yoy": 8.0,  "mkt_cap": 3.50e11},
    "601888": {"sector_l1": "商贸零售", "pe": 24.0, "pb": 3.00, "roe": 13.0, "rev_yoy": 6.0,  "mkt_cap": 1.40e11},
}


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


# ----- Phase 4: synthetic fundamentals / valuation / sector / northbound -----

def _anchor_for(code: str) -> dict:
    """Return DEMO_FUNDAMENTALS entry or a generic mid-cap default."""
    return DEMO_FUNDAMENTALS.get(code, {
        "sector_l1": "综合",
        "pe": 18.0, "pb": 2.0, "roe": 10.0, "rev_yoy": 5.0, "mkt_cap": 5.0e10,
    })


def generate_synthetic_sector(code: str) -> dict:
    """Return {sw_l1_name, sw_l1_code, sw_l2_name, sw_l2_code} for a code."""
    a = _anchor_for(code)
    name = a["sector_l1"]
    # Stable synthetic L1 code derived from sector name hash
    l1_code = "8" + str(int(hashlib.sha256(name.encode()).hexdigest()[:6], 16))[:5]
    return {"sw_l1_name": name, "sw_l1_code": l1_code, "sw_l2_name": None, "sw_l2_code": None}


def _quarter_ends(start: str, end: str) -> list[pd.Timestamp]:
    """Mar-31, Jun-30, Sep-30, Dec-31 within [start, end]."""
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    qs = pd.date_range(start=s - pd.offsets.QuarterEnd(2), end=e, freq="QE")
    return [q for q in qs if q >= s - pd.Timedelta(days=120) and q <= e]


def generate_synthetic_fundamentals(code: str, start: str, end: str) -> pd.DataFrame:
    """Per-quarter fundamentals with ~45-day reporting lag for announce_date."""
    rng = np.random.default_rng(_seed_from_code(code, salt=1))
    anchor = _anchor_for(code)
    quarters = _quarter_ends(start, end)
    if not quarters:
        return pd.DataFrame(columns=[
            "report_date", "announce_date", "pe_ttm", "pb", "ps_ttm",
            "roe_ttm", "revenue_yoy", "net_profit_yoy", "eps_ttm",
        ])

    n = len(quarters)
    # Wobble each metric around the anchor: roe ±3pp, rev_yoy ±10pp, pe ±20%, pb ±15%
    roe = anchor["roe"] + rng.normal(0, 3.0, n)
    rev = anchor["rev_yoy"] + rng.normal(0, 10.0, n)
    npy = rev + rng.normal(0, 8.0, n)
    pe = anchor["pe"] * (1 + rng.normal(0, 0.15, n))
    pb = anchor["pb"] * (1 + rng.normal(0, 0.12, n))
    ps = pe * 0.25 * (1 + rng.normal(0, 0.10, n))
    # Synthetic EPS — anchor / pe gives close-price-relative; fine for demo
    eps = np.maximum(0.1, anchor["pe"] / np.maximum(pe, 1.0))

    return pd.DataFrame({
        "report_date": [q.strftime("%Y-%m-%d") for q in quarters],
        "announce_date": [(q + pd.Timedelta(days=45)).strftime("%Y-%m-%d") for q in quarters],
        "pe_ttm": np.round(pe, 2),
        "pb": np.round(pb, 2),
        "ps_ttm": np.round(ps, 2),
        "roe_ttm": np.round(roe, 2),
        "revenue_yoy": np.round(rev, 2),
        "net_profit_yoy": np.round(npy, 2),
        "eps_ttm": np.round(eps, 3),
    })


def generate_synthetic_valuation_daily(
    code: str, start: str, end: str, ohlcv: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Per-day PE/PB/PS + market cap. Drifts with price when OHLCV is supplied."""
    anchor = _anchor_for(code)
    rng = np.random.default_rng(_seed_from_code(code, salt=2))

    if ohlcv is not None and not ohlcv.empty:
        # Anchor mkt_cap implies shares = mkt_cap / start_price; drift mkt_cap with close
        first_close = float(ohlcv.iloc[0]["close"])
        shares_implied = anchor["mkt_cap"] / first_close
        dates = pd.to_datetime(ohlcv["date"]).dt.strftime("%Y-%m-%d").tolist()
        closes = ohlcv["close"].astype(float).to_numpy()
    else:
        dates_idx = _trading_days(start, end)
        dates = dates_idx.strftime("%Y-%m-%d").tolist()
        closes = np.full(len(dates), 50.0)
        shares_implied = anchor["mkt_cap"] / 50.0

    n = len(dates)
    if n == 0:
        return pd.DataFrame(columns=["date", "pe_ttm", "pb", "ps_ttm", "mkt_cap", "float_cap"])

    mkt_cap = closes * shares_implied
    pe = anchor["pe"] * (closes / closes[0]) * (1 + rng.normal(0, 0.02, n))
    pb = anchor["pb"] * (closes / closes[0]) * (1 + rng.normal(0, 0.02, n))
    ps = pe * 0.25

    return pd.DataFrame({
        "date": dates,
        "pe_ttm": np.round(pe, 3),
        "pb": np.round(pb, 3),
        "ps_ttm": np.round(ps, 3),
        "mkt_cap": np.round(mkt_cap, 0),
        "float_cap": np.round(mkt_cap * 0.7, 0),  # assume 70% float
    })


def generate_synthetic_northbound(code: str, start: str, end: str) -> pd.DataFrame:
    """Slow-walking holding_pct in [0.5, 8.0]; daily net flow ~ normal(0, 1e8)."""
    rng = np.random.default_rng(_seed_from_code(code, salt=3))
    dates = _trading_days(start, end)
    n = len(dates)
    if n == 0:
        return pd.DataFrame(columns=[
            "date", "holding_shares", "holding_value", "holding_pct",
            "net_buy_shares", "net_buy_value",
        ])

    # Random walk holding_pct, clipped to [0.3, 8.0]
    walk = np.cumsum(rng.normal(0, 0.02, n))
    holding_pct = np.clip(2.0 + walk, 0.3, 8.0)
    net_buy_value = rng.normal(0, 1.0e8, n).astype(float)
    # Make holding_value roughly proportional to mkt_cap implied by anchor
    anchor = _anchor_for(code)
    holding_value = (holding_pct / 100.0) * anchor["mkt_cap"]
    # Use 25¥ average price for share counts
    holding_shares = holding_value / 25.0
    net_buy_shares = net_buy_value / 25.0

    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "holding_shares": np.round(holding_shares, 0),
        "holding_value": np.round(holding_value, 0),
        "holding_pct": np.round(holding_pct, 3),
        "net_buy_shares": np.round(net_buy_shares, 0),
        "net_buy_value": np.round(net_buy_value, 0),
    })
