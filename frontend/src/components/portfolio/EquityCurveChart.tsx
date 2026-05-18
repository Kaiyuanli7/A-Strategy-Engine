import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import type { EquityPoint } from '@/types/api'

interface Props {
  data: EquityPoint[]
  initialEquity: number
}

export default function EquityCurveChart({ data, initialEquity }: Props) {
  const enriched = data.map((p) => ({
    ...p,
    baseline: initialEquity,
    pct: ((p.equity / initialEquity) - 1) * 100,
  }))
  return (
    <div className="card">
      <div className="metric-key mb-2">Equity Curve</div>
      <div style={{ width: '100%', height: 320 }}>
        <ResponsiveContainer>
          <LineChart data={enriched} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#eceef2" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={40} />
            <YAxis
              tick={{ fontSize: 11 }}
              tickFormatter={(v) => '¥' + (v / 1000).toFixed(0) + 'k'}
              domain={['dataMin - 5000', 'dataMax + 5000']}
            />
            <Tooltip
              formatter={(v: number) => '¥' + Math.round(v).toLocaleString()}
              labelStyle={{ fontSize: 12 }}
              contentStyle={{ fontSize: 12 }}
            />
            <ReferenceLine y={initialEquity} stroke="#cfd4dd" strokeDasharray="4 4" />
            <Line
              type="monotone" dataKey="equity"
              stroke="#2563eb" strokeWidth={1.5} dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
