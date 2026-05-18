"""FastAPI server — factor research workstation REST API.

Endpoints:
  - GET  /health
  - GET  /api/data/universe         — universe membership (PIT, as-of)
  - GET  /api/data/stock/{code}     — OHLCV bars for one stock
  - GET  /api/data/sectors          — distinct SW L1 sectors
  - POST /api/data/fetch            — prime cache (real or synthetic)
  - GET  /api/factors               — list registered factors
  - GET  /api/factors/{name}/evaluate — run IC / quintile / decay
  - GET  /api/backtest/runs         — list backtest runs (Sprint 3+ writes; empty until then)
  - GET  /api/backtest/walk_forward — list walk-forward runs (Sprint 3+ writes)
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from astrategy import __version__
from astrategy.api.schemas import (
    BacktestRunListItem,
    FactorEvaluationResponse,
    FactorMeta,
    FetchRequest,
    FetchResponse,
    HealthResponse,
    StockBar,
    StockOHLCVResponse,
    UniverseResponse,
    UniverseStock,
    WalkForwardRunListItem,
)
from astrategy.api.storage import RunStorage
from astrategy.config import classify_board, is_st_name
from astrategy.data.cache import SQLiteCache
from astrategy.data.loader import DataLoader
from astrategy.data.universes import KNOWN_INDICES
from astrategy.evaluation.runner import evaluate_factor, EvaluationConfig
from astrategy.factors import get_factor, list_factors

log = logging.getLogger(__name__)


def get_cache() -> SQLiteCache:
    return SQLiteCache()


def get_storage() -> RunStorage:
    return RunStorage()


def get_loader() -> DataLoader:
    return DataLoader()


app = FastAPI(
    title="A-Strategy-Engine API",
    description="A-share factor research workstation",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health ----------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health(
    cache: Annotated[SQLiteCache, Depends(get_cache)],
    storage: Annotated[RunStorage, Depends(get_storage)],
) -> HealthResponse:
    # Count anything in stock_meta as a cached stock.
    cached_stocks = len(cache.all_meta_codes())
    return HealthResponse(
        version=__version__,
        cached_stocks=cached_stocks,
        cached_runs=storage.count(),
    )


# --- Data ------------------------------------------------------------------

@app.get("/api/data/universe", response_model=UniverseResponse, tags=["data"])
def get_universe(
    cache: Annotated[SQLiteCache, Depends(get_cache)],
    index: str = Query("000300", description="Index code (e.g. 000300, 000905, 000852)"),
    as_of: str | None = Query(None, description="YYYY-MM-DD; default = latest"),
) -> UniverseResponse:
    if as_of:
        codes = cache.get_index_constituents_as_of(index, as_of)
    else:
        codes = cache.get_index_members_ever(index)
    if not codes:
        # Fallback: any cached stock_meta
        codes = cache.all_meta_codes()
    stocks: list[UniverseStock] = []
    for code in codes:
        meta = cache.get_stock_meta(code) or {}
        stocks.append(UniverseStock(
            code=code,
            name=meta.get("name"),
            board=meta.get("board") or classify_board(code),
            is_st=bool(meta.get("is_st") or is_st_name(meta.get("name") or "")),
        ))
    name = KNOWN_INDICES.get(index, index)
    return UniverseResponse(name=name, codes=codes, stocks=stocks)


@app.get("/api/data/stock/{code}", response_model=StockOHLCVResponse, tags=["data"])
def get_stock(
    code: str,
    cache: Annotated[SQLiteCache, Depends(get_cache)],
    start: str = Query("2023-05-18"),
    end: str = Query("2026-05-18"),
) -> StockOHLCVResponse:
    df = cache.get_daily_bars(code, start, end)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"no cached bars for {code} in {start}..{end}")
    meta = cache.get_stock_meta(code) or {}
    bars = [
        StockBar(
            date=str(r["date"].date() if hasattr(r["date"], "date") else r["date"]),
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=float(r["volume"]),
        )
        for _, r in df.iterrows()
    ]
    return StockOHLCVResponse(
        code=code,
        name=meta.get("name"),
        board=meta.get("board") or classify_board(code),
        is_st=bool(meta.get("is_st") or False),
        bars=bars,
    )


@app.get("/api/data/sectors", tags=["data"])
def list_sectors(cache: Annotated[SQLiteCache, Depends(get_cache)]) -> dict:
    return {"sectors_l1": cache.distinct_sectors()}


@app.post("/api/data/fetch", response_model=FetchResponse, tags=["data"])
def fetch_data(
    req: FetchRequest,
    loader: Annotated[DataLoader, Depends(get_loader)],
    cache: Annotated[SQLiteCache, Depends(get_cache)],
) -> FetchResponse:
    codes_with_names = [(c, c) for c in req.codes]  # Caller can later upsert real names
    if req.synthetic:
        from astrategy.data.synthetic import generate_synthetic_ohlcv
        results: dict[str, int] = {}
        for code, name in codes_with_names:
            cache.upsert_stock_meta(code, name, classify_board(code), is_st_name(name))
            df = generate_synthetic_ohlcv(code, req.start, req.end)
            cache.delete_bars(code)
            n = cache.upsert_daily_bars(code, df)
            cache.record_fetch(code, req.start, req.end, n)
            results[code] = n
        return FetchResponse(rows_per_code=results, total_rows=sum(results.values()), used_synthetic=True)

    results = loader.prime_cache(codes_with_names, start=req.start, end=req.end)
    return FetchResponse(rows_per_code=results, total_rows=sum(results.values()), used_synthetic=False)


# --- Factors ---------------------------------------------------------------

@app.get("/api/factors", response_model=list[FactorMeta], tags=["factors"])
def list_factors_endpoint() -> list[FactorMeta]:
    return [_factor_to_meta(get_factor(name)) for name in list_factors()]


@app.get(
    "/api/factors/{name}/evaluate",
    response_model=FactorEvaluationResponse,
    tags=["factors"],
)
def evaluate_factor_endpoint(
    name: str,
    cache: Annotated[SQLiteCache, Depends(get_cache)],
    storage: Annotated[RunStorage, Depends(get_storage)],
    start: str = Query("2023-05-18"),
    end: str = Query("2026-05-18"),
    universe: str = Query("000300", description="Index code or 'all_cached'"),
    horizon: int = Query(20, ge=1, le=120),
    rebalance: str = Query("weekly", pattern="^(daily|weekly|monthly)$"),
    lookback: int | None = Query(None, description="Override factor's default lookback"),
    use_cache: bool = Query(True),
) -> FactorEvaluationResponse:
    factor_cls = get_factor(name)
    if factor_cls is None:
        raise HTTPException(status_code=404, detail=f"unknown factor '{name}'")

    params: dict = {}
    if lookback is not None:
        params["lookback"] = lookback
    factor = factor_cls(**params)

    config = EvaluationConfig(
        start=start,
        end=end,
        universe=universe,
        horizon=horizon,
        rebalance=rebalance,
    )

    cached = False
    if use_cache:
        cached_payload = storage.get_factor_evaluation(name, factor.params, config.to_dict())
        if cached_payload is not None:
            cached_payload["cached"] = True
            return FactorEvaluationResponse.model_validate(cached_payload)

    try:
        result = evaluate_factor(factor, cache, config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    payload = {
        "factor": _factor_to_meta(factor_cls).model_dump(),
        "params": factor.params,
        "universe": universe,
        "start": start,
        "end": end,
        "rebalance": rebalance,
        "horizon": horizon,
        "n_dates": result.n_dates,
        "n_stocks_avg": result.n_stocks_avg,
        "ic_series": result.ic_series_dicts(),
        "ic_summary": result.ic_summary,
        "quintile_cum": result.quintile_cum_dicts(),
        "quintile_summary": result.quintile_summary,
        "decay": result.decay_dicts(),
        "cached": cached,
    }
    storage.save_factor_evaluation(name, factor.params, config.to_dict(), payload)
    return FactorEvaluationResponse.model_validate(payload)


# --- Backtest / Walk-forward placeholders (Sprint 3 will wire these) ------

@app.get(
    "/api/backtest/runs",
    response_model=list[BacktestRunListItem],
    tags=["backtest"],
)
def list_backtest_runs(
    storage: Annotated[RunStorage, Depends(get_storage)],
    limit: int = Query(50, ge=1, le=500),
) -> list[BacktestRunListItem]:
    return [BacktestRunListItem(**r) for r in storage.list_runs(limit=limit)]


@app.get(
    "/api/backtest/walk_forward",
    response_model=list[WalkForwardRunListItem],
    tags=["backtest"],
)
def list_walk_forward_runs(
    storage: Annotated[RunStorage, Depends(get_storage)],
    limit: int = Query(50, ge=1, le=500),
) -> list[WalkForwardRunListItem]:
    return [WalkForwardRunListItem(**r) for r in storage.list_walk_forward_runs(limit=limit)]


# --- helpers ---------------------------------------------------------------

def _factor_to_meta(factor_cls) -> FactorMeta:
    """Build a FactorMeta from a Factor subclass."""
    return FactorMeta(
        name=factor_cls.name,
        category=factor_cls.category,
        description=factor_cls.description,
        lookback_days=factor_cls.lookback_days,
        rebalance_freq=factor_cls.rebalance_freq,
        params=[p.model_dump() if hasattr(p, "model_dump") else p for p in factor_cls.param_specs()],
    )
