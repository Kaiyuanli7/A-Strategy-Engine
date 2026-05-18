"""Top-N factor-ranked portfolio strategy.

Rebalances weekly/monthly: compute composite factor score, rank cross-section,
build a portfolio of the top N stocks (with sector / single-name / ST /
market-cap filters), emit buy/sell orders that the existing event-driven
backtester fills at the next bar's open with full A-share constraints
(T+1, price limits, lot rounding, suspension, commission/tax).

Designed to consume an `astrategy.composites.Composite` so the same strategy
backs both equal-weight and signed-IC-weighted experiments without changes.
"""

from __future__ import annotations

import logging
from typing import Literal

import pandas as pd

from astrategy.composites.base import Composite
from astrategy.data.cache import SQLiteCache
from astrategy.engine.constraints import round_to_lot
from astrategy.engine.orders import Order, OrderSide
from astrategy.factors.base import FactorContext
from astrategy.strategies.base import Strategy, StrategyContext

log = logging.getLogger(__name__)


def _rebalance_dates(
    start: pd.Timestamp,
    end: pd.Timestamp,
    freq: Literal["weekly", "monthly"],
) -> list[pd.Timestamp]:
    """Last business day per week/month within [start, end]."""
    bdays = pd.bdate_range(start=start, end=end)
    if bdays.empty:
        return []
    df = pd.DataFrame({"d": bdays})
    if freq == "weekly":
        df["bucket"] = df["d"].dt.to_period("W")
    elif freq == "monthly":
        df["bucket"] = df["d"].dt.to_period("M")
    else:
        raise ValueError(f"unknown rebalance_freq={freq!r}")
    last_per_bucket = df.groupby("bucket", observed=True)["d"].max()
    return [pd.Timestamp(d) for d in sorted(last_per_bucket.tolist())]


