import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/api/client'
import BacktestConfigForm from '@/components/builder/BacktestConfigForm'
import ConditionList from '@/components/builder/ConditionList'
import ExitRulesForm from '@/components/builder/ExitRulesForm'
import JsonPreview from '@/components/builder/JsonPreview'
import NumInput from '@/components/builder/NumInput'
import SizingForm from '@/components/builder/SizingForm'
import UniverseFilterPanel from '@/components/builder/UniverseFilterPanel'
import UniversePreviewBadge from '@/components/builder/UniversePreviewBadge'
import { CONDITION_DEF } from '@/components/builder/conditions'
import type {
  BacktestConfigSpec,
  ConditionSpec,
  ExitRulesSpec,
  SizingSpec,
  UniverseFilter,
  WalkForwardConfigSpec,
  WalkForwardRequest,
} from '@/types/api'

const DEMO_UNIVERSE = [
  '600519', '601318', '300750', '601398', '000858',
  '600036', '601012', '002594', '600276', '601888',
]

const DEFAULT_FILTER: UniverseFilter = {
  boards: null, exclude_st: true, market_cap_min: null, market_cap_max: null, sectors_l1: null,
}
const DEFAULT_EXIT: ExitRulesSpec = {
  stop_loss_pct: 0.08, take_profit_pct: 0.20, max_hold_days: 30, signal_reversal: true,
}
const DEFAULT_SIZING: SizingSpec = {
  method: 'equal_weight', position_size_pct: 0.10, amount: null, target_vol_pct: null,
}
const DEFAULT_CONFIG: BacktestConfigSpec = {
  start: '2023-05-18', end: '2026-05-18', initial_cash: 1_000_000,
  limit_hit_fill_prob: 0.20, random_seed: 42,
}
const DEFAULT_WF: WalkForwardConfigSpec = {
  train_months: 12, test_months: 3, step_months: 3,
  min_train_bars: 200, overfit_gap_threshold: 0.5,
}

function uid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return Math.random().toString(36).slice(2)
}

export default function WalkForward() {
  const [filter, setFilter] = useState<UniverseFilter>(DEFAULT_FILTER)
  const [conditions, setConditions] = useState([
    { id: uid(), spec: CONDITION_DEF.ma_cross.defaults() as ConditionSpec },
  ])
  const [exitRules, setExitRules] = useState<ExitRulesSpec>(DEFAULT_EXIT)
  const [sizing, setSizing] = useState<SizingSpec>(DEFAULT_SIZING)
  const [maxPositions, setMaxPositions] = useState(8)
  const [config, setConfig] = useState<BacktestConfigSpec>(DEFAULT_CONFIG)
  const [wfConfig, setWfConfig] = useState<WalkForwardConfigSpec>(DEFAULT_WF)
  const [previewCount, setPreviewCount] = useState<number | null>(null)
  const [previewTotal, setPreviewTotal] = useState<number | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const nav = useNavigate()

  useEffect(() => {
    setPreviewLoading(true)
    const t = setTimeout(() => {
      api.screenerPreview(filter)
        .then((r) => { setPreviewCount(r.count); setPreviewTotal(r.total) })
        .catch(() => { setPreviewCount(null); setPreviewTotal(null) })
        .finally(() => setPreviewLoading(false))
    }, 250)
    return () => clearTimeout(t)
  }, [filter])

  const request: WalkForwardRequest = useMemo(() => ({
    request: {
      strategy: {
        type: 'composable',
        params: {
          entry_conditions: conditions.map((r) => r.spec),
          exit_rules: exitRules,
          sizing,
          max_positions: maxPositions,
        },
      },
      universe: DEMO_UNIVERSE,
      universe_filter:
        filter.boards || filter.sectors_l1 || filter.market_cap_min !== null ||
        filter.market_cap_max !== null || !filter.exclude_st ? filter : null,
      config,
    },
    walk_forward: wfConfig,
  }), [conditions, exitRules, sizing, maxPositions, filter, config, wfConfig])

  const submit = async () => {
    if (conditions.length === 0) { setError('Add at least one entry condition.'); return }
    setSubmitting(true); setError(null)
    try {
      const res = await api.runWalkForward(request)
      nav(`/walkforward/${res.run_id}`)
    } catch (e) {
      setError(String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1>Walk-forward validation</h1>
          <div className="text-xs text-ink-400 mt-1">
            Roll a fixed strategy across rolling train/test windows. Flags overfit when
            in-sample vs out-of-sample Sharpe diverges by &gt; 0.5.
          </div>
        </div>
        <div className="flex items-center gap-4">
          <UniversePreviewBadge count={previewCount} total={previewTotal} loading={previewLoading} />
          <button
            onClick={submit}
            disabled={submitting || conditions.length === 0 || previewCount === 0}
            className="bg-ink-800 text-white px-4 py-2 rounded-md text-sm hover:bg-ink-900 disabled:opacity-50"
          >
            {submitting ? 'Running…' : 'Run walk-forward'}
          </button>
        </div>
      </div>

      {error && <div className="card border-accent-red text-accent-red text-sm">{error}</div>}

      <div className="card space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-400">
          Walk-forward windows
        </h2>
        <div className="flex flex-wrap gap-3 text-sm items-center">
          <label className="flex items-center gap-2">
            <span className="text-ink-600">Train (months)</span>
            <NumInput value={wfConfig.train_months}
              onChange={(v) => setWfConfig({ ...wfConfig, train_months: v ?? 12 })}
              min={1} max={60} />
          </label>
          <label className="flex items-center gap-2">
            <span className="text-ink-600">Test (months)</span>
            <NumInput value={wfConfig.test_months}
              onChange={(v) => setWfConfig({ ...wfConfig, test_months: v ?? 3 })}
              min={1} max={36} />
          </label>
          <label className="flex items-center gap-2">
            <span className="text-ink-600">Step (months)</span>
            <NumInput value={wfConfig.step_months}
              onChange={(v) => setWfConfig({ ...wfConfig, step_months: v ?? 3 })}
              min={1} max={36} />
          </label>
          <label className="flex items-center gap-2">
            <span className="text-ink-600">Min train bars</span>
            <NumInput value={wfConfig.min_train_bars}
              onChange={(v) => setWfConfig({ ...wfConfig, min_train_bars: v ?? 200 })}
              min={20} />
          </label>
          <label className="flex items-center gap-2">
            <span className="text-ink-600">Overfit gap threshold</span>
            <NumInput value={wfConfig.overfit_gap_threshold}
              onChange={(v) => setWfConfig({ ...wfConfig, overfit_gap_threshold: v ?? 0.5 })}
              step={0.1} min={0} />
          </label>
        </div>
      </div>

      <UniverseFilterPanel value={filter} onChange={setFilter} />
      <ConditionList rows={conditions} onChange={setConditions} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ExitRulesForm value={exitRules} onChange={setExitRules} />
        <SizingForm value={sizing} maxPositions={maxPositions}
          onChange={setSizing} onMaxPositionsChange={setMaxPositions} />
      </div>
      <BacktestConfigForm value={config} onChange={setConfig} />
      <JsonPreview data={request} />
    </div>
  )
}
