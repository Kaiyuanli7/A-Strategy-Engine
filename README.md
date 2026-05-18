# A-Strategy-Engine

A-share (Chinese stock market / 沪深A股) trading strategy research platform.

## Status

- **Phase 1**: data layer + core backtest engine with A-share constraints — ✅ shipped
- **Phase 2**: FastAPI REST server wrapping the engine — ✅ shipped
- **Phase 3+**: React UI, optimizers (grid / Bayesian / walk-forward / genetic), screener — deferred

## Quickstart

```bash
pip install -r requirements.txt

# Prime the SQLite cache (real AKShare fetch; --synthetic for offline / sandboxed envs)
python scripts/fetch_data.py
# or:  python scripts/fetch_data.py --synthetic

# Run the demo dual-MA crossover backtest directly
python scripts/run_ma_backtest.py

# OR run the same backtest through the REST API
python scripts/run_api.py            # starts uvicorn on :8000
# then: open http://127.0.0.1:8000/docs  (Swagger UI)
```

### REST API examples

```bash
# Health + cached state
curl http://127.0.0.1:8000/health

# Demo universe
curl http://127.0.0.1:8000/api/data/universe

# Run a backtest synchronously
curl -X POST http://127.0.0.1:8000/api/backtest/run \
  -H 'Content-Type: application/json' \
  -d '{
    "strategy": {"type": "ma_cross", "params": {"fast": 5, "slow": 20}},
    "universe": ["600519","601318","300750","601398","000858"],
    "config": {"start": "2023-05-18", "end": "2026-05-18", "initial_cash": 1000000}
  }'

# Retrieve full result (equity curve + fills) by run_id
curl http://127.0.0.1:8000/api/backtest/results/<RUN_ID>
```

## Architecture

- `astrategy/data/` — AKShare wrapper, SQLite cache, universe loader, synthetic fallback
- `astrategy/engine/` — backtest loop with full A-share constraints (T+1, price limits, lot sizes, costs)
- `astrategy/strategies/` — Strategy ABC and reference implementations
- `astrategy/api/` — FastAPI server, Pydantic schemas, backtest persistence
- `scripts/` — entry-point scripts (fetch data, run backtest, launch API)
- `tests/` — unit + integration + API tests (47 passing)

## A-Share Constraints Modeled

- T+1 settlement (cannot sell shares bought same day)
- Price limits 涨跌停: main board ±10%, ChiNext/STAR ±20%, ST ±5%, Beijing ±30%
- Probabilistic limit-hit fill failure (80% reject by default)
- 100-share lot rounding
- Stamp tax 0.05% on sells, commission 0.025% each way (¥5 floor), transfer fee 0.001%
- Suspension detection (volume == 0 or missing date)
- Next-bar-open fill timing (no lookahead)
