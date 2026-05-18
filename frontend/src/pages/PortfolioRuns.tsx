import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/api/client'
import type { PortfolioRunListItem } from '@/types/api'


function pct(v: number | null, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return (v * 100).toFixed(digits) + '%'
}

function num(v: number | null, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return v.toFixed(digits)
}


export default function PortfolioRuns() {
  const [runs, setRuns] = useState<PortfolioRunListItem[] | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.portfolioRuns()
      .then(setRuns)
      .catch((e) => setErr(String(e)))
  }, [])

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1>Portfolio backtest runs</h1>
          <div className="text-sm text-ink-600 mt-1">
            All portfolio backtests, newest first. Click any to see the full result.
          </div>
        </div>
        <Link to="/portfolio" className="text-sm text-accent-blue underline">
          ← new backtest
        </Link>
      </div>

      {err && <div className="card border-accent-red text-accent-red text-sm">{err}</div>}

      {runs === null ? (
        <div className="text-ink-400">Loading…</div>
      ) : runs.length === 0 ? (
        <div className="card text-sm text-ink-400">
          No runs yet. Go to <Link to="/portfolio" className="text-accent-blue underline">/portfolio</Link>
          {' '}to create one.
        </div>
      ) : (
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
              {runs.map((r) => (
                <tr key={r.run_id}>
                  <td className="font-mono text-xs">
                    <Link to={`/portfolio/runs/${r.run_id}`}
                          className="text-accent-blue hover:underline">
                      {r.run_id.slice(0, 8)}…
                    </Link>
                  </td>
                  <td className="text-xs font-mono">{r.strategy_type}</td>
                  <td className="text-right">{r.universe_size}</td>
                  <td className="font-mono text-xs">{r.start} → {r.end}</td>
                  <td className={'text-right ' +
                                 (r.total_return !== null && r.total_return > 0 ? 'pos' : 'neg')}>
                    {pct(r.total_return)}
                  </td>
                  <td className={'text-right ' +
                                 (r.sharpe !== null && r.sharpe > 0 ? 'pos' : 'neg')}>
                    {num(r.sharpe)}
                  </td>
                  <td className="text-xs">{r.status}</td>
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
