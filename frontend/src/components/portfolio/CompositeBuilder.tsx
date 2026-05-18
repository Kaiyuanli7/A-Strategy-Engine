import type { CompositeSpec, FactorMeta, FactorWeightSpec } from '@/types/api'

interface Props {
  factors: FactorMeta[]
  spec: CompositeSpec
  onChange: (spec: CompositeSpec) => void
}

const MAX_FACTORS = 5

export default function CompositeBuilder({ factors, spec, onChange }: Props) {
  const used = new Set(spec.factors.map((f) => f.factor_name))
  const available = factors.filter((f) => !used.has(f.name))

  const updateMethod = (method: CompositeSpec['method']) =>
    onChange({ ...spec, method })

  const addFactor = (factor: FactorMeta) => {
    if (spec.factors.length >= MAX_FACTORS) return
    const params: Record<string, unknown> = {}
    for (const p of factor.params) {
      params[p.name] = p.default
    }
    const next: FactorWeightSpec = {
      factor_name: factor.name,
      params,
      weight: null,
    }
    onChange({ ...spec, factors: [...spec.factors, next] })
  }

  const removeFactor = (idx: number) => {
    const factors = spec.factors.filter((_, i) => i !== idx)
    onChange({ ...spec, factors })
  }

  const setFactorParam = (idx: number, paramName: string, value: number) => {
    const factors = [...spec.factors]
    factors[idx] = { ...factors[idx], params: { ...factors[idx].params, [paramName]: value } }
    onChange({ ...spec, factors })
  }

  return (
    <div className="card space-y-3">
      <div className="flex items-baseline justify-between">
        <div className="metric-key">Composite ({spec.factors.length}/{MAX_FACTORS} factors)</div>
        <div className="flex gap-2 text-sm">
          <label className="flex items-center gap-1">
            <input
              type="radio"
              checked={spec.method === 'equal_weight'}
              onChange={() => updateMethod('equal_weight')}
            />
            Equal weight
          </label>
          <label className="flex items-center gap-1">
            <input
              type="radio"
              checked={spec.method === 'signed_ic_weighted'}
              onChange={() => updateMethod('signed_ic_weighted')}
            />
            Signed IC
          </label>
        </div>
      </div>

      <div className="space-y-2">
        {spec.factors.map((fw, idx) => {
          const meta = factors.find((f) => f.name === fw.factor_name)
          return (
            <div key={fw.factor_name + idx} className="border border-ink-100 rounded-md p-3 bg-ink-50">
              <div className="flex items-baseline justify-between">
                <div className="font-medium">
                  {fw.factor_name}
                  {meta && <span className="text-xs text-ink-400 ml-2">· {meta.category}</span>}
                </div>
                <button onClick={() => removeFactor(idx)}
                        className="text-xs text-accent-red hover:underline">
                  remove
                </button>
              </div>
              {meta?.description && (
                <div className="text-xs text-ink-400 mt-1">{meta.description}</div>
              )}
              {meta && meta.params.length > 0 && (
                <div className="mt-2 flex gap-3 flex-wrap">
                  {meta.params.map((p) => (
                    <label key={p.name} className="text-xs flex items-center gap-1">
                      <span>{p.name}</span>
                      <input
                        type="number"
                        className="w-20 border border-ink-200 rounded px-2 py-1 text-xs font-mono"
                        value={fw.params[p.name] as number ?? p.default as number}
                        onChange={(e) => setFactorParam(idx, p.name, Number(e.target.value))}
                        min={p.min ?? undefined}
                        max={p.max ?? undefined}
                      />
                    </label>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {spec.factors.length < MAX_FACTORS && available.length > 0 && (
        <div>
          <div className="metric-key mb-1">Add factor</div>
          <div className="flex gap-2 flex-wrap">
            {available.map((f) => (
              <button
                key={f.name}
                onClick={() => addFactor(f)}
                className="text-sm border border-ink-200 rounded-md px-3 py-1 bg-white hover:bg-ink-50"
              >
                + {f.name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
