import { useState } from 'react'

interface Props {
  data: unknown
}

export default function JsonPreview({ data }: Props) {
  const [collapsed, setCollapsed] = useState(true)
  const [copied, setCopied] = useState(false)
  const json = JSON.stringify(data, null, 2)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(json)
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    } catch {
      // ignore
    }
  }

  return (
    <div className="card">
      <div className="flex items-baseline justify-between">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="text-sm font-semibold uppercase tracking-wider text-ink-400 hover:text-ink-600"
        >
          {collapsed ? '▸' : '▾'} Backtest request JSON
        </button>
        {!collapsed && (
          <button
            onClick={copy}
            className="text-xs text-ink-600 hover:text-ink-900 px-2 py-1 rounded hover:bg-ink-50"
          >
            {copied ? 'copied!' : 'copy'}
          </button>
        )}
      </div>
      {!collapsed && (
        <pre className="text-xs font-mono mt-2 p-3 bg-ink-50 rounded overflow-auto max-h-96">
{json}
        </pre>
      )}
    </div>
  )
}
