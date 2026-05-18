"""Main bar-by-bar backtest loop with A-share constraint modeling."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field

import pandas as pd

from astrategy.config import LIMIT_HIT_FILL_PROB, classify_board, is_st_name
from astrategy.engine.constraints import (
    StockStaticInfo,
    is_at_lower_limit,
    is_at_upper_limit,
    is_suspended,
    round_to_lot,
)
from astrategy.engine.costs import buy_cost, sell_cost
from astrategy.engine.orders import Fill, Order, OrderSide
from astrategy.engine.portfolio import Portfolio
from astrategy.strategies.base import Strategy, StrategyContext

log = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    start: str = "2023-05-18"
    end: str = "2026-05-18"
    initial_cash: float = 1_000_000.0
    fill_at: str = "next_open"        # only "next_open" supported in Phase 1
    limit_hit_fill_prob: float = LIMIT_HIT_FILL_PROB
    random_seed: int = 42


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    fills: list[Fill] = field(default_factory=list)
    rejections: list[Fill] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def enrich_summary(
    result: "BacktestResult",
    cache,
    universe: list[str],
    start: str,
    end: str,
    market_index: str = "000300",
    include_factor: bool = True,
    include_regime: bool = True,
) -> None:
    """
    Augment result.summary in-place with `factor_loadings` + `regime_metrics`.
    Best-effort — silently skips if market index or factor data isn't cached.
    """
    if result.equity_curve.empty:
        return

    strategy_returns = result.equity_curve.pct_change().dropna()
    if strategy_returns.empty:
        return

    # Market index for regime classification
    if include_regime:
        try:
            mkt_bars = cache.get_daily_bars(market_index, start, end)
            if not mkt_bars.empty:
                mkt = mkt_bars.set_index("date").sort_index()["close"].pct_change().dropna()
                from astrategy.engine.regime import classify_regimes, per_regime_metrics
                regimes = classify_regimes(mkt, window=60, min_duration=10)
                regimes_aligned = regimes.reindex(strategy_returns.index, method="ffill")
                result.summary["regime_metrics"] = per_regime_metrics(strategy_returns, regimes_aligned)
        except Exception as e:
            log.debug("regime enrichment skipped: %s", e)

    if include_factor:
        try:
            from astrategy.engine.attribution import (
                attribute_returns, build_factor_returns, summarize_attribution,
            )
            factor_df = build_factor_returns(cache, universe, start, end, market_index)
            attr = attribute_returns(strategy_returns, factor_df)
            if attr is not None:
                result.summary["factor_attribution"] = summarize_attribution(attr)
        except Exception as e:
            log.debug("factor attribution skipped: %s", e)


class Backtester:
    def __init__(
        self,
        config: BacktestConfig,
        strategy: Strategy,
        data: dict[str, pd.DataFrame],
        meta: dict[str, dict] | None = None,
    ):
        self.config = config
        self.strategy = strategy
        # Filter data to config window + ensure DatetimeIndex
        self.data: dict[str, pd.DataFrame] = {}
        for code, df in data.items():
            if df.empty:
                continue
            if not isinstance(df.index, pd.DatetimeIndex):
                df = df.set_index(pd.to_datetime(df.index))
            d = df.loc[(df.index >= config.start) & (df.index <= config.end)].copy()
            if not d.empty:
                self.data[code] = d

        # Build per-stock static info
        self.info: dict[str, StockStaticInfo] = {}
        for code in self.data:
            m = (meta or {}).get(code) or {}
            self.info[code] = StockStaticInfo(
                code=code,
                board=m.get("board") or classify_board(code),
                is_st=bool(m.get("is_st") or is_st_name(m.get("name", ""))),
            )

        self.portfolio = Portfolio(config.initial_cash)
        self.fills: list[Fill] = []
        self.rejections: list[Fill] = []
        self.rng = random.Random(config.random_seed)
        self._ctx: StrategyContext | None = None

    def run(self) -> BacktestResult:
        if not self.data:
            raise ValueError("no data loaded in backtest window")

        # Sorted union of all trading days across the universe
        all_dates = sorted({d for df in self.data.values() for d in df.index})
        if not all_dates:
            raise ValueError("no trading days in backtest window")

        ctx = StrategyContext(
            portfolio=self.portfolio,
            universe=list(self.data.keys()),
            data=self.data,
        )
        self._ctx = ctx
        self.strategy.initialize(ctx)

        equity_by_date: dict[pd.Timestamp, float] = {}
        pending: list[Order] = []

        for date in all_dates:
            ctx.current_date = date

            # 1. T+1 settlement: yesterday's buys become sellable today
            self.portfolio.settle_t1()

            # 2. Build today's bars (only stocks with non-suspended bar)
            today_bars: dict[str, pd.Series] = {}
            for code, df in self.data.items():
                if date in df.index:
                    bar = df.loc[date]
                    if not is_suspended(bar):
                        today_bars[code] = bar

            # 3. Execute pending orders (placed yesterday) at today's open
            for order in pending:
                self._execute_order(order, date, today_bars)
            pending = []

            # 4. Mark equity using today's close
            close_marks = {code: float(bar["close"]) for code, bar in today_bars.items()}
            equity_by_date[date] = self.portfolio.equity(close_marks)

            # 5. Generate new orders for tomorrow's open
            new_orders = self.strategy.on_bar(date, today_bars, ctx)
            pending = list(new_orders)

        equity = pd.Series(equity_by_date).sort_index()

        from astrategy.engine.metrics import summarize
        summary = summarize(equity, self.fills, self.rejections)

        return BacktestResult(
            equity_curve=equity,
            fills=self.fills,
            rejections=self.rejections,
            summary=summary,
        )

    def _execute_order(
        self,
        order: Order,
        date: pd.Timestamp,
        today_bars: dict[str, pd.Series],
    ) -> None:
        bar = today_bars.get(order.code)
        if bar is None:
            self._reject(order, date, 0.0, "suspended")
            return

        df = self.data[order.code]
        try:
            idx = df.index.get_loc(date)
        except KeyError:
            self._reject(order, date, 0.0, "missing_bar")
            return
        if idx == 0:
            self._reject(order, date, 0.0, "no_prev_close")
            return

        prev_close = float(df.iloc[idx - 1]["close"])
        info = self.info[order.code]
        open_price = float(bar["open"])

        if order.side == OrderSide.BUY:
            self._fill_buy(order, date, open_price, prev_close, info)
        else:
            self._fill_sell(order, date, open_price, prev_close, info)

    def _fill_buy(
        self,
        order: Order,
        date: pd.Timestamp,
        open_price: float,
        prev_close: float,
        info: StockStaticInfo,
    ) -> None:
        if is_at_upper_limit(open_price, prev_close, info):
            if self.rng.random() >= self.config.limit_hit_fill_prob:
                self._reject(order, date, open_price, "limit_up")
                return

        shares = round_to_lot(order.shares)
        if shares <= 0:
            self._reject(order, date, open_price, "below_lot")
            return

        # Scale down if insufficient cash (try max affordable)
        notional = shares * open_price
        cost = buy_cost(notional)
        while shares > 0 and notional + cost > self.portfolio.cash:
            shares -= 100
            notional = shares * open_price
            cost = buy_cost(notional) if shares > 0 else 0.0
        if shares <= 0:
            self._reject(order, date, open_price, "insufficient_cash")
            return

        if not self.portfolio.apply_buy(order.code, shares, open_price, cost):
            self._reject(order, date, open_price, "apply_buy_failed")
            return

        self._record_fill(Fill(
            code=order.code,
            side=OrderSide.BUY,
            shares=shares,
            price=open_price,
            cost=cost,
            timestamp=date,
        ))

    def _fill_sell(
        self,
        order: Order,
        date: pd.Timestamp,
        open_price: float,
        prev_close: float,
        info: StockStaticInfo,
    ) -> None:
        if is_at_lower_limit(open_price, prev_close, info):
            if self.rng.random() >= self.config.limit_hit_fill_prob:
                self._reject(order, date, open_price, "limit_down")
                return

        pos = self.portfolio.positions.get(order.code)
        sellable = pos.sellable if pos else 0
        shares = min(round_to_lot(order.shares), round_to_lot(sellable))
        if shares <= 0:
            self._reject(order, date, open_price, "not_sellable")
            return

        notional = shares * open_price
        cost = sell_cost(notional)
        if not self.portfolio.apply_sell(order.code, shares, open_price, cost):
            self._reject(order, date, open_price, "apply_sell_failed")
            return

        self._record_fill(Fill(
            code=order.code,
            side=OrderSide.SELL,
            shares=shares,
            price=open_price,
            cost=cost,
            timestamp=date,
        ))

    def _record_fill(self, fill: Fill) -> None:
        self.fills.append(fill)
        if self._ctx is not None:
            try:
                self.strategy.on_fill(fill, self._ctx)
            except Exception as e:  # noqa: BLE001
                log.warning("strategy.on_fill raised: %s", e)

    def _reject(self, order: Order, date: pd.Timestamp, price: float, reason: str) -> None:
        self.rejections.append(Fill(
            code=order.code,
            side=order.side,
            shares=order.shares,
            price=price,
            cost=0.0,
            timestamp=date,
            rejected_reason=reason,
        ))
