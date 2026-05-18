import type {
  BacktestRequest,
  BacktestResult,
  BacktestRunListItem,
  BacktestRunResponse,
  ConditionTypeMeta,
  Health,
  ScreenerPreview,
  StockOHLCV,
  Universe,
  UniverseFilter,
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
  conditionTypes: () =>
    req<{ condition_types: ConditionTypeMeta[] }>('/api/strategies/condition-types'),
  sectors: () => req<{ sectors_l1: string[] }>('/api/data/sectors'),
  screenerPreview: (filter: UniverseFilter) => {
    const params = new URLSearchParams()
    if (filter.boards && filter.boards.length > 0) params.set('boards', filter.boards.join(','))
    if (filter.sectors_l1 && filter.sectors_l1.length > 0) params.set('sectors_l1', filter.sectors_l1.join(','))
    if (filter.market_cap_min !== null) params.set('market_cap_min', String(filter.market_cap_min))
    if (filter.market_cap_max !== null) params.set('market_cap_max', String(filter.market_cap_max))
    params.set('exclude_st', String(filter.exclude_st))
    return req<ScreenerPreview>(`/api/data/screener/preview?${params.toString()}`)
  },
}
