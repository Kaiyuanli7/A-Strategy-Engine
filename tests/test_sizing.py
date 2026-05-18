"""Tests for position sizing methods."""

import pytest

from astrategy.strategies.sizing import (
    SizingContext,
    equal_weight,
    fixed_amount,
    size,
    vol_adjusted,
)


def test_equal_weight_lot_rounds():
    ctx = SizingContext(equity=1_000_000.0, close=50.0)
    # 5% target = ¥50,000 → 1000 shares exactly
    assert equal_weight(ctx, 0.05) == 1000


def test_equal_weight_lot_rounds_down():
    ctx = SizingContext(equity=1_000_000.0, close=55.0)
    # 5% target = ¥50,000 → 909 shares → floor to 900 lots
    assert equal_weight(ctx, 0.05) == 900


def test_equal_weight_zero_close():
    ctx = SizingContext(equity=1_000_000.0, close=0.0)
    assert equal_weight(ctx, 0.05) == 0


def test_fixed_amount():
    ctx = SizingContext(equity=1_000_000.0, close=10.0)
    # ¥5000 / ¥10 = 500 shares (already lot multiple)
    assert fixed_amount(ctx, 5000.0) == 500


def test_vol_adjusted_falls_back_to_equal_when_no_vol():
    ctx = SizingContext(equity=1_000_000.0, close=50.0, realized_vol=None)
    # Should match equal_weight at 5%
    assert vol_adjusted(ctx, 0.20, 0.05) == equal_weight(ctx, 0.05)


def test_vol_adjusted_scales_down_high_vol():
    """Realized vol 40% with target 20% → weight = 0.5 × 0.05 = 0.025."""
    ctx = SizingContext(equity=1_000_000.0, close=50.0, realized_vol=0.40)
    # 2.5% of 1M = 25k → 500 shares
    assert vol_adjusted(ctx, 0.20, 0.05) == 500


def test_vol_adjusted_caps_at_full_size_low_vol():
    """Realized vol 10% with target 20% → weight capped at 0.05 (min(1, 2) * 0.05)."""
    ctx = SizingContext(equity=1_000_000.0, close=50.0, realized_vol=0.10)
    assert vol_adjusted(ctx, 0.20, 0.05) == 1000  # full 5%


def test_size_dispatcher():
    ctx = SizingContext(equity=1_000_000.0, close=50.0)
    assert size("equal_weight", ctx, {"position_size_pct": 0.05}) == 1000
    assert size("fixed_amount", ctx, {"amount": 25_000.0}) == 500
    with pytest.raises(ValueError):
        size("nonexistent", ctx, {})
