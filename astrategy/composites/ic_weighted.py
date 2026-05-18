"""Signed-IC-weighted composite.

Key design choice: SIGNED IC, not absolute IC. A factor with consistently
negative IC (e.g., A-share price momentum on CSI 300 — Liu/Stambaugh/Yuan
2019 §5) automatically gets a negative weight, becoming a short signal in
the composite. This avoids needing to manually invert factor implementations
or maintain a "direction" sign per factor.

Weight derivation:

    raw_weight[f] = mean(IC[f, last rolling_window periods])
    if |raw_weight[f]| < min_ic_abs:
        raw_weight[f] = 0       # factor with no clear edge contributes nothing

    weights[f] = raw_weight[f] / sum(|raw_weight|)   # L1 normalize

If all factors fall below `min_ic_abs`, fall back to equal-weight to avoid
producing a useless zero-everywhere composite.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pandas as pd

from astrategy.composites.base import Composite


class SignedICWeightedComposite(Composite):
    """Weights factors by their trailing signed IC."""

    name: ClassVar[str] = "signed_ic_weighted"

    def __init__(
        self,
        factor_weights,
        rolling_window: int = 60,
        min_ic_abs: float = 0.005,
    ):
        super().__init__(factor_weights)
        self.rolling_window = rolling_window
        self.min_ic_abs = min_ic_abs

    def derive_weights(
        self,
        ctx,
        ic_history: dict[str, pd.Series] | None = None,
    ) -> dict[str, float]:
        names = self.factor_names
        if not ic_history:
            # No IC history available (e.g., first rebalance date) → equal weight
            n = len(names)
            return {n_: 1.0 / n for n_ in names}

        raw: dict[str, float] = {}
        for name in names:
            series = ic_history.get(name)
            if series is None or series.empty:
                raw[name] = 0.0
                continue
            # Trailing window of per-period IC, take the mean (signed)
            recent = series.dropna().tail(self.rolling_window)
            if recent.empty:
                raw[name] = 0.0
                continue
            mean_ic = float(recent.mean())
            if abs(mean_ic) < self.min_ic_abs:
                raw[name] = 0.0
            else:
                raw[name] = mean_ic

        total_abs = sum(abs(v) for v in raw.values())
        if total_abs <= 0:
            # Every factor below the threshold — fall back to equal weight
            n = len(names)
            return {n_: 1.0 / n for n_ in names}
        return {name: raw[name] / total_abs for name in names}
