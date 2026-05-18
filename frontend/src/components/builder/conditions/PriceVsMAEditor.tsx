import NumInput from '../NumInput'
import type { PriceVsMACond } from '@/types/api'

interface Props {
  spec: PriceVsMACond
  onChange: (s: PriceVsMACond) => void
}

export default function PriceVsMAEditor({ spec, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-2 items-center text-sm">
      <span>period</span>
      <NumInput value={spec.period} onChange={(v) => onChange({ ...spec, period: v ?? 20 })} min={1} />
      <select
        value={spec.op}
        onChange={(e) => onChange({ ...spec, op: e.target.value as '>' | '<' })}
        className="border border-ink-200 rounded-md px-2 py-1 text-sm"
      >
        <option value=">">close &gt; SMA</option>
        <option value="<">close &lt; SMA</option>
      </select>
    </div>
  )
}
