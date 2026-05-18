import NumInput from '../NumInput'
import type { BoundCond } from '@/types/api'

interface Props {
  spec: BoundCond
  onChange: (s: BoundCond) => void
}

export default function BoundEditor({ spec, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-2 items-center text-sm">
      <span>min</span>
      <NumInput
        value={spec.min}
        onChange={(v) => onChange({ ...spec, min: v })}
        allowNull
        placeholder="—"
        step={0.1}
      />
      <span>max</span>
      <NumInput
        value={spec.max}
        onChange={(v) => onChange({ ...spec, max: v })}
        allowNull
        placeholder="—"
        step={0.1}
      />
      <span className="text-ink-400 text-xs">leave blank for unbounded</span>
    </div>
  )
}