class TopNRankerStrategy(Strategy):
    """
    Hold the top-N stocks by composite score, rebalanced periodically.

    Parameters
    ----------
    composite:
        A configured `Composite` (e.g. EqualWeightComposite, SignedICWeightedComposite).
        Called once per rebalance date with a `FactorContext`.
    top_n:
        Number of stocks to hold at each rebalance.
    rebalance_freq:
        "weekly" or "monthly". Rebalance happens at last business day of each bucket.
    max_sector_pct:
        Max fraction of `top_n` positions allowed in any single SW L1 sector.
        Default 0.25 (max 25% concentration).
    max_single_position_pct:
        Max equity fraction per single name. Default 0.05.
    min_market_cap:
        Drop candidates with cached market cap below this. Default 3 bn RMB.
    exclude_st:
        Drop ST stocks. Default True.
    weighting:
        "equal" — equal-weight across the top-N. (Score-weighted is a follow-up.)
    cache:
        SQLiteCache instance. If None, uses default.
    ic_history:
        Optional {factor_name: IC time series} for the composite. Forward
        through every call to composite.compute(). The walk-forward optimizer
        precomputes this from in-sample data; for one-shot backtests, leave
        None and the composite will fall back to its default weighting.
    """

    name = "top_n_ranker"

    def __init__(
        self,
        composite: Composite,
        top_n: int = 30,
        rebalance_freq: Literal["weekly", "monthly"] = "weekly",
        max_sector_pct: float = 0.25,
        max_single_position_pct: float = 0.05,
        min_market_cap: float = 3.0e9,
        exclude_st: bool = True,
        weighting: Literal["equal"] = "equal",
        cache: SQLiteCache | None = None,
        ic_history: dict[str, pd.Series] | None = None,
    ):
        if top_n < 1:
            raise ValueError(f"top_n must be >= 1, got {top_n}")
        if not 0 < max_sector_pct <= 1.0:
            raise ValueError(f"max_sector_pct must be in (0, 1], got {max_sector_pct}")
        if not 0 < max_single_position_pct <= 1.0:
            raise ValueError(f"max_single_position_pct must be in (0, 1], got {max_single_position_pct}")
        self.composite = composite
        self.top_n = top_n
        self.rebalance_freq = rebalance_freq
        self.max_sector_pct = max_sector_pct
        self.max_single_position_pct = max_single_position_pct
        self.min_market_cap = min_market_cap
        self.exclude_st = exclude_st
        self.weighting = weighting
        self.cache = cache or SQLiteCache()
        self.ic_history = ic_history
        # Filled in initialize()
        self._target_by_date: dict[pd.Timestamp, list[str]] = {}

    # ---------------- Strategy interface ----------------

    def initialize(self, context: StrategyContext) -> None:
        """Precompute target portfolios at each rebalance date in the run window."""
        # Find the data window from the strategy context (intersection of all
        # symbols' available index range).
        all_dates: set[pd.Timestamp] = set()
        for df in context.data.values():
            all_dates.update(df.index)
        if not all_dates:
            log.warning("TopNRanker: no data in context; nothing to do.")
            return
        start = min(all_dates)
        end = max(all_dates)
        reb_dates = _rebalance_dates(start, end, self.rebalance_freq)

        for d in reb_dates:
            target = self._compute_targets_at(d, context.universe)
            self._target_by_date[d] = target

        log.info(
            "TopNRanker initialize: %d rebalance dates, "
            "avg %.1f targets per date",
            len(reb_dates),
            sum(len(v) for v in self._target_by_date.values()) / max(len(reb_dates), 1),
        )

    def on_bar(
        self,
        date: pd.Timestamp,
        bars: dict[str, pd.Series],
        context: StrategyContext,
    ) -> list[Order]:
        target_codes = self._target_by_date.get(date)
        if target_codes is None:
            # Not a rebalance day — hold
            return []
        if not target_codes:
            # Rebalance day but composite couldn't pick anything (no data yet)
            return []

        target_set = set(target_codes)
        current_holdings = {
            code: pos.shares
            for code, pos in context.portfolio.positions.items()
            if pos.shares > 0
        }
        current_set = set(current_holdings)

        orders: list[Order] = []

        # 1. SELL stocks leaving the portfolio.
        # T+1: only `sellable` shares can be sold today. Engine handles the
        # T+1 unlock at next-bar start; if a stock was bought yesterday it
        # has sellable < shares and we partially sell what's free.
        for code in sorted(current_set - target_set):
            pos = context.portfolio.positions[code]
            if pos.sellable <= 0:
                continue
            orders.append(Order(
                code=code, side=OrderSide.SELL, shares=int(pos.sellable),
                reason="exiting top_n",
            ))

        # 2. BUY stocks entering the portfolio.
        # Sizing: equal-weight by total equity / top_n. Use latest close as the
        # mark; engine fills at the next bar's open so this is an estimate.
        marks = {c: float(bar["close"]) for c, bar in bars.items()
                 if bar is not None and not pd.isna(bar.get("close"))}
        total_equity = context.portfolio.equity(marks)
        if total_equity <= 0:
            return orders

        per_position_budget = total_equity / max(self.top_n, 1)
        # Also enforce single-name cap: never allocate more than this fraction
        per_position_cap = total_equity * self.max_single_position_pct
        per_position = min(per_position_budget, per_position_cap)

        for code in sorted(target_set - current_set):
            close = marks.get(code)
            if close is None or close <= 0:
                continue
            raw_shares = per_position / close
            shares = round_to_lot(raw_shares)
            if shares > 0:
                orders.append(Order(
                    code=code, side=OrderSide.BUY, shares=shares,
                    reason="entering top_n",
                ))

        return orders

    # ---------------- internal helpers ----------------

    def _compute_targets_at(
        self,
        as_of: pd.Timestamp,
        universe: list[str],
    ) -> list[str]:
        """Run the composite, apply filters, pick top-N with sector cap."""
        ctx = FactorContext(cache=self.cache, universe=universe, as_of=as_of)
        try:
            scores = self.composite.compute(ctx, ic_history=self.ic_history)
        except TypeError:
            # Older composites without ic_history kwarg
            scores = self.composite.compute(ctx)
        except Exception as e:
            log.warning("composite.compute failed at %s: %s", as_of, e)
            return []
        if scores is None or scores.empty:
            return []

        # Apply scalar filters: ST exclusion + min_market_cap.
        scores = self._filter_by_meta_and_marketcap(scores, ctx)
        if scores.empty:
            return []

        # Top-N with sector cap: walk in score order, keep candidates respecting
        # max_sector_pct.
        return self._select_top_n_with_sector_cap(scores, ctx)

    def _filter_by_meta_and_marketcap(
        self,
        scores: pd.Series,
        ctx: FactorContext,
    ) -> pd.Series:
        keep: list[str] = []
        for code in scores.index:
            meta = self.cache.get_stock_meta(code) or {}
            if self.exclude_st and bool(meta.get("is_st")):
                continue
            if self.min_market_cap > 0:
                val = ctx.valuation(code) or {}
                mkt_cap = val.get("mkt_cap")
                if mkt_cap is None or float(mkt_cap) < self.min_market_cap:
                    continue
            keep.append(code)
        return scores.loc[keep] if keep else pd.Series(dtype="float64")

    def _select_top_n_with_sector_cap(
        self,
        scores: pd.Series,
        ctx: FactorContext,
    ) -> list[str]:
        """Walk scores DESC; greedy include while sector cap holds."""
        sorted_codes = scores.sort_values(ascending=False).index.tolist()
        # Sector lookup once for all candidates (cheap join)
        sectors_map = self.cache.get_sectors(sorted_codes)
        max_per_sector = max(1, int(self.top_n * self.max_sector_pct))

        selected: list[str] = []
        sector_counts: dict[str, int] = {}
        for code in sorted_codes:
            if len(selected) >= self.top_n:
                break
            sector = sectors_map.get(code, {}).get("sw_l1_name") or "_unknown"
            if sector_counts.get(sector, 0) >= max_per_sector:
                continue
            selected.append(code)
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
        return selected
