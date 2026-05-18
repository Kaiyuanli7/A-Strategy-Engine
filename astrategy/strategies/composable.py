"""
ComposableStrategy — JSON-configurable long-only strategy.

AND-reduces a list of entry conditions into a single bool Series per stock.
Exits on stop-loss / take-profit (close-only), max-hold-days, or signal reversal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from astrategy.data.cache import SQLiteCache
from astrategy.engine.orders import Fill, Order, OrderSide
from astrategy.strategies import indicators as ind
from astrategy.strategies import sizing as siz
from astrategy.strategies.base import Strategy, StrategyContext
from astrategy.strategies.conditions import (
    ConditionSpec,
    build_cond_data,
    precompute_condition,
)


# ----- Strategy params (Pydantic for API edge validation) -----

class ExitRulesSpec(BaseModel):
    stop_loss_pct: float | None = None     # e.g. 0.08 = 8% drop below entry
    take_profit_pct: float | None = None   # e.g. 0.20 = 20% gain
    max_hold_days: int | None = None       # bars since entry fill
    signal_reversal: bool = False          # exit when entry signal goes False
    model_config = ConfigDict(extra="forbid")


class SizingSpec(BaseModel):
    method: Literal["equal_weight", "fixed_amount", "vol_adjusted"] = "equal_weight"
    position_size_pct: float = 0.05
    amount: float | None = None            # for fixed_amount
    target_vol_pct: float | None = None    # for vol_adjusted (e.g. 0.20)
    model_config = ConfigDict(extra="forbid")


class ComposableStrategyParams(BaseModel):
    entry_conditions: list[ConditionSpec] = Field(..., min_length=1)
    exit_rules: ExitRulesSpec = Field(default_factory=ExitRulesSpec)
    sizing: SizingSpec = Field(default_factory=SizingSpec)
    max_positions: int = 10
    model_config = ConfigDict(extra="forbid")


# ----- Strategy impl --------------------------------------------------------

@dataclass
class _EntryRecord:
    timestamp: pd.Timestamp
    price: float


class ComposableStrategy(Strategy):
    def __init__(
        self,
        entry_conditions: list[dict] | list[Any],
        exit_rules: dict | ExitRulesSpec | None = None,
        sizing: dict | SizingSpec | None = None,
        max_positions: int = 10,
        cache: SQLiteCache | None = None,
    ):
        # Parse via Pydantic for strong validation
        if isinstance(exit_rules, dict) or exit_rules is None:
            self.exit_rules = ExitRulesSpec.model_validate(exit_rules or {})
        else:
            self.exit_rules = exit_rules
        if isinstance(sizing, dict) or sizing is None:
            self.sizing = SizingSpec.model_validate(sizing or {})
        else:
            self.sizing = sizing
        self.entry_specs = list(entry_conditions)
        self.max_positions = int(max_positions)
        self.cache = cache or SQLiteCache()
        self.name = f"composable_{len(self.entry_specs)}cond"

        # Filled by initialize()
        self._entry_signal: dict[str, pd.Series] = {}
        self._realized_vol: dict[str, pd.Series] = {}

        # Mutated during run via on_fill / on_bar
        self._entries: dict[str, _EntryRecord] = {}

    # -- precompute --

    def initialize(self, ctx: StrategyContext) -> None:
        start = min(df.index.min() for df in ctx.data.values()).strftime("%Y-%m-%d")
        end = max(df.index.max() for df in ctx.data.values()).strftime("%Y-%m-%d")

        for code, df in ctx.data.items():
            ohlcv = df if isinstance(df.index, pd.DatetimeIndex) else df.set_index(
                pd.to_datetime(df.index)
            )
            fundamentals = self._load_fundamentals(code, end)
            valuation = self._load_valuation(code, start, end)
            northbound = self._load_northbound(code, start, end)
            cond_data = build_cond_data(ohlcv, fundamentals, valuation, northbound)

            # AND-reduce all conditions
            combined: pd.Series | None = None
            for spec in self.entry_specs:
                cond = precompute_condition(spec, cond_data)
                combined = cond if combined is None else (combined & cond)
            assert combined is not None
            self._entry_signal[code] = combined.astype(bool)

            # Realized vol for vol_adjusted sizing
            self._realized_vol[code] = ind.realized_vol(ohlcv["close"].astype(float), 20)

    def _load_fundamentals(self, code: str, end: str) -> pd.DataFrame | None:
        try:
            df = self.cache.get_fundamentals(code, end=end)
        except Exception:
            return None
        return df if df is not None and not df.empty else None

    def _load_valuation(self, code: str, start: str, end: str) -> pd.DataFrame | None:
        try:
            df = self.cache.get_valuation_daily(code, start, end)
        except Exception:
            return None
        return df if df is not None and not df.empty else None

    def _load_northbound(self, code: str, start: str, end: str) -> pd.DataFrame | None:
        try:
            df = self.cache.get_northbound(code, start, end)
        except Exception:
            return None
        return df if df is not None and not df.empty else None

    # -- per-bar --

    def on_bar(
        self,
        date: pd.Timestamp,
        bars: dict[str, pd.Series],
        context: StrategyContext,
    ) -> list[Order]:
        orders: list[Order] = []
        pf = context.portfolio

        # 1. Exits first (frees slots)
        for code in list(self._entries.keys()):
            bar = bars.get(code)
            if bar is None:
                continue
            pos = pf.positions.get(code)
            if pos is None or pos.shares == 0:
                # External / unexpected — clear tracker
                self._entries.pop(code, None)
                continue
            close = float(bar["close"])
            entry = self._entries[code]
            if self._should_exit(date, code, close, entry):
                orders.append(Order(code=code, side=OrderSide.SELL,
                                    shares=pos.shares, reason="composable_exit"))

        # 2. Entries
        active = {c for c, p in pf.positions.items() if p.shares > 0}
        # Subtract codes already being exited this bar
        exiting = {o.code for o in orders if o.side == OrderSide.SELL}
        slots = self.max_positions - (len(active) - len(exiting))

        if slots > 0:
            equity = pf.equity({c: float(b["close"]) for c, b in bars.items()})
            for code, bar in bars.items():
                if slots <= 0:
                    break
                if code in active and code not in exiting:
                    continue
                sig = self._entry_signal.get(code)
                if sig is None or date not in sig.index or not bool(sig.loc[date]):
                    continue
                close = float(bar["close"])
                rv = self._realized_vol.get(code)
                rv_today = (
                    float(rv.loc[date]) if rv is not None and date in rv.index
                    and not pd.isna(rv.loc[date]) else None
                )
                shares = siz.size(
                    self.sizing.method,
                    siz.SizingContext(equity=equity, close=close, realized_vol=rv_today),
                    self._sizing_params(),
                )
                if shares >= 100:
                    orders.append(Order(code=code, side=OrderSide.BUY, shares=shares,
                                        reason="composable_entry"))
                    slots -= 1

        return orders

    def _sizing_params(self) -> dict:
        return {
            "position_size_pct": self.sizing.position_size_pct,
            "amount": self.sizing.amount,
            "target_vol_pct": self.sizing.target_vol_pct,
        }

    def _should_exit(
        self,
        date: pd.Timestamp,
        code: str,
        close: float,
        entry: _EntryRecord,
    ) -> bool:
        rules = self.exit_rules
        if rules.stop_loss_pct is not None and entry.price > 0:
            if close <= entry.price * (1.0 - rules.stop_loss_pct):
                return True
        if rules.take_profit_pct is not None and entry.price > 0:
            if close >= entry.price * (1.0 + rules.take_profit_pct):
                return True
        if rules.max_hold_days is not None:
            held = (date - entry.timestamp).days
            if held >= rules.max_hold_days:
                return True
        if rules.signal_reversal:
            sig = self._entry_signal.get(code)
            if sig is not None and date in sig.index and not bool(sig.loc[date]):
                return True
        return False

    def on_fill(self, fill: Fill, context: StrategyContext) -> None:
        if fill.rejected_reason is not None:
            return
        if fill.side == OrderSide.BUY:
            # First buy sets entry; subsequent buys (rare in this strategy)
            # don't overwrite — keep the oldest entry timestamp for max_hold.
            if fill.code not in self._entries:
                self._entries[fill.code] = _EntryRecord(
                    timestamp=fill.timestamp, price=float(fill.price)
                )
        else:
            self._entries.pop(fill.code, None)
