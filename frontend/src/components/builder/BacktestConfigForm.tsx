import NumInput from './NumInput'
import type { BacktestConfigSpec } from '@/types/api'

interface Props {
  value: BacktestConfigSpec
  onChange: (v: BacktestConfigSpec) => void
}

export default function BacktestConfigForm({ value, onChange }: Props) {
  return (
    <div className="card space-y-2">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-400">Backtest config</h2>
      <div className="flex flex-wrap gap-3 text-sm items-center">
        <label className="flex items-center gap-2">
          <span className="text-ink-600">Start</span>
          <input
            type="date"
            value={value.start}
            onChange={(e) => onChange({ ...value, start: e.target.value })}
            className="border border-ink-200 rounded-md px-2 py-1 text-sm"
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="text-ink-600">End</span>
          <input
            type="date"
            value={value.end}
            onChange={(e) => onChange({ ...value, end: e.target.value })}
            className="border border-ink-200 rounded-md px-2 py-1 text-sm"
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="text-ink-600">Initial cash ¥</span>
          <NumInput
            value={value.initial_cash}
            onChange={(v) => onChange({ ...value, initial_cash: v ?? 1_000_000 })}
            step={100_000}
            min={10_000}
            className="w-36"
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="text-ink-600">Seed</span>
          <NumInput
            value={value.random_seed}
            onChange={(v) => onChange({ ...value, random_seed: v ?? 42 })}
            step={1}
          />
        </label>
      </div>
    </div>
  )
}
