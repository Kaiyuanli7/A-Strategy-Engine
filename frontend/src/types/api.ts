// Mirrors the Pydantic schemas in astrategy/api/schemas.py.

export interface Health {
  status: 'ok'
  version: string
  cached_stocks: number
  cached_runs: number
}

export interface StockBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface StockOHLCV {
  code: string
  name: string | null
  board: string | null
  is_st: boolean
  bars: StockBar[]
}

export interface UniverseStock {
  code: string
  name: string | null
  board: string | null
  is_st: boolean
}

export interface Universe {
  name: string
  codes: string[]
  stocks: UniverseStock[]
}

export interface FactorParamSpec {
  name: string
  type: 'int' | 'float' | 'str' | 'bool'
  default: number | string | boolean
  description: string | null
  min: number | null
  max: number | null
}

export type FactorCategory = 'flow' | 'fundamental' | 'technical' | 'event' | 'sector'

export interface FactorMeta {
  name: string
  category: FactorCategory
  description: string
  lookback_days: number
  rebalance_freq: 'daily' | 'weekly' | 'monthly'
  params: FactorParamSpec[]
}

export interface ICPoint {
  date: string
  ic: number
}

export interface QuintileCumPoint {
  date: string
  q1: number
  q2: number
  q3: number
  q4: number
  q5: number
  long_short: number
}

export interface DecayPoint {
  horizon: number
  ic_mean: number
  ic_ir: number
}

export interface ICSummary {
  mean: number
  std: number
  ir: number
  hit_rate: number
  t_stat: number
  n: number
}

export interface QuintileSummary {
  long_short_mean: number
  long_short_std: number
  long_short_sharpe: number
  long_short_total_return: number
  monotonicity: number
  avg_turnover: number
}

export interface FactorCorrelation {
  factors: string[]
  matrix: number[][]
  universe: string
  start: string
  end: string
  rebalance: 'daily' | 'weekly' | 'monthly'
  n_dates: number
}


export interface FactorEvaluation {
  factor: FactorMeta
  params: Record<string, unknown>
  universe: string
  start: string
  end: string
  rebalance: 'daily' | 'weekly' | 'monthly'
  horizon: number
  n_dates: number
  n_stocks_avg: number
  ic_series: ICPoint[]
  ic_summary: ICSummary
  quintile_cum: QuintileCumPoint[]
  quintile_summary: QuintileSummary
  decay: DecayPoint[]
  cached: boolean
}

export interface EvaluateParams {
  start: string
  end: string
  universe: string
  horizon: number
  rebalance: 'daily' | 'weekly' | 'monthly'
  lookback?: number
  use_cache?: boolean
}


// --- Portfolio Backtest (Sprint 3) ------------------------------------------

export interface FactorWeightSpec {
  factor_name: string
  params: Record<string, unknown>
  weight: number | null
}

export interface CompositeSpec {
  method: 'equal_weight' | 'signed_ic_weighted' | 'fixed_weight'
  factors: FactorWeightSpec[]
  rolling_window?: number
  min_ic_abs?: number
}

export interface PortfolioConfigSpec {
  top_n: number
  rebalance_freq: 'weekly' | 'monthly'
  max_sector_pct: number
  max_single_position_pct: number
  min_market_cap: number
  exclude_st: boolean
  weighting: 'equal'
}

export interface PortfolioBacktestRequest {
  composite: CompositeSpec
  portfolio: PortfolioConfigSpec
  universe: string
  start: string
  end: string
  initial_cash: number
  limit_hit_fill_prob: number
  random_seed: number
}

export interface PortfolioBacktestResponse {
  run_id: string
  status: 'completed' | 'failed'
  summary: Record<string, unknown> | null
  error: string | null
}

export interface EquityPoint {
  date: string
  equity: number
}

export interface FillRecord {
  date: string
  code: string
  side: 'buy' | 'sell'
  shares: number
  price: number
  cost: number
  rejected_reason?: string | null
}

export interface PortfolioResult {
  run_id: string
  status: string
  config: PortfolioBacktestRequest
  summary: Record<string, unknown> | null
  equity_curve: EquityPoint[]
  fills: FillRecord[]
  rejections: FillRecord[]
  error: string | null
}

export interface PortfolioRunListItem {
  run_id: string
  status: string
  strategy_type: string
  universe_size: number
  start: string
  end: string
  created_at: string
  sharpe: number | null
  total_return: number | null
}
