"""IC computation + summary tests."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from astrategy.evaluation.ic import compute_ic_series, spearman_ic, summarize_ic


def test_spearman_ic_perfect_positive():
    s = pd.Series({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0})
    r = pd.Series({"A": 0.01, "B": 0.02, "C": 0.03, "D": 0.04, "E": 0.05})
    assert spearman_ic(s, r) == pytest.approx(1.0)


def test_spearman_ic_perfect_negative():
    s = pd.Series({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0})
    r = pd.Series({"A": 0.05, "B": 0.04, "C": 0.03, "D": 0.02, "E": 0.01})
    assert spearman_ic(s, r) == pytest.approx(-1.0)


def test_spearman_ic_drops_nans():
    s = pd.Series({"A": 1.0, "B": 2.0, "C": np.nan, "D": 4.0, "E": 5.0})
    r = pd.Series({"A": 0.01, "B": 0.02, "C": 0.03, "D": 0.04, "E": 0.05})
    assert spearman_ic(s, r) == pytest.approx(1.0)


def test_spearman_ic_returns_nan_for_too_few():
    s = pd.Series({"A": 1.0, "B": 2.0})
    r = pd.Series({"A": 0.01, "B": 0.02})
    assert math.isnan(spearman_ic(s, r))


def test_compute_ic_series_skips_dates_without_returns():
    d1, d2 = pd.Timestamp("2024-01-05"), pd.Timestamp("2024-01-12")
    scores = {
        d1: pd.Series({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0}),
        d2: pd.Series({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0}),
    }
    returns = {
        d1: pd.Series({"A": 0.01, "B": 0.02, "C": 0.03, "D": 0.04, "E": 0.05}),
        # d2 missing
    }
    ic = compute_ic_series(scores, returns)
    assert len(ic) == 1
    assert ic.loc[d1] == pytest.approx(1.0)


def test_summarize_ic_basic():
    ic = pd.Series([0.05, 0.02, -0.01, 0.04, 0.03])
    summary = summarize_ic(ic)
    assert summary["n"] == 5
    assert summary["mean"] == pytest.approx(0.026)
    assert summary["hit_rate"] == 0.8
    assert summary["ir"] > 0


def test_summarize_ic_empty():
    summary = summarize_ic(pd.Series(dtype="float64"))
    assert summary["n"] == 0
    assert summary["mean"] == 0.0
    assert summary["hit_rate"] == 0.0
