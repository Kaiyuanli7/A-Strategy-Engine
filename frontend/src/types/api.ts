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

// --- Phase 4: composable strategy spec --------------------------------------

export type ConditionType =
  | 'ma_cross' | 'price_vs_ma' | 'rsi' | 'bollinger_breakout' | 'macd'
  | 'volume_spike' | 'pe_bound' | 'pb_bound' | 'ps_bound' | 'roe_bound'
  | 'revenue_growth' | 'nb_net_inflow' | 'nb_holding_pct'

export interface ConditionSpecBase {
  type: ConditionType
}
export interface MACrossCond extends ConditionSpecBase {
  type: 'ma_cross'
  fast: number
  slow: number
  direction: 'up' | 'down'
}
export interface PriceVsMACond extends ConditionSpecBase {
  type: 'price_vs_ma'
  period: number
  op: '>' | '<'
}
export interface RSICond extends ConditionSpecBase {
  type: 'rsi'
  period: number
  threshold: number
  direction: 'above' | 'below' | 'cross_up' | 'cross_down'
}
export interface BollingerBreakoutCond extends ConditionSpecBase {
  type: 'bollinger_breakout'
  period: number
  k: number
  band: 'upper' | 'lower'
}
export interface MACDCond extends ConditionSpecBase {
  type: 'macd'
  fast: number
  slow: number
  signal: number
  event: 'hist_cross_up' | 'hist_cross_down' | 'macd_above_signal' | 'macd_below_signal'
}
export interface VolumeSpikeCond extends ConditionSpecBase {
  type: 'volume_spike'
  period: number
  multiple: number
}
export interface BoundCond extends ConditionSpecBase {
  type: 'pe_bound' | 'pb_bound' | 'ps_bound' | 'roe_bound' | 'revenue_growth' | 'nb_holding_pct'
  min: number | null
  max: number | null
}
export interface NorthboundNetInflowCond extends ConditionSpecBase {
  type: 'nb_net_inflow'
  window: number
  min_value: number
}

export type ConditionSpec =
  | MACrossCond | PriceVsMACond | RSICond | BollingerBreakoutCond | MACDCond
  | VolumeSpikeCond | BoundCond | NorthboundNetInflowCond

export interface ExitRulesSpec {
  stop_loss_pct: number | null
  take_profit_pct: number | null
  max_hold_days: number | null
  signal_reversal: boolean
}

export interface SizingSpec {
  method: 'equal_weight' | 'fixed_amount' | 'vol_adjusted'
  position_size_pct: number
  amount?: number | null
  target_vol_pct?: number | null
}

export interface UniverseFilter {
  boards: string[] | null
  exclude_st: boolean
  market_cap_min: number | null
  market_cap_max: number | null
  sectors_l1: string[] | null
}

export interface ComposableStrategyParams {
  entry_conditions: ConditionSpec[]
  exit_rules: ExitRulesSpec
  sizing: SizingSpec
  max_positions: number
}

export interface ConditionTypeMeta {
  type: ConditionType
  label: string
  params: Record<string, unknown>
}

export interface ScreenerPreview {
  filtered_codes: string[]
  count: number
  total: number
}

// --- Phase 5: walk-forward + factor + regime --------------------------------

export interface FactorAttribution {
  alpha_annualized: number
  loadings: Record<string, number>
  t_stats: Record<string, number>
  r_squared: number
  residual_vol_annualized: number
  n_obs: number
}

export interface RegimePerf {
  n_days: number
  annualized_return: number
  sharpe: number
  max_drawdown: number
}

export interface WalkForwardConfigSpec {
  train_months: number
  test_months: number
  step_months: number
  min_train_bars: number
  overfit_gap_threshold: number
}

export interface WalkForwardRequest {
  request: BacktestRequest
  walk_forward: WalkForwardConfigSpec
}

export interface WindowResultSchema {
  window_idx: number
  train_start: string
  train_end: string
  test_start: string
  test_end: string
  is_summary: Record<string, unknown>
  oos_summary: Record<string, unknown>
  is_oos_sharpe_gap: number
  skipped: boolean
  skip_reason: string | null
}

export interface WalkForwardRunResponse {
  run_id: string
  status: 'completed' | 'failed'
  aggregate_is_sharpe: number
  aggregate_oos_sharpe: number
  aggregate_gap: number
  overfit_flag: boolean
  n_windows: number
  error: string | null
}

export interface WalkForwardResultResponse {
  run_id: string
  status: string
  request: WalkForwardRequest
  aggregate_is_sharpe: number
  aggregate_oos_sharpe: number
  aggregate_gap: number
  overfit_flag: boolean
  windows: WindowResultSchema[]
  oos_equity_curve: EquityPoint[]
  error: string | null
}

export interface WalkForwardRunListItem {
  run_id: string
  status: string
  strategy_type: string
  aggregate_oos_sharpe: number | null
  overfit_flag: boolean | null
  n_windows: number | null
  created_at: string
}
