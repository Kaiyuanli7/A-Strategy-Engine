import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from '@/api/client'
import type { WalkForwardResultResponse } from '@/types/api'


function pct(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—'
  return (x * 100).toFixed(2) + '%'
}

function num(x: number | null | undefined, digits = 2): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—'
  return x.toFixed(digits)
}

export default function WalkForwardResult() {
  const { runId } = useParams<{ runId: string }>()
  const [data, setData] = useState<WalkForwardResultResponse | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (!runId) return
    api.walkForwardResult(runId).then(setData).catch((e) => setErr(String(e)))
  }, [runId])

  if (err) return (
    <div className="card border-accent-red text-accent-red text-sm">
      {err} <Link to="/walkforward" className="underline">← back</Link>
    </div>
  )
  if (!data) return <div className="text-ink-400">Loading…</div>

  const completed = data.windows.filter((w) => !w.skipped)
  const scatter = completed.map((w) => ({
    is: (w.is_summary as Record<string, unknown>).sharpe as number ?? 0,
    oos: (w.oos_summary as Record<string, unknown>).sharpe as number ?? 0,
    label: `W${w.window_idx}`,
  }))
  const minScatter = Math.min(-1, ...scatter.flatMap((p) => [p.is, p.oos]))
  const maxScatter = Math.max(1, ...scatter.flatMap((p) => [p.is, p.oos]))

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1>Walk-forward result</h1>
          <div className="text-xs text-ink-400 mt-1 font-mono">{data.run_id}</div>
        </div>
        <Link to="/walkforward" className="text-sm text-accent-blue underline">← new run</Link>
      </div>

      {/* Headline */}
      <div className={
        'card ' + (data.overfit_flag ? 'border-accent-red bg-red-50' : '')
      }>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <div className="metric-key">Aggregate IS Sharpe</div>
            <div className="metric-val">{num(data.aggregate_is_sharpe)}</div>
          </div>
          <div>
            <div className="metric-key">Aggregate OOS Sharpe</div>
            <div className={'metric-val ' + (data.aggregate_oos_sharpe > 0 ? 'pos' : 'neg')}>
              {num(data.aggregate_oos_sharpe)}
            </div>
          </div>
          <div>
            <div className="metric-key">IS - OOS Gap</div>
            <div className={'metric-val ' + (Math.abs(data.aggregate_gap) > 0.5 ? 'neg' : '')}>
              {num(data.aggregate_gap)}
            </div>
          </div>
          <div>
            <div className="metric-key">Overfit flag</div>
            <div className={'metric-val ' + (data.overfit_flag ? 'neg' : 'pos')}>
              {data.overfit_flag ? '⚠ OVERFIT' : 'OK'}
            </div>
          </div>
        </div>
        {data.overfit_flag && (
          <div className="text-sm text-accent-red mt-3">
            IS-OOS Sharpe gap exceeds threshold. The strategy fits training data
            much better than it generalizes — do NOT deploy.
          </div>
        )}
      </div>

      {/* OOS equity curve */}
      <div className="card">
        <div className="metric-key mb-2">Concatenated OOS Equity Curve</div>
        {data.oos_equity_curve.length > 0 ? (
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
              <LineChart data={data.oos_equity_curve}>
                <CartesianGrid stroke="#eceef2" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={40} />
                <YAxis tick={{ fontSize: 11 }}
                  tickFormatter={(v) => '¥' + (v / 1000).toFixed(0) + 'k'}
                  domain={['dataMin - 5000', 'dataMax + 5000']} />
                <Tooltip formatter={(v: number) => '¥' + Math.round(v).toLocaleString()}
                  contentStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="equity" stroke="#2563eb"
                  strokeWidth={1.5} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="text-ink-400 text-sm">No OOS bars produced — strategy may have made no trades.</div>
        )}
      </div>

      {/* IS vs OOS scatter */}
      <div className="card">
        <div className="metric-key mb-2">IS vs OOS Sharpe per Window</div>
        <div className="text-xs text-ink-400 mb-2">
          Points on the dashed line: backtest generalizes. Points far below the line: overfit window.
        </div>
        {scatter.length > 0 ? (
          <div style={{ width: '100%', height: 280 }}>
            <ResponsiveContainer>
              <ScatterChart>
                <CartesianGrid stroke="#eceef2" />
                <XAxis dataKey="is" type="number" name="IS Sharpe"
                  domain={[minScatter, maxScatter]} tick={{ fontSize: 11 }} />
                <YAxis dataKey="oos" type="number" name="OOS Sharpe"
                  domain={[minScatter, maxScatter]} tick={{ fontSize: 11 }} />
                <ReferenceLine
                  segment={[{ x: minScatter, y: minScatter }, { x: maxScatter, y: maxScatter }]}
                  stroke="#cfd4dd" strokeDasharray="4 4" />
                <Tooltip cursor={{ strokeDasharray: '3 3' }}
                  contentStyle={{ fontSize: 12 }} />
                <Scatter data={scatter} fill="#2563eb" />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="text-ink-400 text-sm">No completed windows.</div>
        )}
      </div>

      {/* Window table */}
      <div className="card overflow-hidden">
        <div className="metric-key mb-2">Per-Window Detail ({data.windows.length} windows)</div>
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
                <th className="text-right">OOS Return</th>
                <th className="text-right">OOS Fills</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.windows.map((w) => {
                const isS = (w.is_summary as Record<string, unknown>).sharpe as number | undefined
                const oosS = (w.oos_summary as Record<string, unknown>).sharpe as number | undefined
                const oosR = (w.oos_summary as Record<string, unknown>).total_return as number | undefined
                const oosF = (w.oos_summary as Record<string, unknown>).n_fills as number | undefined
                const gap = w.is_oos_sharpe_gap
                const overfit = Math.abs(gap) > 0.5
                return (
                  <tr key={w.window_idx} className={overfit ? 'bg-red-50' : ''}>
                    <td className="font-mono text-xs">{w.window_idx}</td>
                    <td className="font-mono text-xs">{w.train_start}→{w.train_end}</td>
                    <td className="font-mono text-xs">{w.test_start}→{w.test_end}</td>
                    <td className="text-right">{num(isS)}</td>
                    <td className={'text-right ' + (oosS && oosS > 0 ? 'pos' : 'neg')}>{num(oosS)}</td>
                    <td className={'text-right ' + (overfit ? 'neg' : '')}>{num(gap)}</td>
                    <td className="text-right">{pct(oosR)}</td>
                    <td className="text-right">{oosF ?? '—'}</td>
                    <td className="text-xs">
                      {w.skipped ? <span className="text-ink-400">skipped: {w.skip_reason}</span> : 'ok'}
                    </td>
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
