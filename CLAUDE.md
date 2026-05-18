# CLAUDE.md — instructions for any Claude session working on this repo

This file is loaded automatically at the start of every Claude Code session in this
repository. Read it fully before doing anything substantive. Update it (and bump the
version below) when goals or constraints shift.

**Last revised:** 2026-05-18 · **Version:** 1.0

---

## 0. Project identity

A-share (Chinese stock market / 沪深A股) trading strategy research platform.

The owner is a **college junior** who is a junior analyst at a university investment
fund, an incoming summer intern at **CSC Financial (中信建投)**, and an active options
trader. Treat them as a sophisticated user but assume zero institutional infrastructure
(no Bloomberg, no proprietary data, no co-located servers).

---

## 1. What we are actually trying to achieve (priority-ordered)

1. **Make money trading A-shares.** Medium-frequency (weekly→monthly rebalance) systematic
   strategies. This is the primary motivation; everything else falls out of getting this right.
2. **Build credibility for the CSC Financial internship.** A serious, defensible research
   process visible in this repo.
3. **Provide a working research tool for the university investment fund.**
4. **Learn quant finance properly.** Meta-goal that compounds the others.

When you are making a tradeoff and unsure, **default to goal #1**. A platform that
genuinely helps the owner make money also satisfies #2, #3, and #4 by construction.

---

## 2. Success criteria — when have we "arrived"?

This project succeeds when the owner can:

- Run real A-share data through 1+ strategies whose **out-of-sample** Sharpe (net of all
  costs) is between 0.6 and 1.2 over a 12+ month rolling window — this is the realistic
  band for genuinely working factor / behavioral strategies in China.
- Show CSC interviewers a paper-trading track record of 3-6 months with clean factor
  attribution and regime-by-regime breakdown.
- Deploy real capital with portfolio-level risk discipline (sector caps, vol targeting,
  drawdown circuit breakers) and follow the system rather than overriding it.
- Confidently say what their edge is, why it persists, and what would invalidate it.

A platform demo that just produces pretty charts is **not** success. A clean codebase
that doesn't include real validation is **not** success.

---

## 3. Hard rules — never violate these

These are non-negotiable. If a request seems to ask you to break one of them, push back
explicitly rather than complying.

### Trading & validation

1. **NEVER claim a strategy "works" without out-of-sample validation.** In-sample numbers
   alone are meaningless. Always run walk-forward and report IS vs OOS side by side.
2. **NEVER auto-execute live trades.** This platform generates orders for manual review.
   Live broker integration, when it exists, must be opt-in per-order, never per-session.
3. **NEVER present synthetic-data backtest numbers as real performance.** The synthetic
   path exists only for engine correctness testing and offline demos. Backtest
   conclusions on synthetic data are noise.
4. **NEVER cap parameter count above 4 per strategy.** Each extra knob steals a degree of
   freedom from OOS performance. If the user wants 8 parameters, suggest a regression
   test instead.
5. **WARN when in-sample → out-of-sample Sharpe drops by more than 0.5.** This is the
   overfit detector. Add it as a hard gate before promoting any strategy to paper trading.
6. **REFUSE to remove A-share constraints** (T+1, price limits, lot sizes, stamp tax,
   commission floor, suspension detection) "just for testing." A backtest without these
   is garbage and produces misleading numbers.

### Realistic Sharpe ranges (use as sanity checks)

| Setup | Realistic Sharpe (net) | Flag if you see |
|---|---|---|
| Single-factor strategy, 300+ stocks, walk-forward | 0.4 – 0.9 | > 1.5 = look for the bug |
| Multi-factor combo, walk-forward | 0.7 – 1.3 | > 2.0 = almost certainly overfit |
| In-sample only (any setup) | meaningless | "alpha" here is regression-to-training |
| Synthetic data (any setup) | meaningless | the data has no signal |

If a backtest comes back with Sharpe > 2.0 on real data, **the default assumption is
overfitting or a bug**, not skill. Investigate. Check: lookahead, survivorship bias,
data leakage, transaction costs missing, position sizes too small to trigger commission floor.

