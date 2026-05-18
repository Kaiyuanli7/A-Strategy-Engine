"""Valuation Composite factor (2.4)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from astrategy.data.cache import SQLiteCache
from astrategy.factors.base import FactorContext
from astrategy.factors.fundamental import ValuationCompositeFactor


def _seed_valuation_history(
    cache: SQLiteCache, code: str,
    pe_series: list[float], pb_series: list[float] | None = None, ps_series: list[float] | None = None,
):
    """Plant a daily valuation history."""
    n = len(pe_series)
    dates = pd.date_range("2022-01-03", periods=n, freq="B").strftime("%Y-%m-%d")
    cache.upsert_valuation_daily(code, pd.DataFrame({
        "date": dates,
        "pe_ttm": pe_series,
        "pb": pb_series if pb_series is not None else pe_series,
        "ps_ttm": ps_series if ps_series is not None else [v * 0.25 for v in pe_series],
        "mkt_cap": [1.0e10] * n,
        "float_cap": [7.0e9] * n,
    }))


def test_factor_registered():
    from astrategy.factors import get_factor
    assert get_factor("valuation_composite") is ValuationCompositeFactor


def test_default_history_days():
    f = ValuationCompositeFactor()
    assert f.params["history_days"] == 756


def test_low_percentile_scores_higher_than_high_percentile(tmp_path):
    """CHEAP has latest value at the bottom of its history → high score.
    EXPENSIVE has latest value at the top → low score."""
    cache = SQLiteCache(db_path=str(tmp_path / "rank.db"))
    # 100 days where PE walks from 30 down to 11; latest = 11 (very cheap)
    cheap = list(np.linspace(30.0, 11.0, 100))
    # 100 days where PE walks from 10 up to 30; latest = 30 (very expensive)
    expensive = list(np.linspace(10.0, 30.0, 100))
    _seed_valuation_history(cache, "CHEAP", cheap)
    _seed_valuation_history(cache, "EXPENSIVE", expensive)

    f = ValuationCompositeFactor(history_days=200)
    # `as_of` must be after the last seeded date (2022-01-03 + 99 bdays ≈ 2022-05-23)
    ctx = FactorContext(
        cache=cache, universe=["CHEAP", "EXPENSIVE"],
        as_of=pd.Timestamp("2022-06-01"),
    )
    scores = f.compute(ctx)
    assert scores["CHEAP"] > scores["EXPENSIVE"]
    # Cheap stock should be at very low percentile → score near -0
    assert scores["CHEAP"] > -0.1
    # Expensive stock should be at very high percentile → score near -1
    assert scores["EXPENSIVE"] < -0.85


def test_abstains_with_short_history(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "short.db"))
    _seed_valuation_history(cache, "SHORT", [15.0] * 5)  # too few rows
    f = ValuationCompositeFactor(history_days=200)
    ctx = FactorContext(cache=cache, universe=["SHORT"], as_of=pd.Timestamp("2022-06-01"))
    assert f.compute(ctx).empty


def test_pit_excludes_as_of(tmp_path):
    """An extreme valuation row landing AT as_of must not change the score."""
    cache = SQLiteCache(db_path=str(tmp_path / "pit.db"))
    pe = list(np.linspace(10.0, 30.0, 100))
    _seed_valuation_history(cache, "P", pe)

    f = ValuationCompositeFactor(history_days=300)
    ctx = FactorContext(cache=cache, universe=["P"], as_of=pd.Timestamp("2022-06-01"))
    s_before = f.compute(ctx)["P"]

    # Plant an extreme value at as_of: must not influence the score (date < as_of).
    cache.upsert_valuation_daily("P", pd.DataFrame({
        "date": ["2022-06-01"], "pe_ttm": [9999.0], "pb": [9999.0],
        "ps_ttm": [9999.0], "mkt_cap": [1.0e10], "float_cap": [7.0e9],
    }))
    s_after = f.compute(ctx)["P"]
    assert s_before == s_after


def test_skips_metric_with_too_few_observations(tmp_path):
    """If one of the three metrics has fewer than 20 observations, just skip
    that metric in the composite — don't abstain entirely."""
    cache = SQLiteCache(db_path=str(tmp_path / "miss.db"))
    n = 100
    dates = pd.date_range("2022-01-03", periods=n, freq="B").strftime("%Y-%m-%d")
    # PE has full history; PB is mostly NaN
    cache.upsert_valuation_daily("P", pd.DataFrame({
        "date": dates,
        "pe_ttm": list(np.linspace(10.0, 30.0, n)),
        "pb": [np.nan] * 90 + list(range(10)),  # only 10 non-NaN values
        "ps_ttm": list(np.linspace(2.0, 6.0, n)),
        "mkt_cap": [1.0e10] * n,
        "float_cap": [7.0e9] * n,
    }))
    f = ValuationCompositeFactor(history_days=300)
    ctx = FactorContext(cache=cache, universe=["P"], as_of=pd.Timestamp("2022-06-01"))
    scores = f.compute(ctx)
    # Should produce a score (PE + PS only); PB skipped due to short history.
    assert "P" in scores
    assert not pd.isna(scores["P"])
