"""Transaction cost models for A-share trades."""

from __future__ import annotations

from astrategy.config import COMMISSION_MIN, COMMISSION_RATE, STAMP_TAX_SELL, TRANSFER_FEE


def buy_cost(notional: float) -> float:
    """Commission (with ¥5 floor) + transfer fee on buy notional."""
    commission = max(notional * COMMISSION_RATE, COMMISSION_MIN)
    transfer = notional * TRANSFER_FEE
    return commission + transfer


def sell_cost(notional: float) -> float:
    """Buy-side costs + stamp tax (0.05%) on sell notional."""
    return buy_cost(notional) + notional * STAMP_TAX_SELL
