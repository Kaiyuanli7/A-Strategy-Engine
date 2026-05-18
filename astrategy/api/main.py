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
    EquityPoint,
    FactorCorrelationResponse,
    FactorEvaluationResponse,
    FactorMeta,
    FetchRequest,
    FetchResponse,
    FillRecord,
    HealthResponse,
    HoldingResponse,
    PortfolioBacktestRequest,
    PortfolioBacktestResponse,
    PortfolioResultResponse,
    SectorWeightResponse,
    StockBar,
    StockOHLCVResponse,
    UniverseResponse,
    UniverseStock,
    WalkForwardRunListItem,
)
from astrategy.api.storage import RunStorage
from astrategy.composites import (
    EqualWeightComposite,
    FactorWeight,
    FixedWeightComposite,
    SignedICWeightedComposite,
)
from astrategy.config import classify_board, is_st_name
from astrategy.data.cache import SQLiteCache
from astrategy.data.loader import DataLoader
from astrategy.data.universes import KNOWN_INDICES, load_universe
from astrategy.engine.backtest import Backtester, BacktestConfig, enrich_summary
from astrategy.evaluation.correlation import pairwise_factor_correlation
from astrategy.evaluation.runner import (
    _rebalance_dates,
    _resolve_universe,
    evaluate_factor,
    EvaluationConfig,
)
from astrategy.factors import get_factor, list_factors
from astrategy.strategies.holdings import (
    derive_final_holdings,
    derive_sector_exposure,
)
from astrategy.strategies.top_n_ranker import TopNRankerStrategy

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
    # Factor-specific tunables (None means use the factor's default)
    lookback: int | None = Query(None, description="Factor 1.1, 3.2: trailing window."),
    window: int | None = Query(None, description="Factor 1.2: per-side flow window."),
    gap: int | None = Query(None, description="Factor 1.2: gap between flow windows."),
    skip: int | None = Query(None, description="Factor 3.2: days to skip at the end."),
    min_ocf_ratio: float | None = Query(None, description="Factor 2.1: OCF/NI gate."),
    history_days: int | None = Query(None, description="Factor 2.4: percentile lookback."),
    use_cache: bool = Query(True),
) -> FactorEvaluationResponse:
    factor_cls = get_factor(name)
    if factor_cls is None:
        raise HTTPException(status_code=404, detail=f"unknown factor '{name}'")

    # Forward only the params the factor declares; ignore extras.
    valid = {p.name for p in factor_cls.param_specs()}
    incoming = {
        "lookback": lookback, "window": window, "gap": gap, "skip": skip,
        "min_ocf_ratio": min_ocf_ratio, "history_days": history_days,
    }
    params = {k: v for k, v in incoming.items() if v is not None and k in valid}
    try:
        factor = factor_cls(**params)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

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


@app.get(
    "/api/factors/correlation",
    response_model=FactorCorrelationResponse,
    tags=["factors"],
)
def factor_correlation(
    cache: Annotated[SQLiteCache, Depends(get_cache)],
    factors: str = Query(..., description="Comma-separated factor names (2-10)."),
    start: str = Query("2023-01-01"),
    end: str = Query("2024-12-31"),
    universe: str = Query("000300"),
    rebalance: str = Query("monthly", pattern="^(daily|weekly|monthly)$"),
) -> FactorCorrelationResponse:
    """
    Pairwise Spearman rank correlation between factor scores, averaged across
    rebalance dates.

    Use this to prune redundant factors before building a composite. Two
    factors with correlation > 0.7 are mostly carrying the same information;
    pick the one with stronger IC. Per CLAUDE.md §9 — combining low-correlation
    factors is the sane way to get composite IC > best individual IC.
    """
    names = [n.strip() for n in factors.split(",") if n.strip()]
    if len(names) < 2:
        raise HTTPException(
            status_code=400,
            detail="need at least 2 factors for correlation",
        )
    if len(names) > 10:
        raise HTTPException(
            status_code=400,
            detail="max 10 factors per correlation request",
        )

    # Construct each factor at defaults; ignore param tuning here.
    constructed: list = []
    for name in names:
        factor_cls = get_factor(name)
        if factor_cls is None:
            raise HTTPException(status_code=400, detail=f"unknown factor '{name}'")
        constructed.append(factor_cls())

    # Compute scores at each rebalance date for each factor.
    reb_dates = _rebalance_dates(start, end, rebalance)
    scores_by_factor: dict[str, dict] = {f.name: {} for f in constructed}
    for d in reb_dates:
        universe_codes = _resolve_universe(cache, universe, d.strftime("%Y-%m-%d"))
        if not universe_codes:
            continue
        ctx_obj = type("ctx", (), {})()
        from astrategy.factors.base import FactorContext
        ctx_obj = FactorContext(cache=cache, universe=universe_codes, as_of=d)
        for f in constructed:
            try:
                scores = f.compute(ctx_obj)
            except Exception as e:
                log.warning("factor %s compute failed at %s: %s", f.name, d, e)
                continue
            if scores is not None and not scores.empty:
                scores_by_factor[f.name][d] = scores

    matrix = pairwise_factor_correlation(scores_by_factor)
    matrix_ordered = matrix.reindex(index=names, columns=names)
    matrix_values = [
        [float(matrix_ordered.iloc[i, j]) for j in range(len(names))]
        for i in range(len(names))
    ]

    n_dates = max(
        (len(scores_by_factor[name]) for name in names if name in scores_by_factor),
        default=0,
    )

    return FactorCorrelationResponse(
        factors=names, matrix=matrix_values,
        universe=universe, start=start, end=end,
        rebalance=rebalance, n_dates=n_dates,
    )


