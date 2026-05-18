import { useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '@/api/client'
import type { StockOHLCV, Universe, UniverseStock } from '@/types/api'

const BOARD_LABEL: Record<string, string> = {
  main_sh: '沪市主板',
  main_sz: '深市主板',
  chinext: '创业板',
  star: '科创板',
  beijing: '北交所',
  unknown: '—',
}

export default function Screener() {
  const [universe, setUniverse] = useState<Universe | null>(null)
  const [board, setBoard] = useState<string>('all')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [bars, setBars] = useState<StockOHLCV | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.universe().then(setUniverse).catch((e) => setErr(String(e)))
  }, [])

  useEffect(() => {
    if (!selected) {
      setBars(null)
      return
    }
    api.stock(selected).then(setBars).catch((e) => setErr(String(e)))
  }, [selected])

  const filtered: UniverseStock[] = useMemo(() => {
    if (!universe) return []
    const s = search.trim().toLowerCase()
    return universe.stocks.filter((u) => {
      if (board !== 'all' && u.board !== board) return false
      if (!s) return true
      return u.code.includes(s) || u.name.toLowerCase().includes(s)
    })
  }, [universe, board, search])

  return (
    <div className="space-y-4">
      <h1>Screener</h1>
      {err && <div className="card border-accent-red text-accent-red text-sm">{err}</div>}

      <div className="flex flex-wrap gap-2 items-center">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Code or name…"
          className="border border-ink-200 rounded-md px-3 py-1.5 text-sm w-56"
        />
        <select
          value={board}
          onChange={(e) => setBoard(e.target.value)}
          className="border border-ink-200 rounded-md px-3 py-1.5 text-sm"
        >
          <option value="all">All boards</option>
          <option value="main_sh">沪市主板 (Main SH)</option>
          <option value="main_sz">深市主板 (Main SZ)</option>
          <option value="chinext">创业板 (ChiNext)</option>
          <option value="star">科创板 (STAR)</option>
        </select>
        <div className="text-xs text-ink-400">
          {filtered.length} / {universe?.stocks.length ?? 0} stocks
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card overflow-hidden lg:col-span-1">
          <table className="data">
            <thead>
              <tr>
                <th>Code</th>
                <th>Name</th>
                <th>Board</th>
                <th>ST</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
                <tr
                  key={s.code}
                  onClick={() => setSelected(s.code)}
                  className={
                    'cursor-pointer ' +
                    (selected === s.code ? 'bg-ink-100' : '')
                  }
                >
                  <td className="font-mono">{s.code}</td>
                  <td>{s.name}</td>
                  <td className="text-xs text-ink-600">{BOARD_LABEL[s.board] ?? s.board}</td>
                  <td>{s.is_st ? <span className="neg">ST</span> : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="lg:col-span-2 space-y-4">
          {!selected ? (
            <div className="card text-ink-400 text-sm">
              Click a stock on the left to see its OHLCV chart.
            </div>
          ) : !bars ? (
            <div className="card text-ink-400 text-sm">Loading {selected}…</div>
          ) : (
            <>
              <div className="card">
                <div className="flex items-baseline gap-4">
                  <div>
                    <span className="font-mono text-lg">{bars.code}</span>{' '}
                    <span className="text-lg">{bars.name}</span>
                  </div>
                  <div className="text-xs text-ink-400">
                    {BOARD_LABEL[bars.board ?? 'unknown']} · {bars.bars.length} bars
                  </div>
                </div>
                <div style={{ width: '100%', height: 320 }} className="mt-2">
                  <ResponsiveContainer>
                    <LineChart data={bars.bars} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                      <CartesianGrid stroke="#eceef2" />
                      <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={50} />
                      <YAxis
                        tick={{ fontSize: 11 }}
                        domain={['auto', 'auto']}
                        tickFormatter={(v) => '¥' + v.toFixed(0)}
                      />
                      <Tooltip
                        formatter={(v: number) => '¥' + v.toFixed(2)}
                        contentStyle={{ fontSize: 12 }}
                      />
                      <Line
                        type="monotone"
                        dataKey="close"
                        stroke="#2563eb"
                        strokeWidth={1.5}
                        dot={false}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
