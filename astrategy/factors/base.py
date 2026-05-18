"""Factor ABC + per-evaluation context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

import pandas as pd
from pydantic import BaseModel

from astrategy.data.cache import SQLiteCache


@dataclass
class FactorContext:
    """
    Data access for one factor `compute()` call.

    Point-in-time discipline: every getter only returns data with timestamps
    strictly before `as_of`. Factors must not bypass this object to read
    `daily_bars` for `as_of` itself — by convention, signal at close[t-1]
    drives the score for date `t`, and the signal trades at open[t+1].
    """
    cache: SQLiteCache
    universe: list[str]
    as_of: pd.Timestamp

    def as_of_str(self) -> str:
        return self.as_of.strftime("%Y-%m-%d")

    def northbound(self, code: str, lookback_days: int = 30) -> pd.DataFrame:
        """Per-stock northbound rows in [as_of - lookback_days, as_of)."""
        return self.cache.northbound_as_of(code, self.as_of_str(), lookback_days)

    def valuation(self, code: str) -> dict | None:
        """Most recent valuation row strictly before as_of."""
        return self.cache.valuation_as_of(code, self.as_of_str())

    def cross_sectional_valuation(self) -> pd.DataFrame:
        """Latest pre-as_of valuation row per code in universe. Indexed by code."""
        return self.cache.cross_sectional_valuation_as_of(self.universe, self.as_of_str())


class FactorParamSpec(BaseModel):
    """Description of one tunable parameter on a Factor (drives API + UI)."""
    name: str
    type: Literal["int", "float", "str", "bool"]
    default: Any
    description: str | None = None
    min: float | None = None
    max: float | None = None


class Factor(ABC):
    """
    Base class. Subclasses set the class attributes (name, category, etc.)
    and implement `compute()`. Constructor accepts tunable params as kwargs.

    Required class attributes on every subclass:

        name: short_snake_case identifier (registry key)
        category: one of "flow", "fundamental", "technical", "event", "sector"
        description: 1-2 sentence purpose for the UI
        lookback_days: minimum trailing data window the factor needs
        rebalance_freq: "daily" | "weekly" | "monthly" (UI default rebalance)
    """

    name: ClassVar[str] = "unnamed"
    category: ClassVar[Literal["flow", "fundamental", "technical", "event", "sector"]] = "flow"
    description: ClassVar[str] = ""
    lookback_days: ClassVar[int] = 30
    rebalance_freq: ClassVar[Literal["daily", "weekly", "monthly"]] = "weekly"
    _param_specs: ClassVar[list[FactorParamSpec]] = []

    def __init__(self, **params: Any) -> None:
        # Apply defaults, then user overrides; reject unknown params.
        defaults = {p.name: p.default for p in self._param_specs}
        for k in params:
            if k not in defaults:
                raise ValueError(
                    f"{self.name}: unknown parameter '{k}'; "
                    f"valid params are {sorted(defaults)}"
                )
        merged = {**defaults, **params}
        self.params: dict[str, Any] = merged

    @classmethod
    def param_specs(cls) -> list[FactorParamSpec]:
        return list(cls._param_specs)

    @abstractmethod
    def compute(self, ctx: FactorContext) -> pd.Series:
        """
        Return a Series indexed by stock code with the factor score on `ctx.as_of`.
        Higher score = more bullish. NaN means the factor abstains for that code
        (insufficient data, suspended, etc.). The evaluation framework drops NaNs.
        """
