# A-Strategy-Engine

An A-share (Chinese stock market / 沪深A股) trading strategy research platform.
End-to-end: data layer, backtest engine, REST API, React UI, composable strategy
builder, walk-forward validation with overfit detection, factor attribution, and
per-regime performance breakdown.

Designed for medium-frequency systematic strategies (weekly → monthly rebalance)
on factor and behavioral signals — see [`docs/STRATEGY.md`](docs/STRATEGY.md)
for the honest take on what this platform can and can't do, and
[`CLAUDE.md`](CLAUDE.md) for the persistent instructions any AI assistant
working on this repo should respect.

---

## Status

| Phase | What | State |
|---|---|---|
| 1 | Data layer + backtest engine with full A-share constraints | shipped |
| 2 | FastAPI REST server + Pydantic schemas + persistent run storage | shipped |
| 3 | React + Tailwind + Recharts frontend (runs, dashboard, screener) | shipped |
| 4 | Composable strategies + fundamentals/sector/northbound data + visual builder | shipped |
| 5 | PIT index membership + walk-forward validation + factor attribution + regime tagging | shipped |
| 6 | Grid + Bayesian parameter optimization with overfit guards | deferred |
| 7 | Paper trading + drift monitoring | deferred |
| 8 | Portfolio risk management (vol targeting, sector caps, drawdown breakers) | deferred |
| 9 | Options support (50ETF/300ETF/individual-name; IV rank; defined-risk templates) | deferred |
| 10 | Live broker execution (semi-automatic) | deferred |

Tests: **157 passing**. Frontend typechecks and builds clean.

---

## Table of contents

