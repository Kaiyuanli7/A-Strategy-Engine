"""
Walk-forward validation: split history into rolling train/test windows, run the
SAME strategy on each, report in-sample vs out-of-sample side by side.

Phase 5 scope: fixed strategy across all windows. Per-window parameter
optimization (grid search inside each window) is Phase 6.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from astrategy.config import DEFAULT_RISK_FREE_RATE, TRADING_DAYS_PER_YEAR
from astrategy.engine.backtest import Backtester, BacktestConfig, BacktestResult
from astrategy.strategies.base import Strategy

log = logging.getLogger(__name__)


@dataclass
class WalkForwardConfig:
    train_months: int = 12
    test_months: int = 3
    step_months: int = 3
    min_train_bars: int = 200
    overfit_gap_threshold: float = 0.5


@dataclass
class WindowResult:
    window_idx: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    is_summary: dict
    oos_summary: dict
    is_oos_sharpe_gap: float
    skipped: bool = False
    skip_reason: str | None = None


@dataclass
class WalkForwardResult:
    windows: list[WindowResult] = field(default_factory=list)
    oos_equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    aggregate_is_sharpe: float = 0.0
    aggregate_oos_sharpe: float = 0.0
    aggregate_gap: float = 0.0
    overfit_flag: bool = False
    config: WalkForwardConfig | None = None


def _month_offset(date: pd.Timestamp, months: int) -> pd.Timestamp:
    return date + pd.DateOffset(months=months)


def _summary_dict(result: BacktestResult) -> dict:
    """Coerce non-JSON Timestamp values for safe serialization."""
    out = dict(result.summary)
    for k in ("max_drawdown_peak", "max_drawdown_trough"):
        v = out.get(k)
        if v is not None and not isinstance(v, str):
            try:
                out[k] = v.isoformat()
            except Exception:
                out[k] = str(v)
    return out


def _annualized_sharpe(returns: pd.Series, rf_annual: float = DEFAULT_RISK_FREE_RATE) -> float:
    """Sharpe from a daily-return series; matches engine.metrics convention."""
    if len(returns) < 2:
        return 0.0
    daily_rf = rf_annual / TRADING_DAYS_PER_YEAR
    excess = returns - daily_rf
    mu = excess.mean()
    sigma = returns.std(ddof=1)
    if sigma == 0 or pd.isna(sigma):
        return 0.0
    return float(mu / sigma * math.sqrt(TRADING_DAYS_PER_YEAR))


def generate_windows(
    data_start: pd.Timestamp,
    data_end: pd.Timestamp,
    config: WalkForwardConfig,
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """Return list of (train_start, train_end, test_start, test_end)."""
    out = []
    train_start = data_start
    while True:
        train_end = _month_offset(train_start, config.train_months)
        test_start = train_end
        test_end = _month_offset(test_start, config.test_months)
        if test_end > data_end + pd.Timedelta(days=1):
            break
        out.append((train_start, train_end, test_start, test_end))
        train_start = _month_offset(train_start, config.step_months)
    return out


class WalkForwardRunner:
    """
    Runs `strategy_factory()` against rolling train/test windows.

    `strategy_factory` is a zero-arg callable that returns a *fresh*
    `Strategy` instance. We re-instantiate per window so that any
    precomputed state in `initialize()` is rebuilt with only the bars
    available up to the window boundary.
    """

    def __init__(
        self,
        base_config: BacktestConfig,
        strategy_factory: Callable[[], Strategy],
        data: dict[str, pd.DataFrame],
        meta: dict[str, dict] | None = None,
        wf_config: WalkForwardConfig | None = None,
    ):
        self.base_config = base_config
        self.strategy_factory = strategy_factory
        self.data = data
        self.meta = meta or {}
        self.wf_config = wf_config or WalkForwardConfig()

    def _data_span(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        starts, ends = [], []
        for df in self.data.values():
            if df.empty:
                continue
            starts.append(df.index.min())
            ends.append(df.index.max())
        if not starts:
            raise ValueError("no data in walk-forward runner")
        return min(starts), max(ends)

    def _slice_data(
        self, start: pd.Timestamp, end: pd.Timestamp
    ) -> dict[str, pd.DataFrame]:
        out = {}
        for code, df in self.data.items():
            d = df.loc[(df.index >= start) & (df.index < end)]
            if not d.empty:
                out[code] = d
        return out

    def _run_one(self, start: pd.Timestamp, end: pd.Timestamp) -> BacktestResult | None:
        sliced = self._slice_data(start, end)
        if not sliced:
            return None
        sub_config = BacktestConfig(
            start=start.strftime("%Y-%m-%d"),
            end=(end - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            initial_cash=self.base_config.initial_cash,
            fill_at=self.base_config.fill_at,
            limit_hit_fill_prob=self.base_config.limit_hit_fill_prob,
            random_seed=self.base_config.random_seed,
        )
        strategy = self.strategy_factory()
        bt = Backtester(sub_config, strategy, sliced, self.meta)
        return bt.run()

    def run(self) -> WalkForwardResult:
        data_start, data_end = self._data_span()
        windows = generate_windows(data_start, data_end, self.wf_config)
        if not windows:
            log.warning("walk-forward: no windows fit in [%s, %s]", data_start, data_end)
            return WalkForwardResult(config=self.wf_config)

        results: list[WindowResult] = []
        oos_returns_pieces: list[pd.Series] = []
        is_returns_pieces: list[pd.Series] = []

        for idx, (train_start, train_end, test_start, test_end) in enumerate(windows):
            train_data = self._slice_data(train_start, train_end)
            train_bar_count = max((len(df) for df in train_data.values()), default=0)
            if train_bar_count < self.wf_config.min_train_bars:
                results.append(WindowResult(
                    window_idx=idx,
                    train_start=train_start.strftime("%Y-%m-%d"),
                    train_end=train_end.strftime("%Y-%m-%d"),
                    test_start=test_start.strftime("%Y-%m-%d"),
                    test_end=test_end.strftime("%Y-%m-%d"),
                    is_summary={}, oos_summary={},
                    is_oos_sharpe_gap=0.0,
                    skipped=True,
                    skip_reason=f"train bars {train_bar_count} < min {self.wf_config.min_train_bars}",
                ))
                continue

            is_result = self._run_one(train_start, train_end)
            oos_result = self._run_one(test_start, test_end)
            if is_result is None or oos_result is None:
                results.append(WindowResult(
                    window_idx=idx,
                    train_start=train_start.strftime("%Y-%m-%d"),
                    train_end=train_end.strftime("%Y-%m-%d"),
                    test_start=test_start.strftime("%Y-%m-%d"),
                    test_end=test_end.strftime("%Y-%m-%d"),
                    is_summary={}, oos_summary={},
                    is_oos_sharpe_gap=0.0,
                    skipped=True,
                    skip_reason="no data in window",
                ))
                continue

            is_summary = _summary_dict(is_result)
            oos_summary = _summary_dict(oos_result)
            gap = is_summary.get("sharpe", 0.0) - oos_summary.get("sharpe", 0.0)
            results.append(WindowResult(
                window_idx=idx,
                train_start=train_start.strftime("%Y-%m-%d"),
                train_end=train_end.strftime("%Y-%m-%d"),
                test_start=test_start.strftime("%Y-%m-%d"),
                test_end=test_end.strftime("%Y-%m-%d"),
                is_summary=is_summary,
                oos_summary=oos_summary,
                is_oos_sharpe_gap=float(gap),
            ))

            # Collect daily returns for proper aggregation (concatenate, then Sharpe)
            if not is_result.equity_curve.empty:
                is_returns_pieces.append(is_result.equity_curve.pct_change().dropna())
            if not oos_result.equity_curve.empty:
                oos_returns_pieces.append(oos_result.equity_curve.pct_change().dropna())

        # Build concatenated OOS equity curve (re-base to initial_cash, compound across windows)
        if oos_returns_pieces:
            oos_returns = pd.concat(oos_returns_pieces).sort_index()
            # Deduplicate the boundary day between adjacent windows
            oos_returns = oos_returns[~oos_returns.index.duplicated(keep="first")]
            oos_equity = self.base_config.initial_cash * (1 + oos_returns).cumprod()
        else:
            oos_returns = pd.Series(dtype=float)
            oos_equity = pd.Series(dtype=float)

        is_returns = pd.concat(is_returns_pieces).sort_index() if is_returns_pieces else pd.Series(dtype=float)
        is_returns = is_returns[~is_returns.index.duplicated(keep="first")]

        agg_is = _annualized_sharpe(is_returns)
        agg_oos = _annualized_sharpe(oos_returns)
        gap = agg_is - agg_oos
        overfit = abs(gap) > self.wf_config.overfit_gap_threshold

        return WalkForwardResult(
            windows=results,
            oos_equity_curve=oos_equity,
            aggregate_is_sharpe=agg_is,
            aggregate_oos_sharpe=agg_oos,
            aggregate_gap=gap,
            overfit_flag=overfit,
            config=self.wf_config,
        )
