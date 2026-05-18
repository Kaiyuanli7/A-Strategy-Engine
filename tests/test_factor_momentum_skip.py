"""Momentum Skip-5 factor (3.2)."""

from __future__ import annotations

import pandas as pd

from astrategy.data.cache import SQLiteCache
from astrategy.factors.base import FactorContext
from astrategy.factors.technical import MomentumSkipFactor


def _seed_bars(cache: SQLiteCache, code: str, closes: list[float], start: str = "2024-01-02"):
    dates = pd.bdate_range(start=start, periods=len(closes)).strftime("%Y-%m-%d")
    df = pd.DataFrame({
        "date": dates,
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": [1e6] * len(closes),
    })
    cache.upsert_daily_bars(code, df)


def test_factor_registered():
    from astrategy.factors import get_factor
    assert get_factor("momentum_skip") is MomentumSkipFactor


def test_default_params():
    f = MomentumSkipFactor()
    assert f.params["lookback"] == 20
    assert f.params["skip"] == 5


def test_score_matches_formula(tmp_path):
    """Score on day t = close[t-skip-1] / close[t-skip-lookback-1] - 1."""
    cache = SQLiteCache(db_path=str(tmp_path / "t.db"))
    # 30 trading days of closes from 100 to 129 (linear ramp = +0.29 over the full range)
    closes = [100.0 + i for i in range(30)]
    _seed_bars(cache, "UP", closes)

    # as_of placed after the last bar; the bar series is strictly < as_of.
    as_of = pd.Timestamp("2024-02-16")  # one bday after 30th synthetic day
    f = MomentumSkipFactor(lookback=20, skip=5)
    ctx = FactorContext(cache=cache, universe=["UP"], as_of=as_of)
    scores = f.compute(ctx)
    # closes[-(5+1)] / closes[-(5+20+1)] - 1 = closes[24] / closes[4] - 1
    expected = closes[24] / closes[4] - 1.0
    assert abs(scores["UP"] - expected) < 1e-9


def test_higher_momentum_higher_score(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "rank.db"))
    _seed_bars(cache, "UP", [100.0 + i for i in range(40)])      # strong ramp
    _seed_bars(cache, "FLAT", [100.0 for _ in range(40)])         # no return
    _seed_bars(cache, "DOWN", [100.0 - i * 0.5 for i in range(40)])  # mild decay
    f = MomentumSkipFactor(lookback=20, skip=5)
    ctx = FactorContext(
        cache=cache, universe=["UP", "FLAT", "DOWN"],
        as_of=pd.Timestamp("2024-03-02"),
    )
    scores = f.compute(ctx)
    assert scores["UP"] > scores["FLAT"] > scores["DOWN"]


def test_abstains_with_insufficient_history(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "short.db"))
    _seed_bars(cache, "SHORT", [100.0 + i for i in range(10)])  # only 10 bars
    f = MomentumSkipFactor(lookback=20, skip=5)
    ctx = FactorContext(cache=cache, universe=["SHORT"], as_of=pd.Timestamp("2024-02-01"))
    scores = f.compute(ctx)
    assert scores.empty


def test_pit_does_not_peek_at_as_of(tmp_path):
    """If we set the closing price of as_of itself to a wildly different value,
    the score must not change — the factor strictly looks before as_of."""
    cache = SQLiteCache(db_path=str(tmp_path / "pit.db"))
    closes = [100.0 + i for i in range(30)]
    _seed_bars(cache, "X", closes)
    f = MomentumSkipFactor(lookback=20, skip=5)
    as_of = pd.Timestamp("2024-02-16")
    ctx = FactorContext(cache=cache, universe=["X"], as_of=as_of)
    s_before = f.compute(ctx)["X"]

    # Now insert a bar AT as_of with an extreme price — score must be unchanged.
    cache.upsert_daily_bars("X", pd.DataFrame({
        "date": ["2024-02-16"],
        "open": [9999.0], "high": [9999.0], "low": [9999.0], "close": [9999.0],
        "volume": [1e6],
    }))
    s_after = f.compute(ctx)["X"]
    assert s_before == s_after
