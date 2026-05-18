import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ICPoint } from '@/types/api'

interface Props {
  data: ICPoint[]
  mean: number
}

function rolling(data: ICPoint[], window: number): { date: string; ic: number; rolling: number | null }[] {
  return data.map((p, i) => {
    if (i < window - 1) return { ...p, rolling: null }
    let s = 0
    for (let j = i - window + 1; j <= i; j++) s += data[j].ic
    return { ...p, rolling: s / window }
  })
}

export default function ICTimeSeriesChart({ data, mean }: Props) {
  const withRolling = rolling(data, Math.min(8, Math.max(2, Math.floor(data.length / 6))))
  return (
    <div className="card">
      <div className="flex items-baseline justify-between mb-2">
        <div className="metric-key">IC time series</div>
        <div className="text-xs text-ink-400">
          mean = <span className={mean > 0 ? 'pos' : 'neg'}>{mean.toFixed(4)}</span>{' '}
          · n = {data.length}
        </div>
      </div>
      <div style={{ width: '100%', height: 280 }}>
        <ResponsiveContainer>
          <LineChart data={withRolling} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#eceef2" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={40} />
            <YAxis
              tick={{ fontSize: 11 }}
              tickFormatter={(v) => v.toFixed(2)}
              domain={[-0.5, 0.5]}
            />
            <Tooltip
              formatter={(v: number) => (v === null ? '—' : v.toFixed(4))}
              labelStyle={{ fontSize: 12 }}
              contentStyle={{ fontSize: 12 }}
            />
            <ReferenceLine y={0} stroke="#cfd4dd" />
            <ReferenceLine y={mean} stroke="#dc2626" strokeDasharray="3 3" />
            <Line
              type="monotone"
              dataKey="ic"
              stroke="#94a3b8"
              strokeWidth={1}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="rolling"
              stroke="#2563eb"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="text-xs text-ink-400 mt-2">
        Grey = per-period IC; Blue = rolling average; Red dashed = full-period mean.
      </div>
    </div>
  )
}
