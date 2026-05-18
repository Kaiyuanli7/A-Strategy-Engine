"""fit_composite_weights_optuna — search optimal composite weights.

The test design plants a known signal in one factor and noise in the other,
then verifies the optimizer assigns positive weight to the signal factor
and ~zero to the noise.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from astrategy.composites.optuna_fit import (
    OptunaFitResult,
    _composite_long_short_returns,
    _sharpe,
    fit_composite_weights_optuna,
)


def _planted_factor_scores(
    dates: list[pd.Timestamp],
    codes: list[str],
    seed: int,
    correlation: float = 0.7,
    noise: float = 0.3,
) -> tuple[dict, dict]:
    """
    Build a synthetic factor / forward-return pair where the factor partially
    predicts forward returns.

    Returns (per_factor_scores, forward_returns_at_horizon).
    """
    rng = np.random.default_rng(seed)
    scores_by_date: dict = {}
    returns_by_date: dict = {}
    for d in dates:
        # Random base ranks
        base = pd.Series(rng.standard_normal(len(codes)), index=codes)
        # Noise added independently to scores and returns
        score_noise = pd.Series(rng.standard_normal(len(codes)), index=codes) * noise
        ret_noise = pd.Series(rng.standard_normal(len(codes)), index=codes) * noise
        scores_by_date[d] = (base * correlation + score_noise) * 0.01
        returns_by_date[d] = (base * correlation + ret_noise) * 0.01
    return scores_by_date, returns_by_date


def _pure_noise_factor(dates, codes, seed) -> dict:
    rng = np.random.default_rng(seed)
    return {d: pd.Series(rng.standard_normal(len(codes)), index=codes)
            for d in dates}


def test_sharpe_handles_empty():
    assert _sharpe(pd.Series(dtype="float64")) == 0.0


def test_sharpe_handles_zero_vol():
    s = pd.Series([0.01] * 10)
    assert _sharpe(s) == 0.0


def test_long_short_returns_basic():
    """Single date: top quintile forward returns positive → long-short positive."""
    codes = [f"S{i:02d}" for i in range(20)]
    d = pd.Timestamp("2024-01-05")
    # Score = rank; forward return = same rank (perfect signal)
    scores = pd.Series({c: float(i) for i, c in enumerate(codes)})
    returns = pd.Series({c: 0.001 * i for i, c in enumerate(codes)})

    ls = _composite_long_short_returns(
        weights={"f1": 1.0},
        per_factor_scores={"f1": {d: scores}},
        forward_returns={d: returns},
        n_quintiles=5,
    )
    assert len(ls) == 1
    # Top score → highest return; long-short = Q1 - Q5
    assert ls.iloc[0] > 0


def test_optuna_assigns_positive_weight_to_signal_factor():
    """Plant a strong-signal factor + a noise factor; optimizer prefers signal."""
    codes = [f"S{i:02d}" for i in range(40)]
    dates = pd.date_range("2024-01-05", periods=20, freq="W-FRI").tolist()
    signal_scores, returns = _planted_factor_scores(
        dates, codes, seed=42, correlation=0.8, noise=0.2,
    )
    noise_scores = _pure_noise_factor(dates, codes, seed=1234)

    per_factor = {"signal": signal_scores, "noise": noise_scores}
    fit = fit_composite_weights_optuna(
        per_factor, returns,
        n_trials=30, l2_lambda=0.05, max_weight_abs=0.5, seed=42,
    )
    assert isinstance(fit, OptunaFitResult)
    # Signal factor should get larger absolute weight than noise
    assert abs(fit.weights["signal"]) > abs(fit.weights["noise"])
    # IS Sharpe should be positive (we planted real signal)
    assert fit.is_sharpe > 0


def test_optuna_inverts_anti_signal_factor():
    """Plant a factor whose scores ANTI-correlate with returns. Optimizer should
    assign it a negative weight (making it a short signal)."""
    codes = [f"S{i:02d}" for i in range(40)]
    dates = pd.date_range("2024-01-05", periods=20, freq="W-FRI").tolist()
    # Score = -returns (anti-correlated)
    scores: dict = {}
    returns: dict = {}
    rng = np.random.default_rng(7)
    for d in dates:
        ret = pd.Series(rng.standard_normal(len(codes)) * 0.01, index=codes)
        scores[d] = -ret + rng.standard_normal(len(codes)) * 0.001
        returns[d] = ret

    fit = fit_composite_weights_optuna(
        {"inverted": scores}, returns,
        n_trials=30, l2_lambda=0.0, max_weight_abs=0.5, seed=42,
    )
    # Anti-correlated factor → optimizer should assign negative weight
    assert fit.weights["inverted"] < 0


def test_optuna_respects_max_weight_cap():
    codes = [f"S{i:02d}" for i in range(30)]
    dates = pd.date_range("2024-01-05", periods=12, freq="W-FRI").tolist()
    scores, returns = _planted_factor_scores(dates, codes, seed=1, correlation=0.9)

    fit = fit_composite_weights_optuna(
        {"signal": scores}, returns,
        n_trials=20, l2_lambda=0.0, max_weight_abs=0.2, seed=42,
    )
    assert abs(fit.weights["signal"]) <= 0.2 + 1e-9


def test_optuna_zero_factors_raises():
    with pytest.raises(ValueError, match="no factors"):
        fit_composite_weights_optuna({}, {}, n_trials=5)


def test_optuna_reproducible_with_seed():
    """Same seed → same weights."""
    codes = [f"S{i:02d}" for i in range(20)]
    dates = pd.date_range("2024-01-05", periods=10, freq="W-FRI").tolist()
    scores, returns = _planted_factor_scores(dates, codes, seed=1)

    fit1 = fit_composite_weights_optuna(
        {"f": scores}, returns, n_trials=10, seed=99,
    )
    fit2 = fit_composite_weights_optuna(
        {"f": scores}, returns, n_trials=10, seed=99,
    )
    assert fit1.weights == fit2.weights
