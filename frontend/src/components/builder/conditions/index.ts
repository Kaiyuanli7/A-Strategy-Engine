import type { ConditionSpec, ConditionType } from '@/types/api'
import BollingerEditor from './BollingerEditor'
import BoundEditor from './BoundEditor'
import MACDEditor from './MACDEditor'
import MACrossEditor from './MACrossEditor'
import NorthboundFlowEditor from './NorthboundFlowEditor'
import PriceVsMAEditor from './PriceVsMAEditor'
import RSIEditor from './RSIEditor'
import VolumeSpikeEditor from './VolumeSpikeEditor'

export interface ConditionTypeDef {
  type: ConditionType
  label: string
  category: 'technical' | 'fundamental' | 'flow'
  component: React.ComponentType<{ spec: any; onChange: (s: any) => void }>
  defaults: () => ConditionSpec
}

export const CONDITION_TYPES: ConditionTypeDef[] = [
  { type: 'ma_cross', label: 'MA crossover', category: 'technical', component: MACrossEditor,
    defaults: () => ({ type: 'ma_cross', fast: 5, slow: 20, direction: 'up' }) },
  { type: 'price_vs_ma', label: 'Price vs MA', category: 'technical', component: PriceVsMAEditor,
    defaults: () => ({ type: 'price_vs_ma', period: 20, op: '>' }) },
  { type: 'rsi', label: 'RSI threshold', category: 'technical', component: RSIEditor,
    defaults: () => ({ type: 'rsi', period: 14, threshold: 30, direction: 'below' }) },
  { type: 'bollinger_breakout', label: 'Bollinger breakout', category: 'technical', component: BollingerEditor,
    defaults: () => ({ type: 'bollinger_breakout', period: 20, k: 2, band: 'upper' }) },
  { type: 'macd', label: 'MACD signal', category: 'technical', component: MACDEditor,
    defaults: () => ({ type: 'macd', fast: 12, slow: 26, signal: 9, event: 'hist_cross_up' }) },
  { type: 'volume_spike', label: 'Volume spike', category: 'technical', component: VolumeSpikeEditor,
    defaults: () => ({ type: 'volume_spike', period: 20, multiple: 2 }) },
  { type: 'pe_bound', label: 'PE bound', category: 'fundamental', component: BoundEditor,
    defaults: () => ({ type: 'pe_bound', min: null, max: 30 }) },
  { type: 'pb_bound', label: 'PB bound', category: 'fundamental', component: BoundEditor,
    defaults: () => ({ type: 'pb_bound', min: null, max: 5 }) },
  { type: 'ps_bound', label: 'PS bound', category: 'fundamental', component: BoundEditor,
    defaults: () => ({ type: 'ps_bound', min: null, max: 10 }) },
  { type: 'roe_bound', label: 'ROE bound (%)', category: 'fundamental', component: BoundEditor,
    defaults: () => ({ type: 'roe_bound', min: 12, max: null }) },
  { type: 'revenue_growth', label: 'Revenue YoY (%)', category: 'fundamental', component: BoundEditor,
    defaults: () => ({ type: 'revenue_growth', min: 10, max: null }) },
  { type: 'nb_net_inflow', label: 'Northbound net inflow', category: 'flow', component: NorthboundFlowEditor,
    defaults: () => ({ type: 'nb_net_inflow', window: 5, min_value: 50_000_000 }) },
  { type: 'nb_holding_pct', label: 'Northbound holding %', category: 'flow', component: BoundEditor,
    defaults: () => ({ type: 'nb_holding_pct', min: 2, max: null }) },
]

export const CONDITION_DEF: Record<ConditionType, ConditionTypeDef> =
  Object.fromEntries(CONDITION_TYPES.map((c) => [c.type, c])) as Record<ConditionType, ConditionTypeDef>
