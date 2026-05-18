"""FixedWeightComposite — applies explicit per-factor weights."""

from __future__ import annotations

import pandas as pd
import pytest

from astrategy.composites.base import FactorWeight
from astrategy.composites.fixed import FixedWeightComposite
from astrategy.data.cache import SQLiteCache
from astrategy.factors.base import Factor, FactorContext


class _PinnedFactor(Factor):
    name = "_pinned_base"
    category = "flow"
    description = "test"
    lookback_days = 1
    rebalance_freq = "weekly"
    _param_specs: list = []

    def __init__(self, scores: pd.Series):
        super().__init__()
        self._scores = scores

    def compute(self, ctx):
        return self._scores


class _A(_PinnedFactor):
    name = "_a"


class _B(_PinnedFactor):
    name = "_b"


@pytest.fixture
def cache(tmp_path):
    return SQLiteCache(db_path=str(tmp_path / "t.db"))


@pytest.fixture
def ctx(cache):
    return FactorContext(cache=cache, universe=["X", "Y", "Z"],
                          as_of=pd.Timestamp("2024-06-01"))


def test_fixed_weight_basic(ctx):
    fa = _A(pd.Series({"X": 1.0, "Y": 2.0, "Z": 3.0}))
    fb = _B(pd.Series({"X": 3.0, "Y": 2.0, "Z": 1.0}))
    composite = FixedWeightComposite([
        FactorWeight(factor=fa, weight=0.75),
        FactorWeight(factor=fb, weight=0.25),
    ])
    weights = composite.derive_weights(ctx)
    assert weights == {"_a": 0.75, "_b": 0.25}


def test_fixed_weight_negates_inverted_factor(ctx):
    """A negative weight makes the factor a short signal."""
    fa = _A(pd.Series({"X": 1.0, "Y": 2.0, "Z": 3.0}))
    composite = FixedWeightComposite([FactorWeight(factor=fa, weight=-1.0)])
    out = composite.compute(ctx)
    # Z had the highest raw score → after -1 weighting it should be lowest
    assert out["Z"] < out["X"]


def test_fixed_weight_rejects_none_weight():
    fa = _A(pd.Series({"X": 1.0}))
    with pytest.raises(ValueError, match="weight=None"):
        FixedWeightComposite([FactorWeight(factor=fa, weight=None)])
