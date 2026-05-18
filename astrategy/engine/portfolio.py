"""Portfolio state — cash, positions, T+1 sellable tracking."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Position:
    code: str
    shares: int = 0
    sellable: int = 0   # shares free of T+1 lock
    avg_cost: float = 0.0


class Portfolio:
    """
    Models a cash + long-only positions portfolio with T+1 settlement.

    T+1 invariant: shares purchased on day N have `sellable == 0` for the rest of
    day N. At the start of day N+1, `settle_t1()` unlocks them (sellable = shares).
    """

    def __init__(self, initial_cash: float):
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.positions: dict[str, Position] = {}

    def settle_t1(self) -> None:
        """Run at the start of each new trading day, before signal generation."""
        for pos in self.positions.values():
            pos.sellable = pos.shares

    def equity(self, marks: dict[str, float]) -> float:
        """Total equity = cash + sum(shares × last close)."""
        mv = 0.0
        for code, pos in self.positions.items():
            if pos.shares > 0 and code in marks:
                mv += pos.shares * marks[code]
        return self.cash + mv

    def apply_buy(self, code: str, shares: int, price: float, cost: float) -> bool:
        notional = shares * price
        total = notional + cost
        if shares <= 0 or total > self.cash + 1e-6:
            return False
        self.cash -= total
        pos = self.positions.setdefault(code, Position(code=code))
        new_shares = pos.shares + shares
        # Volume-weighted average cost includes commission/fees in the cost basis
        pos.avg_cost = (pos.avg_cost * pos.shares + notional + cost) / new_shares if new_shares else 0.0
        pos.shares = new_shares
        # T+1: newly bought shares are NOT sellable today
        # sellable stays put — settle_t1() will unlock everything at next bar start
        return True

    def apply_sell(self, code: str, shares: int, price: float, cost: float) -> bool:
        pos = self.positions.get(code)
        if pos is None or shares <= 0 or shares > pos.sellable:
            return False
        notional = shares * price
        proceeds = notional - cost
        self.cash += proceeds
        pos.shares -= shares
        pos.sellable -= shares
        if pos.shares == 0:
            pos.avg_cost = 0.0
        return True
