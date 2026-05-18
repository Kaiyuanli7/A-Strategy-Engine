"""Fit composite weights via Optuna with walk-forward discipline in mind.

This module solves the "what weights should the composite use?" problem:

    weights = fit_composite_weights_optuna(
        per_factor_scores,        # IS data only
        forward_returns,          # IS forward returns at the chosen horizon
        n_trials=100,
        l2_lambda=0.5,
        max_weight_abs=0.35,
    )

The optimizer searches the per-factor weight vector that maximizes the
in-sample long-short Sharpe of the composite. The L2 regularization pulls
weights toward equal-weight (1/N) and the per-factor cap (default 0.35
per CLAUDE.md §3 rule 4 anti-overconcentration) hard-bounds each weight.

A walk-forward harness that calls this on each IS window, builds a
`FixedWeightComposite` with the fitted weights, then runs the OOS window
through `TopNRankerStrategy` gives you the rigorous "weights generalize
out-of-sample?" answer required by CLAUDE.md §3 hard rule #2.

We work with PRE-COMPUTED factor scores rather than re-running factor
compute() inside every optuna trial — that would be O(trials × dates ×
universe). Pre-computing once and iterating numerically is fast enough
for ~100 trials × 250 rebalances × 300 stocks.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
import optuna
import pandas as pd

from astrategy.composites.base import zscore_cross_section

log = logging.getLogger(__name__)


@dataclass
class OptunaFitResult:
    weights: dict[str, float]
    is_sharpe: float          # IS long-short Sharpe of the optimal weights
    n_trials: int
    best_trial_idx: int


def _composite_long_short_returns(
    weights: dict[str, float],
    per_factor_scores: dict[str, dict[pd.Timestamp, pd.Series]],
    forward_returns: dict[pd.Timestamp, pd.Series],
    n_quintiles: int = 5,
) -> pd.Series:
    """
    Per-rebalance long-short return of a composite with given weights.

    For each rebalance date:
      1. Combine z-scored factor scores via weights → composite scores.
      2. Sort into n_quintiles buckets; top quintile = Q1, bottom = Q_n.
      3. Long-short = mean forward return of Q1 - mean of Q_n.
    Returns a Series indexed by date.
    """
    dates = sorted(forward_returns.keys())
    ls_per_date: dict[pd.Timestamp, float] = {}

    for d in dates:
        fwd = forward_returns.get(d)
        if fwd is None or fwd.empty:
            continue
        # Per-factor z-scored series at this date
        z_per_factor: dict[str, pd.Series] = {}
        for name, scores_map in per_factor_scores.items():
            raw = scores_map.get(d)
            if raw is None or raw.empty:
                continue
            z_per_factor[name] = zscore_cross_section(raw)
        if not z_per_factor:
            continue

        # Weighted sum (NaN ↦ 0 contribution)
        combined = pd.DataFrame(z_per_factor).fillna(0.0)
        weight_vec = pd.Series(weights).reindex(combined.columns).fillna(0.0)
        composite = combined.dot(weight_vec)

        # Align with forward returns
        joined = pd.concat(
            [composite.rename("score"), fwd.rename("ret")], axis=1
        ).dropna()
        if len(joined) < n_quintiles * 2:
            continue

        # qcut highest score → bucket 0; we want Q1 at the top
        try:
            buckets = pd.qcut(-joined["score"], q=n_quintiles, labels=False, duplicates="drop")
        except ValueError:
            continue
        buckets = buckets.dropna().astype(int) + 1
        joined = joined.assign(bucket=buckets).dropna()
        if joined.empty:
            continue
        q1 = joined.loc[joined["bucket"] == 1, "ret"].mean()
        qn = joined.loc[joined["bucket"] == n_quintiles, "ret"].mean()
        if pd.isna(q1) or pd.isna(qn):
            continue
        ls_per_date[d] = float(q1) - float(qn)

    if not ls_per_date:
        return pd.Series(dtype="float64")
    return pd.Series(ls_per_date).sort_index()


def _sharpe(ls: pd.Series) -> float:
    if len(ls) < 2:
        return 0.0
    mu = ls.mean()
    sigma = ls.std(ddof=1)
    # Treat near-zero σ as zero — protects against float-precision artifacts on
    # constant inputs where pd.Series.std() can return ~1e-17 instead of exact 0.
    if not np.isfinite(sigma) or abs(sigma) < 1e-12:
        return 0.0
    return float(mu / sigma)


def fit_composite_weights_optuna(
    per_factor_scores: dict[str, dict[pd.Timestamp, pd.Series]],
    forward_returns: dict[pd.Timestamp, pd.Series],
    n_trials: int = 100,
    l2_lambda: float = 0.5,
    max_weight_abs: float = 0.35,
    n_quintiles: int = 5,
    seed: int = 42,
) -> OptunaFitResult:
    """
    Search per-factor weights that maximize IS long-short Sharpe with an L2
    penalty toward equal weights.

    Parameters
    ----------
    per_factor_scores:
        {factor_name: {rebalance_date: pd.Series[code -> score]}}
    forward_returns:
        {rebalance_date: pd.Series[code -> forward return]}
    n_trials:
        Optuna trial budget.
    l2_lambda:
        Strength of the L2 penalty (||w - 1/N||₂²) pulling weights toward
        equal-weight. Higher = less overfitting.
    max_weight_abs:
        Hard per-factor cap. Default 0.35 per CLAUDE.md §3 hard rule 4
        (no single factor dominates the composite).
    n_quintiles:
        Quintile bucket count for the long-short objective.

    Returns
    -------
    OptunaFitResult with the fitted weights, IS Sharpe at those weights, and
    bookkeeping.
    """
    factor_names = sorted(per_factor_scores.keys())
    n = len(factor_names)
    if n == 0:
        raise ValueError("fit_composite_weights_optuna: no factors supplied")
    equal_weight = 1.0 / n

    def objective(trial: optuna.Trial) -> float:
        weights = {
            name: trial.suggest_float(name, -max_weight_abs, max_weight_abs)
            for name in factor_names
        }
        ls = _composite_long_short_returns(
            weights, per_factor_scores, forward_returns,
            n_quintiles=n_quintiles,
        )
        sharpe = _sharpe(ls)
        # L2 penalty toward equal-weight
        l2 = sum((w - equal_weight) ** 2 for w in weights.values())
        # Maximize: sharpe minus penalty
        return sharpe - l2_lambda * l2

    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    # Silence Optuna's INFO logging in tests / scripts unless explicitly enabled.
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best = study.best_trial
    fitted = {name: float(best.params[name]) for name in factor_names}

    # Measure IS Sharpe at the fitted weights (without the L2 penalty)
    ls_at_best = _composite_long_short_returns(
        fitted, per_factor_scores, forward_returns, n_quintiles=n_quintiles
    )
    is_sharpe = _sharpe(ls_at_best)

    log.info(
        "Optuna fit: best weights=%s, IS LS Sharpe=%.3f (n_trials=%d, λ=%.2f)",
        {k: round(v, 4) for k, v in fitted.items()},
        is_sharpe, n_trials, l2_lambda,
    )
    return OptunaFitResult(
        weights=fitted, is_sharpe=is_sharpe, n_trials=n_trials,
        best_trial_idx=best.number,
    )
