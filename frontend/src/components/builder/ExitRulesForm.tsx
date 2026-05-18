import NumInput from './NumInput'
import type { ExitRulesSpec } from '@/types/api'

interface Props {
  value: ExitRulesSpec
  onChange: (v: ExitRulesSpec) => void
}

export default function ExitRulesForm({ value, onChange }: Props) {
  return (
    <div className="card space-y-2">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-400">Exit rules</h2>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <label className="flex items-center gap-2">
          <span className="w-32 text-ink-600">Stop-loss %</span>
          <NumInput
            value={value.stop_loss_pct === null ? null : value.stop_loss_pct * 100}
            onChange={(v) => onChange({ ...value, stop_loss_pct: v === null ? null : v / 100 })}
            allowNull
            placeholder="—"
            step={0.5}
            min={0}
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="w-32 text-ink-600">Take-profit %</span>
          <NumInput
            value={value.take_profit_pct === null ? null : value.take_profit_pct * 100}
            onChange={(v) => onChange({ ...value, take_profit_pct: v === null ? null : v / 100 })}
            allowNull
            placeholder="—"
            step={0.5}
            min={0}
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="w-32 text-ink-600">Max hold (days)</span>
          <NumInput
            value={value.max_hold_days}
            onChange={(v) => onChange({ ...value, max_hold_days: v })}
            allowNull
            placeholder="—"
            min={1}
          />
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={value.signal_reversal}
            onChange={(e) => onChange({ ...value, signal_reversal: e.target.checked })}
          />
          <span>Exit when entry signal reverses</span>
        </label>
      </div>
    </div>
  )
}
