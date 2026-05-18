import type { FactorEvaluation } from '@/types/api'

interface Props {
  evaluation: FactorEvaluation
}

function pct(v: number, digits = 2): string {
  return (v * 100).toFixed(digits) + '%'
}

function classify(v: number, good: number, bad: number): string {
  if (v >= good) return 'pos'
  if (v <= bad) return 'neg'
  return ''
}

export default function FactorStatsPanel({ evaluation }: Props) {
  const { ic_summary: ic, quintile_summary: qs } = evaluation
  return (
    <div className="card">
      <div className="metric-key mb-3">Factor diagnostics</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat
          label="IC mean"
          value={ic.mean.toFixed(4)}
          subtitle={`hit rate ${pct(ic.hit_rate, 0)}`}
          tone={classify(ic.mean, 0.03, -0.01)}
        />
        <Stat
          label="IC IR"
          value={ic.ir.toFixed(3)}
          subtitle={`t-stat ${ic.t_stat.toFixed(2)}`}
          tone={classify(ic.ir, 0.5, -0.1)}
        />
        <Stat
          label="Long-short Sharpe"
          value={qs.long_short_sharpe.toFixed(3)}
          subtitle={`per-period mean ${pct(qs.long_short_mean, 3)}`}
          tone={classify(qs.long_short_sharpe, 0.3, -0.1)}
        />
        <Stat
          label="LS total return"
          value={pct(qs.long_short_total_return)}
          subtitle="compounded"
          tone={classify(qs.long_short_total_return, 0.05, -0.02)}
        />
        <Stat
          label="Monotonicity"
          value={qs.monotonicity.toFixed(3)}
          subtitle="rank corr buckets vs returns"
          tone={classify(qs.monotonicity, 0.6, 0.0)}
        />
        <Stat
          label="Quintile turnover"
          value={pct(qs.avg_turnover, 0)}
          subtitle={`@ ${evaluation.rebalance} rebalance`}
        />
        <Stat
          label="Rebalance dates"
          value={String(evaluation.n_dates)}
          subtitle={`avg ${evaluation.n_stocks_avg.toFixed(0)} stocks`}
        />
        <Stat
          label="Forward horizon"
          value={`${evaluation.horizon}d`}
          subtitle="for IC + quintile"
        />
      </div>
    </div>
  )
}

function Stat({
  label, value, subtitle, tone,
}: { label: string; value: string; subtitle?: string; tone?: string }) {
  return (
    <div>
      <div className="metric-key">{label}</div>
      <div className={'metric-val ' + (tone ?? '')}>{value}</div>
      {subtitle && <div className="text-xs text-ink-400 mt-0.5">{subtitle}</div>}
    </div>
  )
}
