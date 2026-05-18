import type { EquityPoint, StockBar } from '@/types/api'

interface Props {
  equity: EquityPoint[]
  initialEquity: number
  benchmark?: StockBar[]
  benchmarkLabel?: string
  summary: Record<string, unknown> | null
}

function pct(v: number, digits = 2): string {
  if (!Number.isFinite(v)) return '—'
  return (v * 100).toFixed(digits) + '%'
}

function num(v: number, digits = 2): string {
  if (!Number.isFinite(v)) return '—'
  return v.toFixed(digits)
}

export default function TldrCard({
  equity, initialEquity, benchmark, benchmarkLabel = 'CSI 300', summary,
}: Props) {
  if (equity.length === 0 || !summary) return null
  const finalEquity = (summary.final_equity as number) ?? equity[equity.length - 1].equity
  const portReturn = (finalEquity / initialEquity) - 1

  let benchReturn: number | null = null
  if (benchmark && benchmark.length > 0) {
    const byDate = new Map(benchmark.map((b) => [b.date, b.close]))
    let firstClose: number | null = null
    let lastClose: number | null = null
    for (const p of equity) {
      const c = byDate.get(p.date)
      if (c !== undefined) {
        if (firstClose === null) firstClose = c
        lastClose = c
      }
    }
    if (firstClose !== null && lastClose !== null && firstClose > 0) {
      benchReturn = lastClose / firstClose - 1
    }
  }
  const alpha = benchReturn !== null ? portReturn - benchReturn : null
  const sharpe = (summary.sharpe as number) ?? 0
  const maxDd = (summary.max_drawdown as number) ?? 0

  const beat = alpha !== null && alpha > 0
  const tone = beat ? 'bg-emerald-50 border-emerald-200' : 'bg-rose-50 border-rose-200'

  return (
    <div className={'card border-l-4 ' + tone}>
      <div className="flex flex-wrap items-baseline gap-4">
        <div className="text-base font-medium">
          Portfolio returned{' '}
          <span className={portReturn > 0 ? 'pos' : 'neg'}>{pct(portReturn)}</span>
          {benchReturn !== null && (
            <>
              {' '}vs {benchmarkLabel}{' '}
              <span className={benchReturn > 0 ? 'pos' : 'neg'}>{pct(benchReturn)}</span>
              {alpha !== null && (
                <>
                  {' '}→ alpha{' '}
                  <span className={alpha > 0 ? 'pos' : 'neg'}>{pct(alpha)}</span>
                </>
              )}
            </>
          )}
        </div>
        <div className="text-sm text-ink-600">
          Sharpe <span className={sharpe > 0 ? 'pos' : 'neg'}>{num(sharpe)}</span>
          {' · '}
          Max DD <span className="neg">{pct(maxDd)}</span>
        </div>
      </div>
      <div className="text-xs text-ink-400 mt-1">
        {benchReturn === null
          ? 'No CSI 300 benchmark in cache — prime the index OHLCV to enable alpha calculation.'
          : beat
            ? 'Strategy beat the benchmark over this period. Check the rest of the panels for attribution.'
            : 'Strategy underperformed the benchmark over this period. Check regime breakdown and factor attribution to understand why.'}
      </div>
    </div>
  )
}
