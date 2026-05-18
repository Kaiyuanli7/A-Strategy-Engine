# A-Strategy-Engine

A-share (Chinese stock market / 沪深A股) trading strategy research platform.

## Status

- **Phase 1**: data layer + core backtest engine with A-share constraints — ✅ shipped
- **Phase 2**: FastAPI REST server wrapping the engine — ✅ shipped
- **Phase 3**: React + Tailwind frontend (runs list, results dashboard, screener) — ✅ shipped
- **Phase 4**: composable strategies (technical + fundamental + flow conditions) + visual builder — ✅ shipped
- **Phase 5+**: optimizers (grid / Bayesian / walk-forward / genetic) — deferred

## Quickstart (macOS)

Tested on macOS 14+ on both Apple Silicon (M1/M2/M3) and Intel.

### 1. Install prerequisites

If you don't already have Homebrew, install it first:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then install Python 3.11 and Node 20+:

```bash
brew install python@3.11 node
```

Verify the versions (you want Python ≥ 3.11 and Node ≥ 20):

```bash
python3 --version    # Python 3.11.x
node --version       # v20.x or v22.x
```

> Note: macOS ships its own `python` binary (Python 2 on older systems, gone in 14+).
> Always use `python3` and `pip3` — never the bare `python`.

### 2. Clone and set up the Python environment

```bash
git clone https://github.com/Kaiyuanli7/A-Strategy-Engine.git
cd A-Strategy-Engine

# Create + activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install backend deps
pip install -r requirements.txt
```

Whenever you open a new terminal, re-activate with `source .venv/bin/activate`.

### 3. Prime the SQLite cache

```bash
# Real AKShare fetch (requires network access to push2his.eastmoney.com)
python scripts/fetch_data.py

# OR — sandboxed / offline / behind GFW: use the synthetic generator
python scripts/fetch_data.py --synthetic
```

This populates `data/astrategy.db` with 3 years of daily OHLCV plus fundamentals,
sector classification, and northbound flow for the 10-stock demo universe.

### 4. Run a backtest from the CLI

```bash
python scripts/run_ma_backtest.py
```

Prints a metrics table (total return, Sharpe, max drawdown, fills, etc.).

### 5. Run the full stack (API + frontend)

You'll need **two terminal tabs**. In Terminal 1, start the backend:

```bash
source .venv/bin/activate      # if not already active
python scripts/run_api.py      # uvicorn on :8000
```

In Terminal 2, install frontend deps and start Vite:

```bash
cd frontend
npm install                    # only the first time, ~1-2 min
npm run dev                    # vite on :5173, proxies /api → :8000
```

Open the app in your default browser:

```bash
open http://localhost:5173
```

Or open the OpenAPI docs:

```bash
open http://localhost:8000/docs
```

Stop either server with `Ctrl+C` in its terminal.

### 6. Run the test suite

```bash
source .venv/bin/activate
pytest tests/                  # 130 passing
```

And for the frontend:

```bash
cd frontend
npm run typecheck
npm run build
```

### Troubleshooting

**Port already in use** (`OSError: [Errno 48] Address already in use`):

```bash
lsof -ti:8000 | xargs kill     # find + kill whatever owns port 8000
lsof -ti:5173 | xargs kill     # same for the Vite dev port
```

**`pip install akshare` fails on Apple Silicon** with a build error for `jsonpath`:

```bash
pip install --use-pep517 akshare
```

This forces the PEP 517 build path which works around an old setuptools shim.

**System `python` points to Python 2** (very rare on macOS 14+): use `python3 -m pip`
instead of bare `pip` everywhere, or alias inside `~/.zshrc`:

```bash
echo 'alias python=python3' >> ~/.zshrc
echo 'alias pip=pip3' >> ~/.zshrc
source ~/.zshrc
```

**Browser opens with a security warning about the dev cert**: there is no cert — Vite
serves over plain HTTP on `localhost`. Safari sometimes flags this; Chrome and Firefox
don't. Use `open -a "Google Chrome" http://localhost:5173` to bypass.

### REST API examples (Mac)

```bash
# Health + cached state
curl http://localhost:8000/health

# List the demo universe
curl -s http://localhost:8000/api/data/universe | python3 -m json.tool

# Live universe filter — narrow to the ChiNext board
curl -s 'http://localhost:8000/api/data/screener/preview?boards=chinext' | python3 -m json.tool

# Run a composable backtest synchronously (returns run_id + summary)
curl -X POST http://localhost:8000/api/backtest/run \
  -H 'Content-Type: application/json' \
  -d '{
    "strategy": {
      "type": "composable",
      "params": {
        "entry_conditions": [
          {"type": "ma_cross", "fast": 5, "slow": 20, "direction": "up"},
          {"type": "roe_bound", "min": 12}
        ],
        "exit_rules": {"stop_loss_pct": 0.08, "max_hold_days": 30, "signal_reversal": true},
        "sizing": {"method": "equal_weight", "position_size_pct": 0.10},
        "max_positions": 8
      }
    },
    "universe": ["600519","601318","300750","601398","000858","600036","601012","002594","600276","601888"],
    "universe_filter": {"sectors_l1": ["食品饮料","电力设备","医药生物"], "exclude_st": true},
    "config": {"start": "2023-05-18", "end": "2026-05-18", "initial_cash": 1000000}
  }' | python3 -m json.tool

# Retrieve full result by run_id (equity curve + every fill)
curl -s http://localhost:8000/api/backtest/results/<RUN_ID> | python3 -m json.tool
```

Visit `http://localhost:5173/builder` for the visual strategy composer.

## Architecture

- `astrategy/data/` — AKShare wrapper, SQLite cache (OHLCV + fundamentals + sectors + northbound), synthetic fallback
- `astrategy/engine/` — backtest loop with full A-share constraints (T+1, price limits, lot sizes, costs)
- `astrategy/strategies/` — Strategy ABC, dual-MA reference, composable strategy + indicator library + condition specs + sizing methods
- `astrategy/api/` — FastAPI server, Pydantic schemas, backtest persistence
- `frontend/` — React + Tailwind + Recharts SPA (runs list, dashboard, screener, **visual strategy builder**)
- `scripts/` — entry-point scripts (fetch data, run backtest, launch API)
- `tests/` — unit + integration + API tests (130 passing)

## A-Share Constraints Modeled

- T+1 settlement (cannot sell shares bought same day)
- Price limits 涨跌停: main board ±10%, ChiNext/STAR ±20%, ST ±5%, Beijing ±30%
- Probabilistic limit-hit fill failure (80% reject by default)
- 100-share lot rounding
- Stamp tax 0.05% on sells, commission 0.025% each way (¥5 floor), transfer fee 0.001%
- Suspension detection (volume == 0 or missing date)
- Next-bar-open fill timing (no lookahead)
