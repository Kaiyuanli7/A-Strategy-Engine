import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { DecayPoint } from '@/types/api'

interface Props {
  data: DecayPoint[]
}

export default function DecayCurveChart({ data }: Props) {
  return (
    <div className="card">
      <div className="metric-key mb-2">Factor decay (IC by forward horizon)</div>
      <div style={{ width: '100%', height: 240 }}>
        <ResponsiveContainer>
          <BarChart
            data={data.map((p) => ({ ...p, label: `${p.horizon}d` }))}
            margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
          >
            <CartesianGrid stroke="#eceef2" />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => v.toFixed(3)} />
            <Tooltip
              formatter={(v: number, name: string) => [
                v.toFixed(4),
                name === 'ic_mean' ? 'IC mean' : name === 'ic_ir' ? 'IC IR' : name,
              ]}
              labelStyle={{ fontSize: 12 }}
              contentStyle={{ fontSize: 12 }}
            />
            <Bar dataKey="ic_mean" fill="#2563eb" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="text-xs text-ink-400 mt-2">
        Peak horizon tells you the natural holding period; fast-decaying factors need
        frequent rebalancing.
      </div>
    </div>
  )
}