1. [What this is (and isn't)](#what-this-is-and-isnt)
2. [Quickstart (macOS)](#quickstart-macos)
3. [Architecture tour](#architecture-tour)
4. [Workflows](#workflows)
5. [A-share constraints modeled](#a-share-constraints-modeled)
6. [Strategy reference](#strategy-reference)
7. [REST API reference](#rest-api-reference)
8. [Frontend tour](#frontend-tour)
9. [Data layer](#data-layer)
10. [Testing](#testing)
11. [Troubleshooting](#troubleshooting)
12. [Going deeper](#going-deeper)

---

## What this is (and isn't)

**What it is.** A research platform that lets you:

- Compose long-only A-share strategies (technical + fundamental + flow conditions, AND-combined)
  with exit rules, position sizing, and a universe filter — all through a web UI or JSON spec.
- Backtest those strategies with **honest A-share market constraint modeling**: T+1, board-specific
  price limits (±10% / ±20% / ±5% ST), 100-share lots, stamp tax (0.05% sells), commission
  (0.025% each way, ¥5 floor), transfer fees, suspension detection, probabilistic limit-hit
  fill failure, next-bar-open fills (no lookahead).
- Run **walk-forward validation** to see if a strategy generalizes — concatenated OOS equity
  curves, per-window IS-vs-OOS Sharpe, automatic overfit flag when IS-OOS gap > 0.5.
- Decompose strategy returns against **factor portfolios** (market, value, momentum, size,
  low-vol) and see which **regimes** (bull/bear/range/high-vol) the strategy actually made
  money in.

**What it isn't.** This is **not** a trading bot that prints money. The platform reduces
your uncertainty about whether a strategy works — it doesn't create alpha. Edge comes from
research, discipline, and time spent on the right problems. Read
[`docs/STRATEGY.md`](docs/STRATEGY.md) before risking real capital.

Specific non-goals (settled, do not relitigate):

- **No HFT or market making** — millisecond infrastructure isn't here and won't be.
- **No auto-execution against a live broker** — the platform generates orders for manual
  review; live execution is a future phase requiring 6+ months of clean paper trading first.
- **No daily round-trip strategies** — T+1 forbids them; the engine refuses to model them.
- **No claims a strategy "works" without out-of-sample validation** — every metric the engine
  publishes outside of walk-forward mode is in-sample and labeled as such.

---

## Quickstart (macOS)

Tested on macOS 14+ on both Apple Silicon (M1/M2/M3) and Intel.

### 1. Install prerequisites

If you don't already have Homebrew:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then Python 3.11 + Node 20+:

```bash
brew install python@3.11 node
python3 --version    # Python 3.11.x
node --version       # v20+
```

> macOS-specific: always use `python3` and `pip3` — never bare `python` (which is
> deprecated Python 2 on older systems and gone in 14+).

### 2. Clone and set up the Python environment

```bash
git clone https://github.com/Kaiyuanli7/A-Strategy-Engine.git
cd A-Strategy-Engine

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Re-activate the venv in every new terminal: `source .venv/bin/activate`.

### 3. Prime the SQLite cache

Real path (requires network access to `push2his.eastmoney.com` and `quote.sina.com.cn`):

```bash
python scripts/fetch_data.py        # the 10-stock demo universe
python scripts/prime_csi300.py      # the synthetic-fallback 300-stock universe
```

Offline / sandbox / behind GFW — use synthetic mode:

```bash
python scripts/fetch_data.py --synthetic
python scripts/prime_csi300.py --synthetic   # ~10 min, populates 300 stocks
```

Validate the real AKShare endpoints (run this **before merging Phase 5+ work** to catch
upstream API drift):

```bash
python scripts/smoke_real_akshare.py
```

### 4. Run a CLI backtest

```bash
python scripts/run_ma_backtest.py
```

Prints a metrics table for the dual-MA crossover strategy on the demo universe.

### 5. Run the full stack (two terminals)

**Terminal 1 — backend:**

```bash
source .venv/bin/activate
python scripts/run_api.py        # uvicorn on :8000
```

**Terminal 2 — frontend:**

```bash
cd frontend
npm install                       # only the first time, ~1-2 min
npm run dev                       # vite on :5173, proxies /api → :8000
```

Open the app:

```bash
open http://localhost:5173        # runs list (home)
open http://localhost:5173/builder        # compose a strategy
open http://localhost:5173/walkforward    # walk-forward validation
open http://localhost:8000/docs           # OpenAPI / Swagger
```

Stop either server with `Ctrl+C`.

### 6. Run the test suite

```bash
source .venv/bin/activate
pytest tests/                     # 157 passing
```

Frontend type-check + production build:

```bash
cd frontend
npm run typecheck
npm run build
```

---

## Architecture tour

```
A-Strategy-Engine/
├── CLAUDE.md                 # persistent instructions auto-loaded by Claude Code
├── docs/
│   └── STRATEGY.md           # honest assessment + A-share edge catalog + academic refs
├── astrategy/                # Python package
│   ├── config.py             # constants: cost rates, price limits, board classification
│   ├── data/                 # data layer
│   │   ├── cache.py          # SQLite schema + queries (8 tables: bars, meta, indices, ...)
│   │   ├── akshare_client.py # AKShare wrapper with retries + 3-endpoint fallbacks
│   │   ├── synthetic.py      # GBM OHLCV + synthetic fundamentals/sector/northbound + PIT universe
│   │   ├── loader.py         # high-level cache-first orchestration
│   │   ├── universes.py      # KNOWN_INDICES + load_universe with PIT support
│   │   └── universe.py       # the 10-stock DEMO_UNIVERSE
│   ├── engine/               # backtest engine
│   │   ├── constraints.py    # T+1, price limits, lot rounding, suspension
│   │   ├── costs.py          # commission, stamp tax, transfer fee
│   │   ├── portfolio.py      # cash, positions, T+1 sellable tracking
│   │   ├── orders.py         # Order + Fill dataclasses
│   │   ├── backtest.py       # main bar-by-bar loop + enrich_summary helper
│   │   ├── metrics.py        # Sharpe, max DD, Calmar, FIFO round trips
│   │   ├── walk_forward.py   # rolling train/test validation + overfit flag
│   │   ├── attribution.py    # OLS factor regression (mkt/val/mom/size/vol)
│   │   └── regime.py         # bull/bear/range/high_vol classification
│   ├── strategies/           # strategy implementations
│   │   ├── base.py           # Strategy ABC + StrategyContext
│   │   ├── ma_cross.py       # DualMACrossStrategy reference
│   │   ├── composable.py     # ComposableStrategy (JSON-configurable)
│   │   ├── conditions.py     # 13 ConditionSpec variants (discriminated union)
│   │   ├── indicators.py     # pure SMA/EMA/RSI/Bollinger/MACD/vol functions
│   │   └── sizing.py         # equal_weight / fixed_amount / vol_adjusted
│   └── api/                  # FastAPI server
│       ├── main.py           # endpoints + dependency injection
│       ├── schemas.py        # Pydantic request/response models
│       ├── strategy_factory.py  # JSON spec → Strategy instance registry
│       └── storage.py        # backtest_runs + walk_forward_runs persistence
├── frontend/                 # React + Vite + TypeScript SPA
│   ├── src/
│   │   ├── pages/            # RunsList, Builder, WalkForward, WalkForwardResult, Dashboard, Screener
│   │   ├── components/       # Layout, MetricsPanel, EquityChart, DrawdownChart, FillsTable, ...
│   │   │   └── builder/      # 9-component composable strategy form
│   │   ├── api/client.ts     # typed fetch wrappers
│   │   └── types/api.ts      # TS types mirroring Pydantic models
│   ├── tailwind.config.js
│   └── vite.config.ts
├── scripts/                  # entry points
│   ├── fetch_data.py         # prime cache for the 10-stock demo
│   ├── prime_csi300.py       # prime a 300-stock CSI 300 universe
│   ├── smoke_real_akshare.py # validate real AKShare endpoints locally
│   ├── run_ma_backtest.py    # CLI dual-MA backtest demo
│   └── run_api.py            # uvicorn launcher
├── tests/                    # 157 tests
│   ├── test_constraints.py / test_costs.py / test_portfolio.py / test_metrics.py
│   ├── test_indicators.py / test_conditions.py / test_sizing.py
│   ├── test_composable_strategy.py / test_data_synthetic_extras.py
│   ├── test_pit_membership.py / test_walk_forward.py
│   ├── test_attribution.py / test_regime.py
│   └── test_api.py           # FastAPI TestClient suite
├── data/                     # SQLite DB (gitignored)
├── pyproject.toml
├── requirements.txt
└── README.md
```

### Design invariants

These are settled — see [`CLAUDE.md` §5](CLAUDE.md):

- Python 3.11+, pandas, numpy, FastAPI, SQLite
- AKShare for data + synthetic fallback for sandboxed envs
- React 18 + TypeScript strict + Tailwind + Recharts + Vite
- Event-driven bar-by-bar engine (correctness > speed)
- Strategy ABC pattern: precompute signals in `initialize()`, lookup in `on_bar()`
- Next-bar-open fills (no lookahead)
- 252 trading days/year, 2.0% risk-free rate for Sharpe

---

## Workflows

### A. CLI dual-MA backtest

The simplest workflow — runs against the cached 10-stock demo universe.

```bash
python scripts/run_ma_backtest.py
```

Output:

```
============================================================
Dual MA Crossover Backtest — Phase 1 Deliverable
============================================================
Period:            2023-05-18 → 2026-05-18
Universe:          10 stocks (CSI 300 subset)
Initial Capital:   ¥1,000,000
Final Equity:      ¥1,017,172
Total Return:      1.72%
Annualized Return: 0.59%
Annualized Vol:    3.31%
Sharpe (rf=2%):    -0.43
Max Drawdown:      -9.84% (peak 2023-10-23 → trough 2025-10-24)
Calmar:            0.06
Win Rate:          35.00% (220 closed trades)
Avg Hold Days:     23.1
Turnover (annual): 7.32x
Fills:             445 (rejections: 0)
============================================================
```

These are in-sample numbers on synthetic data — meaningless as a basis for real money.
Use the walk-forward workflow for trustworthy metrics.

### B. UI composable strategy

Navigate to `http://localhost:5173/builder`. Compose entry conditions (AND), exit rules,
position sizing, universe filter. Submit → backtest runs synchronously → redirected to
`/runs/:id` dashboard with full metrics, equity curve, drawdown, fills table, plus
factor attribution and per-regime performance breakdown.

### C. Walk-forward validation

Navigate to `http://localhost:5173/walkforward`. Same composable form plus a "walk-forward
windows" section (train/test/step months + overfit gap threshold). Submit → engine runs the
strategy across rolling train/test windows → redirected to `/walkforward/:runId`:

- Big red **OVERFIT** banner if `|IS - OOS Sharpe gap| > 0.5`
- Aggregate IS vs OOS Sharpe (computed from concatenated daily returns, not mean-of-window-Sharpes)
- Concatenated OOS equity curve
- IS-vs-OOS scatter with y=x reference line (points below = overfit windows)
- Per-window detail table with overfit rows highlighted in red

This is the ONLY trustworthy way to evaluate a strategy. In-sample backtests alone are noise.

### D. Screener + per-stock OHLCV chart

Navigate to `http://localhost:5173/screener`. Browse the cached universe, filter by board
or name, click a stock to see its OHLCV chart.

---

## A-share constraints modeled

These are the difference between a useful tool and "garbage" backtest results. All enforced
in `astrategy/engine/`:

| Rule | Implementation |
|---|---|
| **T+1 settlement** | `Position.sellable` separate from `shares`; unlocked at start of each bar |
| **Main board price limit** (沪/深主板, 60/00 prefix) | ±10% |
| **ChiNext / STAR price limit** (300/301/688 prefix) | ±20% |
| **Beijing exchange** (8/4/92 prefix) | ±30% |
| **ST stocks** | ±5% (overrides board) |
| **Limit-hit fill failure** | 80% reject probability at limit (configurable, seeded RNG) |
| **Lot size** | All orders floor-rounded to multiples of 100 |
| **Stamp tax** | 0.05% on sells only (post Aug 2023) |
| **Commission** | 0.025% each way, **¥5 floor** per trade |
| **Transfer fee** | 0.001% on both sides |
| **Suspension** | Detected via `volume == 0` or missing date → orders rejected |
| **Fill timing** | Next-bar open (signal at N close → execute at N+1 open) |

**Implication for strategy design:** a daily round-trip strategy needs roughly 0.15%
directional edge per trade just to break even before slippage. Bias toward weekly+ hold
periods.

---

## Strategy reference

### `ma_cross` — dual moving-average crossover

Reference implementation; the canonical "strategy ABC pattern" example.

```json
{
  "type": "ma_cross",
  "params": {
    "fast": 5,
    "slow": 20,
    "position_size_pct": 0.05,
    "max_positions": 10
  }
}
```

### `composable` — JSON-configurable strategy

AND-reduces a list of entry conditions, applies exit rules, sizes positions, respects a
universe filter. The platform's main workflow.

```json
{
  "type": "composable",
  "params": {
    "entry_conditions": [
      {"type": "ma_cross", "fast": 5, "slow": 20, "direction": "up"},
      {"type": "roe_bound", "min": 12},
      {"type": "nb_net_inflow", "window": 5, "min_value": 50000000}
    ],
    "exit_rules": {
      "stop_loss_pct": 0.08,
      "take_profit_pct": 0.20,
      "max_hold_days": 30,
      "signal_reversal": true
    },
    "sizing": {"method": "equal_weight", "position_size_pct": 0.10},
    "max_positions": 8
  }
}
```

#### Condition types (13)

**Technical** (use OHLCV only — no extra data needed):

| Type | Params | Fires when |
|---|---|---|
| `ma_cross` | `fast`, `slow`, `direction` (up/down) | fast SMA crosses slow SMA in `direction` |
| `price_vs_ma` | `period`, `op` (>/<) | close `op` SMA(period) |
| `rsi` | `period`, `threshold`, `direction` (above/below/cross_up/cross_down) | RSI vs threshold per `direction` |
| `bollinger_breakout` | `period`, `k`, `band` (upper/lower) | close breaks the band |
| `macd` | `fast`, `slow`, `signal`, `event` | MACD signal event fires |
| `volume_spike` | `period`, `multiple` | today's volume ≥ multiple × N-day avg |

**Fundamental** (require fundamentals data cached — `fetch_data.py --synthetic` provides):

| Type | Params | Fires when |
|---|---|---|
| `pe_bound` | `min`, `max` | PE TTM in [min, max] (either bound optional) |
| `pb_bound` | `min`, `max` | PB in [min, max] |
| `ps_bound` | `min`, `max` | PS TTM in [min, max] |
| `roe_bound` | `min`, `max` | ROE TTM in [min, max] (pct) |
| `revenue_growth` | `min`, `max` | Revenue YoY in [min, max] (pct) |

**Flow** (require northbound data):

| Type | Params | Fires when |
|---|---|---|
| `nb_net_inflow` | `window`, `min_value` | rolling N-day net buy value ≥ min_value (¥) |
| `nb_holding_pct` | `min`, `max` | northbound holding % in [min, max] |

**PIT correctness:** fundamental conditions use `announce_date <= bar_date`, not
`report_date`. The engine forward-fills the most recent ANNOUNCED row up to each bar.

#### Exit rules

```json
{
  "stop_loss_pct": 0.08,        // close ≤ entry × (1 - stop_loss_pct) → SELL
  "take_profit_pct": 0.20,      // close ≥ entry × (1 + take_profit_pct) → SELL
  "max_hold_days": 30,          // (bar_date - entry_date).days ≥ N → SELL
  "signal_reversal": true       // entry condition goes False → SELL
}
```

Stops use **close-only** evaluation (not intrabar high/low) — keeps semantics consistent
with the close-evaluated signals and avoids re-architecting the next-bar-open executor.
Intrabar triggers are deferred.

#### Position sizing

| Method | Params | Behavior |
|---|---|---|
| `equal_weight` | `position_size_pct` | target N% of equity per name, lot-rounded |
| `fixed_amount` | `amount` | buy fixed ¥N worth per name |
| `vol_adjusted` | `target_vol_pct`, `position_size_pct` | scale down position when realized vol > target |

#### Universe filter

```json
{
  "boards": ["main_sh", "main_sz", "chinext"],
  "exclude_st": true,
  "market_cap_min": 50000000000,
  "market_cap_max": null,
  "sectors_l1": ["食品饮料", "电力设备", "医药生物"]
}
```

Applied as an SQL JOIN against `stock_meta` + latest `valuation_daily` + `sector_classification`.
Empty result → 422.

---

## REST API reference

Swagger UI: `http://localhost:8000/docs` when the API is running.

### Meta

| Method | Path | Returns |
|---|---|---|
| `GET` | `/health` | `{status, version, cached_stocks, cached_runs}` |
| `GET` | `/api/strategies` | `{types: ["ma_cross", "composable"]}` |
| `GET` | `/api/strategies/condition-types` | schema for all 13 condition variants (drives the builder UI) |

### Data

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/data/universe` | demo universe with board + ST tags |
| `GET` | `/api/data/stock/{code}?start=&end=` | OHLCV |
| `POST` | `/api/data/fetch` | prime cache for given codes (real or `synthetic: true`) |
| `GET` | `/api/data/screener/preview?boards=&sectors_l1=&market_cap_min=...` | filtered universe count |
| `GET` | `/api/data/sectors` | distinct SW L1 sectors in cache |

### Backtest

| Method | Path | Returns |
|---|---|---|
| `POST` | `/api/backtest/run` | synchronous; returns `run_id` + summary (with factor + regime if data cached) |
| `GET` | `/api/backtest/results/{id}` | full result: config + equity curve + fills + rejections |
| `GET` | `/api/backtest/runs?limit=` | list past runs |

### Walk-forward

| Method | Path | Returns |
|---|---|---|
| `POST` | `/api/backtest/walk_forward` | runs across rolling windows; returns aggregate Sharpes + overfit flag |
| `GET` | `/api/backtest/walk_forward/{id}` | full result: windows + concatenated OOS equity curve |
| `GET` | `/api/backtest/walk_forward?limit=` | list past walk-forward runs |

### Example: composable backtest with universe filter

```bash
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
```

### Example: walk-forward over the same spec

```bash
curl -X POST http://localhost:8000/api/backtest/walk_forward \
  -H 'Content-Type: application/json' \
  -d '{
    "request": { ... same as /api/backtest/run body ... },
    "walk_forward": {
      "train_months": 12,
      "test_months": 3,
      "step_months": 3,
      "min_train_bars": 200,
      "overfit_gap_threshold": 0.5
    }
  }' | python3 -m json.tool
```

Response includes `aggregate_is_sharpe`, `aggregate_oos_sharpe`, `aggregate_gap`,
`overfit_flag`, `n_windows`.

---

## Frontend tour

| Route | Purpose |
|---|---|
| `/` | Runs list — past backtests + one-click "Run dual-MA on demo universe" button |
| `/builder` | Strategy builder — compose conditions + exit/sizing/config, JSON preview, submit |
| `/walkforward` | Walk-forward form — builder + windows config |
| `/walkforward/:runId` | Walk-forward result — IS/OOS Sharpe banner + windows table + scatter + equity curve |
| `/runs/:runId` | Backtest dashboard — 12-metric panel, equity, drawdown, fills, factor + regime panels |
| `/screener` | Universe browser — filter by board + name, per-stock OHLCV chart |

**Stack:** Vite + React 18 + TypeScript strict + Tailwind CSS + Recharts + react-router-dom.

`src/types/api.ts` mirrors every Pydantic model — type safety against the backend contract.
If the API ever drifts, the TS compiler catches it.

---

## Data layer

### SQLite schema (9 tables)

```
daily_bars                   per-stock OHLCV (forward-adjusted)
stock_meta                   name, board, is_st, listing date
index_constituents           DEMO universe (legacy snapshot)
index_constituents_pit       point-in-time index membership with effective/expiry dates
fundamentals                 per-quarter PE/PB/PS/ROE/revenue YoY (announce_date for PIT)
valuation_daily              daily PE/PB/PS + total/float market cap
sector_classification        申万 (SW) L1/L2 classification
northbound_daily             per-day Stock Connect holding + net flow per stock
backtest_runs                config + summary + status for `/api/backtest/run` invocations
backtest_equity              per-run daily equity curve
backtest_fills               per-run fills + rejections
walk_forward_runs            walk-forward run + JSON result blob
fetch_log                    diagnostic record of AKShare fetches
```

### Real AKShare path (recommended for actual research)

```bash
python scripts/smoke_real_akshare.py       # validate endpoints first
python scripts/fetch_data.py               # 10 demo stocks
python scripts/prime_csi300.py             # 300+ stocks with PIT membership
```

Each AKShare call wraps 2-3 fallback endpoints (e.g., `index_stock_cons_csindex` →
`index_stock_cons` → `index_stock_cons_sina`). The wrapper detects empty DataFrames
and Chinese-to-English column renames at the edge.

### Synthetic mode (for sandboxed envs / CI / quick demos)

```bash
python scripts/fetch_data.py --synthetic
python scripts/prime_csi300.py --synthetic
```

- Geometric Brownian motion OHLCV anchored to plausible start prices
- 10 demo stocks have **real sector + plausible PE/PB/ROE anchors** so synthetic-mode
  conditions still produce sane behavior (Moutai gets ~28x PE / 30% ROE; ICBC gets 6x PE
  / 11% ROE)
- 300-stock synthetic universe simulates **5% quarterly turnover** so the
  point-in-time membership codepath isn't vacuous

**Warning:** synthetic backtests are for engine correctness testing only. Do NOT treat
synthetic-mode Sharpes as evidence a strategy works.

### AKShare endpoint drift

AKShare's API surface changes regularly. The codebase guards against this with try-three-
fallbacks in `astrategy/data/akshare_client.py`. If `scripts/smoke_real_akshare.py` flags
a critical failure, paste the output into a PR comment and the fallback chain gets adjusted.

---

## Testing

### Backend

```bash
pytest tests/              # 157 passing
pytest tests/ -v -k rsi    # specific test selection
pytest tests/test_walk_forward.py
```

Coverage areas:

| Area | Tests |
|---|---|
| A-share constraints (T+1, price limits, lot rounding, suspension) | 13 |
| Transaction costs (commission floor, stamp tax) | 4 |
| Portfolio (T+1 sellable tracking, equity calculation) | 8 |
| Metrics (Sharpe, max DD, FIFO round trips) | 8 |
| Indicators (Wilder RSI golden value, MACD, Bollinger, cross detection) | 10 |
| Condition evaluator (all 13 variants + PIT-safety) | 9 |
| Sizing methods | 8 |
| Composable strategy (AND-reduce, stop-loss, max-hold) | 4 |
| Synthetic data generators | 38 |
| PIT index membership | 6 |
| Walk-forward | 6 |
| Factor attribution (OLS regression vs known answers) | 5 |
| Regime classification | 7 |
| FastAPI endpoints (TestClient) | 27 |
| Misc (round_trips idempotency, etc.) | 4 |

### Frontend

```bash
cd frontend
npm run typecheck                 # strict TS
npm run build                     # production bundle (~620 KB, ~175 KB gzipped)
```

---

## Troubleshooting

**Port already in use** (`OSError: [Errno 48] Address already in use`):

```bash
lsof -ti:8000 | xargs kill        # backend port
lsof -ti:5173 | xargs kill        # frontend port
```

**`pip install akshare` fails on Apple Silicon** with a build error for `jsonpath`:

```bash
pip install --use-pep517 akshare
```

This forces the PEP 517 build path which works around an old setuptools shim.

**System `python` points to Python 2** (very rare on macOS 14+):

```bash
echo 'alias python=python3' >> ~/.zshrc
echo 'alias pip=pip3' >> ~/.zshrc
source ~/.zshrc
```

**Browser blocks `localhost` due to dev cert warning** (Safari is more strict than Chrome):

```bash
open -a "Google Chrome" http://localhost:5173
```

**`smoke_real_akshare.py` reports CRITICAL FAILURE** on `csi300_constituents` /
`daily_ohlcv` / `market_index_ohlcv`: the AKShare upstream endpoint changed. Paste the
script output into a PR comment so the fallback chain in `astrategy/data/akshare_client.py`
can be updated.

**Backtest produces zero fills.** Either:
- The universe filter narrowed to zero stocks (check the screener preview badge in `/builder`)
- All entry conditions are too restrictive (try one condition at a time)
- The strategy ran on a date range where data isn't cached (re-run `fetch_data.py`)

**OOS Sharpe > 1.5 on real data.** Default assumption: **the strategy is overfit or there's a
bug**, not skill. Investigate in order:
1. Lookahead (using future data in the entry signal)
2. Survivorship bias (universe filter using today's index, not point-in-time)
3. Transaction costs missing or under-modeled
4. Position sizes too small to trigger commission floor (making fixed-cost trades look free)
5. In-sample-only fitting (use `/walkforward`, not `/builder`)

See [`docs/STRATEGY.md`](docs/STRATEGY.md) §8 for realistic Sharpe bands.

**Walk-forward window has zero fills.** Expected behavior — a window with no trades doesn't
crash, it just contributes nothing to the OOS Sharpe. The strategy/universe may not produce
signals frequently enough for the configured train/test sizes.

---

## Going deeper

- **[`CLAUDE.md`](CLAUDE.md)** — persistent instructions for any AI assistant working in
  this repo. Hard rules, realistic Sharpe bands, anti-patterns. Read this if you're
  contributing changes.
- **[`docs/STRATEGY.md`](docs/STRATEGY.md)** — the honest strategic review. What this
  platform is, what it isn't, A-share edge catalog with academic citations, realistic
  expectations, anti-patterns to recognize. Read this **before risking real capital**.
- **[Original prompt](https://github.com/Kaiyuanli7/A-Strategy-Engine/pull/3)** — the full
  spec the platform was built to address; see PR descriptions for phase-by-phase context.

### Recommended reading list (per `docs/STRATEGY.md` §9)

1. Liu, Stambaugh, Yuan (2019) — *Size and Value in China*
2. Carpenter, Lu, Whitelaw (2021) — *The real value of China's stock market*
3. Hung, Li, Wang (2015) — *Post-earnings announcement drift in the Chinese stock market*
4. Asness, Moskowitz, Pedersen (2013) — *Value and Momentum Everywhere*
5. Lo (2002) — *The Statistics of Sharpe Ratios*
6. López de Prado (2018) — *Advances in Financial Machine Learning* (chapters 1-7)

---

## Roadmap (what's next)

**Phase 6 — Optimization with overfit guards.** Grid search + Optuna Bayesian over
parameter spaces. Critical anti-overfit measures from day one: IS + OOS heatmaps side by
side; reject candidates with IS-OOS gap > 0.5; penalize parameter count.

**Phase 7 — Paper trading + drift monitoring.** Daily live mode: fetch today's close,
generate tomorrow's orders, user submits manually. Drift detector pauses strategies whose
realized Sharpe diverges from backtested expectation by > 1.0 over 3+ months.

**Phase 8 — Portfolio risk management.** Vol targeting (default 12% annualized), sector
caps (max 25%), single-name caps (max 8%), drawdown circuit breakers (-10% pauses new
entries; -15% pauses everything).

**Phase 9 — Options support.** The latent edge — 50ETF/300ETF/individual-name options,
IV rank/percentile signals, covered calls + cash-secured puts + defined-risk verticals.

**Phase 10 — Live broker execution.** Semi-automatic via 同花顺 / 通达信 / brokerage API
after 6+ months of clean paper trading.

See [`CLAUDE.md` §8](CLAUDE.md) for the full phase plan with rationale.

---

## License / contributing

Personal research project. No license intent yet — assume all rights reserved unless
this section says otherwise. Contributors: read `CLAUDE.md` first; the hard rules in §3
are non-negotiable.
