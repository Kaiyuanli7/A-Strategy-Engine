import type {
  EvaluateParams,
  FactorCorrelation,
  FactorEvaluation,
  FactorMeta,
  Health,
  PortfolioBacktestRequest,
  PortfolioBacktestResponse,
  PortfolioResult,
  PortfolioRunListItem,
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
  universe: (index = '000300', asOf?: string) => {
    const qs = new URLSearchParams({ index })
    if (asOf) qs.set('as_of', asOf)
    return req<Universe>(`/api/data/universe?${qs.toString()}`)
  },
  stock: (code: string, start?: string, end?: string) => {
    const params = new URLSearchParams()
    if (start) params.set('start', start)
    if (end) params.set('end', end)
    const qs = params.toString()
    return req<StockOHLCV>(`/api/data/stock/${code}${qs ? '?' + qs : ''}`)
  },
  sectors: () => req<{ sectors_l1: string[] }>('/api/data/sectors'),
  factors: () => req<FactorMeta[]>('/api/factors'),
  evaluateFactor: (name: string, params: EvaluateParams) => {
    const qs = new URLSearchParams({
      start: params.start,
      end: params.end,
      universe: params.universe,
      horizon: String(params.horizon),
      rebalance: params.rebalance,
    })
    if (params.lookback !== undefined) qs.set('lookback', String(params.lookback))
    if (params.use_cache !== undefined) qs.set('use_cache', String(params.use_cache))
    return req<FactorEvaluation>(`/api/factors/${name}/evaluate?${qs.toString()}`)
  },
  factorCorrelation: (
    factors: string[],
    start: string,
    end: string,
    universe: string,
    rebalance: 'daily' | 'weekly' | 'monthly' = 'monthly',
  ) => {
    const qs = new URLSearchParams({
      factors: factors.join(','),
      start, end, universe, rebalance,
    })
    return req<FactorCorrelation>(`/api/factors/correlation?${qs.toString()}`)
  },
  runPortfolioBacktest: (body: PortfolioBacktestRequest) =>
    req<PortfolioBacktestResponse>('/api/portfolios/backtest', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  portfolioResult: (runId: string) =>
    req<PortfolioResult>(`/api/portfolios/runs/${runId}`),
  portfolioRuns: () => req<PortfolioRunListItem[]>('/api/portfolios/runs'),
}
