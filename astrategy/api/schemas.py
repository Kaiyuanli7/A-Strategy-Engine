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


# --- Backtest / walk-forward shells (kept for Sprint 3 re-use) -------------

class EquityPoint(BaseModel):
    date: str
    equity: float


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
