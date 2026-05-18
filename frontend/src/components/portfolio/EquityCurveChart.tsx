import {
  CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import type { EquityPoint, StockBar } from '@/types/api'

interface Props {
  data: EquityPoint[]
  initialEquity: number
  benchmark?: StockBar[]      // CSI 300 (or other) OHLCV; close used for normalization
  benchmarkLabel?: string
}

function buildSeries(
  equity: EquityPoint[],
  initialEquity: number,
  benchmark: StockBar[] | undefined,
  benchmarkLabel: string,
) {
  if (!benchmark || benchmark.length === 0) {
    return equity.map((p) => ({ ...p, baseline: initialEquity }))
  }
  // Normalize benchmark to initialEquity at first matching date.
  const byDate = new Map(benchmark.map((b) => [b.date, b.close]))
  const equityDates = equity.map((p) => p.date)
  // Find first date present in both series for the anchor close.
  let anchorClose: number | null = null
  for (const d of equityDates) {
    const c = byDate.get(d)
    if (c !== undefined && c > 0) { anchorClose = c; break }
  }
  return equity.map((p) => {
    const close = byDate.get(p.date)
    const benchmarkValue = anchorClose !== null && close !== undefined
      ? (close / anchorClose) * initialEquity
      : null
    return {
      date: p.date,
      equity: p.equity,
      baseline: initialEquity,
      [benchmarkLabel]: benchmarkValue,
    }
  })
}

export default function EquityCurveChart({
  data, initialEquity, benchmark, benchmarkLabel = 'CSI 300',
}: Props) {
  const series = buildSeries(data, initialEquity, benchmark, benchmarkLabel)
  return (
    <div className="card">
      <div className="metric-key mb-2">Equity Curve</div>
      <div style={{ width: '100%', height: 320 }}>
        <ResponsiveContainer>
          <LineChart data={series} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#eceef2" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={40} />
            <YAxis
              tick={{ fontSize: 11 }}
              tickFormatter={(v) => '¥' + (v / 1000).toFixed(0) + 'k'}
              domain={['dataMin - 5000', 'dataMax + 5000']}
            />
            <Tooltip
              formatter={(v: number) =>
                v === null || v === undefined ? '—' : '¥' + Math.round(v).toLocaleString()
              }
              labelStyle={{ fontSize: 12 }}
              contentStyle={{ fontSize: 12 }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <ReferenceLine y={initialEquity} stroke="#cfd4dd" strokeDasharray="4 4" />
            <Line
              name="Portfolio"
              type="monotone" dataKey="equity"
              stroke="#2563eb" strokeWidth={1.8} dot={false}
              isAnimationActive={false}
            />
            {benchmark && benchmark.length > 0 && (
              <Line
                name={benchmarkLabel}
                type="monotone" dataKey={benchmarkLabel}
                stroke="#94a3b8" strokeWidth={1.2}
                strokeDasharray="3 3"
                dot={false} isAnimationActive={false}
                connectNulls
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
      {benchmark && benchmark.length > 0 && (
        <div className="text-xs text-ink-400 mt-2">
          {benchmarkLabel} normalized to ¥{initialEquity.toLocaleString()} at the first
          shared date — both lines start equal so you can read the alpha visually.
        </div>
      )}
    </div>
  )
}
