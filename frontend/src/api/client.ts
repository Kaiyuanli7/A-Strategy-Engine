import type {
  BacktestRequest,
  BacktestResult,
  BacktestRunListItem,
  BacktestRunResponse,
  Health,
  StockOHLCV,
  Universe,
} from '@/types/api'

const BASE = '' // vite proxy forwards /api → backend in dev; absolute in prod

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      // body not JSON
    }
    throw new Error(`${res.status} ${detail}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => req<Health>('/health'),
  universe: () => req<Universe>('/api/data/universe'),
  stock: (code: string, start?: string, end?: string) => {
    const params = new URLSearchParams()
    if (start) params.set('start', start)
    if (end) params.set('end', end)
    const qs = params.toString()
    return req<StockOHLCV>(`/api/data/stock/${code}${qs ? '?' + qs : ''}`)
  },
  runs: () => req<BacktestRunListItem[]>('/api/backtest/runs'),
  result: (runId: string) => req<BacktestResult>(`/api/backtest/results/${runId}`),
  runBacktest: (body: BacktestRequest) =>
    req<BacktestRunResponse>('/api/backtest/run', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}