### Code

7. **Tests are required** for new strategy / indicator / condition code. The pattern is
   established in `tests/test_*.py`; follow it.
8. **No silent data conversions.** AKShare returns Chinese column names, fraction vs
   percent inconsistencies, NaN-vs-empty distinctions. Normalize at the edge
   (`AKShareClient`), assert in tests, never let it propagate.
9. **No new dependencies without justification.** Adding `polars`, `vectorbt`, `qlib`, etc.
   needs an explicit reason. We already chose pandas + a custom engine for A-share
   constraint correctness — those choices are settled.

---

## 4. What edges to pursue (and what NOT to)

### Edges worth pursuing

Roughly priority-ordered for a college student / small fund:

- **Value + Momentum combo** — Liu, Stambaugh, Yuan 2019 ("Size and Value in China") is
  the canonical citation. Strongest documented persistent edge in A-shares.
- **Northbound flow (北向资金) follow-through** — Stock Connect net inflows precede
  multi-day price moves on foreign-favored names.
- **PEAD (post-earnings announcement drift)** — survives in A-shares with more strength
  than in the US, because retail underreaction.
- **Limit-up follow-through (涨停板续板)** — stocks closing at limit-up frequently
  gap-up next day. Highly behavioral, very A-share-specific. Requires same-day-ish
  signal and disciplined exits.
- **Policy theme rotation** — 新质生产力, 国产替代, etc. Sector momentum lags policy
  announcements by days to weeks. Slowest, most thesis-driven of the edges here.
- **Mean reversion after extreme drawdowns** — national team (国家队) intervention
  creates structural reversion at index level. Use sparingly; entries are rare.
- **Options volatility selling** — sell premium when IV rank > 70, buy when < 30.
  The user already trades options; this is their latent biggest edge and the platform
  doesn't address it yet (Phase 9).

### Edges to NOT pursue

Don't build, don't suggest, don't waste time on:

- **HFT / market making** — millisecond infrastructure, you have none.
- **Daily round-trip strategies** — T+1 makes them impossible by construction.
- **News sentiment NLP on Chinese text** — institutions have the same APIs you do,
  plus human analysts. Negative-EV unless you have proprietary text.
- **Beating CSC's own prop desk** — they ARE the market in mid-cap A-shares.
- **Pure black-box ML on price data** — overfits catastrophically with retail-scale data.
  ML is fine for feature engineering or as a layer on top of a thesis-driven strategy.
- **Insider info, anything that touches MNPI** — illegal, career-ending.

---

## 5. Engineering invariants (decisions that are settled)

Don't relitigate these unless explicitly asked:

- **Python 3.11+**, pandas, numpy, FastAPI for backend. SQLite for persistence (single-file,
  embeddable, fast enough at our scale).
- **AKShare** as primary data source; synthetic fallback for sandboxed/offline. Real AKShare
  endpoints drift — every call has try-three-fallbacks pattern in `astrategy/data/akshare_client.py`.
- **React 18 + TypeScript strict + Tailwind + Recharts + Vite** for frontend.
- **Event-driven bar-by-bar backtest engine** (not vectorized). Correctness > speed.
  We can parallelize across CPU cores later; we won't sacrifice T+1 correctness for vectorization.
- **Strategy ABC pattern**: precompute signals in `initialize()`, look up by date in
  `on_bar()`. Both `DualMACrossStrategy` and `ComposableStrategy` follow this — new
  strategies must too.
- **Next-bar-open fill** is the default. Signal at bar N close → execute at bar N+1 open.
  Prevents lookahead. Never change this default without an explicit ADR.
- **252 trading days/year**, **2.0% risk-free rate** for Sharpe — universal convention,
  comparable across research.

---

## 6. A-share constraints — always model these correctly

