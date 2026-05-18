"""Factor decay curve tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from astrategy.evaluation.decay import compute_decay_curve


def test_decay_curve_includes_each_horizon():
    np.random.seed(7)
    codes = [f"S{i:03d}" for i in range(40)]
    dates = [pd.Timestamp("2024-01-05"), pd.Timestamp("2024-01-12"), pd.Timestamp("2024-01-19")]
    scores_by_date = {d: pd.Series({c: float(i) for i, c in enumerate(codes)}) for d in dates}
    fwd = {
        1: {d: pd.Series({c: 0.001 * i for i, c in enumerate(codes)}) for d in dates},
        5: {d: pd.Series({c: 0.001 * i + 0.001 for i, c in enumerate(codes)}) for d in dates},
        20: {d: pd.Series({c: 0.001 * i + 0.005 for i, c in enumerate(codes)}) for d in dates},
    }
    df = compute_decay_curve(scores_by_date, fwd)
    assert list(df["horizon"]) == [1, 5, 20]
    # Perfect rank correlation → IC ~ 1.0 at every horizon
    assert (df["ic_mean"] > 0.9).all()
    assert (df["n"] == len(dates)).all()


def test_decay_curve_empty_horizons_returns_empty_frame():
    df = compute_decay_curve({}, {})
    assert df.empty
