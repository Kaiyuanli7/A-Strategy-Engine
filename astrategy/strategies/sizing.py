"""Position sizing methods for ComposableStrategy."""

from __future__ import annotations

from dataclasses import dataclass

from astrategy.engine.constraints import round_to_lot


@dataclass
class SizingContext:
    equity: float
    close: float
    realized_vol: float | None = None  # annualized, e.g. 0.30


def equal_weight(ctx: SizingContext, position_size_pct: float) -> int:
    """Target `position_size_pct` of equity per name, lot-rounded down."""
    if ctx.close <= 0:
        return 0
    target_notional = ctx.equity * position_size_pct
    raw_shares = target_notional // ctx.close
    return round_to_lot(int(raw_shares))


def fixed_amount(ctx: SizingContext, amount: float) -> int:
    """Buy `amount` yuan worth, lot-rounded down."""
    if ctx.close <= 0:
        return 0
    raw_shares = amount // ctx.close
    return round_to_lot(int(raw_shares))


def vol_adjusted(
    ctx: SizingContext, target_vol_pct: float, position_size_pct: float
) -> int:
    """
    Scale equal-weight down when realized volatility exceeds `target_vol_pct`.
    Falls back to equal_weight when realized_vol is None/0 (e.g. warmup).
    """
    if ctx.realized_vol is None or ctx.realized_vol <= 0:
        return equal_weight(ctx, position_size_pct)
    weight = min(1.0, target_vol_pct / ctx.realized_vol) * position_size_pct
    return equal_weight(SizingContext(ctx.equity, ctx.close, None), weight)


def size(method: str, ctx: SizingContext, params: dict) -> int:
    """Top-level dispatcher used by ComposableStrategy."""
    if method == "equal_weight":
        return equal_weight(ctx, float(params.get("position_size_pct", 0.05)))
    if method == "fixed_amount":
        return fixed_amount(ctx, float(params.get("amount", 50_000.0)))
    if method == "vol_adjusted":
        return vol_adjusted(
            ctx,
            float(params.get("target_vol_pct", 0.20)),
            float(params.get("position_size_pct", 0.05)),
        )
    raise ValueError(f"unknown sizing method: {method}")
