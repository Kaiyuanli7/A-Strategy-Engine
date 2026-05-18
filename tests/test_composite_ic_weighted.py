"""SignedICWeightedComposite — signed-IC weighting handles inverted factors."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from astrategy.composites.base import FactorWeight
from astrategy.composites.ic_weighted import SignedICWeightedComposite
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


class _Positive(_PinnedFactor):
    name = "_positive_ic"


class _Negative(_PinnedFactor):
    name = "_negative_ic"


class _Flat(_PinnedFactor):
    name = "_flat_ic"


@pytest.fixture
def cache(tmp_path):
    return SQLiteCache(db_path=str(tmp_path / "t.db"))


@pytest.fixture
def ctx(cache):
    return FactorContext(cache=cache, universe=["A", "B", "C", "D", "E"],
                          as_of=pd.Timestamp("2024-06-01"))


def _ic_series(values: list[float]) -> pd.Series:
    """Build a fake IC time series indexed by weekly dates."""
    dates = pd.date_range("2024-01-05", periods=len(values), freq="W-FRI")
    return pd.Series(values, index=dates, name="ic")


# --- weight derivation ---------------------------------------------------------

def test_positive_ic_gets_positive_weight(ctx):
    pos = _Positive(pd.Series({"A": 1.0, "B": 2.0}))
    flat = _Flat(pd.Series({"A": 1.0, "B": 2.0}))
    composite = SignedICWeightedComposite([FactorWeight(pos), FactorWeight(flat)])
    ic_hist = {
        "_positive_ic": _ic_series([0.03, 0.04, 0.05, 0.02, 0.04] * 12),
        "_flat_ic":     _ic_series([0.0, 0.001, -0.001, 0.0] * 15),
    }
    weights = composite.derive_weights(ctx, ic_history=ic_hist)
    assert weights["_positive_ic"] > 0
    # _flat_ic mean is below the 0.005 threshold → zero weight
    assert weights["_flat_ic"] == 0.0
    # L1-normalized: |w| should sum to 1
    assert sum(abs(w) for w in weights.values()) == pytest.approx(1.0)


def test_negative_ic_gets_negative_weight(ctx):
    """A factor with consistently negative IC becomes a short signal (negative weight)."""
    pos = _Positive(pd.Series({"A": 1.0}))
    neg = _Negative(pd.Series({"A": 1.0}))
    composite = SignedICWeightedComposite([FactorWeight(pos), FactorWeight(neg)])
    ic_hist = {
        "_positive_ic": _ic_series([0.04] * 60),
        "_negative_ic": _ic_series([-0.03] * 60),
    }
    weights = composite.derive_weights(ctx, ic_history=ic_hist)
    assert weights["_positive_ic"] > 0
    assert weights["_negative_ic"] < 0
    # Roughly proportional to abs(IC); +0.04 vs -0.03 → +4/7 vs -3/7
    assert weights["_positive_ic"] == pytest.approx(4 / 7, abs=0.01)
    assert weights["_negative_ic"] == pytest.approx(-3 / 7, abs=0.01)


def test_no_ic_history_falls_back_to_equal_weight(ctx):
    pos = _Positive(pd.Series({"A": 1.0}))
    neg = _Negative(pd.Series({"A": 1.0}))
    composite = SignedICWeightedComposite([FactorWeight(pos), FactorWeight(neg)])
    weights = composite.derive_weights(ctx, ic_history=None)
    assert weights == {"_positive_ic": 0.5, "_negative_ic": 0.5}


def test_all_factors_below_threshold_falls_back_to_equal_weight(ctx):
    pos = _Positive(pd.Series({"A": 1.0}))
    flat = _Flat(pd.Series({"A": 1.0}))
    composite = SignedICWeightedComposite([FactorWeight(pos), FactorWeight(flat)],
                                          min_ic_abs=0.10)  # impossibly high
    ic_hist = {
        "_positive_ic": _ic_series([0.04] * 60),
        "_flat_ic":     _ic_series([0.001] * 60),
    }
    weights = composite.derive_weights(ctx, ic_history=ic_hist)
    # All factors fell below threshold → equal weight fallback
    assert weights == {"_positive_ic": 0.5, "_flat_ic": 0.5}


def test_rolling_window_uses_only_last_n_observations(ctx):
    """Old history shouldn't pollute the weight."""
    pos = _Positive(pd.Series({"A": 1.0}))
    composite = SignedICWeightedComposite([FactorWeight(pos)], rolling_window=10)
    # 50 ancient periods at IC=+0.10, then 10 recent at IC=-0.05
    ic_hist = {
        "_positive_ic": _ic_series([0.10] * 50 + [-0.05] * 10),
    }
    weights = composite.derive_weights(ctx, ic_history=ic_hist)
    # Only the last 10 should matter; mean = -0.05 → negative weight after norm
    assert weights["_positive_ic"] == pytest.approx(-1.0)  # only factor, L1=1


# --- full composite path (compute) --------------------------------------------

def test_compute_with_signed_ic_inverts_negative_factor(ctx):
    """End-to-end: a factor with negative IC contributes its score INVERTED."""
    pos = _Positive(pd.Series({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0}))
    neg = _Negative(pd.Series({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0}))
    composite = SignedICWeightedComposite([FactorWeight(pos), FactorWeight(neg)])
    ic_hist = {
        "_positive_ic": _ic_series([0.04] * 60),
        "_negative_ic": _ic_series([-0.04] * 60),
    }
    out = composite.compute(ctx, ic_history=ic_hist)
    # Both factors have the same raw scores. The positive-IC one contributes
    # +z; the negative-IC one contributes -z. They cancel out → composite ~ 0.
    for code in ("A", "B", "C", "D", "E"):
        assert abs(out[code]) < 1e-9
