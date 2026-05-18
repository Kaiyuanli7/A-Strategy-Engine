"""Equal-weight composite — the baseline."""

from __future__ import annotations

from typing import ClassVar

from astrategy.composites.base import Composite
from astrategy.factors.base import FactorContext


class EqualWeightComposite(Composite):
    """
    Average of z-scored factor scores. Each factor gets weight 1/N.

    User-provided weights on the FactorWeight entries are ignored — pick this
    composite when you want to be agnostic about which factor matters most.
    "Hard to beat" per CLAUDE.md: it's the starting point and the floor.
    """

    name: ClassVar[str] = "equal_weight"

    def derive_weights(self, ctx, ic_history=None) -> dict[str, float]:
        n = len(self.factor_weights)
        w = 1.0 / n
        return {fw.factor.name: w for fw in self.factor_weights}