These are the difference between a useful tool and "garbage" (owner's word):

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

A strategy that round-trips daily needs ~0.15% directional edge **just to break even**
before slippage. Bias toward weekly+ holding periods.

---

## 7. Current state (as of 2026-05-18)

Shipped on `claude/ashare-trading-strategy-RegyP` → PR #1 against `main`:

- **Phase 1**: data layer + backtest engine with A-share constraints + dual-MA demo
- **Phase 2**: FastAPI REST server + Pydantic schemas + backtest run persistence
- **Phase 3**: React/Vite/TS/Tailwind frontend (runs list, results dashboard, screener)
- **Phase 4**: composable strategies + fundamentals/sector/northbound data + visual builder

Test suite: 130 passing. Frontend typechecks + builds clean.

**Critical gap:** all backtests so far run on synthetic GBM data because this sandbox
blocks AKShare's eastmoney/sina endpoints (403). The real-data path exists and is
implemented correctly but unvalidated against real prices. **Closing this gap is the
single highest-leverage thing left to do** — see Phase 5.

---

## 8. Phase roadmap

Phases 1-4 done. Next phases, in implementation priority order:

### Phase 5 — Real data + universe scale-up + walk-forward (REQUIRED before anything else)

**This is the most important phase. Without it, every metric in this repo is noise.**

- Run the real AKShare fetch path locally on the owner's Mac (sandbox can't). Validate
  data shape, completeness, holiday handling on real prices.
- Expand universe from 10 demo stocks → full CSI 300 (then later CSI 500 / 1000).
- Implement **point-in-time index membership** to eliminate survivorship bias. Without
  this, every "winner" backtest is partly luck of being in today's index.
- Implement **walk-forward validation** as a first-class feature of the engine. Default:
  12-month train, 3-month test, rolling. Every backtest produces IS + OOS metrics
  side-by-side. Strategies with OOS Sharpe < 0.3 or IS-OOS gap > 0.5 are flagged.
- Add **factor attribution** to backtest output: decompose returns vs value/momentum/size/
  vol/beta-300 factors so the user knows what their "alpha" is actually loading on.
- Add **regime tagging** (bull/bear/range/high-vol) and per-regime metrics.

### Phase 6 — Grid search optimizer (with overfit guards)

Per the original prompt, but with critical anti-overfit measures from the start:
- All grid sweeps display IS + OOS side by side. Hide IS-only "best" results.
- Auto-flag candidates with IS-OOS gap > 0.5.
- Penalize complexity: more parameters → higher OOS Sharpe threshold to "pass."
- Heatmap visualization in the React UI.

### Phase 7 — Paper trading + drift monitoring

- "Live mode": same engine fed by daily real-close data. Produces "orders for tomorrow."
  User executes manually in their broker until trust is established.
- Drift detector: realized live Sharpe vs backtested expectation. If gap > 1.0 for 3+
  months, pause the strategy.
- Trade journal: every order tagged with reason + signal value + expected exit. Mandatory
  weekly post-trade review.

### Phase 8 — Portfolio risk management

- Portfolio-level vol targeting (default 12% annualized).
- Sector caps (max 25% any single SW L1).
- Single-name caps (max 8%).
- Drawdown circuit breakers: pause new entries at -10% MTM, pause everything at -15%.
- Optional beta hedge via 沪深300 ETF or index futures.

### Phase 9 — Options (the latent edge)

The owner trades options actively but the platform has zero options support. This is the
single biggest unleveraged edge in the project.

- 50ETF期权 / 300ETF期权 / on liquid individual names.
- IV surface ingestion + IV rank / IV percentile signals.
- Strategy templates: covered calls (income on long-stock sleeve), cash-secured puts
  (deploy cash with discount entry), defined-risk verticals.
- Pin risk + early-assignment handling for American-style.

### Phase 10 — Live broker execution

Only after 6+ months of clean paper trading. Likely via 同花顺 / 通达信 / brokerage API.
Even then, semi-automatic: platform generates orders, user reviews, user submits.

### Phase 11+ — Genetic / Bayesian / strategy discovery

Per original prompt. Defer until Phases 5-10 ship — these techniques are dangerous
without strong overfit guards.

---

## 9. Decision framework — when working, ask:

