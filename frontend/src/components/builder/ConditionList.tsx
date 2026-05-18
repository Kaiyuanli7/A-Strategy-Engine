import type { ConditionSpec, ConditionType } from '@/types/api'
import { CONDITION_DEF, CONDITION_TYPES } from './conditions'

interface Row {
  id: string
  spec: ConditionSpec
}

interface Props {
  rows: Row[]
  onChange: (rows: Row[]) => void
}

const CATEGORY_COLOR: Record<string, string> = {
  technical: 'bg-blue-50 text-blue-800 border-blue-200',
  fundamental: 'bg-amber-50 text-amber-800 border-amber-200',
  flow: 'bg-purple-50 text-purple-800 border-purple-200',
}

function uid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return Math.random().toString(36).slice(2)
}

export default function ConditionList({ rows, onChange }: Props) {
  const addRow = (type: ConditionType) => {
    const def = CONDITION_DEF[type]
    onChange([...rows, { id: uid(), spec: def.defaults() }])
  }

  const updateRow = (id: string, spec: ConditionSpec) => {
    onChange(rows.map((r) => (r.id === id ? { ...r, spec } : r)))
  }

  const changeType = (id: string, type: ConditionType) => {
    const def = CONDITION_DEF[type]
    onChange(rows.map((r) => (r.id === id ? { ...r, spec: def.defaults() } : r)))
  }

  const removeRow = (id: string) => onChange(rows.filter((r) => r.id !== id))

  return (
    <div className="card space-y-2">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-400">
          Entry conditions (AND)
        </h2>
        <div className="text-xs text-ink-400">{rows.length} active</div>
      </div>

      {rows.length === 0 && (
        <div className="text-sm text-ink-400 py-3">
          No conditions yet — add at least one to enable the run button.
        </div>
      )}

      <div className="space-y-2">
        {rows.map((row, i) => {
          const def = CONDITION_DEF[row.spec.type]
          const Editor = def.component
          return (
            <div key={row.id} className="flex items-start gap-2 border border-ink-100 rounded-md p-2">
              <div className="text-xs text-ink-400 mt-1 font-mono w-6">#{i + 1}</div>
              <select
                value={row.spec.type}
                onChange={(e) => changeType(row.id, e.target.value as ConditionType)}
                className="border border-ink-200 rounded-md px-2 py-1 text-sm w-44"
              >
                {(['technical', 'fundamental', 'flow'] as const).map((cat) => (
                  <optgroup key={cat} label={cat.toUpperCase()}>
                    {CONDITION_TYPES.filter((c) => c.category === cat).map((c) => (
                      <option key={c.type} value={c.type}>{c.label}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
              <span className={`text-xs uppercase px-2 py-1 rounded border ${CATEGORY_COLOR[def.category]}`}>
                {def.category}
              </span>
              <div className="flex-1">
                <Editor spec={row.spec} onChange={(s) => updateRow(row.id, s)} />
              </div>
              <button
                onClick={() => removeRow(row.id)}
                className="text-accent-red text-sm px-2 py-1 hover:bg-ink-50 rounded"
                title="Remove"
              >
                ✕
              </button>
            </div>
          )
        })}
      </div>

      <div className="pt-2 border-t border-ink-100">
        <select
          onChange={(e) => {
            if (e.target.value) {
              addRow(e.target.value as ConditionType)
              e.target.value = ''
            }
          }}
          className="border border-ink-200 rounded-md px-2 py-1 text-sm"
          defaultValue=""
        >
          <option value="">+ Add condition…</option>
          {(['technical', 'fundamental', 'flow'] as const).map((cat) => (
            <optgroup key={cat} label={cat.toUpperCase()}>
              {CONDITION_TYPES.filter((c) => c.category === cat).map((c) => (
                <option key={c.type} value={c.type}>{c.label}</option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>
    </div>
  )
}
