"""Pydantic request/response models for the REST API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrategySpec(BaseModel):
    """JSON-serializable strategy configuration."""
    type: Literal["ma_cross"] = Field(..., description="Registered strategy type")
    params: dict[str, Any] = Field(default_factory=dict)

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
    config: BacktestConfigSpec = Field(default_factory=BacktestConfigSpec)

    model_config = ConfigDict(extra="forbid")


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
