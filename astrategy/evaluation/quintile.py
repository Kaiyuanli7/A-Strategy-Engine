"""Quintile spread analysis: sort by factor, track forward returns per bucket."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats


def assign_quintiles(scores: pd.Series, n: int = 5) -> pd.Series:
    """
    Return integer bucket [1..n] per stock, where 1 = highest factor score (most
    bullish) and n = lowest.

    Stocks with tied scores get the same bucket via `pd.qcut(duplicates='drop')`.
    If too few unique scores exist, the function falls back to rank-based
    buckets so we don't crash on degenerate days.
    """
    s = scores.dropna()
    if s.empty:
        return pd.Series(dtype="int64")
    # Highest score → bucket 1. Use the negated scores so qcut's ascending
    # default puts the lowest of `-scores` (= highest scores) in bucket 0.
    try:
        buckets = pd.qcut(-s, q=n, labels=False, duplicates="drop")
    except ValueError:
        # All identical scores → everyone in middle bucket.
        return pd.Series(((n + 1) // 2), index=s.index, dtype="int64")
    if buckets.isna().all():
        # qcut collapsed everything (all-identical scores) → middle bucket.
        return pd.Series(((n + 1) // 2), index=s.index, dtype="int64")
    # qcut may collapse buckets when there are ties; renormalize to 1..k.
    buckets = buckets.fillna(((n + 1) // 2) - 1).astype(int) + 1
    return buckets


def compute_quintile_returns(
    scores_by_date: dict[pd.Timestamp, pd.Series],
    forward_returns_by_date: dict[pd.Timestamp, pd.Series],
    n: int = 5,
) -> pd.DataFrame:
    """
    Per rebalance date: bucket stocks into quintiles by factor score and
    compute the mean forward return per bucket.

    Returns DataFrame indexed by date with columns 'Q1'..'Qn' and 'long_short'
    (= Q1 - Qn). Missing buckets on a given date appear as NaN.
    """
    rows = []
    index = []
    cols = [f"Q{i}" for i in range(1, n + 1)]
    for date, scores in scores_by_date.items():
        fwd = forward_returns_by_date.get(date)
        if fwd is None or scores.empty:
            continue
        df = pd.concat([scores.rename("score"), fwd.rename("ret")], axis=1).dropna()
        if df.empty:
            continue
        df["bucket"] = assign_quintiles(df["score"], n=n)
        means = df.groupby("bucket")["ret"].mean()
        row = {f"Q{int(b)}": float(v) for b, v in means.items()}
        # Long-short = highest-score bucket (1) minus lowest (n)
        ls = float(means.get(1, np.nan) - means.get(n, np.nan))
        row["long_short"] = ls
        rows.append(row)
        index.append(date)

    if not rows:
        return pd.DataFrame(columns=cols + ["long_short"])
    df_out = pd.DataFrame(rows, index=pd.DatetimeIndex(index)).sort_index()
    # Ensure all quintile columns are present in stable order
    for c in cols:
        if c not in df_out.columns:
            df_out[c] = np.nan
    return df_out[cols + ["long_short"]]


def cumulative_quintile_returns(quintile_returns: pd.DataFrame) -> pd.DataFrame:
    """Compound per-period returns into a cumulative series per column."""
    if quintile_returns.empty:
        return quintile_returns.copy()
    return (1.0 + quintile_returns.fillna(0.0)).cumprod() - 1.0


def quintile_summary(quintile_returns: pd.DataFrame, n: int = 5) -> dict:
    """
    Aggregate stats:
        - long_short_mean / std / sharpe (per-period, no annualization)
        - long_short_total_return = compounded LS return
        - monotonicity = Spearman corr between bucket index (1..n) and mean per-bucket return
        - avg_turnover not computed here (see quintile_turnover)
    """
    if quintile_returns.empty:
        return {
            "long_short_mean": 0.0,
            "long_short_std": 0.0,
            "long_short_sharpe": 0.0,
            "long_short_total_return": 0.0,
            "monotonicity": 0.0,
            "avg_turnover": 0.0,
        }
    ls = quintile_returns["long_short"].dropna()
    ls_mean = float(ls.mean()) if not ls.empty else 0.0
    ls_std = float(ls.std(ddof=1)) if ls.size > 1 else 0.0
    ls_sharpe = ls_mean / ls_std if ls_std > 0 else 0.0
    ls_total = float((1.0 + ls.fillna(0.0)).prod() - 1.0)

    # Monotonicity: corr(bucket_idx, mean per-bucket return). Higher score
    # bucket should have higher mean return.
    cols = [f"Q{i}" for i in range(1, n + 1)]
    per_bucket_mean = quintile_returns[cols].mean()
    # We want bucket 1 (highest score) to deliver the highest return.
    # Plot mean return against "1 - bucket_idx" so a monotone signal
    # produces a positive monotonicity score.
    ordered_buckets = list(range(1, n + 1))
    # Want positive monotonicity for a useful long-only factor: higher score
    # → higher forward return. Use the descending bucket index so that a
    # better signal produces a more positive coefficient.
    ranks_desc = list(reversed(ordered_buckets))  # [n, n-1, ..., 1]
    valid = per_bucket_mean.dropna()
    if len(valid) < 2:
        mono = 0.0
    else:
        # Align: for each present bucket idx i, pair (n+1-i, mean)
        xs = [n + 1 - int(c.replace("Q", "")) for c in valid.index]
        ys = valid.values
        rho, _ = stats.spearmanr(xs, ys)
        mono = 0.0 if rho is None or math.isnan(rho) else float(rho)

    return {
        "long_short_mean": ls_mean,
        "long_short_std": ls_std,
        "long_short_sharpe": float(ls_sharpe),
        "long_short_total_return": ls_total,
        "monotonicity": mono,
        "avg_turnover": 0.0,  # filled in by caller via quintile_turnover
    }


def quintile_turnover(
    scores_by_date: dict[pd.Timestamp, pd.Series], n: int = 5,
) -> float:
    """
    Average fraction of stocks that change quintile between consecutive
    rebalance dates. 0.0 = perfectly stable; 1.0 = total churn.
    """
    dates = sorted(scores_by_date.keys())
    if len(dates) < 2:
        return 0.0
    prev_buckets: pd.Series | None = None
    churn_rates = []
    for d in dates:
        s = scores_by_date.get(d)
        if s is None or s.empty:
            continue
        b = assign_quintiles(s, n=n)
        if prev_buckets is not None:
            common = b.index.intersection(prev_buckets.index)
            if len(common) > 0:
                changed = (b.loc[common] != prev_buckets.loc[common]).sum()
                churn_rates.append(changed / len(common))
        prev_buckets = b
    if not churn_rates:
        return 0.0
    return float(np.mean(churn_rates))
