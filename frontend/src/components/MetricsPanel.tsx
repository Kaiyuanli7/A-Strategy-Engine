import type { BacktestSummary } from '@/types/api'

interface Props {
  summary: BacktestSummary
}

function pct(x: number): string {
  return (x * 100).toFixed(2) + '%'
}

function money(x: number): string {
  return '¥' + Math.round(x).toLocaleString('en-US')
}

function signedClass(x: number): string {
  return x > 0 ? 'pos' : x < 0 ? 'neg' : ''
}

const Metric = ({ label, value, klass }: { label: string; value: string; klass?: string }) => (
  <div className="card">
    <div className="metric-key">{label}</div>
    <div className={`metric-val ${klass ?? ''}`}>{value}</div>
  </div>
)

export default function MetricsPanel({ summary }: Props) {
  const mddPeak = summary.max_drawdown_peak?.slice(0, 10)
  const mddTrough = summary.max_drawdown_trough?.slice(0, 10)
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <Metric label="Final Equity" value={money(summary.final_equity)} />
      <Metric
        label="Total Return"
        value={pct(summary.total_return)}
        klass={signedClass(summary.total_return)}
      />
      <Metric
        label="Annualized"
        value={pct(summary.annualized_return)}
        klass={signedClass(summary.annualized_return)}
      />
      <Metric label="Ann. Vol" value={pct(summary.annualized_vol)} />
      <Metric
        label="Sharpe (rf 2%)"
        value={summary.sharpe.toFixed(2)}
        klass={signedClass(summary.sharpe)}
      />
      <Metric
        label="Max Drawdown"
        value={`${pct(summary.max_drawdown)}${mddPeak && mddTrough ? ` (${mddPeak} → ${mddTrough})` : ''}`}
        klass="neg"
      />
      <Metric label="Calmar" value={summary.calmar.toFixed(2)} />
      <Metric
        label="Win Rate"
        value={`${pct(summary.win_rate)} (${summary.n_trips} trades)`}
      />
      <Metric label="Avg Hold" value={`${summary.avg_hold_days.toFixed(1)} days`} />
      <Metric label="Turnover" value={`${summary.turnover.toFixed(2)}×`} />
      <Metric label="Fills" value={String(summary.n_fills)} />
      <Metric
        label="Rejections"
        value={String(summary.n_rejections)}
        klass={summary.n_rejections > 0 ? 'neg' : ''}
      />
    </div>
  )
}
