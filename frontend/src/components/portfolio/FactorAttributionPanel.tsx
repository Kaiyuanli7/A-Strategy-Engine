interface Loadings { [factor: string]: number }
interface Tstats { [factor: string]: number }

interface FactorAttribution {
  alpha_annualized: number
  loadings: Loadings
  t_stats: Tstats
  r_squared: number
  residual_vol_annualized: number
  n_obs: number
}

interface Props {
  attribution: FactorAttribution | null | undefined
}

function pct(v: number, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return (v * 100).toFixed(digits) + '%'
}

function num(v: number, digits = 3): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return v.toFixed(digits)
}

const FACTOR_LABELS: Record<string, string> = {
  mkt: 'Market (CSI 300)',
  val: 'Value',
  mom: 'Momentum',
  size: 'Size',
  vol: 'Low Vol',
}

export default function FactorAttributionPanel({ attribution }: Props) {
  if (!attribution) {
    return (
      <div className="card text-sm text-ink-400">
        Factor attribution unavailable (no market index cached for this period).
      </div>
    )
  }

  const factors = Object.keys(attribution.loadings || {})
  return (
    <div className="card">
      <div className="metric-key mb-3">Factor attribution (post-hoc OLS decomposition)</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <Stat
          label="Alpha (annualized)"
          value={pct(attribution.alpha_annualized)}
          tone={attribution.alpha_annualized > 0 ? 'pos' : 'neg'}
        />
        <Stat label="R²" value={num(attribution.r_squared, 3)} />
        <Stat label="Residual vol (annualized)" value={pct(attribution.residual_vol_annualized)} />
        <Stat label="Observations" value={String(attribution.n_obs)} />
      </div>
      <table className="data">
        <thead>
          <tr>
            <th>Factor</th>
            <th className="text-right">Loading (β)</th>
            <th className="text-right">t-stat</th>
            <th className="text-right">Significant</th>
          </tr>
        </thead>
        <tbody>
          {factors.map((f) => {
            const beta = attribution.loadings[f]
            const t = attribution.t_stats[f] ?? 0
            const sig = Math.abs(t) >= 2
            return (
              <tr key={f}>
                <td>{FACTOR_LABELS[f] ?? f}</td>
                <td className={'text-right ' + (beta > 0 ? 'pos' : 'neg')}>
                  {num(beta, 3)}
                </td>
                <td className={'text-right ' + (Math.abs(t) >= 2 ? '' : 'text-ink-400')}>
                  {num(t, 2)}
                </td>
                <td className={'text-right text-xs ' + (sig ? 'pos' : 'text-ink-400')}>
                  {sig ? '✓ |t| ≥ 2' : '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="text-xs text-ink-400 mt-2">
        Decomposes strategy daily returns against constructed factor portfolios
        (market beta + value + momentum + size + low-vol). |t| ≥ 2 ⇒ statistically
        significant exposure.
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
