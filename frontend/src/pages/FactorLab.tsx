import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '@/api/client'
import ICTimeSeriesChart from '@/components/factor/ICTimeSeriesChart'
import QuintileChart from '@/components/factor/QuintileChart'
import DecayCurveChart from '@/components/factor/DecayCurveChart'
import FactorStatsPanel from '@/components/factor/FactorStatsPanel'
import type { FactorEvaluation, FactorMeta } from '@/types/api'


const DEFAULT_START = '2023-06-01'
const DEFAULT_END = '2025-12-31'
const DEFAULT_UNIVERSE = '000300'
const DEFAULT_HORIZON = 20
const DEFAULT_REBALANCE: 'weekly' = 'weekly'


export default function FactorLab() {
  const { name } = useParams<{ name: string }>()
  const nav = useNavigate()

  const [factors, setFactors] = useState<FactorMeta[] | null>(null)
  const [evaluation, setEvaluation] = useState<FactorEvaluation | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const [start, setStart] = useState(DEFAULT_START)
  const [end, setEnd] = useState(DEFAULT_END)
  const [universe, setUniverse] = useState(DEFAULT_UNIVERSE)
  const [horizon, setHorizon] = useState(DEFAULT_HORIZON)
  const [rebalance, setRebalance] = useState<'daily' | 'weekly' | 'monthly'>(DEFAULT_REBALANCE)
  const [lookback, setLookback] = useState<number | undefined>(undefined)

  useEffect(() => {
    api.factors().then(setFactors).catch((e) => setErr(String(e)))
  }, [])

  const selectedFactor = useMemo<FactorMeta | null>(() => {
    if (!factors) return null
    if (!name) return factors[0] ?? null
    return factors.find((f) => f.name === name) ?? factors[0] ?? null
  }, [factors, name])

  useEffect(() => {
    if (!selectedFactor) return
    // Initialize lookback from factor's default
    const lp = selectedFactor.params.find((p) => p.name === 'lookback')
    if (lp && typeof lp.default === 'number') {
      setLookback(lp.default)
    } else {
      setLookback(undefined)
    }
    setEvaluation(null)
    setErr(null)
  }, [selectedFactor?.name])

  const runEval = async () => {
    if (!selectedFactor) return
    setLoading(true)
    setErr(null)
    try {
      const ev = await api.evaluateFactor(selectedFactor.name, {
        start, end, universe, horizon, rebalance,
        lookback: lookback,
      })
      setEvaluation(ev)
    } catch (e) {
      setErr(String(e))
    } finally {
      setLoading(false)
    }
  }

  const onPickFactor = (n: string) => {
    setEvaluation(null)
    nav(`/factors/${n}`)
  }

  if (factors === null && err === null) {
    return <div className="text-ink-400">Loading factors…</div>
  }
  if (err && factors === null) {
    return <div className="card border-accent-red text-accent-red text-sm">{err}</div>
  }

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1>Factor Research Lab</h1>
          {selectedFactor && (
            <div className="text-sm text-ink-600 mt-1">{selectedFactor.description}</div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-4 items-end">
          <div className="lg:col-span-2">
            <label className="metric-key block mb-1">Factor</label>
            <select
              className="w-full border border-ink-200 rounded-md px-3 py-2 text-sm bg-white"
              value={selectedFactor?.name ?? ''}
              onChange={(e) => onPickFactor(e.target.value)}
            >
              {factors?.map((f) => (
                <option key={f.name} value={f.name}>
                  {f.name} · {f.category}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="metric-key block mb-1">Universe</label>
            <input
              type="text"
              className="w-full border border-ink-200 rounded-md px-3 py-2 text-sm font-mono"
              value={universe}
              onChange={(e) => setUniverse(e.target.value)}
              placeholder="000300"
            />
          </div>

          <div>
            <label className="metric-key block mb-1">Rebalance</label>
            <select
              className="w-full border border-ink-200 rounded-md px-3 py-2 text-sm"
              value={rebalance}
              onChange={(e) => setRebalance(e.target.value as 'daily' | 'weekly' | 'monthly')}
            >
              <option value="daily">daily</option>
              <option value="weekly">weekly</option>
              <option value="monthly">monthly</option>
            </select>
          </div>

          <div>
            <label className="metric-key block mb-1">Horizon (days)</label>
            <input
              type="number"
              min={1}
              max={120}
              className="w-full border border-ink-200 rounded-md px-3 py-2 text-sm font-mono"
              value={horizon}
              onChange={(e) => setHorizon(Number(e.target.value))}
            />
          </div>

          <div>
            <label className="metric-key block mb-1">Lookback</label>
            <input
              type="number"
              min={2}
              max={60}
              className="w-full border border-ink-200 rounded-md px-3 py-2 text-sm font-mono"
              value={lookback ?? ''}
              onChange={(e) => setLookback(e.target.value === '' ? undefined : Number(e.target.value))}
              placeholder={String(selectedFactor?.params.find((p) => p.name === 'lookback')?.default ?? '—')}
            />
          </div>

          <div>
            <label className="metric-key block mb-1">Start</label>
            <input
              type="date"
              className="w-full border border-ink-200 rounded-md px-3 py-2 text-sm font-mono"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </div>

          <div>
            <label className="metric-key block mb-1">End</label>
            <input
              type="date"
              className="w-full border border-ink-200 rounded-md px-3 py-2 text-sm font-mono"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          </div>

          <div className="lg:col-span-2 flex justify-end">
            <button
              onClick={runEval}
              disabled={loading || !selectedFactor}
              className="bg-ink-800 text-white px-6 py-2 rounded-md text-sm hover:bg-ink-900 disabled:opacity-50"
            >
              {loading ? 'Evaluating…' : 'Evaluate'}
            </button>
          </div>
        </div>
      </div>

      {err && <div className="card border-accent-red text-accent-red text-sm">{err}</div>}

      {evaluation && (
        <>
          <FactorStatsPanel evaluation={evaluation} />
          <ICTimeSeriesChart data={evaluation.ic_series} mean={evaluation.ic_summary.mean} />
          <QuintileChart data={evaluation.quintile_cum} />
          <DecayCurveChart data={evaluation.decay} />
          {evaluation.cached && (
            <div className="text-xs text-ink-400">
              ↻ Cached result. Tweak any parameter to recompute.
            </div>
          )}
        </>
      )}

      {!evaluation && !loading && (
        <div className="card text-sm text-ink-400">
          Pick a factor, set parameters, and click Evaluate to compute its IC, quintile
          spread, and decay curve. First-time evaluations typically take 10-30 seconds.
        </div>
      )}
    </div>
  )
}
