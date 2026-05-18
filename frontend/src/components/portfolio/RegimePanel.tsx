interface RegimePerf {
  n_days: number
  annualized_return: number
  sharpe: number
  max_drawdown: number
}

interface Props {
  regimes: Record<string, RegimePerf> | null | undefined
}

const REGIME_LABELS: Record<string, string> = {
  bull: 'Bull (uptrend)',
  bear: 'Bear (downtrend)',
  range: 'Range-bound',
  high_vol: 'High vol',
  low_vol: 'Low vol',
}

function pct(v: number, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return (v * 100).toFixed(digits) + '%'
}

function num(v: number, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return v.toFixed(digits)
}

export default function RegimePanel({ regimes }: Props) {
  if (!regimes || Object.keys(regimes).length === 0) {
    return (
      <div className="card text-sm text-ink-400">
        Regime breakdown unavailable (no market index cached for this period).
      </div>
    )
  }

  const totalDays = Object.values(regimes).reduce((acc, r) => acc + r.n_days, 0)
  const sortedRegimes = Object.entries(regimes).sort(
    (a, b) => b[1].n_days - a[1].n_days,
  )

  return (
    <div className="card">
      <div className="metric-key mb-3">Performance by market regime</div>
      <table className="data">
        <thead>
          <tr>
            <th>Regime</th>
            <th className="text-right">Days</th>
            <th className="text-right">% of period</th>
            <th className="text-right">Ann. return</th>
            <th className="text-right">Sharpe</th>
            <th className="text-right">Max DD</th>
          </tr>
        </thead>
        <tbody>
          {sortedRegimes.map(([key, r]) => {
            const share = totalDays > 0 ? r.n_days / totalDays : 0
            return (
              <tr key={key}>
                <td>{REGIME_LABELS[key] ?? key}</td>
                <td className="text-right">{r.n_days}</td>
                <td className="text-right text-xs text-ink-400">
                  {pct(share, 1)}
                </td>
                <td className={'text-right ' + (r.annualized_return > 0 ? 'pos' : 'neg')}>
                  {pct(r.annualized_return)}
                </td>
                <td className={'text-right ' + (r.sharpe > 0 ? 'pos' : 'neg')}>
                  {num(r.sharpe)}
                </td>
                <td className="text-right neg">{pct(r.max_drawdown)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="text-xs text-ink-400 mt-2">
        Days are classified by trailing 60-day market trend (CSI 300). A strategy
        that's only profitable in one regime is more fragile than one that holds
        up across regimes.
      </div>
    </div>
  )
}
