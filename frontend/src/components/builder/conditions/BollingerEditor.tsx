import NumInput from '../NumInput'
import type { BollingerBreakoutCond } from '@/types/api'

interface Props {
  spec: BollingerBreakoutCond
  onChange: (s: BollingerBreakoutCond) => void
}

export default function BollingerEditor({ spec, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-2 items-center text-sm">
      <span>period</span>
      <NumInput value={spec.period} onChange={(v) => onChange({ ...spec, period: v ?? 20 })} min={2} />
      <span>k (stdevs)</span>
      <NumInput value={spec.k} onChange={(v) => onChange({ ...spec, k: v ?? 2 })} step={0.1} />
      <select
        value={spec.band}
        onChange={(e) => onChange({ ...spec, band: e.target.value as 'upper' | 'lower' })}
        className="border border-ink-200 rounded-md px-2 py-1 text-sm"
      >
        <option value="upper">break upper</option>
        <option value="lower">break lower</option>
      </select>
    </div>
  )
}
