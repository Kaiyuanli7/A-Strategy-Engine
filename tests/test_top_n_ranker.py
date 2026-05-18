"""TopNRankerStrategy — composite-driven top-N portfolio rebalancing."""

from __future__ import annotations

import pandas as pd
import pytest

from astrategy.composites.base import FactorWeight
from astrategy.composites.equal_weight import EqualWeightComposite
from astrategy.data.cache import SQLiteCache
from astrategy.data.synthetic import generate_synthetic_ohlcv
from astrategy.engine.backtest import Backtester, BacktestConfig
from astrategy.engine.orders import OrderSide
from astrategy.engine.portfolio import Portfolio
from astrategy.factors.base import Factor, FactorContext
from astrategy.strategies.base import StrategyContext
from astrategy.strategies.top_n_ranker import TopNRankerStrategy, _rebalance_dates


# ---------------- Test factor that returns pinned scores keyed by as_of -----

class _MockFactor(Factor):
    name = "_mock_factor"
    category = "flow"
    description = "test"
    lookback_days = 1
    rebalance_freq = "weekly"
    _param_specs: list = []

    def __init__(self, scores_by_date: dict | None = None, constant: pd.Series | None = None):
        super().__init__()
        self._scores_by_date = scores_by_date or {}
        self._constant = constant

    def compute(self, ctx):
        if self._constant is not None:
            # Same scores every rebalance date
            return self._constant
        # Per-date scores keyed by as_of date
        return self._scores_by_date.get(ctx.as_of, pd.Series(dtype="float64"))


def _seed_universe(
    cache: SQLiteCache,
    codes: list[str],
    start: str = "2024-01-02",
    end: str = "2024-12-31",
    *,
    market_cap: float = 1.0e10,
    sectors: dict[str, str] | None = None,
    st_codes: set[str] | None = None,
) -> None:
    """Plant OHLCV, meta, valuation, sector rows for a synthetic universe."""
    sectors = sectors or {}
    st_codes = st_codes or set()
    for code in codes:
        df = generate_synthetic_ohlcv(code, start, end)
        cache.upsert_daily_bars(code, df)
        cache.upsert_stock_meta(code, code, "main_sh", code in st_codes)
        # Daily valuation: write a single row near the start so valuation_as_of works
        cache.upsert_valuation_daily(code, pd.DataFrame({
            "date": [start],
            "pe_ttm": [15.0], "pb": [2.0], "ps_ttm": [3.0],
            "mkt_cap": [market_cap], "float_cap": [market_cap * 0.7],
        }))
        cache.upsert_sector(code, sw_l1_name=sectors.get(code, "综合"))


# ---------------- _rebalance_dates helper -----------------------------------

