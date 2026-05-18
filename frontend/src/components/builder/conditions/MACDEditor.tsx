import NumInput from '../NumInput'
import type { MACDCond } from '@/types/api'

interface Props {
  spec: MACDCond
  onChange: (s: MACDCond) => void
}

const EVENT_LABELS: Record<MACDCond['event'], string> = {
  hist_cross_up: 'histogram crosses up',
  hist_cross_down: 'histogram crosses down',
  macd_above_signal: 'MACD above signal',
  macd_below_signal: 'MACD below signal',
}

export default function MACDEditor({ spec, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-2 items-center text-sm">
      <span>fast</span>
      <NumInput value={spec.fast} onChange={(v) => onChange({ ...spec, fast: v ?? 12 })} min={1} />
      <span>slow</span>
      <NumInput value={spec.slow} onChange={(v) => onChange({ ...spec, slow: v ?? 26 })} min={2} />
      <span>signal</span>
      <NumInput value={spec.signal} onChange={(v) => onChange({ ...spec, signal: v ?? 9 })} min={1} />
      <select
        value={spec.event}
        onChange={(e) => onChange({ ...spec, event: e.target.value as MACDCond['event'] })}
        className="border border-ink-200 rounded-md px-2 py-1 text-sm"
      >
        {Object.entries(EVENT_LABELS).map(([v, label]) => (
          <option key={v} value={v}>{label}</option>
        ))}
      </select>
    </div>
  )
}
