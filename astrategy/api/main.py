"""FastAPI server — wraps the Phase 1 backtest engine as a REST service."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from astrategy import __version__
from astrategy.api.schemas import (
    BacktestRequest,
    BacktestResultResponse,
    BacktestRunListItem,
    BacktestRunResponse,
    BacktestSummary,
    EquityPoint,
    FetchRequest,
    FetchResponse,
    FillRecord,
    HealthResponse,
    StockBar,
    StockOHLCVResponse,
    UniverseResponse,
)
from astrategy.api.storage import RunStorage
from astrategy.api.strategy_factory import create_strategy, registered_types
from astrategy.config import classify_board, is_st_name
from astrategy.data.cache import SQLiteCache
from astrategy.data.loader import DataLoader
from astrategy.data.synthetic import generate_synthetic_ohlcv
from astrategy.data.universe import DEMO_UNIVERSE
from astrategy.engine.backtest import Backtester, BacktestConfig

log = logging.getLogger(__name__)


def get_cache() -> SQLiteCache:
    return SQLiteCache()


def get_storage() -> RunStorage:
    return RunStorage()


def get_loader() -> DataLoader:
    return DataLoader()


app = FastAPI(
    title="A-Strategy-Engine API",
    description="A-share trading strategy backtesting REST API",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Phase 2 dev only; tighten for prod
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health(
    cache: Annotated[SQLiteCache, Depends(get_cache)],
    storage: Annotated[RunStorage, Depends(get_storage)],
) -> HealthResponse:
    cached_stocks = len(cache.get_index_constituents("DEMO"))
    return HealthResponse(
        version=__version__,
        cached_stocks=cached_stocks,
        cached_runs=storage.count(),
    )


@app.get("/api/strategies", tags=["meta"])
def list_strategies() -> dict:
    return {"types": registered_types()}


# --- Data endpoints -----------------------------------------------------------

@app.get("/api/data/universe", response_model=UniverseResponse, tags=["data"])
def get_universe(
    cache: Annotated[SQLiteCache, Depends(get_cache)],
) -> UniverseResponse:
    codes = [c for c, _ in DEMO_UNIVERSE]
    stocks = []
    for code, name in DEMO_UNIVERSE:
        meta = cache.get_stock_meta(code) or {}
        stocks.append({
            "code": code,
            "name": name,
            "board": meta.get("board") or classify_board(code),
            "is_st": bool(meta.get("is_st") or is_st_name(name)),
        })
    return UniverseResponse(name="demo", codes=codes, stocks=stocks)


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


@app.post("/api/data/fetch", response_model=FetchResponse, tags=["data"])
def fetch_data(
    req: FetchRequest,
    loader: Annotated[DataLoader, Depends(get_loader)],
    cache: Annotated[SQLiteCache, Depends(get_cache)],
) -> FetchResponse:
    # Treat unknown codes as needing both meta and bars; look up name if known
    name_lookup = {c: n for c, n in DEMO_UNIVERSE}
    codes_with_names = [(c, name_lookup.get(c, c)) for c in req.codes]

    if req.synthetic:
        results: dict[str, int] = {}
        for code, name in codes_with_names:
            cache.upsert_stock_meta(code, name, classify_board(code), is_st_name(name))
            df = generate_synthetic_ohlcv(code, req.start, req.end)
            cache.delete_bars(code)
            n = cache.upsert_daily_bars(code, df)
            cache.record_fetch(code, req.start, req.end, n)
            results[code] = n
        return FetchResponse(
            rows_per_code=results,
            total_rows=sum(results.values()),
            used_synthetic=True,
        )

    results = loader.prime_cache(codes_with_names, start=req.start, end=req.end)
    return FetchResponse(
        rows_per_code=results,
        total_rows=sum(results.values()),
        used_synthetic=False,
    )


# --- Backtest endpoints -------------------------------------------------------

@app.post("/api/backtest/run", response_model=BacktestRunResponse, tags=["backtest"])
def run_backtest(
    req: BacktestRequest,
    loader: Annotated[DataLoader, Depends(get_loader)],
    storage: Annotated[RunStorage, Depends(get_storage)],
) -> BacktestRunResponse:
    config_dict = req.model_dump()
    run_id = storage.new_run(config_dict)

    try:
        strategy = create_strategy(req.strategy.type, req.strategy.params)
    except ValueError as e:
        storage.mark_failed(run_id, str(e))
        raise HTTPException(status_code=400, detail=str(e))

    data = loader.load_bars(req.universe, req.config.start, req.config.end)
    if not data:
        msg = f"no cached data for any of {req.universe} in {req.config.start}..{req.config.end}"
        storage.mark_failed(run_id, msg)
        raise HTTPException(status_code=404, detail=msg)
    meta = loader.load_meta(req.universe)

    bt_config = BacktestConfig(
        start=req.config.start,
        end=req.config.end,
        initial_cash=req.config.initial_cash,
        limit_hit_fill_prob=req.config.limit_hit_fill_prob,
        random_seed=req.config.random_seed,
    )

    try:
        bt = Backtester(bt_config, strategy, data, meta)
        result = bt.run()
    except Exception as e:
        storage.mark_failed(run_id, repr(e))
        raise HTTPException(status_code=500, detail=f"backtest failed: {e}")

    storage.save_result(run_id, result)
    return BacktestRunResponse(
        run_id=run_id,
        status="completed",
        summary=_summary_from_dict(result.summary),
    )


@app.get(
    "/api/backtest/results/{run_id}",
    response_model=BacktestResultResponse,
    tags=["backtest"],
)
def get_backtest_result(
    run_id: str,
    storage: Annotated[RunStorage, Depends(get_storage)],
) -> BacktestResultResponse:
    row = storage.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")

    config = BacktestRequest.model_validate(row["config"])
    summary = _summary_from_dict(row["summary"]) if row["summary"] else None

    fills = [
        FillRecord(
            date=f["date"], code=f["code"], side=f["side"],
            shares=int(f["shares"]), price=float(f["price"]), cost=float(f["cost"]),
        )
        for f in row["fills"]
        if not f.get("rejected")
    ]
    rejections = [
        FillRecord(
            date=f["date"], code=f["code"], side=f["side"],
            shares=int(f["shares"]), price=float(f["price"]), cost=float(f["cost"]),
            rejected_reason=f["rejected"],
        )
        for f in row["fills"]
        if f.get("rejected")
    ]
    equity = [
        EquityPoint(date=p["date"], equity=float(p["equity"]))
        for p in row["equity_curve"]
    ]

    return BacktestResultResponse(
        run_id=row["id"],
        status=row["status"],
        config=config,
        summary=summary,
        equity_curve=equity,
        fills=fills,
        rejections=rejections,
        error=row["error"],
    )


@app.get("/api/backtest/runs", response_model=list[BacktestRunListItem], tags=["backtest"])
def list_backtest_runs(
    storage: Annotated[RunStorage, Depends(get_storage)],
    limit: int = Query(50, ge=1, le=500),
) -> list[BacktestRunListItem]:
    return [BacktestRunListItem(**r) for r in storage.list_runs(limit=limit)]


# --- helpers -----------------------------------------------------------------

def _summary_from_dict(d: dict) -> BacktestSummary:
    """Coerce engine summary dict (which has Timestamps) into the Pydantic schema."""
    if d is None:
        return None
    out = dict(d)
    for key in ("max_drawdown_peak", "max_drawdown_trough"):
        v = out.get(key)
        if v is None:
            out[key] = None
        elif hasattr(v, "isoformat"):
            out[key] = v.isoformat() if not isinstance(v, str) else v
        else:
            out[key] = str(v)
    return BacktestSummary(**out)
