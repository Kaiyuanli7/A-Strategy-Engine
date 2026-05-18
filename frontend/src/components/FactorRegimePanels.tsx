import {
  Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import type { BacktestSummary } from '@/types/api'

interface Props {
  summary: BacktestSummary
}

function pct(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—'
  return (x * 100).toFixed(2) + '%'
}

function num(x: number | null | undefined, d = 2): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—'
  return x.toFixed(d)
}

export default function FactorRegimePanels({ summary }: Props) {
  // The Pydantic schema enforces factor_attribution and regime_metrics types
  // but typescript narrows lazily — cast explicitly.
  const factor = (summary as unknown as { factor_attribution?: {
    alpha_annualized: number
    loadings: Record<string, number>
    t_stats: Record<string, number>
    r_squared: number
    residual_vol_annualized: number
    n_obs: number
  } | null }).factor_attribution
  const regime = (summary as unknown as { regime_metrics?: Record<string, {
    n_days: number
    annualized_return: number
    sharpe: number
    max_drawdown: number
  }> | null }).regime_metrics

  if (!factor && !regime) return null

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {factor && (
        <div className="card">
          <div className="metric-key mb-2">Factor Attribution</div>
          <div className="grid grid-cols-3 gap-2 text-sm mb-3">
            <div>
              <div className="text-xs text-ink-400">Alpha (annual)</div>
              <div className={'font-semibold tabular-nums ' + (factor.alpha_annualized > 0 ? 'pos' : 'neg')}>
                {pct(factor.alpha_annualized)}
              </div>
            </div>
            <div>
              <div className="text-xs text-ink-400">R²</div>
              <div className="font-semibold tabular-nums">{(factor.r_squared * 100).toFixed(1)}%</div>
            </div>
            <div>
              <div className="text-xs text-ink-400">Residual Vol</div>
              <div className="font-semibold tabular-nums">{pct(factor.residual_vol_annualized)}</div>
            </div>
          </div>
          <div style={{ width: '100%', height: 180 }}>
            <ResponsiveContainer>
              <BarChart
                data={Object.entries(factor.loadings).map(([name, beta]) => ({
                  name, beta, t: factor.t_stats[name] ?? 0,
                }))}
                margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
              >
                <CartesianGrid stroke="#eceef2" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <ReferenceLine y={0} stroke="#cfd4dd" />
                <Tooltip
                  contentStyle={{ fontSize: 12 }}
                  formatter={(v: number, name: string) =>
                    name === 'beta' ? num(v, 3) : `t=${num(v, 2)}`}
                />
                <Bar dataKey="beta" fill="#2563eb" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="text-xs text-ink-400 mt-2">
            n_obs: {factor.n_obs} · t-stats &gt; |2| indicate statistically significant loading
          </div>
        </div>
      )}

      {regime && (
        <div className="card overflow-hidden">
          <div className="metric-key mb-2">Per-Regime Performance</div>
          <table className="data">
            <thead>
              <tr>
                <th>Regime</th>
                <th className="text-right">Days</th>
                <th className="text-right">Ann. Return</th>
                <th className="text-right">Sharpe</th>
                <th className="text-right">Max DD</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(regime).map(([name, m]) => (
                <tr key={name}>
                  <td className="font-mono">{name}</td>
                  <td className="text-right">{m.n_days}</td>
                  <td className={'text-right ' + (m.annualized_return > 0 ? 'pos' : 'neg')}>
                    {pct(m.annualized_return)}
                  </td>
                  <td className={'text-right ' + (m.sharpe > 0 ? 'pos' : 'neg')}>{num(m.sharpe)}</td>
                  <td className="text-right neg">{pct(m.max_drawdown)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="text-xs text-ink-400 mt-2 px-3">
            Bull/bear/range/high_vol regimes classified from 沪深300 60-day return + vol percentile.
          </div>
        </div>
      )}
    </div>
  )
}
