import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import type { FactorCorrelation, FactorMeta } from '@/types/api'


function corrColor(rho: number): string {
  // Blue (+1) → white (0) → red (-1). Capped at ±1.
  const r = Math.max(-1, Math.min(1, rho))
  if (r >= 0) {
    const alpha = r              // 0..1
    return `rgba(37, 99, 235, ${alpha.toFixed(3)})`   // blue
  } else {
    const alpha = -r             // 0..1
    return `rgba(220, 38, 38, ${alpha.toFixed(3)})`   // red
  }
}

function textColor(rho: number): string {
  return Math.abs(rho) > 0.55 ? '#ffffff' : '#1f2937'
}


export default function FactorCorrelation() {
  const [allFactors, setAllFactors] = useState<FactorMeta[] | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [start, setStart] = useState('2023-01-01')
  const [end, setEnd] = useState('2024-12-31')
  const [universe, setUniverse] = useState('000300')
  const [rebalance, setRebalance] = useState<'weekly' | 'monthly'>('monthly')
  const [running, setRunning] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [result, setResult] = useState<FactorCorrelation | null>(null)

  useEffect(() => {
    api.factors().then((fs) => {
      setAllFactors(fs)
      // Auto-select all factors initially
      setSelected(new Set(fs.map((f) => f.name)))
    }).catch((e) => setErr(String(e)))
  }, [])

  const toggle = (name: string) => {
    const next = new Set(selected)
    if (next.has(name)) next.delete(name)
    else next.add(name)
    setSelected(next)
  }

  const run = async () => {
    if (selected.size < 2) {
      setErr('Pick at least 2 factors')
      return
    }
    setRunning(true)
    setErr(null)
    try {
      const r = await api.factorCorrelation(
        Array.from(selected), start, end, universe, rebalance,
      )
      setResult(r)
    } catch (e) {
      setErr(String(e))
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1>Factor Correlation</h1>
          <div className="text-sm text-ink-600 mt-1">
            Spearman rank correlation between factor scores, averaged across rebalance
            dates. Pairs with |ρ| &gt; 0.7 are mostly redundant — keep one, drop the other.
          </div>
        </div>
      </div>

      {err && <div className="card border-accent-red text-accent-red text-sm">{err}</div>}

      <div className="card space-y-3">
        <div className="metric-key">Factors to compare ({selected.size}/{allFactors?.length ?? 0})</div>
        <div className="flex gap-2 flex-wrap">
          {allFactors?.map((f) => (
            <button
              key={f.name}
              onClick={() => toggle(f.name)}
              className={
                'text-sm border rounded-md px-3 py-1 ' +
                (selected.has(f.name)
                  ? 'border-ink-800 bg-ink-800 text-white'
                  : 'border-ink-200 bg-white hover:bg-ink-50')
              }
            >
              {f.name}
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 items-end">
          <Field label="Universe">
            <input type="text" className="w-full border border-ink-200 rounded px-3 py-2 font-mono text-sm"
                   value={universe} onChange={(e) => setUniverse(e.target.value)} />
          </Field>
          <Field label="Rebalance">
            <select className="w-full border border-ink-200 rounded px-3 py-2 text-sm"
                    value={rebalance} onChange={(e) => setRebalance(e.target.value as 'weekly' | 'monthly')}>
              <option value="weekly">weekly</option>
              <option value="monthly">monthly</option>
            </select>
          </Field>
          <Field label="Start">
            <input type="date" className="w-full border border-ink-200 rounded px-3 py-2 font-mono text-sm"
                   value={start} onChange={(e) => setStart(e.target.value)} />
          </Field>
          <Field label="End">
            <input type="date" className="w-full border border-ink-200 rounded px-3 py-2 font-mono text-sm"
                   value={end} onChange={(e) => setEnd(e.target.value)} />
          </Field>
          <button onClick={run} disabled={running || selected.size < 2}
                  className="bg-ink-800 text-white px-6 py-2 rounded-md text-sm hover:bg-ink-900 disabled:opacity-50">
            {running ? 'Computing…' : 'Compute'}
          </button>
        </div>
      </div>

      {result && (
        <div className="card">
          <div className="flex items-baseline justify-between mb-3">
            <div className="metric-key">Correlation matrix ({result.n_dates} dates)</div>
            <div className="text-xs text-ink-400">
              Blue = positive · Red = negative · Intensity = |ρ|
            </div>
          </div>
          <div className="overflow-auto">
            <table className="border-collapse">
              <thead>
                <tr>
                  <th className="text-xs text-right text-ink-400 px-3 py-1"></th>
                  {result.factors.map((f) => (
                    <th key={f} className="text-xs text-ink-600 px-3 py-1 font-mono">
                      {f}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.matrix.map((row, i) => (
                  <tr key={result.factors[i]}>
                    <td className="text-xs text-right text-ink-600 px-3 py-1 font-mono">
                      {result.factors[i]}
                    </td>
                    {row.map((v, j) => (
                      <td
                        key={j}
                        style={{
                          backgroundColor: corrColor(v),
                          color: textColor(v),
                          minWidth: 80,
                          textAlign: 'center',
                          padding: '8px 12px',
                          fontFamily: 'monospace',
                          fontSize: 12,
                          border: '1px solid #e5e7eb',
                        }}
                        title={`${result.factors[i]} × ${result.factors[j]}: ${v.toFixed(4)}`}
                      >
                        {v.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 text-xs text-ink-400">
            Diagonal cells = 1.0 (factor with itself). High off-diagonal (|ρ| &gt; 0.7) signals
            redundancy — those factors are mostly measuring the same thing.
          </div>
        </div>
      )}

      {!result && !running && (
        <div className="card text-sm text-ink-400">
          Pick factors above and click Compute. Takes ~30 seconds on real CSI 300 data.
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
