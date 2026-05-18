interface Props {
  count: number | null
  total: number | null
  loading?: boolean
}

export default function UniversePreviewBadge({ count, total, loading }: Props) {
  if (loading) {
    return <span className="text-xs text-ink-400">checking…</span>
  }
  if (count === null || total === null) {
    return <span className="text-xs text-ink-400">—</span>
  }
  const klass = count === 0 ? 'neg' : count < total ? 'text-ink-600' : 'text-ink-400'
  return (
    <span className={`text-xs ${klass}`}>
      Matches <span className="font-mono tabular-nums">{count}</span> /{' '}
      <span className="font-mono tabular-nums">{total}</span> stocks
      {count === 0 && ' — strategy will produce zero trades'}
    </span>
  )
}
