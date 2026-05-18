import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import {
  createChart, CandlestickSeries, HistogramSeries, LineSeries,
  CrosshairMode,
  type IChartApi, type ISeriesApi, type SeriesMarker,
  type UTCTimestamp,
} from 'lightweight-charts'
import { api } from '@/api/client'
import type { ChartResponse, ChartSignal } from '@/types/api'


// CN convention: red = up, green = down
const COLOR_UP = '#dc2626'
const COLOR_DOWN = '#16a34a'
const COLOR_VOL_UP = 'rgba(220, 38, 38, 0.5)'
const COLOR_VOL_DOWN = 'rgba(22, 163, 74, 0.5)'

const MA_COLORS: Record<string, string> = {
  ma_5: '#f59e0b',
  ma_10: '#a855f7',
  ma_20: '#2563eb',
  ma_60: '#0891b2',
  ma_120: '#84cc16',
  ma_250: '#9333ea',
  ema_5: '#f59e0b',
  ema_10: '#a855f7',
  ema_20: '#2563eb',
  ema_60: '#0891b2',
}

const PRESETS: Record<string, string[]> = {
  cn_standard: ['ma_5', 'ma_10', 'ma_20', 'ma_60'],
  western: ['ema_20', 'ema_60'],
  minimal: ['ma_20'],
}

const DATE_RANGES: Array<{ label: string; days: number | null }> = [
  { label: '1M', days: 30 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '1Y', days: 365 },
  { label: '3Y', days: 365 * 3 },
  { label: 'ALL', days: null },
]


function toUtcTime(dateStr: string): UTCTimestamp {
  return Math.floor(new Date(dateStr + 'T00:00:00Z').getTime() / 1000) as UTCTimestamp
}


