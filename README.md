# A-Strategy-Engine

A factor research workstation for A-shares (Chinese stock market / 沪深A股).
End-to-end: alt-data ingestion, factor construction with point-in-time
discipline, rigorous evaluation (IC / quintile / decay), and a Recharts
research dashboard.

Designed as a junior version of a WorldQuant / Citadel-style factor research
bench. See [`docs/STRATEGY.md`](docs/STRATEGY.md) for the honest take on
what this can and can't do, and [`CLAUDE.md`](CLAUDE.md) for the persistent
instructions any AI assistant working on this repo should respect.

---

## Status

| Sprint | What | State |
|---|---|---|
| 1 | Foundation: Factor ABC + IC/quintile/decay framework + Factor 1.1 Northbound Momentum E2E | shipped |
| 2 | Factors 1.2 (NB acceleration), 2.1 (earnings quality), 2.4 (valuation composite), 3.2 (momentum skip-5) | in progress |
| 3 | Composite scoring (equal-weight / IC-weighted / Optuna) + TopNRanker portfolio + walk-forward optimizer | deferred |
| 4 | Frontend Views 2-5 (correlation, backtest results, live screener, factor sandbox) | deferred |
| 5 | Real-data validation: prime CSI 300/500/1000 on owner's Mac; document IC per factor | deferred |
| 6 | Paper trading + drift monitoring | deferred |
| 7 | Portfolio risk layer (vol targeting, sector caps, drawdown breakers) + options | deferred |

Engine kept from the previous design: event-driven bar-by-bar backtest with
T+1, board-specific price limits, lot rounding, stamp tax, commission floor,
suspension detection, walk-forward validation, regime tagging, factor
attribution (post-hoc portfolio decomposition). All reused by Sprint 3's
top-N portfolio strategy.

---

## Table of contents

