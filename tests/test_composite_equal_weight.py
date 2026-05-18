"""EqualWeightComposite + zscore_cross_section."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from astrategy.composites.base import FactorWeight, zscore_cross_section
from astrategy.composites.equal_weight import EqualWeightComposite
from astrategy.data.cache import SQLiteCache
from astrategy.factors.base import Factor, FactorContext


class _PinnedFactor(Factor):
    """Test factor that returns its pinned series. Subclasses must set `name`."""

    _scores: pd.Series

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


class _FactorA(_PinnedFactor):
    name = "_factor_a"


class _FactorB(_PinnedFactor):
    name = "_factor_b"


class _FactorC(_PinnedFactor):
    name = "_factor_c"


@pytest.fixture
def cache(tmp_path):
    return SQLiteCache(db_path=str(tmp_path / "t.db"))


@pytest.fixture
def ctx(cache):
    return FactorContext(cache=cache, universe=["A", "B", "C", "D", "E"],
                          as_of=pd.Timestamp("2024-06-01"))


# --- zscore_cross_section -----------------------------------------------------

def test_zscore_basic():
    s = pd.Series({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0})
    z = zscore_cross_section(s)
    assert z.mean() == pytest.approx(0.0, abs=1e-9)
    assert z.std(ddof=1) == pytest.approx(1.0, abs=1e-9)


def test_zscore_returns_zero_on_constant():
    s = pd.Series({"A": 3.0, "B": 3.0, "C": 3.0})
    z = zscore_cross_section(s)
    assert (z == 0.0).all()


def test_zscore_skips_nans():
    s = pd.Series({"A": 1.0, "B": np.nan, "C": 3.0, "D": np.nan, "E": 5.0})
    z = zscore_cross_section(s)
    assert "B" not in z.index
    assert "D" not in z.index
    assert len(z) == 3


def test_zscore_empty_input():
    assert zscore_cross_section(pd.Series(dtype="float64")).empty


# --- EqualWeightComposite -----------------------------------------------------

def test_equal_weight_basic(ctx):
    """Two factors with anti-correlated scores → composite ~ 0 for every code."""
    f1 = _FactorA(pd.Series({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0}))
    f2 = _FactorB(pd.Series({"A": 5.0, "B": 4.0, "C": 3.0, "D": 2.0, "E": 1.0}))
    composite = EqualWeightComposite([FactorWeight(f1), FactorWeight(f2)])
    out = composite.compute(ctx)
    assert len(out) == 5
    for code in ("A", "B", "C", "D", "E"):
        assert abs(out[code]) < 1e-9


def test_equal_weight_aligned_factors_preserve_ranking(ctx):
    """Two factors with same ranking but different scales → composite agrees."""
    base = pd.Series({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0})
    f1 = _FactorA(base)
    f2 = _FactorB(base * 10)   # same ranking, 10x scale
    composite = EqualWeightComposite([FactorWeight(f1), FactorWeight(f2)])
    out = composite.compute(ctx)
    assert out["E"] > out["D"] > out["C"] > out["B"] > out["A"]


def test_equal_weight_handles_missing_codes(ctx):
    """f1 covers A,B,C; f2 covers C,D,E. Composite covers all 5."""
    f1 = _FactorA(pd.Series({"A": 1.0, "B": 2.0, "C": 3.0}))
    f2 = _FactorB(pd.Series({"C": 1.0, "D": 2.0, "E": 3.0}))
    composite = EqualWeightComposite([FactorWeight(f1), FactorWeight(f2)])
    out = composite.compute(ctx)
    assert set(out.index) == {"A", "B", "C", "D", "E"}


def test_equal_weight_weights_dict_correct(ctx):
    f1 = _FactorA(pd.Series({"A": 1.0}))
    f2 = _FactorB(pd.Series({"A": 2.0}))
    composite = EqualWeightComposite([FactorWeight(f1), FactorWeight(f2)])
    weights = composite.derive_weights(ctx)
    assert weights == {"_factor_a": 0.5, "_factor_b": 0.5}


def test_equal_weight_three_factor_split(ctx):
    f1 = _FactorA(pd.Series({"A": 1.0}))
    f2 = _FactorB(pd.Series({"A": 1.0}))
    f3 = _FactorC(pd.Series({"A": 1.0}))
    composite = EqualWeightComposite([FactorWeight(f1), FactorWeight(f2), FactorWeight(f3)])
    weights = composite.derive_weights(ctx)
    assert weights["_factor_a"] == pytest.approx(1.0 / 3)
    assert weights["_factor_b"] == pytest.approx(1.0 / 3)
    assert weights["_factor_c"] == pytest.approx(1.0 / 3)


def test_equal_weight_single_factor(ctx):
    f1 = _FactorA(pd.Series({"A": 1.0, "B": 2.0, "C": 3.0}))
    composite = EqualWeightComposite([FactorWeight(f1)])
    weights = composite.derive_weights(ctx)
    assert weights == {"_factor_a": 1.0}


def test_composite_raises_on_empty_factor_list():
    with pytest.raises(ValueError):
        EqualWeightComposite([])
