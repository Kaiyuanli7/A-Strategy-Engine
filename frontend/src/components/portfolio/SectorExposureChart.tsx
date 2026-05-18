import type { SectorWeight } from '@/types/api'

interface Props {
  exposure: SectorWeight[]
  maxSectorPct?: number    // Threshold to flag (matches the strategy's cap)
}

const SECTOR_COLORS = [
  '#2563eb', '#16a34a', '#dc2626', '#f59e0b', '#a855f7',
  '#0891b2', '#65a30d', '#db2777', '#d97706', '#7c3aed',
  '#0284c7', '#84cc16', '#e11d48', '#f97316', '#9333ea',
]

function pct(v: number, digits = 1): string {
  return (v * 100).toFixed(digits) + '%'
}

export default function SectorExposureChart({ exposure, maxSectorPct = 0.25 }: Props) {
  if (exposure.length === 0) {
    return (
      <div className="card text-sm text-ink-400">
        No sector exposure to show (portfolio is all cash).
      </div>
    )
  }
  const maxWidth = Math.max(...exposure.map((s) => s.weight), 0.01)

  return (
    <div className="card">
      <div className="metric-key mb-2">
        Sector exposure · {exposure.length} sectors
      </div>
      <div className="space-y-1">
        {exposure.map((s, i) => {
          const overCap = s.weight > maxSectorPct
          const widthPct = (s.weight / maxWidth) * 100
          return (
            <div key={s.sector} className="flex items-center text-xs gap-2">
              <div className="w-32 text-right text-ink-600 font-mono truncate">
                {s.sector}
              </div>
              <div className="flex-1 relative h-6 bg-ink-50 rounded-sm overflow-hidden">
                <div
                  style={{
                    width: `${widthPct}%`,
                    background: SECTOR_COLORS[i % SECTOR_COLORS.length],
                    height: '100%',
                  }}
                />
                <div className="absolute inset-0 flex items-center px-2 text-white text-xs font-mono mix-blend-difference">
                  {pct(s.weight)}
                </div>
              </div>
              <div className="w-20 text-right text-ink-400 text-xs font-mono">
                {s.n_stocks}p · ¥{(s.market_value / 1e6).toFixed(1)}M
              </div>
              {overCap && (
                <div className="w-14 text-accent-red text-xs">⚠ over cap</div>
              )}
            </div>
          )
        })}
      </div>
      <div className="text-xs text-ink-400 mt-3">
        Sector cap configured at {pct(maxSectorPct, 0)}. Bars over the cap are flagged;
        the strategy applies the cap *during* selection, so post-fact crossings only
        happen via price drift between rebalances.
      </div>
    </div>
  )
}
