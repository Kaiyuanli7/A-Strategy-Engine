import type { EquityPoint } from '@/types/api'

interface Props {
  data: EquityPoint[]
}

/**
 * Year × Month grid of monthly returns. CN-convention coloring: red = positive,
 * green = negative (matches Chinese market UI).
 *
 * Returns are computed from the equity curve: for each month, take the last
 * equity value of the prior month as the baseline, then (last_in_month /
 * baseline) - 1. The first month uses its earliest available equity.
 */
function computeMonthlyReturns(data: EquityPoint[]): Map<string, number> {
  if (data.length === 0) return new Map()
  // Group by YYYY-MM, take the LAST equity per month.
  const lastByMonth = new Map<string, { date: string; equity: number }>()
  for (const p of data) {
    const ym = p.date.slice(0, 7)
    const existing = lastByMonth.get(ym)
    if (!existing || p.date > existing.date) {
      lastByMonth.set(ym, { date: p.date, equity: p.equity })
    }
  }
  const months = Array.from(lastByMonth.keys()).sort()
  const out = new Map<string, number>()
  let prevEquity: number | null = null
  // Anchor: take the FIRST equity point's value as the pre-period baseline.
  let firstEquity = data[0].equity
  for (const ym of months) {
    const end = lastByMonth.get(ym)!.equity
    const start = prevEquity ?? firstEquity
    if (start > 0) out.set(ym, end / start - 1)
    prevEquity = end
  }
  return out
}

function cellColor(ret: number): string {
  // Chinese-market convention: red = positive, green = negative
  const cap = 0.10
  const r = Math.max(-cap, Math.min(cap, ret)) / cap
  if (r >= 0) {
    return `rgba(220, 38, 38, ${(0.15 + 0.7 * r).toFixed(3)})`     // red
  } else {
    return `rgba(22, 163, 74, ${(0.15 + 0.7 * -r).toFixed(3)})`    // green
  }
}

function textColor(ret: number): string {
  return Math.abs(ret) > 0.04 ? '#ffffff' : '#1f2937'
}

const MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export default function MonthlyHeatmap({ data }: Props) {
  const returns = computeMonthlyReturns(data)
  if (returns.size === 0) return null

  // Pivot into year × month
  const years = Array.from(new Set(Array.from(returns.keys()).map((k) => k.slice(0, 4)))).sort()
  const yearTotals = new Map<string, number>()
  for (const y of years) {
    let cum = 1
    for (let m = 1; m <= 12; m++) {
      const key = `${y}-${String(m).padStart(2, '0')}`
      const r = returns.get(key)
      if (r !== undefined) cum *= 1 + r
    }
    yearTotals.set(y, cum - 1)
  }

  return (
    <div className="card">
      <div className="metric-key mb-2">Monthly returns (CN: red = up, green = down)</div>
      <div className="overflow-auto">
        <table className="border-collapse">
          <thead>
            <tr>
              <th className="text-xs text-ink-400 px-3 py-1"></th>
              {MONTH_LABELS.map((m) => (
                <th key={m} className="text-xs text-ink-400 font-medium px-2 py-1">{m}</th>
              ))}
              <th className="text-xs text-ink-400 font-semibold px-3 py-1">YTD</th>
            </tr>
          </thead>
          <tbody>
            {years.map((y) => (
              <tr key={y}>
                <td className="text-xs font-mono text-ink-600 px-3 py-1">{y}</td>
                {MONTH_LABELS.map((_, mi) => {
                  const key = `${y}-${String(mi + 1).padStart(2, '0')}`
                  const r = returns.get(key)
                  if (r === undefined) {
                    return <td key={mi} className="px-2 py-1 text-center text-ink-300 text-xs">—</td>
                  }
                  return (
                    <td
                      key={mi}
                      style={{
                        background: cellColor(r),
                        color: textColor(r),
                        padding: '6px 8px',
                        textAlign: 'center',
                        fontFamily: 'monospace',
                        fontSize: 11,
                        minWidth: 50,
                        border: '1px solid #e5e7eb',
                      }}
                      title={`${key}: ${(r * 100).toFixed(2)}%`}
                    >
                      {(r * 100).toFixed(1)}
                    </td>
                  )
                })}
                {(() => {
                  const yt = yearTotals.get(y) ?? 0
                  return (
                    <td
                      style={{
                        background: cellColor(yt),
                        color: textColor(yt),
                        padding: '6px 12px',
                        textAlign: 'center',
                        fontFamily: 'monospace',
                        fontSize: 12,
                        fontWeight: 600,
                        border: '1px solid #e5e7eb',
                      }}
                    >
                      {(yt * 100).toFixed(1)}
                    </td>
                  )
                })()}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="text-xs text-ink-400 mt-2">
        Values are % return for that month. YTD column compounds the year's monthly returns.
      </div>
    </div>
  )
}
