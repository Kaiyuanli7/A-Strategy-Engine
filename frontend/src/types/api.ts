// Mirrors the Pydantic schemas in astrategy/api/schemas.py.

export interface BacktestSummary {
  n_bars: number
  initial_equity: number
  final_equity: number
  total_return: number
  annualized_return: number
  annualized_vol: number
  sharpe: number
  max_drawdown: number
  max_drawdown_peak: string | null
  max_drawdown_trough: string | null
  calmar: number
  win_rate: number
  avg_hold_days: number
  n_trips: number
  n_fills: number
  n_rejections: number
  turnover: number
}

export interface StrategySpec {
  type: string
  params: Record<string, unknown>
}

export interface BacktestConfigSpec {
  start: string
  end: string
  initial_cash: number
  limit_hit_fill_prob: number
  random_seed: number
}

export interface BacktestRequest {
  strategy: StrategySpec
  universe: string[]
  config: BacktestConfigSpec
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

export interface BacktestResult {
  run_id: string
  status: string
  config: BacktestRequest
  summary: BacktestSummary | null
  equity_curve: EquityPoint[]
  fills: FillRecord[]
  rejections: FillRecord[]
  error: string | null
}

export interface BacktestRunListItem {
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

export interface BacktestRunResponse {
  run_id: string
  status: 'completed' | 'failed'
  summary: BacktestSummary | null
  error: string | null
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
  name: string
  board: string
  is_st: boolean
}

export interface Universe {
  name: string
  codes: string[]
  stocks: UniverseStock[]
}

export interface Health {
  status: 'ok'
  version: string
  cached_stocks: number
  cached_runs: number
}
