"""Order and Fill dataclasses for the backtest engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Order:
    code: str
    side: OrderSide
    shares: int        # absolute, lot-rounded by caller
    reason: str = ""


@dataclass
class Fill:
    code: str
    side: OrderSide
    shares: int
    price: float
    cost: float
    timestamp: pd.Timestamp
    rejected_reason: str | None = None

    @property
    def notional(self) -> float:
        return self.shares * self.price
