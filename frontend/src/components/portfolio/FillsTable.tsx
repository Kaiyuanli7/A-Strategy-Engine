import type { FillRecord } from '@/types/api'

interface Props {
  fills: FillRecord[]
  rejections: FillRecord[]
}

export default function FillsTable({ fills, rejections }: Props) {
  return (
    <div className="card">
      <div className="metric-key mb-2">
        Fills ({fills.length}) · Rejections ({rejections.length})
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
              <th className="text-right">Cost</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {[...fills, ...rejections].map((f, i) => (
              <tr key={i}>
                <td className="font-mono text-xs">{f.date}</td>
                <td className="font-mono">{f.code}</td>
                <td className={f.side === 'buy' ? 'pos' : 'neg'}>{f.side}</td>
                <td className="text-right">{f.shares.toLocaleString()}</td>
                <td className="text-right">¥{f.price.toFixed(2)}</td>
                <td className="text-right text-ink-400 text-xs">¥{f.cost.toFixed(2)}</td>
                <td className="text-xs">
                  {f.rejected_reason
                    ? <span className="text-accent-red">rej: {f.rejected_reason}</span>
                    : 'OK'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
