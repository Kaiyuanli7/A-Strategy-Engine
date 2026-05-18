"""Holdings + sector exposure derivation from a fills timeline.

Pure functions consumed by the portfolio result API to populate the
frontend's holdings table and sector exposure chart. The backtest engine
records every Fill but doesn't natively snapshot the portfolio at each
date — these helpers replay the fills to derive end-state holdings and
their sector breakdown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass
class HoldingRecord:
    """End-of-backtest position for one stock."""
    code: str
    shares: int
    avg_cost: float           # average cost basis (incl. commission/fees)
    market_value: float       # shares * last_close
    pnl: float                # market_value - shares * avg_cost
    pnl_pct: float            # pnl / (shares * avg_cost), 0.0 if zero-cost
    last_price: float
    entry_date: str           # most-recent date the position went from 0 → >0
    sector: str | None = None


@dataclass
class SectorWeight:
    """Per-sector portfolio weight at end of backtest."""
    sector: str
    weight: float             # fraction of total market value (0..1)
    n_stocks: int             # how many positions in this sector
    market_value: float


def _last_close_per_code(
    bars_by_code: dict[str, pd.DataFrame],
) -> dict[str, float]:
    """Last available close per code from cached bars."""
    out: dict[str, float] = {}
    for code, df in bars_by_code.items():
        if df is None or df.empty:
            continue
        close = df["close"].dropna()
        if close.empty:
            continue
        out[code] = float(close.iloc[-1])
    return out


def derive_final_holdings(
    fills: Iterable[dict],
    bars_by_code: dict[str, pd.DataFrame] | None = None,
    sector_map: dict[str, str] | None = None,
) -> list[HoldingRecord]:
    """
    Replay fills to build the end-state portfolio.

    `fills` are the post-execution Fill dicts from `RunStorage.get_run()`
    (already filtered to non-rejected by the API path). Each must have:
    code, side ('buy'/'sell'), shares, price, cost, date.

    Returns one HoldingRecord per code with shares > 0 at the end. Sorted
    by market value descending.
    """
    bars_by_code = bars_by_code or {}
    sector_map = sector_map or {}

    # Replay fills chronologically.
    state: dict[str, dict] = {}     # code → {shares, cost_total, entry_date}
    sorted_fills = sorted(fills, key=lambda f: (f.get("date") or "", f.get("seq") or 0))

    for f in sorted_fills:
        code = f["code"]
        shares = int(f["shares"])
        price = float(f["price"])
        cost = float(f.get("cost") or 0.0)
        side = f["side"]
        if shares <= 0:
            continue

        if side == "buy":
            entry = state.setdefault(code, {"shares": 0, "cost_total": 0.0,
                                            "entry_date": f["date"]})
            # If we were at zero before this buy, refresh entry_date.
            if entry["shares"] == 0:
                entry["entry_date"] = f["date"]
            entry["shares"] += shares
            entry["cost_total"] += shares * price + cost
        elif side == "sell":
            entry = state.get(code)
            if entry is None or entry["shares"] <= 0:
                continue
            # Reduce shares; proportionally reduce cost basis. Commission/tax
            # on the sell side are realized losses but we ignore here since
            # the engine tracked them in equity_curve directly.
            sell_shares = min(shares, entry["shares"])
            cost_basis_per_share = (entry["cost_total"] / entry["shares"]
                                    if entry["shares"] else 0.0)
            entry["shares"] -= sell_shares
            entry["cost_total"] -= cost_basis_per_share * sell_shares
            if entry["shares"] <= 0:
                # Position fully closed; drop the record so a later re-entry
                # resets entry_date and avg_cost.
                state.pop(code, None)

    last_prices = _last_close_per_code(bars_by_code)

    records: list[HoldingRecord] = []
    for code, entry in state.items():
        if entry["shares"] <= 0:
            continue
        avg_cost = entry["cost_total"] / entry["shares"]
        last = last_prices.get(code, avg_cost)  # fallback: avg_cost (zero PnL)
        mv = entry["shares"] * last
        pnl = mv - entry["shares"] * avg_cost
        denom = entry["shares"] * avg_cost
        pnl_pct = pnl / denom if denom > 0 else 0.0
        records.append(HoldingRecord(
            code=code,
            shares=int(entry["shares"]),
            avg_cost=float(avg_cost),
            market_value=float(mv),
            pnl=float(pnl),
            pnl_pct=float(pnl_pct),
            last_price=float(last),
            entry_date=str(entry["entry_date"]),
            sector=sector_map.get(code),
        ))

    records.sort(key=lambda r: r.market_value, reverse=True)
    return records


def derive_sector_exposure(
    holdings: list[HoldingRecord],
) -> list[SectorWeight]:
    """
    Aggregate end-state holdings into sector weights.

    `holdings` must have `sector` populated (derive_final_holdings does this
    when a sector_map is supplied). Unknown sectors are bucketed under
    "(unknown)".
    """
    if not holdings:
        return []
    total = sum(h.market_value for h in holdings)
    if total <= 0:
        return []

    by_sector: dict[str, dict] = {}
    for h in holdings:
        sec = h.sector or "(unknown)"
        slot = by_sector.setdefault(sec, {"mv": 0.0, "n": 0})
        slot["mv"] += h.market_value
        slot["n"] += 1

    out = [
        SectorWeight(
            sector=sec, weight=slot["mv"] / total,
            n_stocks=slot["n"], market_value=slot["mv"],
        )
        for sec, slot in by_sector.items()
    ]
    out.sort(key=lambda s: s.weight, reverse=True)
    return out
