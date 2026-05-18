# CLAUDE.md — instructions for any Claude session working on this repo

This file is loaded automatically at the start of every Claude Code session in this
repository. Read it fully before doing anything substantive. Update it (and bump the
version below) when goals or constraints shift.

**Last revised:** 2026-05-18 · **Version:** 2.0

---

## 0. Project identity

A-share (沪深A股) **factor research workstation**. Not a generic backtester. Not a
broker. Not an indicator-rule strategy builder (that was the v1 design — deleted in
the May 2026 overhaul).

The product is a junior version of a WorldQuant / Citadel-style factor research bench:

1. Ingest alternative + fundamental A-share data (northbound flow, margin, 龙虎榜,
   limit-up pools, fundamentals, sectors).
2. Construct individual alpha factors with explicit point-in-time discipline.
3. Evaluate each factor rigorously: IC time series, IC IR, hit rate, quintile
   spread, decay curve, regime conditioning.
4. Combine validated factors into composite scores.
5. Rank the universe, build a top-N portfolio, backtest it with real A-share costs
   and constraints.
6. Serve the entire workflow through a React dashboard so the owner can iterate on
   factor ideas in minutes.

The owner is a **college junior**, junior analyst at a university investment fund,
incoming summer intern at **CSC Financial (中信建投)**, active options trader.
Sophisticated user, zero institutional infrastructure (no Bloomberg, no proprietary
data, no co-located servers).

---

## 1. What we are actually trying to achieve (priority-ordered)

1. **Make money trading A-shares.** Build a top-N factor-ranked portfolio (weekly
   rebalance) with out-of-sample Sharpe in the 0.6-1.2 band, net of all costs.
2. **Build credibility for the CSC Financial internship.** A serious factor research
   process — IC analysis, walk-forward weight optimization, factor attribution —
   visible in this repo.
3. **Provide a working research tool for the university investment fund.**
4. **Learn quant finance properly.** Meta-goal that compounds the others.

When you are making a tradeoff and unsure, **default to goal #1**. A platform that
genuinely helps the owner make money also satisfies #2, #3, and #4 by construction.

---

## 2. Success criteria — when have we "arrived"?

This project succeeds when the owner can:

- Show a library of **validated alpha factors**, each documented with: mean IC > 0.03
  OOS, IC IR > 0.5, positive quintile monotonicity, decay curve, regime breakdown.
- Run a composite of ≤5 of these factors against the full CSI 300 (then 500 / 1000)
  and produce a top-N portfolio with OOS Sharpe 0.6-1.2 over a 12+ month walk-forward
  window.
- Paper-trade that portfolio for 3-6 months with clean factor attribution and a
  trade journal.
- Confidently say what each factor is loading on, why the edge persists, and what
  would invalidate it.
- Deploy real capital with portfolio-level risk discipline (sector caps, vol
  targeting, drawdown circuit breakers) and follow the system rather than overriding it.

A platform demo that just produces pretty charts is **not** success. A clean codebase
that doesn't include real validation is **not** success. A factor with IC > 0.05 only
in-sample is **not** success.

---

## 3. Hard rules — never violate these

Non-negotiable. If a request seems to ask you to break one of them, push back
explicitly rather than complying.

### Factor research

1. **NEVER claim a factor "works" without out-of-sample IC analysis.** Show IC
   series, mean IC, IR, hit rate, and quintile spread before declaring victory.
2. **NEVER optimize factor weights in-sample only.** Walk-forward is mandatory —
   default 12-month train, 3-month test, rolling. Show IS vs OOS Sharpe side by side.
3. **WARN when IS-OOS Sharpe gap exceeds 0.5.** That's the overfit detector. Add it
   as a hard gate before promoting a composite to paper trading.
4. **NEVER cap a composite above 5 factors.** Each extra factor steals OOS
   degrees-of-freedom. If a request needs 8 factors, push back and suggest fewer +
   walk-forward.
5. **Suspect any factor with IC > 0.10** on real data. The realistic ceiling for a
   single factor on A-shares is ~0.06 net of trading costs. > 0.10 means almost
   certainly look-ahead, survivorship bias, or a data leak. Investigate.
6. **Look-ahead is the #1 killer.** All `FactorContext` getters return data with
   timestamps strictly **before** `as_of`. Don't bypass them. Don't read raw bars
   for `as_of` itself. Don't use fundamentals before their announce_date.

### Trading & validation

7. **NEVER auto-execute live trades.** The platform produces orders for manual
   review. Live broker integration, when it exists, is opt-in per-order.
8. **NEVER present synthetic-data evaluation numbers as real performance.** The
   synthetic path exists only for engine correctness testing and offline demos.
9. **REFUSE to remove A-share constraints** (T+1, price limits, lot sizes, stamp
   tax, commission floor, suspension detection) "just for testing." A backtest
   without these produces fake numbers.

