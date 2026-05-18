import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '@/api/client'
import CompositeBuilder from '@/components/portfolio/CompositeBuilder'
import DrawdownChart from '@/components/portfolio/DrawdownChart'
import EquityCurveChart from '@/components/portfolio/EquityCurveChart'
import FactorAttributionPanel from '@/components/portfolio/FactorAttributionPanel'
import FillsTable from '@/components/portfolio/FillsTable'
import HoldingsPanel from '@/components/portfolio/HoldingsPanel'
import MonthlyHeatmap from '@/components/portfolio/MonthlyHeatmap'
import RegimePanel from '@/components/portfolio/RegimePanel'
import SectorExposureChart from '@/components/portfolio/SectorExposureChart'
import SummaryPanel from '@/components/portfolio/SummaryPanel'
import TldrCard from '@/components/portfolio/TldrCard'
import type {
  CompositeSpec, FactorMeta, PortfolioBacktestRequest,
  PortfolioConfigSpec, PortfolioResult, StockBar,
} from '@/types/api'


const DEFAULT_PORTFOLIO: PortfolioConfigSpec = {
  top_n: 30,
  rebalance_freq: 'weekly',
  max_sector_pct: 0.25,
  max_single_position_pct: 0.05,
  min_market_cap: 3_000_000_000,
  exclude_st: true,
  weighting: 'equal',
}

const DEFAULT_COMPOSITE: CompositeSpec = {
  method: 'equal_weight',
  factors: [],
}


