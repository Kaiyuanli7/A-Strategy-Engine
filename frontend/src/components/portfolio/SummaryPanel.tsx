interface Props {
  summary: Record<string, unknown> | null
}

function num(v: unknown, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v as number)) return '—'
  return (v as number).toFixed(digits)
}

function pct(v: unknown, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v as number)) return '—'
  return ((v as number) * 100).toFixed(digits) + '%'
}

function tone(v: unknown, good = 0, bad = 0): string {
  if (v === null || v === undefined) return ''
  const x = v as number
  if (x > good) return 'pos'
  if (x < bad) return 'neg'
  return ''
}

export default function SummaryPanel({ summary }: Props) {
  if (!summary) return null
  return (
    <div className="card">
      <div className="metric-key mb-3">Backtest summary</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="Total return" value={pct(summary.total_return)}
              tone={tone(summary.total_return, 0, 0)} />
        <Stat label="Annualized return" value={pct(summary.annualized_return)}
              tone={tone(summary.annualized_return, 0, 0)} />
        <Stat label="Annualized vol" value={pct(summary.annualized_vol)} />
        <Stat label="Sharpe" value={num(summary.sharpe, 2)}
              tone={tone(summary.sharpe, 0, 0)} />
        <Stat label="Max drawdown" value={pct(summary.max_drawdown)}
              tone={tone(summary.max_drawdown, 99, 0)} />
        <Stat label="Calmar" value={num(summary.calmar, 2)} />
        <Stat label="Win rate" value={pct(summary.win_rate, 1)} />
        <Stat label="Turnover" value={pct(summary.turnover, 1)} />
        <Stat label="Initial equity" value={'¥' + num(summary.initial_equity, 0)} />
        <Stat label="Final equity" value={'¥' + num(summary.final_equity, 0)}
              tone={tone((summary.final_equity as number) - (summary.initial_equity as number), 0, 0)} />
        <Stat label="Trips" value={num(summary.n_trips, 0)} />
        <Stat label="Fills / rejections"
              value={`${summary.n_fills ?? '—'} / ${summary.n_rejections ?? '—'}`} />
      </div>
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className="metric-key">{label}</div>
      <div className={'metric-val ' + (tone ?? '')}>{value}</div>
    </div>
  )
}
