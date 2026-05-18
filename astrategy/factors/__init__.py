"""Factor library — alpha-factor construction primitives for A-share research.

A *factor* is a function `(date, universe) -> Series[code -> score]` where a
higher score means more bullish. Every factor enforces point-in-time data
access through `FactorContext` so look-ahead bias is structurally impossible.

Usage:

    from astrategy.factors import get_factor, list_factors
    factor = get_factor("northbound_momentum")(lookback=5)
    scores = factor.compute(ctx)   # pd.Series indexed by code

The registry is populated on import. To add a new factor, write a subclass of
`Factor`, decorate it (or call `register_factor`) in the module, and import
the module here so registration runs.
"""

from astrategy.factors.base import Factor, FactorContext, FactorParamSpec
from astrategy.factors.registry import (
    get_factor,
    list_factors,
    register_factor,
)

# Importing each factor module registers its factor with the registry.
from astrategy.factors import northbound  # noqa: F401  (import for side effects)


__all__ = [
    "Factor",
    "FactorContext",
    "FactorParamSpec",
    "get_factor",
    "list_factors",
    "register_factor",
]
