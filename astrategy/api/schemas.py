"""Pydantic request/response models for the REST API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrategySpec(BaseModel):
    """JSON-serializable strategy configuration."""
    type: Literal["ma_cross", "composable"] = Field(..., description="Registered strategy type")
    params: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class UniverseFilter(BaseModel):
    boards: list[str] | None = None
    exclude_st: bool = True
    market_cap_min: float | None = None
    market_cap_max: float | None = None
    sectors_l1: list[str] | None = None

    model_config = ConfigDict(extra="forbid")


class BacktestConfigSpec(BaseModel):
    start: str = "2023-05-18"
    end: str = "2026-05-18"
    initial_cash: float = 1_000_000.0
    limit_hit_fill_prob: float = 0.20
    random_seed: int = 42

    model_config = ConfigDict(extra="forbid")


class BacktestRequest(BaseModel):
    strategy: StrategySpec
    universe: list[str] = Field(..., min_length=1, description="Stock codes to trade")
    universe_filter: UniverseFilter | None = None
    config: BacktestConfigSpec = Field(default_factory=BacktestConfigSpec)

    model_config = ConfigDict(extra="forbid")


class FactorAttribution(BaseModel):
    alpha_annualized: float
    loadings: dict[str, float] = Field(default_factory=dict)
    t_stats: dict[str, float] = Field(default_factory=dict)
    r_squared: float
    residual_vol_annualized: float
    n_obs: int


class RegimePerf(BaseModel):
    n_days: int
    annualized_return: float
    sharpe: float
    max_drawdown: float


class BacktestSummary(BaseModel):
    n_bars: int
    initial_equity: float
    final_equity: float
    total_return: float
    annualized_return: float
    annualized_vol: float
    sharpe: float
    max_drawdown: float
    max_drawdown_peak: str | None = None
    max_drawdown_trough: str | None = None
    calmar: float
    win_rate: float
    avg_hold_days: float
    n_trips: int
    n_fills: int
    n_rejections: int
    turnover: float
    factor_attribution: FactorAttribution | None = None
    regime_metrics: dict[str, RegimePerf] | None = None


class BacktestRunResponse(BaseModel):
    run_id: str
    status: Literal["completed", "failed"]
    summary: BacktestSummary | None = None
    error: str | None = None


class EquityPoint(BaseModel):
    date: str
    equity: float


class FillRecord(BaseModel):
    date: str
    code: str
    side: Literal["buy", "sell"]
    shares: int
    price: float
    cost: float
    rejected_reason: str | None = None


class BacktestResultResponse(BaseModel):
    run_id: str
    status: str
    config: BacktestRequest
    summary: BacktestSummary | None = None
    equity_curve: list[EquityPoint]
    fills: list[FillRecord]
    rejections: list[FillRecord]
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


class UniverseResponse(BaseModel):
    name: str
    codes: list[str]
    stocks: list[dict[str, Any]]


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


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    cached_stocks: int
    cached_runs: int


# --- Phase 5: walk-forward ----------------------------------------------------

class WalkForwardConfigSpec(BaseModel):
    train_months: int = Field(12, ge=1, le=60)
    test_months: int = Field(3, ge=1, le=36)
    step_months: int = Field(3, ge=1, le=36)
    min_train_bars: int = Field(200, ge=20)
    overfit_gap_threshold: float = Field(0.5, ge=0.0)
    model_config = ConfigDict(extra="forbid")


class WalkForwardRequest(BaseModel):
    request: BacktestRequest
    walk_forward: WalkForwardConfigSpec = Field(default_factory=WalkForwardConfigSpec)
    model_config = ConfigDict(extra="forbid")


class WindowResultSchema(BaseModel):
    window_idx: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    is_summary: dict = Field(default_factory=dict)
    oos_summary: dict = Field(default_factory=dict)
    is_oos_sharpe_gap: float = 0.0
    skipped: bool = False
    skip_reason: str | None = None


class WalkForwardRunResponse(BaseModel):
    run_id: str
    status: Literal["completed", "failed"]
    aggregate_is_sharpe: float = 0.0
    aggregate_oos_sharpe: float = 0.0
    aggregate_gap: float = 0.0
    overfit_flag: bool = False
    n_windows: int = 0
    error: str | None = None


class WalkForwardResultResponse(BaseModel):
    run_id: str
    status: str
    request: WalkForwardRequest
    aggregate_is_sharpe: float
    aggregate_oos_sharpe: float
    aggregate_gap: float
    overfit_flag: bool
    windows: list[WindowResultSchema]
    oos_equity_curve: list[EquityPoint]
    error: str | None = None


class WalkForwardRunListItem(BaseModel):
    run_id: str
    status: str
    strategy_type: str
    aggregate_oos_sharpe: float | None = None
    overfit_flag: bool | None = None
    n_windows: int | None = None
    created_at: str
