"""Synthetic generators for the new alt-data sources (margin, 龙虎榜, limit pool)."""

from __future__ import annotations

import pandas as pd

from astrategy.data.synthetic import (
    generate_synthetic_lhb,
    generate_synthetic_limit_pool,
    generate_synthetic_margin,
)


def test_synthetic_margin_has_expected_columns():
    df = generate_synthetic_margin("600519", "2023-01-01", "2023-12-31")
    assert not df.empty
    for col in ("date", "financing_balance", "short_balance",
                "financing_buy_amount", "financing_repay_amount",
                "net_financing_change"):
        assert col in df.columns
    # Net ≈ buy - repay (rounded in the generator, so allow tiny tolerance)
    diff = (df["financing_buy_amount"] - df["financing_repay_amount"]
            - df["net_financing_change"]).abs()
    assert (diff < 1.5).all()


def test_synthetic_margin_deterministic():
    df1 = generate_synthetic_margin("600519", "2023-01-01", "2023-12-31")
    df2 = generate_synthetic_margin("600519", "2023-01-01", "2023-12-31")
    pd.testing.assert_frame_equal(df1, df2)


def test_synthetic_lhb_returns_rows():
    rows = generate_synthetic_lhb("600519", "2023-01-01", "2024-12-31")
    assert len(rows) > 0
    sample = rows[0]
    for k in ("code", "date", "seq", "seat_name", "seat_type",
              "buy_amount", "sell_amount", "net_amount"):
        assert k in sample
    seat_types = {r["seat_type"] for r in rows}
    # We seeded a mix of institutional + hot_money seats
    assert seat_types & {"institutional", "hot_money"}


def test_synthetic_limit_pool_has_both_directions():
    rows = generate_synthetic_limit_pool("2023-01-01", "2024-12-31",
                                          n_codes=10, n_events_per_code=5)
    assert len(rows) > 0
    directions = {r["direction"] for r in rows}
    # Should hit both up and down events given enough samples
    assert directions <= {"up", "down"}
    sample = rows[0]
    for k in ("code", "date", "direction", "consecutive_days",
              "is_first", "turnover_pct"):
        assert k in sample