export default function StockChart() {
  const { code } = useParams<{ code: string }>()
  const [searchParams] = useSearchParams()
  const runId = searchParams.get('run_id') || undefined

  const [data, setData] = useState<ChartResponse | null>(null)
  const [err, setErr] = useState<string | null>(null)
  // Indicators default OFF — this platform is about factor signals, not TA
  const [selectedIndicators, setSelectedIndicators] = useState<string[]>([])
  const [rangeDays, setRangeDays] = useState<number | null>(180)

  const chartContainerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const indicatorSeriesRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map())
  const [selectedSignal, setSelectedSignal] = useState<ChartSignal | null>(null)

  // Compute the start/end dates from the range selector
  const today = new Date()
  const end = today.toISOString().slice(0, 10)
  const start = rangeDays === null
    ? '2021-01-01'
    : new Date(today.getTime() - rangeDays * 86400000).toISOString().slice(0, 10)

  // Fetch chart data when code / range / indicators / run_id change
  useEffect(() => {
    if (!code) return
    setErr(null)
    setData(null)
    api.chart(code, {
      start, end,
      indicators: selectedIndicators,
      run_id: runId,
    }).then(setData).catch((e) => setErr(String(e)))
  }, [code, start, end, selectedIndicators.join(','), runId])

  // Create/destroy the chart when container is mounted
  useEffect(() => {
    if (!chartContainerRef.current) return
    const chart = createChart(chartContainerRef.current, {
      autoSize: true,
      layout: {
        background: { color: '#ffffff' },
        textColor: '#1f2937',
      },
      grid: {
        vertLines: { color: '#eceef2' },
        horzLines: { color: '#eceef2' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { borderColor: '#cfd4dd', timeVisible: false, secondsVisible: false },
      rightPriceScale: { borderColor: '#cfd4dd' },
    })
    chartRef.current = chart

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: COLOR_UP,
      downColor: COLOR_DOWN,
      borderUpColor: COLOR_UP,
      borderDownColor: COLOR_DOWN,
      wickUpColor: COLOR_UP,
      wickDownColor: COLOR_DOWN,
    })
    candleSeriesRef.current = candles

    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
      color: COLOR_VOL_UP,
    })
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })
    volumeSeriesRef.current = volume

    return () => {
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
      indicatorSeriesRef.current.clear()
    }
  }, [code])    // re-create chart on stock change to fully reset markers

  // Write data into the chart whenever it changes
  useEffect(() => {
    if (!data || !chartRef.current || !candleSeriesRef.current || !volumeSeriesRef.current) return
    const chart = chartRef.current
    const candles = candleSeriesRef.current
    const volume = volumeSeriesRef.current

    // Candles
    candles.setData(data.candles.map((c) => ({
      time: toUtcTime(c.time),
      open: c.open, high: c.high, low: c.low, close: c.close,
    })))

    // Volume with color matching candle direction
    volume.setData(data.candles.map((c, i) => {
      const prev = i > 0 ? data.candles[i - 1].close : c.open
      const up = c.close >= prev
      return {
        time: toUtcTime(c.time),
        value: c.volume,
        color: up ? COLOR_VOL_UP : COLOR_VOL_DOWN,
      }
    }))

    // Indicators: remove ones that aren't in the current selection,
    // add/update the ones that are.
    const wanted = new Set(Object.keys(data.indicators))
    for (const [name, series] of indicatorSeriesRef.current.entries()) {
      if (!wanted.has(name)) {
        chart.removeSeries(series)
        indicatorSeriesRef.current.delete(name)
      }
    }
    for (const [name, points] of Object.entries(data.indicators)) {
      const seriesData = points
        .filter((p) => p.value !== null && p.value !== undefined)
        .map((p) => ({ time: toUtcTime(p.time), value: p.value as number }))
      let series = indicatorSeriesRef.current.get(name)
      if (!series) {
        series = chart.addSeries(LineSeries, {
          color: MA_COLORS[name] ?? '#6b7280',
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: false,
          title: name.toUpperCase().replace('_', '(') + ')',
        })
        indicatorSeriesRef.current.set(name, series)
      } else {
        series.applyOptions({ color: MA_COLORS[name] ?? '#6b7280' })
      }
      series.setData(seriesData)
    }

    // Signal markers: red ▲ for buys, green ▼ for sells (CN convention)
    if (data.signals.length > 0) {
      const markers: SeriesMarker<UTCTimestamp>[] = data.signals.map((s) => ({
        time: toUtcTime(s.time),
        position: s.side === 'buy' ? 'belowBar' : 'aboveBar',
        color: s.side === 'buy' ? COLOR_UP : COLOR_DOWN,
        shape: s.side === 'buy' ? 'arrowUp' : 'arrowDown',
        text: s.side === 'buy' ? '买入' : '卖出',
      }))
      // v5 setMarkers is on a SeriesMarkers primitive; for simplicity here we use the convenience method
      // that's still available on the series via the createSeriesMarkers helper in v5.
      import('lightweight-charts').then(({ createSeriesMarkers }) => {
        if (candleSeriesRef.current) {
          createSeriesMarkers(candleSeriesRef.current, markers)
        }
      })
    }

    chart.timeScale().fitContent()
  }, [data])

  // Click on a candle near a signal to show its details
  useEffect(() => {
    const chart = chartRef.current
    const candleSeries = candleSeriesRef.current
    if (!chart || !candleSeries || !data) return
    const handler = (param: any) => {
      if (!param.time) { setSelectedSignal(null); return }
      // Find a signal on the clicked bar (within ±1 day to be tolerant)
      const match = data.signals.find((s) => Math.abs(
        (toUtcTime(s.time) as unknown as number) - (param.time as number)
      ) < 86400 * 1.5)
      if (match) setSelectedSignal(match)
    }
    chart.subscribeClick(handler)
    return () => chart.unsubscribeClick(handler)
  }, [data])

  if (!code) return <div className="text-ink-400">No stock code in URL.</div>

  const allIndicators = ['ma_5', 'ma_10', 'ma_20', 'ma_60', 'ma_120', 'ma_250',
                        'ema_20', 'ema_60', 'rsi', 'macd']
  const isOn = (name: string) => selectedIndicators.includes(name)
  const toggle = (name: string) => {
    setSelectedIndicators((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <div>
          <h1>
            <span className="font-mono">{code}</span>
            {data?.name && <span className="ml-3 text-ink-600">{data.name}</span>}
          </h1>
          <div className="text-xs text-ink-400 mt-1">
            {data?.sector ?? ''}
            {runId && (
              <>
                {' · '}
                <span>signals from run </span>
                <Link to={`/portfolio/runs/${runId}`}
                      className="text-accent-blue underline font-mono">
                  {runId.slice(0, 8)}…
                </Link>
              </>
            )}
          </div>
        </div>
        <div className="flex gap-1 text-xs">
          {DATE_RANGES.map((r) => (
            <button key={r.label}
                    onClick={() => setRangeDays(r.days)}
                    className={
                      'px-2 py-1 border rounded ' +
                      (rangeDays === r.days
                        ? 'border-ink-800 bg-ink-800 text-white'
                        : 'border-ink-200 bg-white hover:bg-ink-50')
                    }>
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {err && <div className="card border-accent-red text-accent-red text-sm">{err}</div>}

      <div className="card">
        <div className="flex flex-wrap gap-2 mb-3 text-xs">
          <span className="text-ink-400 self-center">presets:</span>
          {Object.entries(PRESETS).map(([key, list]) => (
            <button
              key={key}
              onClick={() => setSelectedIndicators(list)}
              className="px-2 py-1 border border-ink-200 rounded hover:bg-ink-50"
            >
              {key}
            </button>
          ))}
          <span className="text-ink-400 self-center ml-3">indicators:</span>
          {allIndicators.map((name) => (
            <button key={name}
                    onClick={() => toggle(name)}
                    className={
                      'px-2 py-1 border rounded font-mono ' +
                      (isOn(name)
                        ? 'border-ink-800 bg-ink-800 text-white'
                        : 'border-ink-200 bg-white hover:bg-ink-50')
                    }>
              {name}
            </button>
          ))}
        </div>
        <div ref={chartContainerRef} style={{ width: '100%', height: 480 }} />
      </div>

      {data && data.signals.length > 0 && (
        <div className="card">
          <div className="metric-key mb-2">
            Signals on this stock from run {runId?.slice(0, 8)}…
            ({data.signals.length} total)
          </div>
          <div className="text-xs text-ink-400 mb-2">
            Click any signal arrow on the chart to inspect it; or browse the list:
          </div>
          <div className="overflow-auto max-h-72">
            <table className="data">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Side</th>
                  <th className="text-right">Shares</th>
                  <th className="text-right">Price</th>
                  <th className="text-right">Cost</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.signals.map((s, i) => (
                  <tr key={i}
                      className={selectedSignal === s ? 'bg-ink-50' : ''}
                      onClick={() => setSelectedSignal(s)}>
                    <td className="font-mono text-xs">{s.time}</td>
                    <td className={s.side === 'buy' ? 'pos' : 'neg'}>
                      {s.side === 'buy' ? '▲ 买入' : '▼ 卖出'}
                    </td>
                    <td className="text-right">{s.shares.toLocaleString()}</td>
                    <td className="text-right">¥{s.price.toFixed(2)}</td>
                    <td className="text-right text-xs text-ink-400">
                      ¥{s.cost.toFixed(2)}
                    </td>
                    <td className="text-xs">
                      {s.rejected_reason ? (
                        <span className="text-accent-red">rej: {s.rejected_reason}</span>
                      ) : 'filled'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!runId && (
        <div className="card text-xs text-ink-400">
          Tip: open this page from a portfolio backtest's holdings table to see
          that backtest's entries/exits overlaid on the chart. Or append
          <code className="font-mono bg-ink-50 px-1 ml-1 rounded">?run_id=&lt;hash&gt;</code>
          to the URL manually.
        </div>
      )}
    </div>
  )
}
