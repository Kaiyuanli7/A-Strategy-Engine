"""Tests for factor attribution."""

import numpy as np
import pandas as pd
import pytest

from astrategy.engine.attribution import attribute_returns


def test_attribute_empty_returns_none():
    result = attribute_returns(pd.Series(dtype=float), pd.DataFrame())
    assert result is None


def test_pure_market_portfolio_recovers_unit_beta():
    """If strategy_returns == mkt_returns, OLS should give beta_mkt ≈ 1, alpha ≈ 0."""
    rng = np.random.default_rng(42)
    n = 252
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    mkt = pd.Series(rng.normal(0.0005, 0.01, n), index=idx)
    val = pd.Series(rng.normal(0.0001, 0.005, n), index=idx)
    factors = pd.DataFrame({"mkt": mkt, "val": val})
    strategy = mkt.copy()

    result = attribute_returns(strategy, factors)
    assert result is not None
    assert abs(result.loadings["mkt"] - 1.0) < 0.05
    assert abs(result.loadings["val"]) < 0.10
    assert abs(result.alpha_daily) < 1e-3


def test_pure_alpha_no_factor_exposure():
    """If strategy = constant alpha + iid noise unrelated to factors, alpha > 0, loadings ~0."""
    rng = np.random.default_rng(7)
    n = 252
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    mkt = pd.Series(rng.normal(0.0005, 0.012, n), index=idx)
    val = pd.Series(rng.normal(0.0001, 0.008, n), index=idx)
    factors = pd.DataFrame({"mkt": mkt, "val": val})
    strategy = pd.Series(0.001 + rng.normal(0, 0.001, n), index=idx)  # constant alpha + noise

    result = attribute_returns(strategy, factors)
    assert result is not None
    assert result.alpha_daily > 0
    assert abs(result.alpha_daily - 0.001) < 5e-4
    assert abs(result.loadings["mkt"]) < 0.5
    assert abs(result.loadings["val"]) < 0.5


def test_r_squared_high_for_collinear_returns():
    rng = np.random.default_rng(11)
    n = 252
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    mkt = pd.Series(rng.normal(0, 0.01, n), index=idx)
    factors = pd.DataFrame({"mkt": mkt})
    # Strategy is 1.5x market + a tiny bit of noise
    strategy = 1.5 * mkt + pd.Series(rng.normal(0, 1e-5, n), index=idx)
    result = attribute_returns(strategy, factors)
    assert result is not None
    assert result.r_squared > 0.99
    assert abs(result.loadings["mkt"] - 1.5) < 0.02


def test_insufficient_obs_returns_none():
    idx = pd.date_range("2023-01-01", periods=20, freq="B")
    s = pd.Series([0.001] * 20, index=idx)
    f = pd.DataFrame({"mkt": pd.Series([0.001] * 20, index=idx)})
    result = attribute_returns(s, f)
    assert result is None
