import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { HoldingRecord } from '@/types/api'

interface Props {
  holdings: HoldingRecord[]
  runId?: string         // if set, code links go to the chart with this run's signals
}

type SortKey = 'market_value' | 'pnl_pct' | 'shares' | 'code' | 'entry_date'

function pct(v: number, digits = 2): string {
  return (v * 100).toFixed(digits) + '%'
}

function yuan(v: number): string {
  return '¥' + Math.round(v).toLocaleString()
}

export default function HoldingsPanel({ holdings, runId }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('market_value')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  if (holdings.length === 0) {
    return (
      <div className="card text-sm text-ink-400">
        No open positions at end of backtest (fully exited to cash).
      </div>
    )
  }

  const sorted = [...holdings].sort((a, b) => {
    const av = a[sortKey] as number | string
    const bv = b[sortKey] as number | string
    if (typeof av === 'number' && typeof bv === 'number') {
      return sortDir === 'desc' ? bv - av : av - bv
    }
    return sortDir === 'desc'
      ? String(bv).localeCompare(String(av))
      : String(av).localeCompare(String(bv))
  })

  const totalMV = holdings.reduce((acc, h) => acc + h.market_value, 0)
  const winners = holdings.filter((h) => h.pnl > 0).length

  const head = (key: SortKey, label: string, align: 'left' | 'right' = 'right') => (
    <th
      className={'cursor-pointer hover:text-ink-800 ' +
                 (align === 'right' ? 'text-right' : '')}
      onClick={() => {
        if (sortKey === key) setSortDir(sortDir === 'desc' ? 'asc' : 'desc')
        else { setSortKey(key); setSortDir('desc') }
      }}
    >
      {label}
      {sortKey === key && (
        <span className="ml-1 text-xs">{sortDir === 'desc' ? '↓' : '↑'}</span>
      )}
    </th>
  )

  return (
    <div className="card">
      <div className="flex items-baseline justify-between mb-2">
        <div className="metric-key">
          Final holdings · {holdings.length} positions · {yuan(totalMV)} market value
        </div>
        <div className="text-xs text-ink-400">
          {winners}/{holdings.length} winners
        </div>
      </div>
      <div className="overflow-auto max-h-96">
        <table className="data">
          <thead className="sticky top-0 bg-white">
            <tr>
              {head('code', 'Code', 'left')}
              <th>Sector</th>
              {head('shares', 'Shares')}
              <th className="text-right">Avg cost</th>
              <th className="text-right">Last</th>
              {head('market_value', 'Mkt value')}
              <th className="text-right">Weight</th>
              {head('pnl_pct', 'PnL %')}
              {head('entry_date', 'Entry', 'left')}
            </tr>
          </thead>
          <tbody>
            {sorted.map((h) => (
              <tr key={h.code}>
                <td className="font-mono">
                  <Link
                    to={`/chart/${h.code}${runId ? `?run_id=${runId}` : ''}`}
                    className="text-accent-blue hover:underline"
                  >
                    {h.code}
                  </Link>
                </td>
                <td className="text-xs text-ink-600">{h.sector ?? '—'}</td>
                <td className="text-right">{h.shares.toLocaleString()}</td>
                <td className="text-right">¥{h.avg_cost.toFixed(2)}</td>
                <td className="text-right">¥{h.last_price.toFixed(2)}</td>
                <td className="text-right">{yuan(h.market_value)}</td>
                <td className="text-right text-xs text-ink-400">
                  {pct(h.market_value / totalMV, 1)}
                </td>
                <td className={'text-right ' + (h.pnl_pct > 0 ? 'pos' : 'neg')}>
                  {pct(h.pnl_pct)}
                </td>
                <td className="font-mono text-xs">{h.entry_date}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
