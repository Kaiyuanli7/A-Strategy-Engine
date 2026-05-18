# A-Strategy-Engine

A-share (Chinese stock market / 沪深A股) trading strategy research platform.

## Status

**Phase 1: Bootstrap** — data layer + core backtesting engine with A-share constraint modeling, demonstrated by a dual-MA crossover backtest.

Later phases (FastAPI server, React UI, auto-optimizer, genetic strategy discovery, screener) are deferred.

## Quickstart

```bash
pip install -r requirements.txt

# Prime the SQLite cache with 10 mega-cap CSI 300 stocks (3 years daily OHLCV)
python scripts/fetch_data.py

# Run the demo dual-MA crossover backtest
python scripts/run_ma_backtest.py
```

## Architecture

- `astrategy/data/` — AKShare wrapper, SQLite cache, universe loader
- `astrategy/engine/` — backtest loop with full A-share constraints (T+1, price limits, lot sizes, costs)
- `astrategy/strategies/` — Strategy ABC and reference implementations
- `scripts/` — entry-point scripts (fetch data, run backtest)
- `tests/` — unit + integration tests

## A-Share Constraints Modeled

- T+1 settlement (cannot sell shares bought same day)
- Price limits 涨跌停: main board ±10%, ChiNext/STAR ±20%, ST ±5%, Beijing ±30%
- Probabilistic limit-hit fill failure (80% reject by default)
- 100-share lot rounding
- Stamp tax 0.05% on sells, commission 0.025% each way (¥5 floor), transfer fee 0.001%
- Suspension detection (volume == 0 or missing date)
- Next-bar-open fill timing (no lookahead)