# --- Portfolio (Sprint 3) -------------------------------------------------

@app.post(
    "/api/portfolios/backtest",
    response_model=PortfolioBacktestResponse,
    tags=["portfolios"],
)
def run_portfolio_backtest(
    req: PortfolioBacktestRequest,
    cache: Annotated[SQLiteCache, Depends(get_cache)],
    storage: Annotated[RunStorage, Depends(get_storage)],
    loader: Annotated[DataLoader, Depends(get_loader)],
) -> PortfolioBacktestResponse:
    """Build composite + TopNRankerStrategy, run Backtester, persist result."""
    config_dict = req.model_dump()
    run_id = storage.new_run(config_dict)

    # 1. Resolve universe (PIT-aware).
    try:
        if req.universe.isdigit() and len(req.universe) == 6:
            universe = load_universe(req.universe, as_of=req.end, cache=cache)
            if not universe:
                universe = cache.all_meta_codes()
        else:
            universe = cache.all_meta_codes()
    except Exception as e:
        storage.mark_failed(run_id, f"universe resolution failed: {e}")
        raise HTTPException(status_code=400, detail=f"universe resolution failed: {e}")
    if not universe:
        storage.mark_failed(run_id, "empty universe")
        raise HTTPException(status_code=404, detail="empty universe; prime the cache first")

    # 2. Build factor instances from the composite spec.
    try:
        factor_weights = _build_factor_weights(req.composite.factors)
    except (ValueError, TypeError) as e:
        storage.mark_failed(run_id, str(e))
        raise HTTPException(status_code=400, detail=str(e))

    # 3. Build composite.
    composite = _build_composite(req.composite, factor_weights)

    # 4. Build the TopNRankerStrategy.
    strategy = TopNRankerStrategy(
        composite=composite,
        top_n=req.portfolio.top_n,
        rebalance_freq=req.portfolio.rebalance_freq,
        max_sector_pct=req.portfolio.max_sector_pct,
        max_single_position_pct=req.portfolio.max_single_position_pct,
        min_market_cap=req.portfolio.min_market_cap,
        exclude_st=req.portfolio.exclude_st,
        weighting=req.portfolio.weighting,
        cache=cache,
    )

    # 5. Load cached bars for the universe.
    data = loader.load_bars(universe, req.start, req.end)
    if not data:
        storage.mark_failed(run_id, "no cached bars for universe")
        raise HTTPException(
            status_code=404,
            detail=f"no cached bars for universe={req.universe} in {req.start}..{req.end}",
        )
    meta = loader.load_meta(universe)

    bt_config = BacktestConfig(
        start=req.start, end=req.end,
        initial_cash=req.initial_cash,
        limit_hit_fill_prob=req.limit_hit_fill_prob,
        random_seed=req.random_seed,
    )

    try:
        bt = Backtester(bt_config, strategy, data, meta)
        result = bt.run()
    except Exception as e:
        storage.mark_failed(run_id, repr(e))
        raise HTTPException(status_code=500, detail=f"backtest failed: {e}")

    # 6. Enrich with attribution + regime (best-effort; needs market index cached).
    try:
        enrich_summary(result, cache, universe, req.start, req.end)
    except Exception as e:
        log.warning("portfolio summary enrichment skipped: %s", e)

    storage.save_result(run_id, result)
    return PortfolioBacktestResponse(
        run_id=run_id, status="completed",
        summary=_json_safe_summary(result.summary),
    )


