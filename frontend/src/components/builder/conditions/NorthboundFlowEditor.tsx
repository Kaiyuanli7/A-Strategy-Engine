import NumInput from '../NumInput'
import type { NorthboundNetInflowCond } from '@/types/api'

interface Props {
  spec: NorthboundNetInflowCond
  onChange: (s: NorthboundNetInflowCond) => void
}

export default function NorthboundFlowEditor({ spec, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-2 items-center text-sm">
      <span>window (days)</span>
      <NumInput value={spec.window} onChange={(v) => onChange({ ...spec, window: v ?? 5 })} min={1} />
      <span>net inflow ≥ ¥</span>
      <NumInput
        value={spec.min_value}
        onChange={(v) => onChange({ ...spec, min_value: v ?? 0 })}
        step={1_000_000}
      />
    </div>
  )
}
