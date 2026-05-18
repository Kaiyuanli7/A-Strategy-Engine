"""Factor ABC + registry + context contract tests."""

from __future__ import annotations

import pandas as pd
import pytest

from astrategy.data.cache import SQLiteCache
from astrategy.factors.base import Factor, FactorContext, FactorParamSpec
from astrategy.factors.registry import (
    _REGISTRY,
    get_factor,
    list_factors,
    register_factor,
)


class _NoopFactor(Factor):
    name = "_test_noop"
    category = "flow"
    description = "test"
    lookback_days = 5
    rebalance_freq = "weekly"
    _param_specs = [FactorParamSpec(name="alpha", type="float", default=1.5)]

    def compute(self, ctx):
        return pd.Series({"AAA": float(self.params["alpha"])})


def test_factor_subclass_must_set_name():
    class Bad(Factor):
        # no name
        def compute(self, ctx):
            return pd.Series()
    with pytest.raises(ValueError):
        register_factor(Bad)


def test_register_and_get():
    _REGISTRY.pop("_test_noop", None)
    register_factor(_NoopFactor)
    assert "_test_noop" in list_factors()
    assert get_factor("_test_noop") is _NoopFactor


def test_register_collision_raises():
    _REGISTRY.pop("_test_noop", None)
    register_factor(_NoopFactor)
    with pytest.raises(ValueError):
        register_factor(_NoopFactor)


def test_factor_applies_default_params():
    f = _NoopFactor()
    assert f.params["alpha"] == 1.5


def test_factor_overrides_param():
    f = _NoopFactor(alpha=3.14)
    assert f.params["alpha"] == 3.14


def test_factor_rejects_unknown_param():
    with pytest.raises(ValueError):
        _NoopFactor(beta=0.0)


def test_factor_context_as_of_str(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "t.db"))
    ctx = FactorContext(cache=cache, universe=["600519"], as_of=pd.Timestamp("2024-06-15"))
    assert ctx.as_of_str() == "2024-06-15"


def test_factor_context_pulls_pit_data_only(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "t.db"))
    # Insert a couple of northbound rows
    df = pd.DataFrame({
        "date": ["2024-06-10", "2024-06-15", "2024-06-20"],
        "holding_shares": [100, 110, 120],
        "holding_value": [1000, 1100, 1200],
        "holding_pct": [1.0, 1.1, 1.2],
        "net_buy_shares": [1, 2, 3],
        "net_buy_value": [100, 200, 300],
    })
    cache.upsert_northbound("600519", df)
    ctx = FactorContext(cache=cache, universe=["600519"], as_of=pd.Timestamp("2024-06-15"))
    nb = ctx.northbound("600519", lookback_days=30)
    # Strictly BEFORE as_of, so 2024-06-15 itself is excluded.
    assert (nb["date"] < pd.Timestamp("2024-06-15")).all()
    assert len(nb) == 1
