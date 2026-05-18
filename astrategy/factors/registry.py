"""Name -> Factor class registry."""

from __future__ import annotations

from typing import Type

from astrategy.factors.base import Factor


_REGISTRY: dict[str, Type[Factor]] = {}


def register_factor(cls: Type[Factor]) -> Type[Factor]:
    """Class decorator: register `cls` in the global factor map by its `name`."""
    if not issubclass(cls, Factor):
        raise TypeError(f"{cls} is not a Factor subclass")
    if cls.name == "unnamed" or not cls.name:
        raise ValueError(f"{cls} must set class attribute `name`")
    if cls.name in _REGISTRY:
        raise ValueError(f"factor name collision: '{cls.name}' already registered")
    _REGISTRY[cls.name] = cls
    return cls


def get_factor(name: str) -> Type[Factor] | None:
    return _REGISTRY.get(name)


def list_factors() -> list[str]:
    return sorted(_REGISTRY)


def clear_registry_for_tests() -> None:
    """Test-only helper."""
    _REGISTRY.clear()
