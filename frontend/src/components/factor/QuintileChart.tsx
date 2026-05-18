import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { QuintileCumPoint } from '@/types/api'

interface Props {
  data: QuintileCumPoint[]
}

const QUINTILE_COLORS: Record<string, string> = {
  q1: '#16a34a', // top quintile (highest factor score) — green
  q2: '#84cc16',
  q3: '#a3a3a3',
  q4: '#f59e0b',
  q5: '#dc2626', // bottom quintile — red
  long_short: '#2563eb',
}

const LABELS: Record<string, string> = {
  q1: 'Q1 (top)',
  q2: 'Q2',
  q3: 'Q3',
  q4: 'Q4',
  q5: 'Q5 (bottom)',
  long_short: 'Long-Short (Q1-Q5)',
}

export default function QuintileChart({ data }: Props) {
  return (
    <div className="card">
      <div className="metric-key mb-2">Quintile cumulative returns</div>
      <div style={{ width: '100%', height: 320 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#eceef2" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={40} />
            <YAxis
              tick={{ fontSize: 11 }}
              tickFormatter={(v) => (v * 100).toFixed(0) + '%'}
            />
            <Tooltip
              formatter={(v: number, name: string) => [(v * 100).toFixed(2) + '%', LABELS[name] ?? name]}
              labelStyle={{ fontSize: 12 }}
              contentStyle={{ fontSize: 12 }}
            />
            <Legend
              wrapperStyle={{ fontSize: 11 }}
              formatter={(value) => LABELS[value] ?? value}
            />
            {(['q1', 'q2', 'q3', 'q4', 'q5'] as const).map((q) => (
              <Line
                key={q}
                type="monotone"
                dataKey={q}
                stroke={QUINTILE_COLORS[q]}
                strokeWidth={q === 'q1' || q === 'q5' ? 2 : 1}
                dot={false}
                isAnimationActive={false}
              />
            ))}
            <Line
              type="monotone"
              dataKey="long_short"
              stroke={QUINTILE_COLORS.long_short}
              strokeWidth={2}
              strokeDasharray="4 3"
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="text-xs text-ink-400 mt-2">
        Q1 = top 20% by factor score (most bullish), Q5 = bottom 20%. Long-Short = Q1 - Q5.
      </div>
    </div>
  )
}