### Realistic IC / Sharpe ranges

| Setup | Realistic (net) | Flag if you see |
|---|---|---|
| Single factor, mean IC | 0.02 – 0.06 | > 0.10 = bug or leak |
| Single factor, IC IR | 0.3 – 1.0 | > 1.5 = look for the bug |
| Composite (≤5 factors), OOS Sharpe | 0.6 – 1.2 | > 2.0 = almost certainly overfit |
| In-sample only (any setup) | meaningless | "alpha" here is regression-to-training |
| Synthetic data (any setup) | meaningless | the data has no signal |

If a factor evaluation comes back with mean IC > 0.10 on real data, **the default
assumption is overfitting, look-ahead, or a bug** — not skill. Investigate.

### Code

10. **Tests required** for new factor / evaluation / data-ingestion code. The
    pattern is established under `tests/test_factor_*.py`,
    `tests/test_evaluation_*.py`, `tests/test_data_*.py`. Mirror them.
11. **No silent data conversions.** AKShare returns Chinese column names, fraction
    vs percent inconsistencies, NaN vs empty distinctions. Normalize at the edge
    (`astrategy/data/akshare_client.py`), assert in tests, never let it propagate.
12. **No new dependencies without justification.** Adding `polars`, `vectorbt`,
    `qlib`, etc. needs an explicit reason. We've already chosen pandas + scipy +
    statsmodels + optuna and the cache-first SQLite pattern.

---

## 4. Factor edges to pursue (and what NOT to)

The factor library targets these categories. Each phase adds factors to one or more.

### Flow factors (资金流向) — highest priority

- **Northbound Momentum (Factor 1.1)** — trailing northbound net-buy / float cap.
  *Implemented*. Cumulative Stock Connect inflows lead retail by 2-3 weeks.
- Northbound Holding Acceleration (1.2) — second derivative of northbound flow.
- Margin Sentiment Divergence (1.3) — margin balance change vs price action.
  Retail leverage is the dumb money in A-shares; fading it is profitable.
- 龙虎榜 Institutional Net Buying (1.4) — net buying by 机构专用 seats minus
  hot-money 游资 seats.

### Fundamental factors (基本面)

- Earnings Quality (2.1), Revenue Acceleration (2.2), Earnings Surprise / PEAD
  (2.3), Valuation Composite (2.4).

### Technical / behavioral (技术/行为)

- Short-term reversal with volume divergence (3.1), Momentum skip-5 (3.2),
  Volatility-adjusted momentum (3.3).
- Liu, Stambaugh, Yuan 2019 ("Size and Value in China") is the canonical citation.

### Event factors (涨停 / 跌停)

- Limit-up continuation probability (4.1), Post-limit-down recovery (4.2).
  Highly A-share specific; behavioral; need clean limit_pool data.

### Sector rotation (板块轮动)

- Sector momentum relative (5.1), Sector flow concentration (5.2).
  Captures policy / theme-driven sector waves.

### Don't waste time on

- **HFT / market making** — millisecond infra needed, retail has none.
- **Daily round-trip strategies** — T+1 + costs make these unprofitable by
  construction.
- **News-sentiment NLP on Chinese text** — institutions have the same APIs,
  plus human analysts; negative EV unless owner has proprietary text.
- **Pure black-box ML on price data** — overfits catastrophically at retail
  scale. ML is fine as a layer on top of a thesis-driven factor, not as the thesis.
- **Beating CSC's own prop desk** — they ARE the market in mid-cap A-shares.

---

## 5. Engineering invariants (settled decisions)

Don't relitigate these unless explicitly asked:

- **Python 3.11+**, pandas, numpy, scipy, statsmodels, optuna, FastAPI, SQLite.
- **AKShare** as primary data source; synthetic fallback for sandboxed/offline.
  Real AKShare endpoints drift — every call has a try-three-fallbacks pattern in
  `astrategy/data/akshare_client.py`.
- **React 18 + TypeScript strict + Tailwind + Recharts + Vite** for frontend.
- **Event-driven bar-by-bar backtest engine** for the eventual portfolio backtests
  (Sprint 3) — correctness over speed.
- **Factor pattern**: every factor is a subclass of `Factor` in
  `astrategy/factors/`, registered via `@register_factor`, computed through
  `FactorContext` which enforces point-in-time data access.
- **252 trading days/year**, **2.0% risk-free rate** for any Sharpe math —
  universal convention.

---

## 6. A-share constraints — always modeled correctly

