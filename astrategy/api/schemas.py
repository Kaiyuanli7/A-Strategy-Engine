"""Pydantic request/response models for the factor research REST API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# --- Meta / health ----------------------------------------------------------

class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    cached_stocks: int
    cached_runs: int


# --- Data: universe + stock OHLCV ------------------------------------------

class StockBar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class StockOHLCVResponse(BaseModel):
    code: str
    name: str | None = None
    board: str | None = None
    is_st: bool = False
    bars: list[StockBar]


class UniverseStock(BaseModel):
    code: str
    name: str | None = None
    board: str | None = None
    is_st: bool = False


class UniverseResponse(BaseModel):
    name: str
    codes: list[str]
    stocks: list[UniverseStock]


class FetchRequest(BaseModel):
    codes: list[str] = Field(..., min_length=1)
    start: str = "2023-05-18"
    end: str = "2026-05-18"
    synthetic: bool = False

    model_config = ConfigDict(extra="forbid")


class FetchResponse(BaseModel):
    rows_per_code: dict[str, int]
    total_rows: int
    used_synthetic: bool


# --- Factor research --------------------------------------------------------

class FactorParamSpec(BaseModel):
    """One tunable knob on a factor."""
    name: str
    type: Literal["int", "float", "str", "bool"]
    default: Any
    description: str | None = None
    min: float | None = None
    max: float | None = None


class FactorMeta(BaseModel):
    name: str
    category: Literal["flow", "fundamental", "technical", "event", "sector"]
    description: str
    lookback_days: int
    rebalance_freq: Literal["daily", "weekly", "monthly"]
    params: list[FactorParamSpec] = Field(default_factory=list)


class ICPoint(BaseModel):
    date: str
    ic: float


class QuintileCumPoint(BaseModel):
    date: str
    # Cumulative return per quintile, plus the long-short spread (q1-q5).
    q1: float
    q2: float
    q3: float
    q4: float
    q5: float
    long_short: float


class DecayPoint(BaseModel):
    horizon: int
    ic_mean: float
    ic_ir: float


class ICSummary(BaseModel):
    mean: float
    std: float
    ir: float
    hit_rate: float
    t_stat: float
    n: int


class QuintileSummary(BaseModel):
    long_short_mean: float
    long_short_std: float
    long_short_sharpe: float
    long_short_total_return: float
    monotonicity: float = Field(
        ...,
        description="Spearman rank correlation between quintile index 1..5 and "
                    "mean per-period return (positive = monotone deciles).",
    )
    avg_turnover: float


# --- Chart data (Sprint 4 — interactive stock chart) ---------------------

class ChartCandle(BaseModel):
    time: str            # YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float
    volume: float


class ChartLinePoint(BaseModel):
    time: str
    value: float | None = None


class ChartMACDPoint(BaseModel):
    time: str
    macd: float | None = None
    signal: float | None = None
    histogram: float | None = None


class ChartSignal(BaseModel):
    """One backtest-derived entry or exit on this stock."""
    time: str
    side: Literal["buy", "sell"]
    price: float
    shares: int
    cost: float
    reason: str | None = None         # for sells; backtest 'reason' field
    rejected_reason: str | None = None


class ChartResponse(BaseModel):
    code: str
    name: str | None = None
    sector: str | None = None
    candles: list[ChartCandle]
    indicators: dict[str, list[ChartLinePoint]] = Field(default_factory=dict)
    macd: list[ChartMACDPoint] = Field(default_factory=list)
    signals: list[ChartSignal] = Field(default_factory=list)
    run_id: str | None = None


class ScreenerEntry(BaseModel):
    """One row in the live screener: composite + per-factor scores."""
    rank: int
    code: str
    name: str | None = None
    sector: str | None = None
    last_price: float | None = None
    market_cap: float | None = None
    is_st: bool = False
    composite_score: float
    factor_scores: dict[str, float]


class ScreenerResponse(BaseModel):
    as_of: str
    universe: str
    composite_method: str
    factors: list[str]
    top_n: int
    total_ranked: int
    entries: list[ScreenerEntry]


class FactorCorrelationResponse(BaseModel):
    factors: list[str]
    matrix: list[list[float]]
    universe: str
    start: str
    end: str
    rebalance: Literal["daily", "weekly", "monthly"]
    n_dates: int


class FactorEvaluationResponse(BaseModel):
    factor: FactorMeta
    params: dict[str, Any]
    universe: str
    start: str
    end: str
    rebalance: Literal["daily", "weekly", "monthly"]
    horizon: int
    n_dates: int
    n_stocks_avg: float

    ic_series: list[ICPoint]
    ic_summary: ICSummary
    quintile_cum: list[QuintileCumPoint]
    quintile_summary: QuintileSummary
    decay: list[DecayPoint]
    cached: bool = Field(False, description="True if this evaluation was returned from cache.")


# --- Portfolio (Sprint 3): composite + top-N portfolio backtest ------------

class FactorWeightSpec(BaseModel):
    """One slot in a composite: factor name + factor params + weight."""
    factor_name: str
    params: dict[str, Any] = Field(default_factory=dict)
    weight: float | None = Field(
        None,
        description="Explicit weight; None means 'auto' (composite picks).",
    )

    model_config = ConfigDict(extra="forbid")


class CompositeSpec(BaseModel):
    """Composite scoring config."""
    method: Literal["equal_weight", "signed_ic_weighted", "fixed_weight"] = "equal_weight"
    factors: list[FactorWeightSpec] = Field(..., min_length=1, max_length=5)
    rolling_window: int = Field(60, ge=10, le=252,
                                description="signed_ic_weighted only: trailing IC window")
    min_ic_abs: float = Field(0.005, ge=0.0, le=0.5,
                              description="signed_ic_weighted only: drop factors below |IC|")

    model_config = ConfigDict(extra="forbid")


class PortfolioConfigSpec(BaseModel):
    top_n: int = Field(30, ge=1, le=300)
    rebalance_freq: Literal["weekly", "monthly"] = "weekly"
    max_sector_pct: float = Field(0.25, gt=0.0, le=1.0)
    max_single_position_pct: float = Field(0.05, gt=0.0, le=1.0)
    min_market_cap: float = Field(3.0e9, ge=0.0)
    exclude_st: bool = True
    weighting: Literal["equal"] = "equal"

    model_config = ConfigDict(extra="forbid")


class PortfolioBacktestRequest(BaseModel):
    composite: CompositeSpec
    portfolio: PortfolioConfigSpec = Field(default_factory=PortfolioConfigSpec)
    universe: str = "000300"
    start: str = "2023-01-01"
    end: str = "2025-12-31"
    initial_cash: float = 1_000_000.0
    limit_hit_fill_prob: float = 0.20
    random_seed: int = 42

    model_config = ConfigDict(extra="forbid")


class PortfolioBacktestResponse(BaseModel):
    run_id: str
    status: Literal["completed", "failed"]
    summary: dict[str, Any] | None = None
    error: str | None = None


class FillRecord(BaseModel):
    date: str
    code: str
    side: Literal["buy", "sell"]
    shares: int
    price: float
    cost: float
    rejected_reason: str | None = None


class HoldingResponse(BaseModel):
    code: str
    shares: int
    avg_cost: float
    market_value: float
    pnl: float
    pnl_pct: float
    last_price: float
    entry_date: str
    sector: str | None = None


class SectorWeightResponse(BaseModel):
    sector: str
    weight: float
    n_stocks: int
    market_value: float


# --- Backtest / walk-forward shells (kept for Sprint 3 re-use) -------------

class EquityPoint(BaseModel):
    date: str
    equity: float


class PortfolioResultResponse(BaseModel):
    run_id: str
    status: str
    config: PortfolioBacktestRequest
    summary: dict[str, Any] | None = None
    equity_curve: list[EquityPoint]
    fills: list[FillRecord]
    rejections: list[FillRecord]
    final_holdings: list[HoldingResponse] = Field(default_factory=list)
    sector_exposure: list[SectorWeightResponse] = Field(default_factory=list)
    error: str | None = None


class BacktestRunListItem(BaseModel):
    run_id: str
    status: str
    strategy_type: str
    universe_size: int
    start: str
    end: str
    created_at: str
    sharpe: float | None = None
    total_return: float | None = None


class WalkForwardRunListItem(BaseModel):
    run_id: str
    status: str
    strategy_type: str
    aggregate_oos_sharpe: float | None = None
    overfit_flag: bool | None = None
    n_windows: int | None = None
    created_at: str


# --- Walk-forward weight optimization (Sprint 3.5) -------------------------

class WalkForwardWindowResult(BaseModel):
    """One IS/OOS window from the weight optimizer."""
    window_idx: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    is_sharpe: float
    oos_sharpe: float | None = None       # None on OOS data unavailable
    weights: dict[str, float]


class WalkForwardAggregate(BaseModel):
    is_sharpe: float
    oos_sharpe: float
    is_oos_gap: float
    overfit: bool


class WalkForwardResultResponse(BaseModel):
    run_id: str
    status: str
    config: dict[str, Any] = Field(default_factory=dict)
    factors: list[Any] = Field(default_factory=list)
    windows: list[WalkForwardWindowResult] = Field(default_factory=list)
    aggregate: WalkForwardAggregate | None = None
    created_at: str
    error: str | None = None
