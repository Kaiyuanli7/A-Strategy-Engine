import NumInput from './NumInput'
import type { SizingSpec } from '@/types/api'

interface Props {
  value: SizingSpec
  maxPositions: number
  onChange: (v: SizingSpec) => void
  onMaxPositionsChange: (n: number) => void
}

export default function SizingForm({ value, maxPositions, onChange, onMaxPositionsChange }: Props) {
  return (
    <div className="card space-y-2">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-400">Position sizing</h2>
      <div className="flex gap-4 text-sm flex-wrap">
        {(['equal_weight', 'fixed_amount', 'vol_adjusted'] as const).map((m) => (
          <label key={m} className="flex items-center gap-1">
            <input
              type="radio"
              checked={value.method === m}
              onChange={() => onChange({ ...value, method: m })}
            />
            <span>{m.replace('_', ' ')}</span>
          </label>
        ))}
      </div>
      <div className="flex flex-wrap gap-3 text-sm items-center pt-2">
        {value.method !== 'fixed_amount' && (
          <label className="flex items-center gap-2">
            <span className="text-ink-600">Position size %</span>
            <NumInput
              value={value.position_size_pct * 100}
              onChange={(v) => onChange({ ...value, position_size_pct: (v ?? 5) / 100 })}
              step={0.5}
              min={0.1}
            />
          </label>
        )}
        {value.method === 'fixed_amount' && (
          <label className="flex items-center gap-2">
            <span className="text-ink-600">Amount ¥</span>
            <NumInput
              value={value.amount ?? 50000}
              onChange={(v) => onChange({ ...value, amount: v })}
              step={5000}
            />
          </label>
        )}
        {value.method === 'vol_adjusted' && (
          <label className="flex items-center gap-2">
            <span className="text-ink-600">Target vol %</span>
            <NumInput
              value={(value.target_vol_pct ?? 0.20) * 100}
              onChange={(v) => onChange({ ...value, target_vol_pct: (v ?? 20) / 100 })}
              step={1}
            />
          </label>
        )}
        <label className="flex items-center gap-2">
          <span className="text-ink-600">Max positions</span>
          <NumInput value={maxPositions} onChange={(v) => onMaxPositionsChange(v ?? 10)} min={1} />
        </label>
      </div>
    </div>
  )
}
