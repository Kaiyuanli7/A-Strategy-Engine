"""Composite ABC and shared types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

import numpy as np
import pandas as pd

from astrategy.factors.base import Factor, FactorContext


@dataclass
class FactorWeight:
    """One slot in a composite: a factor instance plus an optional explicit weight."""
    factor: Factor
    weight: float | None = None   # None = let the composite decide (e.g., IC-weighted)


def zscore_cross_section(s: pd.Series) -> pd.Series:
    """
    Z-score a cross-section: (x - mean) / std. NaN-tolerant.

    A factor compute() returns scores in arbitrary units (RMB/share count
    ratios, return percentages, percentile floats). Composites must align
    them before combining, otherwise the factor with the largest natural
    scale dominates regardless of signal quality.
    """
    if s is None or s.empty:
        return pd.Series(dtype="float64")
    clean = s.dropna().astype(float)
    if len(clean) < 2:
        return pd.Series(0.0, index=clean.index)
    mu = clean.mean()
    sigma = clean.std(ddof=1)
    if sigma == 0 or not np.isfinite(sigma):
        return pd.Series(0.0, index=clean.index)
    return ((clean - mu) / sigma).astype(float)


class Composite(ABC):
    """
    Combine multiple factors into a single cross-sectional ranking.

    Subclasses implement weight derivation (equal, signed-IC, optuna).
    Composition flow:

        1. For each factor, call factor.compute(ctx) → pd.Series indexed by code.
        2. z-score each factor's scores cross-sectionally.
        3. Combine z-scored series with per-factor weights into one composite.
        4. Drop codes that have NaN in all factors (no data → no opinion).
    """

    name: ClassVar[str] = "unnamed_composite"

    def __init__(self, factor_weights: list[FactorWeight]) -> None:
        if not factor_weights:
            raise ValueError("Composite requires at least one FactorWeight")
        self.factor_weights = factor_weights

    @property
    def factor_names(self) -> list[str]:
        return [fw.factor.name for fw in self.factor_weights]

    def compute_per_factor_scores(self, ctx: FactorContext) -> dict[str, pd.Series]:
        """Returns {factor_name: raw scores Series}. Helper for subclasses."""
        out: dict[str, pd.Series] = {}
        for fw in self.factor_weights:
            try:
                out[fw.factor.name] = fw.factor.compute(ctx)
            except Exception:
                # A misbehaving factor shouldn't take the whole composite down.
                # Log via the factor's compute path; emit empty here.
                out[fw.factor.name] = pd.Series(dtype="float64")
        return out

    @abstractmethod
    def derive_weights(
        self,
        ctx: FactorContext,
        ic_history: dict[str, pd.Series] | None = None,
    ) -> dict[str, float]:
        """Return {factor_name: weight}. Subclass implements."""

    def compute(
        self,
        ctx: FactorContext,
        ic_history: dict[str, pd.Series] | None = None,
    ) -> pd.Series:
        """
        Run the full composite at a single rebalance date.

        Args:
            ctx: factor context (universe + as_of + cache).
            ic_history: optional {factor_name: rolling IC Series} for the
                signed-IC and Optuna composites. None for EqualWeight.

        Returns: pd.Series indexed by stock code with composite score.
        """
        raw = self.compute_per_factor_scores(ctx)
        zscored = {name: zscore_cross_section(s) for name, s in raw.items()}
        weights = self.derive_weights(ctx, ic_history=ic_history)

        # Combine: weighted sum across factors, dropping NaN-only rows.
        combined: pd.DataFrame = pd.DataFrame(zscored)
        if combined.empty:
            return pd.Series(dtype="float64")
        weight_vec = pd.Series(weights).reindex(combined.columns).fillna(0.0)
        combined = combined.fillna(0.0)  # NaN factor at code = 0 contribution
        composite = combined.dot(weight_vec)
        # Re-drop codes that had NO factor coverage (all NaN before fillna)
        any_real = pd.DataFrame(zscored).notna().any(axis=1)
        composite = composite.where(any_real).dropna()
        composite.name = self.name
        return composite