These are the difference between a useful tool and "garbage" (owner's word). Live
in `astrategy/engine/constraints.py` + `costs.py`:

| Constraint | Default |
|---|---|
| T+1 settlement | shares bought today can't be sold today |
| Main board price limit (沪市主板/深市主板) | ±10% |
| ChiNext / STAR (创业板/科创板) | ±20% |
| Beijing exchange | ±30% |
| ST stocks | ±5% |
| Limit-hit fill probability | 20% (80% reject by default; configurable, seeded) |
| Lot size | 100 shares (1手) |
| Stamp tax | 0.05% on SELL notional only (post Aug 2023) |
| Commission | 0.025% each way, ¥5 floor per trade |
| Transfer fee | 0.001% both sides |
| Suspension detection | volume == 0 or missing date → reject orders |

A factor-driven portfolio that round-trips weekly needs ~0.4% directional edge per
rebalance to break even on costs. Bias toward holding periods that respect this.

---

## 7. Current state (as of 2026-05-18)

PR `claude/overhaul-codebase-O7UJJ` ships the factor-research foundation:

- **Deleted** the indicator/composable-strategy paradigm (composable.py,
  conditions.py, indicators.py, ma_cross, DEMO_UNIVERSE, builder frontend).
- **Kept and reused** the event-driven backtest engine + T+1 / price-limit /
  cost layer, walk-forward, regime tagging, attribution, AKShare retry/fallback
  client, SQLite cache, PIT index membership, synthetic generators.
- **Added** the `astrategy/factors/` package (Factor ABC, registry,
  FactorContext) and `astrategy/evaluation/` package (IC, quintile, decay,
  correlation, runner).
- **Added Factor 1.1 — Northbound Momentum** end-to-end: data → compute → IC /
  quintile / decay evaluation → cached REST endpoint → React Factor Lab page.
- **Added alt-data tables**: margin_daily, lhb_disclosure, limit_pool,
  analyst_estimates (scaffold for Factors 1.3, 1.4, 4.1, 4.2, 2.3).
- **Added AKShare client methods**: get_northbound_holdings,
  get_margin_detail, get_lhb_disclosure, get_limit_pool, get_analyst_ratings,
  each with retry + Chinese-column normalization.
- **Added loader methods**: prime_northbound_individual, prime_margin,
  prime_lhb, prime_limit_pools, prime_analyst_estimates.
- **Rewrote API**: /api/factors, /api/factors/{name}/evaluate.
- **Rewrote frontend**: single Factor Research Lab view with selector,
  parameter tuner, IC chart, quintile chart, decay chart, diagnostics panel.
- **Smoke-script extended** to validate the new endpoints on the owner's Mac.

**Critical gap closing in progress:** the sandbox running Claude Code can't reach
eastmoney/sina (403). The owner must run `scripts/smoke_real_akshare.py` and the
priming scripts on their Mac to validate the real-data path. Everything in this
sandbox runs against synthetic data, which is for engine testing only — its
factor evaluations are **noise**, not signal.

---

## 8. Sprint roadmap (post-overhaul)

Sprint 1 ✓ (this PR): Foundation + Factor 1.1 E2E.

Next sprints in priority order:

### Sprint 2 — Factors 1.2 through 5.2 (the rest of the library)

- Implement the remaining eleven factors from the catalogue in §4.
- Each gets: implementation + unit tests + synthetic generator if needed +
  IC evaluation on the synthetic universe (engine sanity check) + real-data
  validation on the owner's Mac.
- Add the factor correlation matrix view to the frontend.

### Sprint 3 — Composite + portfolio + walk-forward optimizer

- IC-weighted composite (rolling 60-day IC weights).
- Equal-weight rank composite as baseline.
- Top-N portfolio strategy (`TopNRankerStrategy`) wired to the existing
  backtest engine.
- Walk-forward weight optimization via optuna with overfit guards
  (regularization toward equal weights, complexity penalty).
- Backtest results page + walk-forward results page in the frontend.

### Sprint 4 — Frontend Views 2-5

- Factor Correlation Dashboard
- Portfolio Backtest Results (re-add)
- Live Screener (top-N + per-factor sub-scores)
- Factor Discovery Sandbox (custom factor formula DSL)

### Sprint 5 — Real-data validation + universe scale-up

- Owner runs `prime_csi300.py` (real mode) + `prime_csi500.py` + `prime_csi1000.py`
  on Mac.
- Real AKShare smoke results trigger fallback-chain updates if endpoints drift.
- Re-evaluate every factor on the real universe; document IC / IR / hit rate
  per factor in `docs/STRATEGY.md`.

### Sprint 6+ — Paper trading + drift monitoring (was old Phase 7)

### Sprint 7+ — Portfolio risk layer + options (was old Phase 8-9)

---

## 9. Decision framework — when working, ask:

Before adding a feature, ask **all five**:

1. **Does this move the owner toward making money?** (vs. demo polish)
2. **Would CSC's quant team consider this rigorous?** (vs. retail-tier shortcuts)
3. **Does this respect the hard rules in §3?** (no overfit-enabling features)
4. **Does the underlying factor have a documented OOS edge?** (mean IC > 0.03,
   quintile monotonicity positive)
5. **Is this in scope for the current sprint?** (no Sprint 4 work while Sprint 2
   factors are unbuilt)

If three or more are "no," push back instead of complying.

When choosing between two implementations, prefer:
- **Correctness over speed.** Vectorization comes after a passing test.
- **Explicit over clever.** Junior quant readers must understand the code.
- **Settled patterns over new abstractions.** Mimic existing factor / evaluation
  patterns.
- **Conservative over aggressive defaults.** Higher commissions, lower fill
  probabilities, wider stops — the user can loosen them deliberately.

---

## 10. Anti-patterns — push back when you see these

If the owner (or any contributor) asks for something matching these, **flag it**
before doing:

- "Factor X has IC 0.12" → suspicious; check look-ahead, surv bias, cost-side
  of forward return calculation.
- "Composite with 10 factors" → no; cap at 5; complexity penalty kicks in.
- "Factor weights tuned in-sample" → no; walk-forward only.
- "Let's skip IC analysis for this one" → no; that's the validation step.
- "Let's skip the quintile chart, just look at IC" → no; monotonicity is a
  separate sanity check.
- "Ship without tests" → no; the test patterns are established.
- "Let's deploy this composite live with real money" → only after 6+ months
  paper trading with clean attribution.
- "Add a daily round-trip strategy" → T+1 + costs make this almost always
  unprofitable.
- "Build a sentiment NLP module" → very low EV unless owner has proprietary text.
- "Let's just mock the data for the real factor evaluation" → no; synthetic is
  for engine testing, not factor validation.

---

## 11. CSC internship lens

When making feature decisions, periodically ask: **would this impress a CSC senior
quant?**

Things they WILL care about:

- Honest IS vs OOS reporting on every composite.
- Per-factor IC / IR / hit rate / decay tables.
- Factor correlation matrix (do your factors actually carry independent signal?).
- Walk-forward methodology, regime-conditional performance.
- A-share market structure knowledge (T+1, limit moves, 印花税, 国家队, 北向 flow).
- Paper trading track record with factor attribution.
- Smart questions about THEIR research (the platform should leave room for it).

Things they will NOT care about:

- React component architecture.
- Line of code count, test count.
- Number of factors implemented (depth > breadth — five well-evaluated factors >
  twelve half-evaluated ones).
- Pretty charts beyond what's needed for analysis.

---

## 12. Concrete next 90 days (the actual plan)

In priority order, weeks 1-12:

| Weeks | Work |
|---|---|
| 1 | Owner runs the new prime scripts on real CSI 300 data. Validate Factor 1.1 IC on real northbound flow. |
| 2-3 | Implement Factors 1.2 (NB acceleration), 2.1 (earnings quality), 3.2 (momentum skip-5), 2.4 (valuation composite). Each fully evaluated. |
| 4-5 | Factor correlation matrix view. Pick a low-correlation composite of 3-5 factors. Walk-forward weight optimization. |
| 6-7 | Wire the top-N portfolio strategy. Backtest the composite on CSI 300 with full A-share constraints. Show OOS Sharpe + factor attribution. |
| 8-12 | Paper trade the composite with real daily data. Log every signal + execution. Weekly review. Aim for 3 months of clean attribution by July (CSC start). |

**The intern goal**: by July 2026 when the CSC internship starts, walk in with one
composite of ≤5 factors, 2-3 months of paper-trading record on real daily data,
factor attribution per month, and a regime-conditional breakdown. That's worth more
than ten half-tested factors.

---

## 13. Pointers

- `docs/STRATEGY.md` — longer strategic review, A-share edge catalogue, academic
  references. May need updates to reflect the factor-research pivot.
- `README.md` — macOS quickstart, REST API examples.
- `tests/test_factor_base.py`, `test_factor_northbound.py` — Factor pattern
  reference implementations.
- `tests/test_evaluation_*.py` — IC / quintile / decay reference tests.
- `astrategy/factors/northbound.py` — the canonical "factor with parameters"
  example; new factors mirror this structure.
- `astrategy/evaluation/runner.py` — `evaluate_factor()` is the end-to-end
  orchestration. Look here before adding evaluation logic anywhere else.

---

## 14. House-keeping

- Active branch: `claude/overhaul-codebase-O7UJJ`
- The owner approved the overhaul + branch on 2026-05-18
- Never push to `main` directly
- Don't commit `data/*.db` (gitignored), `data/evaluations/*` (gitignore
  recommended), `frontend/node_modules`, `*.tsbuildinfo`
- Commit messages: brief subject, blank line, bullet-point body covering what + why
- Always close commit messages with the session URL