@app.get(
    "/api/portfolios/runs/{run_id}",
    response_model=PortfolioResultResponse,
    tags=["portfolios"],
)
def get_portfolio_run(
    run_id: str,
    storage: Annotated[RunStorage, Depends(get_storage)],
    cache: Annotated[SQLiteCache, Depends(get_cache)],
) -> PortfolioResultResponse:
    row = storage.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")

    config = PortfolioBacktestRequest.model_validate(row["config"])
    fills_dicts = [f for f in row["fills"] if not f.get("rejected")]
    fills = [
        FillRecord(date=f["date"], code=f["code"], side=f["side"],
                   shares=int(f["shares"]), price=float(f["price"]),
                   cost=float(f["cost"]))
        for f in fills_dicts
    ]
    rejections = [
        FillRecord(date=f["date"], code=f["code"], side=f["side"],
                   shares=int(f["shares"]), price=float(f["price"]),
                   cost=float(f["cost"]), rejected_reason=f["rejected"])
        for f in row["fills"] if f.get("rejected")
    ]
    equity = [EquityPoint(date=p["date"], equity=float(p["equity"]))
              for p in row["equity_curve"]]

    # Derive end-state holdings + sector exposure from the fills timeline.
    held_codes = sorted({f["code"] for f in fills_dicts})
    bars_by_code = {}
    for code in held_codes:
        df = cache.get_daily_bars(code, config.start, config.end)
        if not df.empty:
            bars_by_code[code] = df.set_index("date").sort_index()
    sector_map_raw = cache.get_sectors(held_codes) if held_codes else {}
    sector_map = {c: m.get("sw_l1_name") for c, m in sector_map_raw.items()}

    raw_holdings = derive_final_holdings(
        fills_dicts, bars_by_code=bars_by_code, sector_map=sector_map,
    )
    holdings = [
        HoldingResponse(
            code=h.code, shares=h.shares, avg_cost=h.avg_cost,
            market_value=h.market_value, pnl=h.pnl, pnl_pct=h.pnl_pct,
            last_price=h.last_price, entry_date=h.entry_date, sector=h.sector,
        )
        for h in raw_holdings
    ]
    raw_sectors = derive_sector_exposure(raw_holdings)
    sector_exposure = [
        SectorWeightResponse(
            sector=s.sector, weight=s.weight,
            n_stocks=s.n_stocks, market_value=s.market_value,
        )
        for s in raw_sectors
    ]

    return PortfolioResultResponse(
        run_id=row["id"], status=row["status"],
        config=config, summary=row["summary"],
        equity_curve=equity, fills=fills, rejections=rejections,
        final_holdings=holdings, sector_exposure=sector_exposure,
        error=row["error"],
    )


@app.get(
    "/api/portfolios/runs",
    response_model=list[BacktestRunListItem],
    tags=["portfolios"],
)
def list_portfolio_runs(
    storage: Annotated[RunStorage, Depends(get_storage)],
    limit: int = Query(50, ge=1, le=500),
) -> list[BacktestRunListItem]:
    return [BacktestRunListItem(**r) for r in storage.list_runs(limit=limit)]


def _build_factor_weights(specs: list) -> list[FactorWeight]:
    out: list[FactorWeight] = []
    for spec in specs:
        factor_cls = get_factor(spec.factor_name)
        if factor_cls is None:
            raise ValueError(f"unknown factor '{spec.factor_name}'")
        # Filter params against the factor's declared param_specs
        valid_names = {p.name for p in factor_cls.param_specs()}
        params = {k: v for k, v in (spec.params or {}).items() if k in valid_names}
        out.append(FactorWeight(factor=factor_cls(**params), weight=spec.weight))
    return out


def _build_composite(composite_spec, factor_weights):
    if composite_spec.method == "equal_weight":
        return EqualWeightComposite(factor_weights)
    if composite_spec.method == "signed_ic_weighted":
        return SignedICWeightedComposite(
            factor_weights,
            rolling_window=composite_spec.rolling_window,
            min_ic_abs=composite_spec.min_ic_abs,
        )
    if composite_spec.method == "fixed_weight":
        # Every FactorWeight must have an explicit weight set
        for fw in factor_weights:
            if fw.weight is None:
                raise ValueError(
                    f"fixed_weight composite requires explicit weights; "
                    f"factor {fw.factor.name!r} has weight=None"
                )
        return FixedWeightComposite(factor_weights)
    raise ValueError(f"unknown composite method '{composite_spec.method}'")


def _json_safe_summary(d: dict | None) -> dict | None:
    if d is None:
        return None
    out: dict = {}
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif hasattr(v, "item"):
            out[k] = v.item()
        else:
            out[k] = v
    return out


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
