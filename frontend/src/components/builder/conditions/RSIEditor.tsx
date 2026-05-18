import NumInput from '../NumInput'
import type { RSICond } from '@/types/api'

interface Props {
  spec: RSICond
  onChange: (s: RSICond) => void
}

export default function RSIEditor({ spec, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-2 items-center text-sm">
      <span>period</span>
      <NumInput value={spec.period} onChange={(v) => onChange({ ...spec, period: v ?? 14 })} min={2} />
      <select
        value={spec.direction}
        onChange={(e) => onChange({ ...spec, direction: e.target.value as RSICond['direction'] })}
        className="border border-ink-200 rounded-md px-2 py-1 text-sm"
      >
        <option value="above">above</option>
        <option value="below">below</option>
        <option value="cross_up">cross up</option>
        <option value="cross_down">cross down</option>
      </select>
      <NumInput
        value={spec.threshold}
        onChange={(v) => onChange({ ...spec, threshold: v ?? 30 })}
        step={1}
        min={0}
        max={100}
      />
    </div>
  )
}
