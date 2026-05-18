"""Construct Strategy instances from JSON-style config dicts."""

from __future__ import annotations

from typing import Callable

from astrategy.strategies.base import Strategy
from astrategy.strategies.composable import ComposableStrategy
from astrategy.strategies.ma_cross import DualMACrossStrategy


_REGISTRY: dict[str, Callable[..., Strategy]] = {
    "ma_cross": DualMACrossStrategy,
    "composable": ComposableStrategy,
}


def create_strategy(type_: str, params: dict | None = None) -> Strategy:
    if type_ not in _REGISTRY:
        raise ValueError(f"unknown strategy type {type_!r}; available: {list(_REGISTRY)}")
    cls = _REGISTRY[type_]
    return cls(**(params or {}))


def registered_types() -> list[str]:
    return sorted(_REGISTRY.keys())
