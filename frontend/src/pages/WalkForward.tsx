import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer,
  ReferenceLine, Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from '@/api/client'
import type {
  WalkForwardResult, WalkForwardRunListItem,
} from '@/types/api'


function num(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  return v.toFixed(digits)
}


export default function WalkForwardPage() {
  const { runId } = useParams<{ runId: string }>()
  const [runs, setRuns] = useState<WalkForwardRunListItem[] | null>(null)
  const [result, setResult] = useState<WalkForwardResult | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.walkForwardRuns().then(setRuns).catch((e) => setErr(String(e)))
  }, [])

  useEffect(() => {
    if (!runId) { setResult(null); return }
    api.walkForwardResult(runId).then(setResult).catch((e) => setErr(String(e)))
  }, [runId])

  if (err) return <div className="card border-accent-red text-accent-red text-sm">{err}</div>

  // --------- Result view ---------
  if (runId) {
    if (!result) return <div className="text-ink-400">Loading…</div>
    const agg = result.aggregate
    const factors = Array.from(new Set(result.windows.flatMap((w) => Object.keys(w.weights))))
    const scatterData = result.windows
      .filter((w) => w.oos_sharpe !== null)
      .map((w) => ({ is: w.is_sharpe, oos: w.oos_sharpe as number, idx: w.window_idx }))
    const scatterMin = Math.min(-1, ...scatterData.flatMap((p) => [p.is, p.oos]))
    const scatterMax = Math.max(1, ...scatterData.flatMap((p) => [p.is, p.oos]))

    return (
      <div className="space-y-4">
        <div className="flex items-baseline justify-between">
          <div>
            <h1>Walk-forward result</h1>
            <div className="text-xs text-ink-400 mt-1 font-mono">{result.run_id}</div>
            <div className="text-xs text-ink-400">
              {result.created_at.slice(0, 16).replace('T', ' ')}
              {' · '}
              factors: {factors.join(', ')}
            </div>
          </div>
          <Link to="/walkforward" className="text-sm text-accent-blue underline">
            ← all runs
          </Link>
        </div>

        {/* Aggregate / overfit headline */}
        {agg && (
          <div className={
            'card border-l-4 ' +
            (agg.overfit ? 'border-accent-red bg-rose-50' : 'border-accent-green bg-emerald-50')
          }>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Stat label="Avg IS Sharpe" value={num(agg.is_sharpe)} />
              <Stat label="Avg OOS Sharpe" value={num(agg.oos_sharpe)}
                    tone={agg.oos_sharpe > 0 ? 'pos' : 'neg'} />
              <Stat label="IS − OOS gap" value={num(agg.is_oos_gap)}
                    tone={Math.abs(agg.is_oos_gap) > 0.5 ? 'neg' : ''} />
              <Stat label="Overfit?"
                    value={agg.overfit ? '⚠ OVERFIT' : '✓ OK'}
                    tone={agg.overfit ? 'neg' : 'pos'} />
            </div>
            {agg.overfit && (
              <div className="text-sm text-accent-red mt-3">
                The IS-OOS Sharpe gap exceeds 0.5 — the fitted weights generalize
                much worse out-of-sample than in-sample. Do <strong>not</strong>
                deploy this composite. Try: more regularization (higher
                l2_lambda), fewer factors, more trials, a longer training window,
                or different factors with less in-sample optimization room.
              </div>
            )}
          </div>
        )}

        {/* IS vs OOS scatter */}
        <div className="card">
          <div className="metric-key mb-2">IS vs OOS Sharpe per window</div>
          <div className="text-xs text-ink-400 mb-2">
            Points on the dashed diagonal: the fit generalized. Points below the
            diagonal: in-sample magic that didn't survive OOS.
          </div>
          {scatterData.length > 0 ? (
            <div style={{ width: '100%', height: 300 }}>
              <ResponsiveContainer>
                <ScatterChart>
                  <CartesianGrid stroke="#eceef2" />
                  <XAxis dataKey="is" type="number" name="IS Sharpe"
                         domain={[scatterMin, scatterMax]} tick={{ fontSize: 11 }} />
                  <YAxis dataKey="oos" type="number" name="OOS Sharpe"
                         domain={[scatterMin, scatterMax]} tick={{ fontSize: 11 }} />
                  <ReferenceLine
                    segment={[
                      { x: scatterMin, y: scatterMin },
                      { x: scatterMax, y: scatterMax },
                    ]}
                    stroke="#cfd4dd" strokeDasharray="4 4" />
                  <Tooltip cursor={{ strokeDasharray: '3 3' }}
                           contentStyle={{ fontSize: 12 }}
                           formatter={(v: number) => v.toFixed(3)}
                           labelFormatter={(_) => ''} />
                  <Scatter data={scatterData} fill="#2563eb" />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="text-ink-400 text-sm">No completed windows.</div>
          )}
        </div>

        {/* Per-window weight stability */}
        <div className="card">
          <div className="metric-key mb-2">Weight stability across windows</div>
          <div className="text-xs text-ink-400 mb-2">
            Each window's fitted weight per factor. Stable weights across windows
            = robust signal. Wildly varying weights = overfitting in-sample.
          </div>
          {factors.map((f) => {
            const data = result.windows.map((w) => ({
              window: 'W' + w.window_idx, weight: w.weights[f] ?? 0,
            }))
            return (
              <div key={f} className="mb-4">
                <div className="text-xs font-mono text-ink-600 mb-1">{f}</div>
                <div style={{ width: '100%', height: 100 }}>
                  <ResponsiveContainer>
                    <BarChart data={data}
                              margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid stroke="#eceef2" vertical={false} />
                      <XAxis dataKey="window" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 10 }}
                             tickFormatter={(v) => v.toFixed(2)} />
                      <ReferenceLine y={0} stroke="#9ca3af" />
                      <Tooltip formatter={(v: number) => v.toFixed(4)}
                               contentStyle={{ fontSize: 12 }} />
                      <Bar dataKey="weight">
                        {data.map((d, i) => (
                          <Cell key={i} fill={d.weight >= 0 ? '#2563eb' : '#dc2626'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )
          })}
        </div>

        {/* Per-window detail table */}
        <div className="card overflow-hidden">
          <div className="metric-key mb-2">Per-window detail</div>
          <div className="overflow-auto max-h-96">
            <table className="data">
              <thead className="sticky top-0 bg-white">
                <tr>
                  <th>#</th>
                  <th>Train</th>
                  <th>Test</th>
                  <th className="text-right">IS Sharpe</th>
                  <th className="text-right">OOS Sharpe</th>
                  <th className="text-right">Gap</th>
                  {factors.map((f) => (
                    <th key={f} className="text-right text-xs font-mono">{f}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.windows.map((w) => {
                  const gap = w.oos_sharpe !== null
                    ? w.is_sharpe - w.oos_sharpe : null
                  const overfit = gap !== null && Math.abs(gap) > 0.5
                  return (
                    <tr key={w.window_idx} className={overfit ? 'bg-rose-50' : ''}>
                      <td className="font-mono text-xs">{w.window_idx}</td>
                      <td className="font-mono text-xs">{w.train_start}→{w.train_end}</td>
                      <td className="font-mono text-xs">{w.test_start}→{w.test_end}</td>
                      <td className="text-right">{num(w.is_sharpe)}</td>
                      <td className={'text-right ' +
                                     (w.oos_sharpe === null ? '' :
                                      w.oos_sharpe > 0 ? 'pos' : 'neg')}>
                        {num(w.oos_sharpe)}
                      </td>
                      <td className={'text-right ' + (overfit ? 'neg' : '')}>
                        {gap !== null ? num(gap) : '—'}
                      </td>
                      {factors.map((f) => (
                        <td key={f} className="text-right text-xs font-mono">
                          {num(w.weights[f] ?? 0, 3)}
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    )
  }

  // --------- List view ---------
  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1>Walk-forward weight optimization</h1>
          <div className="text-sm text-ink-600 mt-1">
            Optuna-fitted composite weights with rolling IS/OOS validation.
          </div>
        </div>
      </div>

      <div className="card text-sm">
        Walk-forward runs are produced by the{' '}
        <code className="font-mono text-xs bg-ink-50 px-1 rounded">scripts/optimize_weights.py</code>
        {' '}CLI. Each run is persisted to the DB and appears below — click any to see
        per-window IS/OOS Sharpe, weight stability across windows, and the overfit verdict.
        <div className="mt-2 text-xs text-ink-400 font-mono whitespace-pre">
{`python scripts/optimize_weights.py \\
    --factors momentum_skip,northbound_momentum,earnings_quality \\
    --start 2022-01-01 --end 2025-12-31 --walk-forward \\
    --train-months 12 --test-months 3 --n-trials 100`}
        </div>
      </div>

      {runs === null ? (
        <div className="text-ink-400">Loading runs…</div>
      ) : runs.length === 0 ? (
        <div className="card text-sm text-ink-400">
          No walk-forward runs yet. Run the CLI command above to create one.
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="data">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Factors</th>
                <th className="text-right">Windows</th>
                <th className="text-right">OOS Sharpe</th>
                <th>Overfit?</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id}>
                  <td className="font-mono text-xs">
                    <Link to={`/walkforward/${r.run_id}`}
                          className="text-accent-blue hover:underline">
                      {r.run_id.slice(0, 8)}…
                    </Link>
                  </td>
                  <td className="font-mono text-xs">{r.strategy_type}</td>
                  <td className="text-right">{r.n_windows ?? '—'}</td>
                  <td className={'text-right ' +
                                 (r.aggregate_oos_sharpe !== null
                                  ? r.aggregate_oos_sharpe! > 0 ? 'pos' : 'neg' : '')}>
                    {num(r.aggregate_oos_sharpe)}
                  </td>
                  <td className={'text-xs ' + (r.overfit_flag ? 'neg' : 'pos')}>
                    {r.overfit_flag ? '⚠ OVERFIT' : '✓ OK'}
                  </td>
                  <td className="text-xs text-ink-400">
                    {r.created_at.slice(0, 16).replace('T', ' ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}


function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className="metric-key">{label}</div>
      <div className={'metric-val ' + (tone ?? '')}>{value}</div>
    </div>
  )
}
