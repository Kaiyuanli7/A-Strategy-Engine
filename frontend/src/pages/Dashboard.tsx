import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '@/api/client'
import EquityChart from '@/components/EquityChart'
import DrawdownChart from '@/components/DrawdownChart'
import FillsTable from '@/components/FillsTable'
import MetricsPanel from '@/components/MetricsPanel'
import type { BacktestResult } from '@/types/api'

export default function Dashboard() {
  const { runId } = useParams<{ runId: string }>()
  const [data, setData] = useState<BacktestResult | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (!runId) return
    api.result(runId).then(setData).catch((e) => setErr(String(e)))
  }, [runId])

  if (err) {
    return (
      <div className="card border-accent-red text-accent-red text-sm">
        {err} <Link to="/" className="underline">← back</Link>
      </div>
    )
  }
  if (!data) {
    return <div className="text-ink-400">Loading…</div>
  }
  if (!data.summary) {
    return (
      <div className="card">
        <div>Status: {data.status}</div>
        {data.error && <div className="text-accent-red text-sm mt-2">{data.error}</div>}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1>Backtest result</h1>
          <div className="text-xs text-ink-400 font-mono mt-1">{data.run_id}</div>
        </div>
        <div className="text-sm text-ink-600">
          <span className="font-mono">{data.config.strategy.type}</span>
          {' · '}
          <span className="font-mono">{data.config.config.start} → {data.config.config.end}</span>
          {' · '}
          {data.config.universe.length} stocks
        </div>
      </div>

      <MetricsPanel summary={data.summary} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <EquityChart data={data.equity_curve} initialEquity={data.summary.initial_equity} />
        </div>
        <div>
          <DrawdownChart data={data.equity_curve} />
        </div>
      </div>

      <FillsTable fills={data.fills} rejections={data.rejections} />
    </div>
  )
}
