import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import NumInput from './NumInput'
import type { UniverseFilter } from '@/types/api'

interface Props {
  value: UniverseFilter
  onChange: (v: UniverseFilter) => void
}

const BOARDS = [
  { id: 'main_sh', label: '沪市主板 (Main SH)' },
  { id: 'main_sz', label: '深市主板 (Main SZ)' },
  { id: 'chinext', label: '创业板 (ChiNext)' },
  { id: 'star', label: '科创板 (STAR)' },
  { id: 'beijing', label: '北交所 (BJ)' },
]

export default function UniverseFilterPanel({ value, onChange }: Props) {
  const [sectors, setSectors] = useState<string[]>([])

  useEffect(() => {
    api.sectors().then((r) => setSectors(r.sectors_l1)).catch(() => setSectors([]))
  }, [])

  const toggleBoard = (id: string) => {
    const current = value.boards ?? []
    const next = current.includes(id) ? current.filter((b) => b !== id) : [...current, id]
    onChange({ ...value, boards: next.length ? next : null })
  }

  const toggleSector = (s: string) => {
    const current = value.sectors_l1 ?? []
    const next = current.includes(s) ? current.filter((x) => x !== s) : [...current, s]
    onChange({ ...value, sectors_l1: next.length ? next : null })
  }

  return (
    <div className="card space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-400">
        Universe filter
      </h2>

      <div>
        <div className="text-xs text-ink-400 mb-1">Boards</div>
        <div className="flex flex-wrap gap-1">
          {BOARDS.map((b) => {
            const active = (value.boards ?? []).includes(b.id)
            return (
              <button
                key={b.id}
                onClick={() => toggleBoard(b.id)}
                className={
                  'text-xs px-2 py-1 rounded-md border ' +
                  (active
                    ? 'bg-ink-800 text-white border-ink-800'
                    : 'bg-white text-ink-600 border-ink-200')
                }
              >
                {b.label}
              </button>
            )
          })}
        </div>
      </div>

      <div>
        <div className="text-xs text-ink-400 mb-1">Sectors (申万 L1)</div>
        <div className="flex flex-wrap gap-1">
          {sectors.length === 0 ? (
            <div className="text-xs text-ink-400">No sectors cached. Run fetch_data.py first.</div>
          ) : (
            sectors.map((s) => {
              const active = (value.sectors_l1 ?? []).includes(s)
              return (
                <button
                  key={s}
                  onClick={() => toggleSector(s)}
                  className={
                    'text-xs px-2 py-1 rounded-md border ' +
                    (active
                      ? 'bg-ink-800 text-white border-ink-800'
                      : 'bg-white text-ink-600 border-ink-200')
                  }
                >
                  {s}
                </button>
              )
            })
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 items-center text-sm">
        <span>Market cap min ¥</span>
        <NumInput
          value={value.market_cap_min}
          onChange={(v) => onChange({ ...value, market_cap_min: v })}
          allowNull
          placeholder="—"
          step={1e10}
          className="w-32"
        />
        <span>max ¥</span>
        <NumInput
          value={value.market_cap_max}
          onChange={(v) => onChange({ ...value, market_cap_max: v })}
          allowNull
          placeholder="—"
          step={1e10}
          className="w-32"
        />
        <label className="flex items-center gap-1 ml-2">
          <input
            type="checkbox"
            checked={value.exclude_st}
            onChange={(e) => onChange({ ...value, exclude_st: e.target.checked })}
          />
          <span>Exclude ST</span>
        </label>
      </div>
    </div>
  )
}