Before adding a feature, ask **all four**:

1. **Does this move the owner toward making money?** (vs. demo polish)
2. **Would CSC's quant team consider this rigorous?** (vs. retail-tier shortcuts)
3. **Does this respect the hard rules in §3?** (no overfit-enabling features)
4. **Is this in scope for the current phase?** (no Phase 9 work while Phase 5 is unmerged)

If three or more are "no," push back instead of complying.

When choosing between two implementations, prefer:
- **Correctness over speed.** We optimize once it works.
- **Explicit over clever.** Junior quant readers must understand the code.
- **Settled patterns over new abstractions.** Mimic existing strategy/condition/test patterns.
- **Conservative over aggressive defaults.** Higher commissions, lower fill probabilities,
  wider stops in defaults — the user can loosen them deliberately.

---

## 10. Anti-patterns — push back when you see these

If the owner (or any contributor) asks for something matching these, **flag it** before doing:

- "Let me run this backtest with 8 parameters tuned" → too many DOF; suggest 3 + walk-forward
- "Strategy X has Sharpe 3.5 in backtest" → suspicious; check for lookahead, surv bias,
  cost model, in-sample only
- "Let's skip walk-forward for this one" → no; that's exactly when it's needed
- "Ship without tests" → no; the strategy / indicator test pattern is established
- "Let's mock the network out and use synthetic for the real backtest" → no; synthetic
  is for engine testing, not strategy validation
- "Add a daily round-trip strategy" → T+1 + costs make this almost always unprofitable
- "Build a sentiment NLP module" → very low EV; only if owner has proprietary text
- "Let's just deploy this with real money" → only after 6+ months paper trading

---

## 11. CSC internship lens

When making feature decisions, periodically ask: **would this impress a CSC senior quant?**

Things they WILL care about (build these):
- Clean walk-forward methodology with honest IS vs OOS reporting
- Factor attribution per backtest
- A-share market structure knowledge (T+1, limit moves, 印花税, 国家队, 北向 flow)
- Paper trading track record with attribution
- Smart questions about THEIR research (this is meta — the platform should leave room for it)

Things they will NOT care about (don't over-invest):
- React component architecture
- Line of code count, test count
- Strategy variety (depth > breadth — one strategy understood cold > ten half-baked)
- Pretty charts beyond what's needed for analysis

---

## 12. Concrete next 90 days (the actual plan)

In priority order, weeks 1-12:

| Weeks | Work |
|---|---|
| 1 | Verify real AKShare path locally on the owner's Mac. Cache 5 years of CSI 300 daily OHLCV. |
| 2-3 | Expand engine support to 300+ stocks. Implement point-in-time index membership. |
| 3-4 | Implement walk-forward validation as a first-class engine feature. |
| 5-6 | Pick ONE strategy that survives walk-forward (probably value + momentum). Develop fully. |
| 7-12 | Paper trade that ONE strategy with real daily data. Log every signal + execution. |

**The intern goal**: by July 2026 when the CSC internship starts, have ONE production-quality
strategy with a 2-3 month real paper-trading record + clean factor attribution.
That's worth more than ten half-tested strategies.

---

## 13. Pointers

- `docs/STRATEGY.md` — longer strategic review, A-share edge catalogue, academic references
- `README.md` — macOS quickstart, REST API examples
- `tests/` — established test patterns (mirror these for new code)
- `astrategy/strategies/composable.py` — the canonical "complex strategy" pattern; new
  strategy types should follow this structure
- PR #1 (https://github.com/Kaiyuanli7/A-Strategy-Engine/pull/1) — Phases 2-4

---

## 14. House-keeping

- Branch: `claude/ashare-trading-strategy-RegyP`
- PR: #1, against `main`
- The owner has approved the branch + PR setup; new commits land on this branch
- Never push to `main` directly
- Don't commit `data/*.db` (gitignored), `frontend/node_modules`, or `*.tsbuildinfo`
- Commit messages: brief subject, blank line, bullet-point body covering what + why
- Always close commit messages with the session URL