export default function PortfolioBacktest() {
  const { runId } = useParams<{ runId: string }>()
  const nav = useNavigate()

  const [factors, setFactors] = useState<FactorMeta[] | null>(null)
  const [composite, setComposite] = useState<CompositeSpec>(DEFAULT_COMPOSITE)
  const [portfolio, setPortfolio] = useState<PortfolioConfigSpec>(DEFAULT_PORTFOLIO)
  const [start, setStart] = useState('2023-01-01')
  const [end, setEnd] = useState('2025-12-31')
  const [universe, setUniverse] = useState('000300')
  const [running, setRunning] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [result, setResult] = useState<PortfolioResult | null>(null)

  useEffect(() => {
    api.factors().then(setFactors).catch((e) => setErr(String(e)))
  }, [])

  const [benchmark, setBenchmark] = useState<StockBar[] | null>(null)

  useEffect(() => {
    if (!runId) {
      setResult(null)
      setBenchmark(null)
      return
    }
    api.portfolioResult(runId).then(setResult).catch((e) => setErr(String(e)))
  }, [runId])

  // Fetch CSI 300 benchmark once we know the run's period.
  useEffect(() => {
    if (!result) {
      setBenchmark(null)
      return
    }
    api.stock('000300', result.config.start, result.config.end)
      .then((s) => setBenchmark(s.bars))
      .catch(() => setBenchmark([]))   // benchmark missing isn't fatal
  }, [result])

  const submit = async () => {
    if (composite.factors.length === 0) {
      setErr('Add at least one factor')
      return
    }
    setRunning(true)
    setErr(null)
    try {
      const body: PortfolioBacktestRequest = {
        composite, portfolio, universe, start, end,
        initial_cash: 1_000_000,
        limit_hit_fill_prob: 0.2,
        random_seed: 42,
      }
      const res = await api.runPortfolioBacktest(body)
      nav(`/portfolio/runs/${res.run_id}`)
    } catch (e) {
      setErr(String(e))
    } finally {
      setRunning(false)
    }
  }

  // --------- Result view ---------
  if (runId) {
    if (err) return <div className="card border-accent-red text-accent-red">{err}</div>
    if (!result) return <div className="text-ink-400">Loading…</div>
    const summary = result.summary as Record<string, unknown> | null
    const attribution = (summary?.factor_attribution as Parameters<typeof FactorAttributionPanel>[0]['attribution']) ?? null
    const regimes = (summary?.regime_metrics as Parameters<typeof RegimePanel>[0]['regimes']) ?? null
    return (
      <div className="space-y-4">
        <div className="flex items-baseline justify-between">
          <div>
            <h1>Portfolio backtest result</h1>
            <div className="text-xs text-ink-400 font-mono mt-1">{result.run_id}</div>
          </div>
          <Link to="/portfolio" className="text-sm text-accent-blue underline">
            ← new backtest
          </Link>
        </div>

        <TldrCard
          equity={result.equity_curve}
          initialEquity={result.config.initial_cash}
          benchmark={benchmark ?? undefined}
          summary={result.summary}
        />

        <SummaryPanel summary={result.summary} />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <EquityCurveChart
              data={result.equity_curve}
              initialEquity={result.config.initial_cash}
              benchmark={benchmark ?? undefined}
            />
          </div>
          <DrawdownChart data={result.equity_curve} />
        </div>

        <MonthlyHeatmap data={result.equity_curve} />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <FactorAttributionPanel attribution={attribution} />
          <RegimePanel regimes={regimes} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <HoldingsPanel holdings={result.final_holdings} runId={result.run_id} />
          </div>
          <SectorExposureChart
            exposure={result.sector_exposure}
            maxSectorPct={result.config.portfolio.max_sector_pct}
          />
        </div>

        <FillsTable fills={result.fills} rejections={result.rejections} />
      </div>
    )
  }

  // --------- Builder form ---------
  if (factors === null && !err) return <div className="text-ink-400">Loading factors…</div>

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1>Portfolio backtest</h1>
        <div className="flex items-center gap-3">
          <Link to="/portfolio/runs" className="text-sm text-accent-blue underline">
            past runs →
          </Link>
        </div>
      </div>
      <div className="text-xs text-ink-400">
        Build a 1-5 factor composite and run a top-N portfolio backtest with
        full A-share constraints (T+1, price limits, costs).
      </div>

      {err && <div className="card border-accent-red text-accent-red text-sm">{err}</div>}

      {factors && (
        <CompositeBuilder factors={factors} spec={composite} onChange={setComposite} />
      )}

      <div className="card">
        <div className="metric-key mb-3">Portfolio config</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <NumInput label="Top N" value={portfolio.top_n}
                    onChange={(v) => setPortfolio({ ...portfolio, top_n: Math.round(v) })}
                    min={1} max={300} step={1} />
          <SelectInput label="Rebalance" value={portfolio.rebalance_freq}
                       onChange={(v) => setPortfolio({ ...portfolio, rebalance_freq: v as 'weekly' | 'monthly' })}
                       options={['weekly', 'monthly']} />
          <NumInput label="Max sector %" value={portfolio.max_sector_pct * 100}
                    onChange={(v) => setPortfolio({ ...portfolio, max_sector_pct: v / 100 })}
                    min={5} max={100} step={5} suffix="%" />
          <NumInput label="Max position %" value={portfolio.max_single_position_pct * 100}
                    onChange={(v) => setPortfolio({ ...portfolio, max_single_position_pct: v / 100 })}
                    min={1} max={100} step={1} suffix="%" />
          <NumInput label="Min mkt cap (¥B)" value={portfolio.min_market_cap / 1e9}
                    onChange={(v) => setPortfolio({ ...portfolio, min_market_cap: v * 1e9 })}
                    min={0} max={1000} step={1} />
          <label className="flex items-center gap-2 mt-5">
            <input type="checkbox" checked={portfolio.exclude_st}
                   onChange={(e) => setPortfolio({ ...portfolio, exclude_st: e.target.checked })} />
            <span className="text-sm">Exclude ST</span>
          </label>
        </div>
      </div>

      <div className="card">
        <div className="metric-key mb-3">Period + universe</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <label className="text-xs">
            <div className="metric-key mb-1">Universe</div>
            <input type="text" className="w-full border border-ink-200 rounded px-3 py-2 font-mono text-sm"
                   value={universe} onChange={(e) => setUniverse(e.target.value)} />
          </label>
          <label className="text-xs">
            <div className="metric-key mb-1">Start</div>
            <input type="date" className="w-full border border-ink-200 rounded px-3 py-2 font-mono text-sm"
                   value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label className="text-xs">
            <div className="metric-key mb-1">End</div>
            <input type="date" className="w-full border border-ink-200 rounded px-3 py-2 font-mono text-sm"
                   value={end} onChange={(e) => setEnd(e.target.value)} />
          </label>
          <div className="flex items-end">
            <button onClick={submit} disabled={running || composite.factors.length === 0}
                    className="w-full bg-ink-800 text-white px-6 py-2 rounded-md text-sm hover:bg-ink-900 disabled:opacity-50">
              {running ? 'Running…' : 'Backtest'}
            </button>
          </div>
        </div>
      </div>

      <div className="text-xs text-ink-400">
        First run can take 30-90 seconds — composite evaluates at every rebalance
        date across the universe, then the backtester walks each bar with full
        T+1 / price-limit / cost modeling.
      </div>
    </div>
  )
}


function NumInput({
  label, value, onChange, min, max, step, suffix,
}: {
  label: string; value: number; onChange: (v: number) => void;
  min?: number; max?: number; step?: number; suffix?: string;
}) {
  return (
    <label className="text-xs">
      <div className="metric-key mb-1">{label}</div>
      <div className="flex items-center">
        <input type="number"
               className="w-full border border-ink-200 rounded px-3 py-2 font-mono text-sm"
               value={value} onChange={(e) => onChange(Number(e.target.value))}
               min={min} max={max} step={step} />
        {suffix && <span className="ml-2 text-ink-400">{suffix}</span>}
      </div>
    </label>
  )
}


function SelectInput<T extends string>({
  label, value, onChange, options,
}: {
  label: string; value: T; onChange: (v: T) => void; options: T[];
}) {
  return (
    <label className="text-xs">
      <div className="metric-key mb-1">{label}</div>
      <select className="w-full border border-ink-200 rounded px-3 py-2 text-sm"
              value={value} onChange={(e) => onChange(e.target.value as T)}>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>
  )
}
