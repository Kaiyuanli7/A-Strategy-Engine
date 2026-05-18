import type { FillRecord } from '@/types/api'

interface Props {
  fills: FillRecord[]
  rejections?: FillRecord[]
  title?: string
}

export default function FillsTable({ fills, rejections = [], title = 'Trades' }: Props) {
  const merged = [
    ...fills.map((f) => ({ ...f, rejected: false })),
    ...rejections.map((f) => ({ ...f, rejected: true })),
  ].sort((a, b) => a.date.localeCompare(b.date))

  return (
    <div className="card overflow-hidden">
      <div className="metric-key mb-2">
        {title} ({fills.length} fills · {rejections.length} rejections)
      </div>
      <div className="overflow-auto max-h-96">
        <table className="data">
          <thead className="sticky top-0 bg-white">
            <tr>
              <th>Date</th>
              <th>Code</th>
              <th>Side</th>
              <th className="text-right">Shares</th>
              <th className="text-right">Price</th>
              <th className="text-right">Notional</th>
              <th className="text-right">Cost</th>
              <th>Note</th>
            </tr>
          </thead>
          <tbody>
            {merged.slice(0, 500).map((f, i) => (
              <tr key={i} className={f.rejected ? 'opacity-50' : ''}>
                <td className="font-mono text-xs">{f.date.slice(0, 10)}</td>
                <td className="font-mono">{f.code}</td>
                <td className={f.side === 'buy' ? 'pos' : 'neg'}>{f.side}</td>
                <td className="text-right">{f.shares.toLocaleString()}</td>
                <td className="text-right">¥{f.price.toFixed(2)}</td>
                <td className="text-right">
                  ¥{(f.shares * f.price).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </td>
                <td className="text-right">¥{f.cost.toFixed(2)}</td>
                <td className="text-xs text-ink-400">
                  {f.rejected ? `rejected: ${f.rejected_reason}` : ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {merged.length > 500 && (
          <div className="text-xs text-ink-400 mt-2 px-3 py-2">
            Showing first 500 of {merged.length} rows.
          </div>
        )}
      </div>
    </div>
  )
}
