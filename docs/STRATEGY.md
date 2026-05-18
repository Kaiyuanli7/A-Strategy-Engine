# Strategic Review — A-Strategy-Engine

The "why" behind `CLAUDE.md`. Where that file is prescriptive ("DO X, NEVER Y"), this
one explains the reasoning, references, and tradeoffs so future Claude sessions (and
human contributors) can make sound judgment calls when something isn't covered by the
hard rules.

**Last revised:** 2026-05-18

---

## Table of contents

1. [The four overlapping goals](#1-the-four-overlapping-goals)
2. [Honest assessment of where the platform stands](#2-honest-assessment-of-where-the-platform-stands)
3. [What "making money" actually requires](#3-what-making-money-actually-requires)
4. [A-share-specific edges](#4-a-share-specific-edges)
5. [Anti-edges — what doesn't work for retail / small fund](#5-anti-edges)
6. [Platform gaps that move toward $$](#6-platform-gaps-that-move-toward-money)
7. [Workstreams outside the codebase](#7-workstreams-outside-the-codebase)
8. [Realistic expectations](#8-realistic-expectations)
9. [Academic references worth reading](#9-academic-references-worth-reading)
10. [Anti-patterns to recognize](#10-anti-patterns-to-recognize)

---

## 1. The four overlapping goals

The owner has four motivations stacked on this one project. They pull in different
directions; being explicit about which one wins each decision matters.

| Goal | Time horizon | What it requires |
|---|---|---|
| Make money trading A-shares | 12-36 months to first real PnL | real data, validated strategies, paper trading, portfolio risk discipline |
| CSC Financial internship credibility | July 2026 start | clean walk-forward methodology, factor attribution, A-share structure mastery |
| University investment fund tool | ongoing | reliability, reproducibility, simple UX for non-coders |
| Quant finance education | compounding | exposure to literature, real data, professional research process |

**Optimization rule:** when ambiguous, default to "make money." Goal #1 done well produces
the others as side effects. Goal #2 alone (build something flashy for the interviewer)
without #1 produces a Potemkin platform that experienced quants will see through.

---

## 2. Honest assessment of where the platform stands

### What's genuinely good

- **A-share constraint correctness.** T+1, board-specific limits, lot rounding, cost
  model, suspension detection — this is the foundation everything else depends on,
  and it's done right with unit tests pinning the formulas.
- **Engine architecture.** Event-driven loop with strategy hooks; precompute-then-lookup
  signal pattern; clean order/fill/portfolio separation. Vectorization is a future
  optimization, not a current need.
- **Composable strategy pattern.** 13 condition types as a Pydantic discriminated union,
  PIT-safe fundamentals joins, AND-reduce semantics — this is meaningfully better
  than what most retail platforms (vectorbt, backtrader naive) produce.
- **Frontend.** Type-safe API contracts, polished UX, working JSON preview. Not toy-level.
- **Test coverage.** 130 tests including PIT-leakage regression, golden-value RSI,
  commission floor edge cases. Real safety net.

### What's a demo, not a tool

- **Universe is 10 stocks.** Statistical conclusions on 10 names over 3 years are noise.
  Real factor strategies need 200-500+ names.
- **All backtests are in-sample.** No walk-forward, no out-of-sample, no overfit detection.
- **Synthetic data only** in this sandbox. The real AKShare path is implemented but
  unvalidated against actual prices.
- **No paper trading.** No way to know what backtests well actually executes well next bar.
- **No portfolio risk management.** Equal-weight 10 names with no beta neutralization,
  no sector caps, no vol targeting at the portfolio level.

### What's missing entirely

- **Survivorship bias correction** (point-in-time index membership).
- **Transaction cost realism beyond commission/tax** — no bid-ask spread, no market impact.
- **Factor attribution.** Returns aren't decomposed against known factors.
- **Regime tagging.** No per-regime performance breakdown.
- **Options support.** Despite the owner being an active options trader, this is nowhere
  in the platform. The single biggest unleveraged edge.
- **Alternative data.** Not necessarily a gap — most alt data is negative-EV for retail.
- **Live execution path.** Manual broker entry remains the path until trust is built.

### One-line summary

**Better skeleton than 95% of college quant projects; less validated than a single junior
quant intern's first month at any real shop.** The platform is well-built — but well-built
demos are common, well-validated edges are rare.

---

## 3. What "making money" actually requires

Most retail systematic traders lose money. The ones who don't have, in some combination:

### Edge

A persistent statistical asymmetry the market hasn't fully arbitraged. In A-shares
specifically, the documented ones survive precisely because they're not glamorous
(see §4).

### Discipline

Following the system rather than overriding it. The #1 way retail loses is
"this signal is wrong, I'll skip it / double it / hold past the stop." The platform
must enforce, not suggest.

### Capital

Enough to overcome fixed costs (the ¥5 commission floor punishes notional below
~¥20k per trade) but small enough not to move markets. **Sweet spot for A-shares:
¥100k – ¥10M.** Below ¥100k, costs eat most edges; above ¥10M, small-cap strategies
hit liquidity walls.

### Patience

Most strategies need **6-12 months of out-of-sample paper trading** before real money.
The temptation to deploy after one good backtest month is universal and almost always
wrong.

### A correct view of what you can NOT do

- HFT / market making (microsecond infrastructure)
- News sentiment on Chinese text vs institutions with same APIs + human analysts
- Pure intraday momentum on liquid blue chips (institutional flow eats it)
- Insider information (illegal)
- Beating CSC's own prop desk on Chinese stocks (they ARE the market)

---

## 4. A-share-specific edges

Roughly priority-ordered by accessibility for a college student / small fund. Each has
a documented academic or practitioner source.

### 4.1 Value + Momentum combo

**Citation:** Liu, Stambaugh, Yuan (2019), *Size and Value in China*, Journal of
Financial Economics, 134(1).

The strongest documented persistent edge in A-shares. Works **better in China than the
US** because retail dominance (~80% of volume) creates persistent inefficiencies.

**Why it persists:** value gets re-rated slowly as institutional ownership grows; momentum
persists because retail extrapolates recent winners.

**How to implement:**
- Value: low PB or low PE relative to sector median; PB has shown stronger results in CN.
- Momentum: 12-1 month return (drop most recent month to avoid short-term reversal).
- Combine: long top-quintile of `value × momentum`; weekly or monthly rebalance.
- Universe: CSI 500 / CSI 1000 (CSI 300 is too large-cap to have much factor dispersion).

### 4.2 Northbound flow (北向资金) follow-through

**Source:** widely cited by practitioners; e.g., 中信证券 + 中金 monthly research.

Stock Connect (沪深港通) net inflows are a smart-money proxy. Consistent multi-day
accumulation tends to precede price moves on foreign-favored names.

**Why it persists:** retail can't easily replicate (data lag + interpretation barrier).

**How to implement:**
- Signal: rolling 5-day net inflow > threshold; or holding-pct change.
- Pair with momentum filter (avoid catching falling knives).
- Watch for **decoupling regime** (rare periods when northbound buys and prices diverge —
  signal weakens).

### 4.3 PEAD — post-earnings announcement drift

**Citation:** Hung, Li, Wang (2015), *Post-earnings announcement drift in the Chinese
stock market*; survives subsequent studies.

Stocks beating earnings consensus drift up for ~30-60 days post-announcement; misses
drift down. **Effect stronger in A-shares than US.**

**Why it persists:** retail underreaction + analyst coverage gaps for mid/small caps.

**How to implement:**
- Need clean earnings surprise data (consensus EPS vs actual). Wind / iFinD / AKShare
  via `stock_yjbb_em()`.
- Long beats / short misses (or just long beats — short selling is restricted retail-side).
- 30-60 day hold.

### 4.4 Limit-up follow-through (涨停板续板)

**Source:** practitioner research; e.g., 国信证券 quant team.

Stocks closing at limit-up (涨停) frequently gap-up the next day. Highly behavioral,
very A-share-specific.

**Why it persists:** retail FOMO + queue dynamics (can't buy at limit-up close, have to
wait for next-day open).

**How to implement carefully:**
- Filter: limit-up that's NOT consecutive (first day, or after a base).
- Avoid: low-quality concept stocks, ST stocks, sub-100M market cap.
- Exit: aggressive, 1-3 day hold. Stops at first close below open.
- This strategy **requires** the platform's `limit_hit_fill_prob` modeling — first-day
  limit-ups are hard to buy.

### 4.5 Policy theme rotation

**Source:** experiential; well-tracked by sell-side strategists.

Major policy themes (新质生产力, 国产替代, 消费刺激, 金融供给侧改革) produce sector
momentum that lags the announcement by **days to weeks**.

**Why it persists:** information dispersion + interpretation lag.

**How to implement:**
- Maintain a theme tag per stock (via SW L2 / L3 sector + manual overlay).
- Long top-momentum sectors filtered to those tied to current policy theme.
- This strategy is **partly discretionary** — the platform should support it but the
  theme labeling is human work.

### 4.6 Mean reversion after extreme drawdowns

**Source:** observed pattern around 国家队 / Central Huijin support events.

Index-level drawdowns > 8% in 5 days frequently mean-revert within 10 days. Single-stock
analog: 30% drawdowns in 20 days followed by partial recovery in 30 days.

**Why it persists:** structural support buying by state actors during stress.

**How to implement:**
- Rare entries (10-30 per year per universe).
- Wide stops (this is volatility-buying).
- Pair with index-level signal to avoid catching truly broken regimes.

### 4.7 Options volatility selling

**Source:** standard derivatives literature; e.g., Israelov (2017).

Sell premium when IV rank > 70th percentile; buy when < 30. Defined-risk verticals to
cap left-tail.

**Why it persists in CN:** options market is younger, retail-heavier, less arbed than US.

**How to implement:**
- Universe: 50ETF期权, 300ETF期权, individual-name options on the largest liquid names.
- Strategies: covered calls (on long-stock sleeve), cash-secured puts (deploy cash with
  discount entry), iron condors during high-IV-rank periods.
- **Platform doesn't support this yet — Phase 9.**

---

## 5. Anti-edges

Things to NOT build / NOT pursue:

- **HFT / market making.** No infrastructure.
- **Daily round-trip strategies.** T+1 makes them illegal-by-construction;
  even with proper holding, costs eat the edge.
- **News sentiment NLP on Chinese.** Institutions have the same APIs + human analysts;
  retail-grade alpha here is negative-EV.
- **Beating institutional flow on mid-cap A-shares.** CSC, CITIC, GS China ARE the
  market in mid-caps.
- **Pure black-box ML on price data.** Overfits horribly at retail scale (~5000 stocks
  × ~5000 trading days = 25M samples = small dataset by ML standards). ML is fine as a
  *feature engineering* layer on a thesis-driven strategy; not as the whole strategy.
- **Multi-strategy without depth.** Better to know three strategies cold than twenty
  superficially.
- **Anything illegal.** Front-running, insider info, market manipulation. Career-ending.

---

## 6. Platform gaps that move toward money

In rough priority order. These map to Phases 5-10 in `CLAUDE.md`.

### Phase 5 (CRITICAL — blocks everything else): real data + universe + walk-forward

- Real AKShare path validated on owner's Mac (sandbox can't).
- 5+ years of daily OHLCV for 300-500 stocks.
- **Point-in-time index membership.** Without this, every backtest is biased toward
  current winners. This single fix can flip a "12% annualized" strategy to "4% loser."
- Walk-forward as a first-class engine feature (12mo train / 3mo test, rolling).
- IS vs OOS reporting on every backtest. Auto-flag overfit candidates.
- Factor attribution (regress strategy returns against value/momentum/size/vol/beta-300).

### Phase 6: grid search + Bayesian optimization (with overfit guards)

- Sweep param spaces; display IS + OOS heatmaps side-by-side.
- Penalize parameter count; reject candidates failing OOS Sharpe threshold.
- Bayesian search via Optuna for high-dim spaces.
- **Critical:** no "best params" without OOS validation.

### Phase 7: paper trading + monitoring

- Daily live mode: fetch today's close, generate tomorrow's orders.
- User submits orders manually until 6+ months of clean drift-free results.
- Drift detector: live Sharpe vs backtest expectation; pause on > 1.0 deviation.

### Phase 8: portfolio risk

- Vol targeting (default 12% annualized).
- Sector caps (max 25% any SW L1), single-name caps (max 8%).
- Drawdown circuit breakers.
- Optional 沪深300 ETF / index futures beta hedge.

### Phase 9: options (latent edge)

- IV surface ingestion + IV rank/percentile.
- Templates: covered calls, cash-secured puts, defined-risk verticals.
- Pin-risk / early-assignment for American-style.

### Phase 10: live execution

- Only after 6+ months clean paper. Likely via 同花顺 / 通达信 / broker API.
- Semi-automatic — platform generates, user reviews and submits.

---

## 7. Workstreams outside the codebase

The platform is necessary but not sufficient. Things that must happen but live outside
the repo:

- **Read the literature.** Liu/Stambaugh/Yuan first. Fama-French, Carhart, Asness for
  factor framing. AQR's research library is free and excellent.
- **Maintain a research journal** from day one. Even a Google Sheet. Log every backtest
  decision, paper trade, signal override (if any). This is what CSC will want to see.
- **Pick 2-3 strategies and know them cold.** Not 20. Depth > breadth.
- **Develop a macro view.** Systematic strategies layer on top of context, they don't
  replace it.
- **Find a quant mentor.** Ideally during the CSC internship. Five minutes of their
  feedback will save six months.

---

## 8. Realistic expectations

### What to expect from a single strategy

| Metric | Realistic (net of all costs) |
|---|---|
| Annualized return | 8-18% |
| Annualized vol | 12-25% |
| Sharpe | 0.4-1.0 single factor; 0.7-1.3 multi-factor combo |
| Max drawdown | 15-30% |
| Win rate | 45-55% (most strategies are right slightly more than half the time) |
| Best year vs worst year | best year often 2-3x worst year |

**If your backtest shows Sharpe > 1.5 on real data**, the default assumption is overfitting
or a bug. Investigate before celebrating. Check, in order: (1) lookahead, (2) survivorship
bias, (3) transaction costs missing, (4) position sizes too small to hit commission floor,
(5) in-sample-only fitting.

### Timeline to real money

| Milestone | Realistic timeline from now |
|---|---|
| Real data ingested + universe at 300+ stocks | 2-4 weeks |
| First walk-forward-validated strategy | 4-8 weeks |
| Confidence in factor attribution | 2-3 months |
| 3 months clean paper trading | 5-6 months |
| First real-money deployment (small size) | 7-12 months |
| Reasonable PnL track record (12+ months live) | 18-24 months |

**Do not skip these.** Every shortcut here is paid for later, usually with money.

---

## 9. Academic references worth reading

In rough order of usefulness for this project:

1. **Liu, Stambaugh, Yuan (2019)** — *Size and Value in China.* JFE 134(1).
   The canonical paper on A-share factor investing.
2. **Carpenter, Lu, Whitelaw (2021)** — *The real value of China's stock market.* JFE 139(3).
   Useful framing on how China's market differs structurally.
3. **Hung, Li, Wang (2015)** — *Post-earnings announcement drift in the Chinese
   stock market.* JIFMIM 33.
   Establishes PEAD persistence in A-shares.
4. **Israelov (2017)** — *Covered Calls Uncovered.* AQR.
   The case for and against systematic option-selling.
5. **Asness, Moskowitz, Pedersen (2013)** — *Value and Momentum Everywhere.* JF 68(3).
   Foundational factor combo paper.
6. **Lo (2002)** — *The Statistics of Sharpe Ratios.* FAJ 58(4).
   Why you should mistrust high Sharpes and how to compute properly.
7. **López de Prado (2018)** — *Advances in Financial Machine Learning.* Wiley.
   The single best book on avoiding ML overfitting in finance. Skim chapters 1-7.

---

## 10. Anti-patterns to recognize

When implementing, watch for these requests / impulses and **push back**:

| Anti-pattern | Why it's bad | What to do instead |
|---|---|---|
| "Tune 10 parameters to find what works" | Each param steals OOS DOF | Cap at 3; defend each on theoretical grounds |
| "Skip walk-forward this time" | That's exactly when it's needed | Refuse |
| "Backtest with synthetic data and call it validated" | No signal in random data | Use real data only for conclusions |
| "Sharpe 4.0 strategy ready to deploy" | Almost certainly overfit/bug | Investigate before celebrating |
| "Add a daily-round-trip strategy" | T+1 + costs make it negative EV | Push to weekly+ |
| "Build a sentiment NLP module" | Institutions dominate; negative EV | Defer indefinitely unless proprietary text |
| "Mock the engine for the real backtest" | Defeats the purpose | No |
| "Deploy real money after 1 good backtest month" | Premature; high regret risk | Minimum 3-6 months paper |
| "Add 5 new strategy types this week" | Breadth without depth | Pick one, do it right |
| "This works without modeling T+1 / limits / costs" | It doesn't | Refuse |

---

## Final framing

**The platform doesn't make money. The owner makes money with the platform.** The
platform's job is to reduce uncertainty about whether a strategy works — to make sure
the owner isn't lying to themselves. Edge comes from research, discipline, and time
spent on the right problems. Everything in this document, and every line of code in
this repo, should serve that single function.
