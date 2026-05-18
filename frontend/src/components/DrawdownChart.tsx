import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useMemo } from 'react'
import type { EquityPoint } from '@/types/api'

interface Props {
  data: EquityPoint[]
}

export default function DrawdownChart({ data }: Props) {
  const dd = useMemo(() => {
    let peak = -Infinity
    return data.map((p) => {
      peak = Math.max(peak, p.equity)
      return { date: p.date, dd: (p.equity / peak - 1) * 100 }
    })
  }, [data])

  return (
    <div className="card">
      <div className="metric-key mb-2">Drawdown</div>
      <div style={{ width: '100%', height: 180 }}>
        <ResponsiveContainer>
          <AreaChart data={dd} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#eceef2" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={40} />
            <YAxis
              tick={{ fontSize: 11 }}
              tickFormatter={(v) => v.toFixed(0) + '%'}
              domain={['auto', 0]}
            />
            <Tooltip
              formatter={(v: number) => v.toFixed(2) + '%'}
              labelStyle={{ fontSize: 12 }}
              contentStyle={{ fontSize: 12 }}
            />
            <Area
              type="monotone"
              dataKey="dd"
              stroke="#dc2626"
              fill="#dc2626"
              fillOpacity={0.15}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
