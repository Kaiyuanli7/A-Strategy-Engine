import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import type { EquityPoint } from '@/types/api'

interface Props {
  data: EquityPoint[]
}

export default function DrawdownChart({ data }: Props) {
  // Compute drawdown vs running peak
  let peak = -Infinity
  const dd = data.map((p) => {
    peak = Math.max(peak, p.equity)
    return { date: p.date, drawdown: peak > 0 ? (p.equity / peak) - 1 : 0 }
  })
  return (
    <div className="card">
      <div className="metric-key mb-2">Drawdown</div>
      <div style={{ width: '100%', height: 220 }}>
        <ResponsiveContainer>
          <AreaChart data={dd} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#eceef2" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={40} />
            <YAxis
              tick={{ fontSize: 11 }}
              tickFormatter={(v) => (v * 100).toFixed(1) + '%'}
              domain={['auto', 0]}
            />
            <Tooltip
              formatter={(v: number) => (v * 100).toFixed(2) + '%'}
              labelStyle={{ fontSize: 12 }}
              contentStyle={{ fontSize: 12 }}
            />
            <Area
              type="monotone" dataKey="drawdown"
              stroke="#dc2626" fill="#fecaca"
              strokeWidth={1.5} isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
