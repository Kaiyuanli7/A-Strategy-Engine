"""Factor decay: IC at multiple forward horizons reveals the holding-period sweet spot."""

from __future__ import annotations

import pandas as pd

from astrategy.evaluation.ic import compute_ic_series, summarize_ic


DEFAULT_HORIZONS = (1, 5, 10, 20, 40, 60)


def compute_decay_curve(
    scores_by_date: dict[pd.Timestamp, pd.Series],
    forward_returns_by_horizon: dict[int, dict[pd.Timestamp, pd.Series]],
) -> pd.DataFrame:
    """
    Build an `IC at horizon h` curve.

    `forward_returns_by_horizon[h]` is the same shape as `scores_by_date`:
    {date -> Series indexed by code}.

    Returns DataFrame with columns: horizon, ic_mean, ic_ir, hit_rate, n.
    """
    rows = []
    for h in sorted(forward_returns_by_horizon.keys()):
        ic_series = compute_ic_series(scores_by_date, forward_returns_by_horizon[h])
        s = summarize_ic(ic_series)
        rows.append({
            "horizon": int(h),
            "ic_mean": float(s["mean"]),
            "ic_ir": float(s["ir"]),
            "hit_rate": float(s["hit_rate"]),
            "n": int(s["n"]),
        })
    return pd.DataFrame(rows, columns=["horizon", "ic_mean", "ic_ir", "hit_rate", "n"])
