import NumInput from '../NumInput'
import type { MACrossCond } from '@/types/api'

interface Props {
  spec: MACrossCond
  onChange: (s: MACrossCond) => void
}

export default function MACrossEditor({ spec, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-2 items-center text-sm">
      <span>fast</span>
      <NumInput value={spec.fast} onChange={(v) => onChange({ ...spec, fast: v ?? 5 })} min={1} />
      <span>slow</span>
      <NumInput value={spec.slow} onChange={(v) => onChange({ ...spec, slow: v ?? 20 })} min={2} />
      <span>direction</span>
      <select
        value={spec.direction}
        onChange={(e) => onChange({ ...spec, direction: e.target.value as 'up' | 'down' })}
        className="border border-ink-200 rounded-md px-2 py-1 text-sm"
      >
        <option value="up">cross up</option>
        <option value="down">cross down</option>
      </select>
    </div>
  )
}
