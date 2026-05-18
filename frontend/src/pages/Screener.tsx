import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/api/client'
import type { FactorMeta, ScreenerResponse } from '@/types/api'


function yuan(v: number | null): string {
  if (v === null || v === undefined) return '—'
  if (v >= 1e8) return '¥' + (v / 1e8).toFixed(1) + '亿'
  return '¥' + Math.round(v).toLocaleString()
}

function num(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  return v.toFixed(digits)
}

function miniBar(value: number, maxAbs: number): React.ReactNode {
  const widthPct = Math.min(100, (Math.abs(value) / Math.max(maxAbs, 1e-9)) * 100)
  const color = value >= 0 ? '#2563eb' : '#dc2626'
  return (
    <div className="relative w-16 h-3 bg-ink-50 rounded-sm overflow-hidden inline-block ml-2">
      <div
        style={{
          width: `${widthPct}%`,
          background: color,
          height: '100%',
          marginLeft: value >= 0 ? 0 : `${100 - widthPct}%`,
        }}
      />
    </div>
  )
}


export default function Screener() {
  const [allFactors, setAllFactors] = useState<FactorMeta[] | null>(null)
  const [selectedFactors, setSelectedFactors] = useState<Set<string>>(new Set())
  const [compositeMethod, setCompositeMethod] = useState<'equal_weight' | 'signed_ic_weighted' | 'fixed_weight'>(
    'equal_weight'
  )
  const [universe, setUniverse] = useState('000300')
  const [topN, setTopN] = useState(30)
  const [excludeSt, setExcludeSt] = useState(true)
  const [minMarketCap, setMinMarketCap] = useState(3_000_000_000)
  const [running, setRunning] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [result, setResult] = useState<ScreenerResponse | null>(null)

  useEffect(() => {
    api.factors().then((fs) => {
      setAllFactors(fs)
      // Pre-select a sensible default composite
      const defaults = new Set<string>()
      for (const f of fs) {
        if (['northbound_momentum', 'earnings_quality', 'valuation_composite'].includes(f.name)) {
          defaults.add(f.name)
        }
      }
      setSelectedFactors(defaults.size > 0 ? defaults : new Set([fs[0]?.name ?? '']))
    }).catch((e) => setErr(String(e)))
  }, [])

  const toggleFactor = (name: string) => {
    const next = new Set(selectedFactors)
    if (next.has(name)) next.delete(name)
    else if (next.size < 5) next.add(name)
    setSelectedFactors(next)
  }

  const run = async () => {
    if (selectedFactors.size === 0) {
      setErr('Pick at least 1 factor')
      return
    }
    setRunning(true)
    setErr(null)
    try {
      const r = await api.screener({
        factors: Array.from(selectedFactors),
        composite_method: compositeMethod,
        universe,
        top_n: topN,
        min_market_cap: minMarketCap,
        exclude_st: excludeSt,
      })
      setResult(r)
    } catch (e) {
      setErr(String(e))
    } finally {
      setRunning(false)
    }
  }

  // For per-factor mini-bars, find each factor's max abs score for normalization
  const factorMaxes = useMemo(() => {
    if (!result) return new Map<string, number>()
    const m = new Map<string, number>()
    for (const e of result.entries) {
      for (const [k, v] of Object.entries(e.factor_scores)) {
        m.set(k, Math.max(m.get(k) ?? 0, Math.abs(v)))
      }
    }
    return m
  }, [result])

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1>Live Screener</h1>
          <div className="text-sm text-ink-600 mt-1">
            "What would I buy today?" — composite ranking on the latest cached date.
            For quality validation, run a backtest first via{' '}
            <Link to="/portfolio" className="text-accent-blue underline">/portfolio</Link>.
          </div>
        </div>
      </div>

      {err && <div className="card border-accent-red text-accent-red text-sm">{err}</div>}

      <div className="card space-y-3">
        <div className="metric-key">Factors ({selectedFactors.size}/5)</div>
        <div className="flex gap-2 flex-wrap">
          {allFactors?.map((f) => (
            <button
              key={f.name}
              onClick={() => toggleFactor(f.name)}
              disabled={!selectedFactors.has(f.name) && selectedFactors.size >= 5}
              className={
                'text-sm border rounded-md px-3 py-1 transition ' +
                (selectedFactors.has(f.name)
                  ? 'border-ink-800 bg-ink-800 text-white'
                  : 'border-ink-200 bg-white hover:bg-ink-50 disabled:opacity-30')
              }
            >
              {f.name}
              <span className="text-xs ml-2 opacity-60">{f.category}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 items-end">
          <Field label="Composite">
            <select className="w-full border border-ink-200 rounded px-3 py-2 text-sm"
                    value={compositeMethod}
                    onChange={(e) => setCompositeMethod(e.target.value as typeof compositeMethod)}>
              <option value="equal_weight">Equal weight</option>
              <option value="signed_ic_weighted">Signed IC</option>
            </select>
          </Field>
          <Field label="Universe">
            <input type="text"
                   className="w-full border border-ink-200 rounded px-3 py-2 font-mono text-sm"
                   value={universe} onChange={(e) => setUniverse(e.target.value)} />
          </Field>
          <Field label="Top N">
            <input type="number" min={1} max={300}
                   className="w-full border border-ink-200 rounded px-3 py-2 font-mono text-sm"
                   value={topN} onChange={(e) => setTopN(Number(e.target.value))} />
          </Field>
          <Field label="Min mkt cap (¥B)">
            <input type="number" min={0} step={1}
                   className="w-full border border-ink-200 rounded px-3 py-2 font-mono text-sm"
                   value={minMarketCap / 1e9}
                   onChange={(e) => setMinMarketCap(Number(e.target.value) * 1e9)} />
          </Field>
          <button onClick={run}
                  disabled={running || selectedFactors.size === 0}
                  className="bg-ink-800 text-white px-6 py-2 rounded-md text-sm hover:bg-ink-900 disabled:opacity-50">
            {running ? 'Computing…' : 'Rank'}
          </button>
        </div>
        <label className="text-xs flex items-center gap-2 mt-3">
          <input type="checkbox" checked={excludeSt} onChange={(e) => setExcludeSt(e.target.checked)} />
          Exclude ST stocks
        </label>
      </div>

      {!result && !running && (
        <div className="card text-sm text-ink-400">
          Pick factors and click Rank. Composite is computed at the most recent
          cached date for all stocks in the universe, filtered by your criteria.
        </div>
      )}

      {result && (
        <div className="card overflow-hidden">
          <div className="flex items-baseline justify-between mb-3">
            <div className="metric-key">
              Top {result.entries.length} of {result.total_ranked} ranked
              <span className="ml-2 text-xs text-ink-400">as of {result.as_of}</span>
            </div>
            <div className="text-xs text-ink-400 font-mono">
              {result.composite_method} · {result.factors.join(' + ')}
            </div>
          </div>
          <div className="overflow-auto max-h-[600px]">
            <table className="data">
              <thead className="sticky top-0 bg-white">
                <tr>
                  <th>#</th>
                  <th>Code</th>
                  <th>Name</th>
                  <th>Sector</th>
                  <th className="text-right">Mkt cap</th>
                  <th className="text-right">Last</th>
                  <th className="text-right">Composite</th>
                  {result.factors.map((f) => (
                    <th key={f} className="text-right text-xs font-mono">{f}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.entries.map((e) => (
                  <tr key={e.code}>
                    <td className="font-mono text-xs">{e.rank}</td>
                    <td className="font-mono">
                      <Link to={`/chart/${e.code}`}
                            className="text-accent-blue hover:underline">
                        {e.code}
                      </Link>
                    </td>
                    <td>{e.name ?? '—'} {e.is_st && <span className="text-accent-red text-xs ml-1">ST</span>}</td>
                    <td className="text-xs text-ink-600">{e.sector ?? '—'}</td>
                    <td className="text-right text-xs">{yuan(e.market_cap)}</td>
                    <td className="text-right">{e.last_price ? '¥' + e.last_price.toFixed(2) : '—'}</td>
                    <td className={'text-right font-semibold ' + (e.composite_score > 0 ? 'pos' : 'neg')}>
                      {num(e.composite_score)}
                    </td>
                    {result.factors.map((f) => {
                      const v = e.factor_scores[f]
                      if (v === undefined) return <td key={f} className="text-right text-ink-300">—</td>
                      const maxAbs = factorMaxes.get(f) ?? 1
                      return (
                        <td key={f} className="text-right">
                          <span className={'text-xs font-mono ' + (v > 0 ? 'pos' : 'neg')}>
                            {num(v, 2)}
                          </span>
                          {miniBar(v, maxAbs)}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}


function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="text-xs">
      <div className="metric-key mb-1">{label}</div>
      {children}
    </label>
  )
}
