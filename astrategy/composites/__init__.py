"""Composite factor scoring — combine multiple factors into a single ranking.

Two composites ship in Sprint 3:

- `EqualWeightComposite` (baseline): z-score each factor cross-sectionally,
  arithmetic mean. Hard to beat as a starting point.
- `SignedICWeightedComposite`: weights factors by their trailing signed IC.
  A factor with consistently negative IC (e.g., A-share price momentum on
  CSI 300) automatically gets negative weight, effectively becoming a short
  signal in the composite — no need to manually invert factor implementations.

Optuna-optimized weights live in `optuna_weighted.py` and are wired through
the walk-forward runner.
"""

from astrategy.composites.base import Composite, FactorWeight
from astrategy.composites.equal_weight import EqualWeightComposite
from astrategy.composites.ic_weighted import SignedICWeightedComposite

__all__ = [
    "Composite",
    "FactorWeight",
    "EqualWeightComposite",
    "SignedICWeightedComposite",
]
