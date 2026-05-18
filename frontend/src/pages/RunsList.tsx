import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '@/api/client'
import type { BacktestRunListItem } from '@/types/api'

const DEMO_UNIVERSE = [
  '600519', '601318', '300750', '601398', '000858',
  '600036', '601012', '002594', '600276', '601888',
]

export default function RunsList() {
  const [runs, setRuns] = useState<BacktestRunListItem[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const nav = useNavigate()

  const refresh = () => {
    setErr(null)
    api.runs().then(setRuns).catch((e) => setErr(String(e)))
  }

  useEffect(refresh, [])

  const launch = async () => {
    setRunning(true)
    setErr(null)
    try {
      const res = await api.runBacktest({
        strategy: { type: 'ma_cross', params: { fast: 5, slow: 20, position_size_pct: 0.05, max_positions: 10 } },
        universe: DEMO_UNIVERSE,
        config: { start: '2023-05-18', end: '2026-05-18', initial_cash: 1_000_000, limit_hit_fill_prob: 0.2, random_seed: 42 },
      })
      nav(`/runs/${res.run_id}`)
    } catch (e) {
      setErr(String(e))
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1>Backtest runs</h1>
        <button
          onClick={launch}
          disabled={running}
          className="bg-ink-800 text-white px-4 py-2 rounded-md text-sm hover:bg-ink-900 disabled:opacity-50"
        >
          {running ? 'Running...' : 'Run dual-MA on demo universe'}
        </button>
      </div>
      {err && <div className="card border-accent-red text-accent-red text-sm">{err}</div>}
      <div className="card overflow-hidden">
        <table className="data">
          <thead>
            <tr>
              <th>Run ID</th>
              <th>Strategy</th>
              <th className="text-right">Universe</th>
              <th>Period</th>
              <th className="text-right">Total Return</th>
              <th className="text-right">Sharpe</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {runs === null ? (
              <tr><td colSpan={8} className="text-ink-400 text-sm">Loading…</td></tr>
            ) : runs.length === 0 ? (
              <tr><td colSpan={8} className="text-ink-400 text-sm">
                No runs yet. Click "Run dual-MA" above to create one.
              </td></tr>
            ) : (
              runs.map((r) => (
                <tr key={r.run_id} className="cursor-pointer">
                  <td className="font-mono text-xs">
                    <Link to={`/runs/${r.run_id}`} className="text-accent-blue hover:underline">
                      {r.run_id.slice(0, 8)}…
                    </Link>
                  </td>
                  <td>{r.strategy_type}</td>
                  <td className="text-right">{r.universe_size}</td>
                  <td className="font-mono text-xs">{r.start} → {r.end}</td>
                  <td className={'text-right ' + (r.total_return && r.total_return > 0 ? 'pos' : 'neg')}>
                    {r.total_return !== null ? (r.total_return * 100).toFixed(2) + '%' : '—'}
                  </td>
                  <td className={'text-right ' + (r.sharpe && r.sharpe > 0 ? 'pos' : 'neg')}>
                    {r.sharpe !== null ? r.sharpe.toFixed(2) : '—'}
                  </td>
                  <td className="text-xs">{r.status}</td>
                  <td className="text-xs text-ink-400">{r.created_at.slice(0, 16).replace('T', ' ')}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