1. [What this is (and isn't)](#what-this-is-and-isnt)
2. [Quickstart (macOS)](#quickstart-macos)
3. [Architecture tour](#architecture-tour)
4. [Factor library](#factor-library)
5. [A-share constraints modeled](#a-share-constraints-modeled)
6. [REST API reference](#rest-api-reference)
7. [Data layer](#data-layer)
8. [Testing](#testing)
9. [Troubleshooting](#troubleshooting)
10. [Going deeper](#going-deeper)

---

## What this is (and isn't)

**What it is.** A factor research platform that lets you:

- Ingest A-share alt-data: per-stock northbound (Stock Connect) flow,
  margin (融资融券), 龙虎榜 disclosures, limit-up/down pools, fundamentals,
  sector classification — all cached in a local SQLite DB.
- Construct alpha factors via the `Factor` ABC + `FactorContext` (which
  enforces point-in-time data access — no look-ahead by construction).
- Evaluate each factor rigorously: cross-sectional IC time series, IC IR,
  hit rate, quintile spreads (Q1-Q5), monotonicity, turnover, IC decay
  curve across forward horizons.
- Serve everything through a React dashboard so the owner can iterate on
  factor ideas in minutes.

Sprint 3 will add composite scoring + top-N portfolio backtesting with the
existing constraint-correct engine.

**What it isn't.** Not a trading bot, not an indicator strategy builder
(that was the v1 design — deleted in the May 2026 overhaul), not a
black-box ML model. Edge comes from research, discipline, and time on the
right problems. Read [`docs/STRATEGY.md`](docs/STRATEGY.md) before risking
real capital.

Non-goals (settled, do not relitigate):

- **No HFT / market making** — millisecond infrastructure isn't here.
- **No auto-execution** — the platform produces orders for manual review.
- **No daily round-trip strategies** — T+1 forbids them.
- **No claim a factor "works" without OOS analysis** — the runner publishes
  IC / IR / hit rate with sample size labels.

---

## Quickstart (macOS)

Tested on macOS 14+ on both Apple Silicon and Intel.

### 1. Install prerequisites

```bash
brew install python@3.11 node
python3 --version    # 3.11.x
node --version       # v20+
```

Use `python3` / `pip3`, never bare `python`.

### 2. Clone + Python env

```bash
git clone https://github.com/Kaiyuanli7/A-Strategy-Engine.git
cd A-Strategy-Engine

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Re-activate the venv every new terminal: `source .venv/bin/activate`.

### 3. Prime the cache + evaluate a factor (one command)

The fastest demo path uses the synthetic universe — populates ~120 stocks
with realistic-ish OHLCV + fundamentals + northbound flow + valuation in
under a minute, then runs the full evaluation pipeline:

```bash
python scripts/evaluate_factor.py \
    --factor northbound_momentum \
    --start 2023-06-01 --end 2025-12-31 \
    --universe 000300 \
    --rebalance weekly --horizon 20 --lookback 5
```

It prints an IC summary + quintile spread + decay curve and writes a JSON
report to `data/evaluations/`.

> Synthetic mode is for engine-correctness testing only. The numbers are
> meaningless as factor evaluation — there's no signal injected. Run on
> real data (next step) for actual research.

### 4. Real-data path (when you're on a network with eastmoney/sina access)

```bash
# Verify endpoints work; the script flags any AKShare drift.
python scripts/smoke_real_akshare.py

# Prime real CSI 300 constituents + qfq OHLCV + best-effort real northbound.
# Fundamentals / valuation / sector are still filled in synthetically — the
# script labels them clearly in its summary.
python scripts/prime_csi300.py
```

Then re-run `evaluate_factor.py` — same flags, real OHLCV.

### 5. Run the full stack (two terminals)

**Terminal 1 — backend:**

```bash
source .venv/bin/activate
python scripts/run_api.py        # uvicorn on :8000
```

**Terminal 2 — frontend:**

```bash
cd frontend
npm install                       # first time only
npm run dev                       # vite on :5173, proxies /api → :8000
```

Open the app:

```bash
open http://localhost:5173            # Factor Research Lab (home)
open http://localhost:8000/docs       # OpenAPI / Swagger
open http://localhost:8000/api/factors    # JSON list of registered factors
```

Stop either server with `Ctrl+C`.

### 6. Tests

```bash
source .venv/bin/activate
pytest tests/                    # backend
```

Frontend:

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
│   └── STRATEGY.md           # honest assessment + edge catalogue + academic refs
├── astrategy/                # Python package
│   ├── config.py             # constants: cost rates, price limits, board classification
│   ├── data/
│   │   ├── cache.py          # SQLite schema (bars, meta, fundamentals, valuation,
│   │   │                     # northbound, margin, lhb, limit_pool, PIT index members)
│   │   ├── akshare_client.py # AKShare wrapper with retries + multi-endpoint fallbacks
│   │   ├── synthetic.py      # OHLCV/fundamentals/sector/northbound/margin/lhb generators
│   │   ├── loader.py         # cache-first orchestration + prime_* methods
│   │   └── universes.py      # KNOWN_INDICES + load_universe with PIT support
│   ├── factors/              # FACTOR LIBRARY — Sprint 1+
│   │   ├── base.py           # Factor ABC, FactorContext (PIT discipline), FactorParamSpec
│   │   ├── registry.py       # @register_factor + get_factor + list_factors
│   │   ├── northbound.py     # Factor 1.1 NorthboundMomentum (+ 1.2 in Sprint 2)
│   │   ├── fundamental.py    # Factors 2.1, 2.4 (Sprint 2)
│   │   └── technical.py      # Factor 3.2 (Sprint 2)
│   ├── evaluation/           # FACTOR EVALUATION — Sprint 1
│   │   ├── ic.py             # Spearman IC + IR / hit rate / t-stat summary
│   │   ├── quintile.py       # quintile bucketing + long-short spread + monotonicity
│   │   ├── decay.py          # IC at multiple forward horizons
│   │   ├── correlation.py    # pairwise factor rank correlation (scaffold)
│   │   └── runner.py         # evaluate_factor() — end-to-end orchestration
│   ├── engine/               # backtest engine (Sprint 3 wires top-N to this)
│   │   ├── constraints.py    # T+1, price limits, lot rounding, suspension
│   │   ├── costs.py          # commission, stamp tax, transfer fee
│   │   ├── portfolio.py      # cash, positions, T+1 sellable tracking
│   │   ├── orders.py         # Order + Fill dataclasses
│   │   ├── backtest.py       # main bar-by-bar loop
│   │   ├── metrics.py        # Sharpe, max DD, Calmar, FIFO round trips
│   │   ├── walk_forward.py   # rolling train/test validation + overfit flag
│   │   ├── attribution.py    # post-hoc OLS decomposition vs value/mom/size/vol/beta
│   │   └── regime.py         # bull/bear/range/high-vol tagging with hysteresis
│   ├── strategies/
│   │   └── base.py           # Strategy ABC — implemented by Sprint 3 TopNRanker
│   └── api/
│       ├── main.py           # FastAPI app + /api/factors + /api/factors/{name}/evaluate
│       ├── schemas.py        # Pydantic request/response models
│       └── storage.py        # RunStorage + factor_evaluations cache table
├── frontend/                 # React 18 + TS strict + Tailwind + Recharts + Vite
│   └── src/
│       ├── pages/FactorLab.tsx                # the Factor Research Lab
│       ├── components/factor/                 # IC/Quintile/Decay charts + stats panel
│       ├── components/Layout.tsx              # top nav
│       └── api/client.ts + types/api.ts       # typed REST client
├── scripts/
│   ├── evaluate_factor.py    # CLI factor evaluation; auto-primes synthetic if cache empty
│   ├── prime_csi300.py       # prime universe + OHLCV (real or synthetic)
│   ├── smoke_real_akshare.py # verify real AKShare endpoints (run locally on Mac)
│   └── run_api.py            # uvicorn entrypoint
└── tests/                    # pytest, ~150 tests; isolated tmp_path SQLite per test
```

### Design invariants

- **Python 3.11+**, pandas, numpy, scipy, statsmodels, optuna, FastAPI, SQLite.
- **AKShare** is the only data provider. Synthetic mode for offline/CI.
- **React 18 + TS strict + Tailwind + Recharts + Vite** for frontend.
- **Event-driven bar-by-bar** engine (Sprint 3 portfolio backtests).
- **Factor pattern**: `Factor` subclass + `@register_factor` + computed
  through `FactorContext` (strict point-in-time data access).
- **252 trading days/year**, **2.0% risk-free rate** universal convention.

---

## Factor library

| ID | Name | Category | Status | Thesis |
|---|---|---|---|---|
| 1.1 | `northbound_momentum` | flow | shipped | Cumulative Stock Connect inflows lead retail by 2-3 weeks |
| 1.2 | `northbound_acceleration` | flow | Sprint 2 | Acceleration of foreign buying signals strengthening conviction |
| 2.1 | `earnings_quality` | fundamental | Sprint 2 | Rising ROE backed by real OCF → outperformance |
| 2.4 | `valuation_composite` | fundamental | Sprint 2 | Cheap on PE/PB/PS percentile outperforms |
| 3.2 | `momentum_skip` | technical | Sprint 2 | Intermediate momentum (skip-5) per Liu-Stambaugh-Yuan 2019 |

Future sprints add Factors 1.3 (margin sentiment), 1.4 (龙虎榜 institutional),
2.2, 2.3, 3.1, 3.3, 4.1, 4.2, 5.1, 5.2. See CLAUDE.md §4 for the catalogue.

To register a new factor, mirror `astrategy/factors/northbound.py`:

```python
@register_factor
class MyFactor(Factor):
    name = "my_factor"
    category = "flow"   # or "fundamental" / "technical" / "event" / "sector"
    description = "..."
    lookback_days = 30
    rebalance_freq = "weekly"
    _param_specs = [FactorParamSpec(name="lookback", type="int", default=5, min=2, max=60)]

    def compute(self, ctx: FactorContext) -> pd.Series:
        # ctx provides PIT-disciplined data accessors
        ...
```

Add the module to `astrategy/factors/__init__.py` so registration runs on
import.

---

## A-share constraints modeled

All defaults live in `astrategy/config.py` + `engine/constraints.py` +
`engine/costs.py`. A backtest without these produces fake numbers.

| Constraint | Default |
|---|---|
| T+1 settlement | shares bought today can't be sold today |
| Main board (沪市主板/深市主板) limit | ±10% |
| ChiNext (创业板) / STAR (科创板) limit | ±20% |
| Beijing exchange | ±30% |
| ST stocks | ±5% |
| Limit-hit fill probability | 20% (80% reject by default; configurable, seeded) |
| Lot size | 100 shares (1手) |
| Stamp tax | 0.05% on SELL notional only (post Aug 2023) |
| Commission | 0.025% each way, ¥5 floor per trade |
| Transfer fee | 0.001% both sides |
| Suspension detection | volume == 0 or missing date → reject orders |

A factor-driven portfolio that round-trips weekly needs ~0.4% directional
edge per rebalance to break even on costs.

---

## REST API reference

```
GET  /health                                — version + cached stock/run counts
GET  /api/data/universe?index=000300        — PIT index membership (as_of optional)
GET  /api/data/stock/{code}?start=&end=     — OHLCV bars for one stock
GET  /api/data/sectors                      — distinct SW L1 sectors
POST /api/data/fetch                        — prime cache (real or synthetic)

GET  /api/factors                           — list registered factors with metadata
GET  /api/factors/{name}/evaluate
        ?start=&end=&universe=000300&horizon=20&rebalance=weekly&lookback=5
        — run IC + quintile + decay; cached by (params, config) hash

GET  /api/backtest/runs                     — list backtest runs (empty until Sprint 3)
GET  /api/backtest/walk_forward             — list walk-forward runs (empty until Sprint 3)
```

### Example: evaluate a factor

```bash
curl 'http://localhost:8000/api/factors/northbound_momentum/evaluate?\
start=2023-06-01&end=2025-12-31&universe=000300&horizon=20&rebalance=weekly&lookback=5'
```

Returns:

```json
{
  "factor": { "name": "northbound_momentum", "category": "flow", ... },
  "params": { "lookback": 5 },
  "n_dates": 83,
  "n_stocks_avg": 107.0,
  "ic_series": [{"date": "2023-06-09", "ic": 0.04}, ...],
  "ic_summary": { "mean": 0.018, "ir": 0.42, "hit_rate": 0.56, "n": 78, ... },
  "quintile_cum": [{"date": "...", "q1": 0.012, "q5": -0.008, "long_short": 0.020}, ...],
  "quintile_summary": { "long_short_sharpe": 0.31, "monotonicity": 0.78, ... },
  "decay": [{"horizon": 1, "ic_mean": 0.02}, {"horizon": 5, "ic_mean": 0.018}, ...]
}
```

---

## Data layer

### SQLite schema (factor-research tables)

`data/astrategy.db` — single file, auto-created. WAL-safe for concurrent
reads.

| Table | Purpose |
|---|---|
| `daily_bars` | OHLCV per (code, date), forward-adjusted (qfq) |
| `stock_meta` | per code: name, board, is_st, listing_date |
| `index_constituents_pit` | point-in-time index membership (effective/expiry dates) |
| `fundamentals` | per code per report_date: PE, PB, PS, ROE, growth, OCF, NI |
| `valuation_daily` | per code per date: PE, PB, PS, market_cap, float_cap |
| `sector_classification` | per code: SW L1/L2 sector |
| `northbound_daily` | per code per date: holding shares/value/pct, net buy |
| `margin_daily` | per code per date: financing/short balance, daily flow |
| `lhb_disclosure` | per (code, date, seq): seat name, type, buy/sell/net |
| `limit_pool` | per code per date: limit-up/down, consecutive_days, turnover |
| `analyst_estimates` | per code per report_date: EPS/revenue estimates, rating |
| `fetch_log` | what data was fetched when (cache invalidation) |
| `backtest_runs` + `backtest_equity` + `backtest_fills` | Sprint 3+ run persistence |
| `factor_evaluations` | cached IC/quintile/decay results by (factor, params) hash |

### AKShare endpoint drift

AKShare function names change frequently. Every fetcher tries 2-3
fallbacks before failing. Run `python scripts/smoke_real_akshare.py` on a
real network connection (the sandbox 403s on eastmoney/sina) to flag any
drift; the script writes a JSON report you can paste into a PR.

---

## Testing

### Backend

```bash
pytest tests/                                    # full suite
pytest tests/test_factor_northbound.py -v        # one factor
pytest tests/test_evaluation_ic.py -v            # IC computation
pytest -k "factor" -q                            # all factor + evaluation tests
```

Tests use isolated `tmp_path` SQLite files (no shared state). Synthetic
generators produce realistic-ish but seed-deterministic data so factor
tests are reproducible without network.

### Frontend

```bash
cd frontend
npm run typecheck     # tsc --noEmit
npm run build         # tsc -b && vite build
```

---

## Troubleshooting

**"ModuleNotFoundError: akshare"** — `pip install -r requirements.txt`
should pull it in. On Apple Silicon, ensure you're using Python 3.11 (not
the system 3.9 which has wheel issues with `curl_cffi`).

**Empty AKShare results / 403** — the sandbox running Claude Code can't
reach eastmoney/sina. Use `--synthetic` paths. The owner runs real fetches
on a Mac with normal network access.

**SQLite "database is locked"** — kill any uvicorn process with the DB
open, then retry. The cache is single-writer.

**Factor IC near zero on synthetic data** — expected. Synthetic data
contains no signal; non-zero IC would indicate a bug in the evaluation
runner.

---

## Going deeper

- [`CLAUDE.md`](CLAUDE.md) — the operating rules. Read this first.
- [`docs/STRATEGY.md`](docs/STRATEGY.md) — the why behind the design. Edge
  catalogue, A-share market structure, academic references.
- `astrategy/factors/northbound.py` — the canonical factor implementation.
- `astrategy/evaluation/runner.py` — `evaluate_factor()` orchestration.
- `tests/test_factor_*.py` + `tests/test_evaluation_*.py` — reference
  test patterns to copy when adding factors.

### Recommended reading (per `docs/STRATEGY.md` §9)

1. **Liu, Stambaugh, Yuan (2019)** — *Size and Value in China*. JFE 134(1).
2. **Carpenter, Lu, Whitelaw (2021)** — *The real value of China's stock market*. JFE 139(3).
3. **Hung, Li, Wang (2015)** — *Post-earnings announcement drift in the Chinese stock market*. JIFMIM 33.
4. **Lo (2002)** — *The Statistics of Sharpe Ratios*. FAJ 58(4).
5. **López de Prado (2018)** — *Advances in Financial Machine Learning*. Wiley. Skim ch. 1-7.
