import NumInput from '../NumInput'
import type { VolumeSpikeCond } from '@/types/api'

interface Props {
  spec: VolumeSpikeCond
  onChange: (s: VolumeSpikeCond) => void
}

export default function VolumeSpikeEditor({ spec, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-2 items-center text-sm">
      <span>period</span>
      <NumInput value={spec.period} onChange={(v) => onChange({ ...spec, period: v ?? 20 })} min={2} />
      <span>multiple ≥</span>
      <NumInput value={spec.multiple} onChange={(v) => onChange({ ...spec, multiple: v ?? 2 })} step={0.1} min={1} />
    </div>
  )
}
