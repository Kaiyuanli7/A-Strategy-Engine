"""FixedWeightComposite — apply explicit per-factor weights.

Distinct from EqualWeightComposite (ignores user weights) and
SignedICWeightedComposite (computes weights at runtime from IC).

Used by the Optuna walk-forward optimizer: the optimizer fits a list of
weights on the IS window, builds a FixedWeightComposite with those weights,
and runs OOS to measure generalization.
"""

from __future__ import annotations

from typing import ClassVar

from astrategy.composites.base import Composite


class FixedWeightComposite(Composite):
    """
    Use explicit weights from each FactorWeight slot.

    Each FactorWeight.weight MUST be set (no None). Weights are used as-is
    (no automatic normalization) so callers can pre-normalize to whatever
    convention they prefer (L1, L2, or unconstrained).
    """

    name: ClassVar[str] = "fixed_weight"

    def __init__(self, factor_weights):
        super().__init__(factor_weights)
        for fw in factor_weights:
            if fw.weight is None:
                raise ValueError(
                    f"FixedWeightComposite: factor {fw.factor.name!r} has weight=None; "
                    "all weights must be set explicitly."
                )

    def derive_weights(self, ctx, ic_history=None) -> dict[str, float]:
        return {fw.factor.name: float(fw.weight) for fw in self.factor_weights}
