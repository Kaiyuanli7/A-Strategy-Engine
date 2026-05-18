"""Strategy abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from astrategy.engine.orders import Order
from astrategy.engine.portfolio import Portfolio


@dataclass
class StrategyContext:
    """
    Per-bar context handed to a Strategy. The engine sets `current_date`
    before each on_bar call.
    """
    portfolio: Portfolio
    universe: list[str]
    data: dict[str, pd.DataFrame]    # full history, indexed by date
    current_date: pd.Timestamp | None = None


class Strategy(ABC):
    name: str = "unnamed"

    @abstractmethod
    def initialize(self, context: StrategyContext) -> None:
        """Called once before the run. Precompute indicators here."""

    @abstractmethod
    def on_bar(
        self,
        date: pd.Timestamp,
        bars: dict[str, pd.Series],
        context: StrategyContext,
    ) -> list[Order]:
        """
        Return new Orders to be queued for execution at the *next* bar's open.

        Args:
            date: current trading day (already closed at this point)
            bars: today's full bar per active (non-suspended) symbol
            context: read-write access to portfolio + read access to data
        """

    def on_fill(self, fill, context: StrategyContext) -> None:
        """Optional hook."""
        pass