def test_rebalance_dates_weekly():
    # Pick a range that ends on a Friday so every week is complete
    out = _rebalance_dates(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-02"), "weekly")
    # 5 Fridays in this range: Jan 5, 12, 19, 26, Feb 2
    assert len(out) == 5
    for d in out:
        assert d.weekday() == 4   # Friday


def test_rebalance_dates_weekly_partial_last_week():
    """If the range ends mid-week, the last entry is the last business day in range."""
    out = _rebalance_dates(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31"), "weekly")
    # The last bucket is the partial week ending Wed Jan 31 → that's the date
    assert out[-1] == pd.Timestamp("2024-01-31")


def test_rebalance_dates_monthly():
    out = _rebalance_dates(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-06-30"), "monthly")
    assert len(out) == 6


def test_rebalance_dates_rejects_unknown_freq():
    with pytest.raises(ValueError):
        _rebalance_dates(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31"), "daily")


# ---------------- TopNRankerStrategy basic logic ----------------------------

def test_strategy_validates_constructor():
    composite = EqualWeightComposite([FactorWeight(_MockFactor(constant=pd.Series({"A": 1.0})))])
    with pytest.raises(ValueError):
        TopNRankerStrategy(composite, top_n=0)
    with pytest.raises(ValueError):
        TopNRankerStrategy(composite, max_sector_pct=0)
    with pytest.raises(ValueError):
        TopNRankerStrategy(composite, max_sector_pct=1.5)


def test_initialize_precomputes_targets(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "t.db"))
    codes = [f"S{i:02d}" for i in range(20)]
    _seed_universe(cache, codes, start="2024-01-02", end="2024-03-29")

    # Constant scores: S00 best, S19 worst
    scores = pd.Series({c: float(19 - i) for i, c in enumerate(codes)})
    factor = _MockFactor(constant=scores)
    composite = EqualWeightComposite([FactorWeight(factor)])

    strat = TopNRankerStrategy(
        composite=composite,
        top_n=5, rebalance_freq="weekly",
        min_market_cap=0, exclude_st=False, max_sector_pct=1.0,
        cache=cache,
    )

    # Load bars for the strategy context (mimic what Backtester does)
    data = {}
    for code in codes:
        df = cache.get_daily_bars(code, "2024-01-02", "2024-03-29")
        data[code] = df.set_index("date").sort_index()
    portfolio = Portfolio(initial_cash=1_000_000.0)
    ctx = StrategyContext(portfolio=portfolio, universe=codes, data=data)

    strat.initialize(ctx)
    assert len(strat._target_by_date) > 0
    # Top-5 should be S00..S04 at every rebalance
    for date, targets in strat._target_by_date.items():
        assert targets == ["S00", "S01", "S02", "S03", "S04"]


def test_st_exclusion(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "t.db"))
    codes = [f"S{i:02d}" for i in range(10)]
    _seed_universe(cache, codes, st_codes={"S00", "S01"})  # top 2 are ST

    scores = pd.Series({c: float(9 - i) for i, c in enumerate(codes)})
    factor = _MockFactor(constant=scores)
    composite = EqualWeightComposite([FactorWeight(factor)])

    strat = TopNRankerStrategy(
        composite=composite, top_n=3, exclude_st=True,
        min_market_cap=0, max_sector_pct=1.0, cache=cache,
    )
    data = {c: cache.get_daily_bars(c, "2024-01-02", "2024-12-31")
                  .set_index("date").sort_index() for c in codes}
    ctx = StrategyContext(portfolio=Portfolio(1_000_000.0), universe=codes, data=data)
    strat.initialize(ctx)

    sample = next(iter(strat._target_by_date.values()))
    # ST stocks (S00, S01) excluded → top 3 should be S02, S03, S04
    assert "S00" not in sample
    assert "S01" not in sample
    assert sample == ["S02", "S03", "S04"]


def test_market_cap_filter(tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "t.db"))
    codes = [f"S{i:02d}" for i in range(6)]
    # Plant individually: top 3 below 3bn, bottom 3 above
    for i, code in enumerate(codes):
        df = generate_synthetic_ohlcv(code, "2024-01-02", "2024-12-31")
        cache.upsert_daily_bars(code, df)
        cache.upsert_stock_meta(code, code, "main_sh", False)
        mkt_cap = 1.0e9 if i < 3 else 1.0e10
        cache.upsert_valuation_daily(code, pd.DataFrame({
            "date": ["2024-01-02"],
            "pe_ttm": [15.0], "pb": [2.0], "ps_ttm": [3.0],
            "mkt_cap": [mkt_cap], "float_cap": [mkt_cap * 0.7],
        }))
        cache.upsert_sector(code, sw_l1_name="综合")

    scores = pd.Series({c: float(5 - i) for i, c in enumerate(codes)})
    factor = _MockFactor(constant=scores)
    composite = EqualWeightComposite([FactorWeight(factor)])
    strat = TopNRankerStrategy(
        composite=composite, top_n=3,
        min_market_cap=3.0e9, exclude_st=False, max_sector_pct=1.0,
        cache=cache,
    )
    data = {c: cache.get_daily_bars(c, "2024-01-02", "2024-12-31")
                  .set_index("date").sort_index() for c in codes}
    ctx = StrategyContext(portfolio=Portfolio(1_000_000.0), universe=codes, data=data)
    strat.initialize(ctx)

    sample = next(iter(strat._target_by_date.values()))
    # Low-cap S00, S01, S02 filtered out → top should be S03, S04, S05
    for code in sample:
        assert code in {"S03", "S04", "S05"}


def test_sector_cap_limits_concentration(tmp_path):
    """20 stocks, 12 in 'tech'. With top_n=10 and max_sector_pct=0.25, max 2 tech."""
    cache = SQLiteCache(db_path=str(tmp_path / "t.db"))
    codes = [f"S{i:02d}" for i in range(20)]
    sectors = {c: ("tech" if i < 12 else "consumer") for i, c in enumerate(codes)}
    _seed_universe(cache, codes, sectors=sectors)

    # Score = inverse order → S00 = best. The top 12 are all tech.
    scores = pd.Series({c: float(19 - i) for i, c in enumerate(codes)})
    factor = _MockFactor(constant=scores)
    composite = EqualWeightComposite([FactorWeight(factor)])
    strat = TopNRankerStrategy(
        composite=composite, top_n=10, max_sector_pct=0.25,
        min_market_cap=0, exclude_st=False, cache=cache,
    )
    data = {c: cache.get_daily_bars(c, "2024-01-02", "2024-12-31")
                  .set_index("date").sort_index() for c in codes}
    ctx = StrategyContext(portfolio=Portfolio(1_000_000.0), universe=codes, data=data)
    strat.initialize(ctx)

    sample = next(iter(strat._target_by_date.values()))
    # max_per_sector = int(10 * 0.25) = 2
    tech_count = sum(1 for c in sample if sectors[c] == "tech")
    assert tech_count <= 2


# ---------------- End-to-end via Backtester ---------------------------------

def test_full_backtest_holds_top_n_after_first_rebalance(tmp_path):
    """Smoke test: run a 3-month backtest, verify portfolio holds ~top_n stocks."""
    cache = SQLiteCache(db_path=str(tmp_path / "t.db"))
    codes = [f"S{i:02d}" for i in range(15)]
    _seed_universe(cache, codes, start="2024-01-02", end="2024-03-29")

    scores = pd.Series({c: float(14 - i) for i, c in enumerate(codes)})
    factor = _MockFactor(constant=scores)
    composite = EqualWeightComposite([FactorWeight(factor)])
    strat = TopNRankerStrategy(
        composite=composite, top_n=5, rebalance_freq="weekly",
        min_market_cap=0, exclude_st=False, max_sector_pct=1.0,
        cache=cache,
    )
    data = {c: cache.get_daily_bars(c, "2024-01-02", "2024-03-29")
                  .set_index("date").sort_index() for c in codes}
    meta = {c: cache.get_stock_meta(c) for c in codes}
    config = BacktestConfig(
        start="2024-01-02", end="2024-03-29", initial_cash=1_000_000.0,
        limit_hit_fill_prob=1.0, random_seed=42,
    )
    bt = Backtester(config, strat, data, meta)
    result = bt.run()

    # Should have generated some fills
    assert len(result.fills) > 0
    # Final portfolio should hold approximately top-N stocks
    final_holdings = sum(1 for pos in bt.portfolio.positions.values()
                         if pos.shares > 0)
    assert 1 <= final_holdings <= 5
    # Equity should be tracking
    assert not result.equity_curve.empty
