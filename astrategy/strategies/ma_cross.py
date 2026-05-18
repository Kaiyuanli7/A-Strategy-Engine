"""Dual moving-average crossover strategy."""

from __future__ import annotations

import pandas as pd

from astrategy.engine.orders import Order, OrderSide
from astrategy.strategies.base import Strategy, StrategyContext


class DualMACrossStrategy(Strategy):
    """
    Long-only dual moving average crossover.

    Entry: fast MA crosses ABOVE slow MA at bar N close → BUY at N+1 open.
    Exit:  fast MA crosses BELOW slow MA at bar N close → SELL full position at N+1 open.

    Position sizing: targets `position_size_pct` of current equity per name,
    lot-rounded down. Concurrent holdings capped at `max_positions`.
    """

    def __init__(
        self,
        fast: int = 5,
        slow: int = 20,
        position_size_pct: float = 0.05,
        max_positions: int = 10,
    ):
        assert fast < slow, "fast period must be < slow period"
        self.fast = fast
        self.slow = slow
        self.position_size_pct = position_size_pct
        self.max_positions = max_positions
        self.name = f"ma_cross_{fast}_{slow}"

        # Precomputed per-stock signals: DataFrame[date] with cols fast_ma, slow_ma, signal
        self._signals: dict[str, pd.DataFrame] = {}

    def initialize(self, context: StrategyContext) -> None:
        for code, df in context.data.items():
            close = df["close"].astype(float)
            fast_ma = close.rolling(self.fast, min_periods=self.fast).mean()
            slow_ma = close.rolling(self.slow, min_periods=self.slow).mean()
            # +1 when fast > slow, -1 when fast < slow, 0 otherwise (warmup)
            sig = pd.Series(0, index=df.index, dtype=int)
            sig[fast_ma > slow_ma] = 1
            sig[fast_ma < slow_ma] = -1
            # Cross detection: previous state vs current
            prev = sig.shift(1).fillna(0).astype(int)
            cross_up = (sig == 1) & (prev != 1)
            cross_dn = (sig == -1) & (prev != -1)
            self._signals[code] = pd.DataFrame({
                "fast_ma": fast_ma,
                "slow_ma": slow_ma,
                "cross_up": cross_up,
                "cross_dn": cross_dn,
            })

    def on_bar(
        self,
        date: pd.Timestamp,
        bars: dict[str, pd.Series],
        context: StrategyContext,
    ) -> list[Order]:
        orders: list[Order] = []
        pf = context.portfolio
        close_marks = {code: float(bar["close"]) for code, bar in bars.items()}
        equity = pf.equity(close_marks)
        target_notional = equity * self.position_size_pct

        # Count currently held positions (post-T+1)
        active_holdings = {code for code, p in pf.positions.items() if p.shares > 0}

        for code, bar in bars.items():
            sig = self._signals.get(code)
            if sig is None or date not in sig.index:
                continue
            row = sig.loc[date]
            close = float(bar["close"])
            held = code in active_holdings
            pos = pf.positions.get(code)

            # Exit first (frees a slot for new entry)
            if bool(row["cross_dn"]) and held and pos and pos.shares > 0:
                orders.append(Order(code=code, side=OrderSide.SELL, shares=pos.shares, reason="cross_dn"))
                active_holdings.discard(code)

            # Entry
            elif bool(row["cross_up"]) and not held and len(active_holdings) < self.max_positions:
                if close > 0:
                    target_shares = int(target_notional // close)
                    if target_shares >= 100:
                        orders.append(Order(code=code, side=OrderSide.BUY, shares=target_shares, reason="cross_up"))
                        active_holdings.add(code)

        return orders
