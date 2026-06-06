import { useEffect, useRef, useState } from 'react';
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
  type CandlestickData,
  type HistogramData,
  type LineData,
} from 'lightweight-charts';
import { getCandles, getForecast, CandleData, ForecastPoint } from '../api/client';

const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'];
const INTERVALS = ['1m', '5m', '1h', '1d'];

const UP = '#10b981';
const DOWN = '#ef4444';
const UP_VOL = 'rgba(16, 185, 129, 0.5)';
const DOWN_VOL = 'rgba(239, 68, 68, 0.5)';
const FORECAST = '#f59e0b';
const BAND = 'rgba(245, 158, 11, 0.35)';

interface Legend {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  up: boolean;
}

const fmtPrice = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 2 });
const fmtVol = (n: number) =>
  new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(n);

function fmtTime(tsSeconds: number): string {
  return new Date(tsSeconds * 1000).toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
}

function changePct(l: Legend): string {
  if (!l.open) return '';
  const pct = ((l.close - l.open) / l.open) * 100;
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
}

const toSeconds = (iso: string) => Math.floor(Date.parse(iso) / 1000) as UTCTimestamp;

function toCandle(d: CandleData): CandlestickData<UTCTimestamp> {
  return { time: toSeconds(d.open_time_utc), open: d.open, high: d.high, low: d.low, close: d.close };
}

function toVolume(d: CandleData): HistogramData<UTCTimestamp> {
  return {
    time: toSeconds(d.open_time_utc),
    value: d.volume,
    color: d.close >= d.open ? UP_VOL : DOWN_VOL,
  };
}

// lightweight-charts requires strictly-ascending, unique timestamps. The source
// data can contain duplicate/out-of-order bars (see the data-quality "duplicate_candle"
// checks), so collapse by timestamp (last write wins) and sort ascending before charting.
function dedupeSorted(data: CandleData[]): CandleData[] {
  const byTime = new Map<number, CandleData>();
  for (const d of data) {
    byTime.set(Math.floor(Date.parse(d.open_time_utc) / 1000), d);
  }
  return [...byTime.entries()].sort((a, b) => a[0] - b[0]).map(([, d]) => d);
}

function toLegend(d: CandleData): Legend {
  return {
    time: fmtTime(Date.parse(d.open_time_utc) / 1000),
    open: d.open,
    high: d.high,
    low: d.low,
    close: d.close,
    volume: d.volume,
    up: d.close >= d.open,
  };
}

// Build a forecast line series that connects from the last actual close so the
// dashed projection visibly continues the candles. `pick` selects which forecast
// field to plot (central close or a band edge).
function forecastLine(
  last: CandleData | undefined,
  forecast: ForecastPoint[],
  pick: (f: ForecastPoint) => number,
): LineData<UTCTimestamp>[] {
  if (!last) return [];
  const anchorTime = toSeconds(last.open_time_utc);
  // Only keep forecast points strictly after the last actual bar, sorted ascending —
  // lightweight-charts requires monotonic time. A stale forecast (all points at or
  // before the latest candle) yields an empty overlay instead of a crash.
  const pts = forecast
    .map(f => ({ time: toSeconds(f.forecast_time_utc), value: pick(f) }))
    .filter(p => p.time > anchorTime)
    .sort((a, b) => a.time - b.time);
  if (pts.length === 0) return [];
  return [{ time: anchorTime, value: last.close }, ...pts];
}

export default function AssetChart() {
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [interval, setInterval] = useState('1h');
  const [loading, setLoading] = useState(false);
  const [count, setCount] = useState(0);
  const [legend, setLegend] = useState<Legend | null>(null);
  const [hasForecast, setHasForecast] = useState(false);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const forecastRef = useRef<ISeriesApi<'Line'> | null>(null);
  const bandLowRef = useRef<ISeriesApi<'Line'> | null>(null);
  const bandHighRef = useRef<ISeriesApi<'Line'> | null>(null);
  const lastBarRef = useRef<Legend | null>(null);

  // Create the chart once on mount; tear it down on unmount.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: '#111827' },
        textColor: '#9ca3af',
        fontSize: 11,
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: '#1f2937' },
        horzLines: { color: '#1f2937' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#374151' },
      timeScale: { borderColor: '#374151', timeVisible: true, secondsVisible: false },
    });

    const candle = chart.addSeries(CandlestickSeries, {
      upColor: UP,
      downColor: DOWN,
      borderUpColor: UP,
      borderDownColor: DOWN,
      wickUpColor: UP,
      wickDownColor: DOWN,
    });

    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    const bandCommon = {
      color: BAND,
      lineWidth: 1 as const,
      lineStyle: LineStyle.Dashed,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    };
    const bandLow = chart.addSeries(LineSeries, bandCommon);
    const bandHigh = chart.addSeries(LineSeries, bandCommon);
    const forecast = chart.addSeries(LineSeries, {
      color: FORECAST,
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    });

    chart.subscribeCrosshairMove((param) => {
      const c = param.seriesData.get(candle) as CandlestickData<UTCTimestamp> | undefined;
      if (!param.time || !param.point || !c) {
        setLegend(lastBarRef.current);
        return;
      }
      const v = param.seriesData.get(volume) as HistogramData<UTCTimestamp> | undefined;
      setLegend({
        time: fmtTime(param.time as number),
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: v?.value ?? 0,
        up: c.close >= c.open,
      });
    });

    chartRef.current = chart;
    candleRef.current = candle;
    volumeRef.current = volume;
    forecastRef.current = forecast;
    bandLowRef.current = bandLow;
    bandHighRef.current = bandHigh;

    return () => {
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volumeRef.current = null;
      forecastRef.current = null;
      bandLowRef.current = null;
      bandHighRef.current = null;
    };
  }, []);

  // Reload candles + forecast whenever the symbol or interval changes.
  useEffect(() => {
    setLoading(true);
    let cancelled = false;

    Promise.all([
      getCandles(symbol, interval, 200),
      getForecast(symbol, interval).catch(() => ({ data: [] as ForecastPoint[] })),
    ])
      .then(([candleRes, forecastRes]) => {
        if (cancelled) return;
        const clean = dedupeSorted(candleRes.data);
        candleRef.current?.setData(clean.map(toCandle));
        volumeRef.current?.setData(clean.map(toVolume));

        const last = clean[clean.length - 1];
        const fc = forecastRes.data ?? [];
        // Isolate forecast rendering so a forecast issue can never wipe the candles.
        try {
          const line = forecastLine(last, fc, f => f.pred_close);
          forecastRef.current?.setData(line);
          bandLowRef.current?.setData(forecastLine(last, fc, f => f.pred_close_low));
          bandHighRef.current?.setData(forecastLine(last, fc, f => f.pred_close_high));
          setHasForecast(line.length > 0);
        } catch {
          forecastRef.current?.setData([]);
          bandLowRef.current?.setData([]);
          bandHighRef.current?.setData([]);
          setHasForecast(false);
        }

        chartRef.current?.timeScale().fitContent();
        setCount(clean.length);
        lastBarRef.current = last ? toLegend(last) : null;
        setLegend(lastBarRef.current);
      })
      .catch(() => {
        if (cancelled) return;
        candleRef.current?.setData([]);
        volumeRef.current?.setData([]);
        forecastRef.current?.setData([]);
        bandLowRef.current?.setData([]);
        bandHighRef.current?.setData([]);
        setHasForecast(false);
        setCount(0);
        lastBarRef.current = null;
        setLegend(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [symbol, interval]);

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="text-sm font-medium text-gray-300">Asset</label>
        <select
          value={symbol}
          onChange={e => setSymbol(e.target.value)}
          className="rounded border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
        >
          {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        <label className="text-sm font-medium text-gray-300">Interval</label>
        <select
          value={interval}
          onChange={e => setInterval(e.target.value)}
          className="rounded border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
        >
          {INTERVALS.map(i => <option key={i} value={i}>{i}</option>)}
        </select>

        <span className="ml-auto text-xs text-gray-500">{count} candles</span>
      </div>

      <div className="relative h-[360px] w-full">
        <div ref={containerRef} className="absolute inset-0" />

        {legend && (
          <div className="pointer-events-none absolute left-3 top-2 z-10 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs">
            <span className="font-semibold text-gray-200">{symbol}</span>
            <span className="text-gray-500">{legend.time}</span>
            <span className="text-gray-400">O <span className="text-gray-200">{fmtPrice(legend.open)}</span></span>
            <span className="text-gray-400">H <span className="text-gray-200">{fmtPrice(legend.high)}</span></span>
            <span className="text-gray-400">L <span className="text-gray-200">{fmtPrice(legend.low)}</span></span>
            <span className="text-gray-400">
              C <span className={legend.up ? 'text-green-400' : 'text-red-400'}>{fmtPrice(legend.close)}</span>
            </span>
            <span className={legend.up ? 'text-green-400' : 'text-red-400'}>{changePct(legend)}</span>
            <span className="text-gray-400">Vol <span className="text-gray-300">{fmtVol(legend.volume)}</span></span>
          </div>
        )}

        {loading && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-gray-900/60 text-gray-500">
            Loading...
          </div>
        )}
        {!loading && count === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-gray-500">
            No data available
          </div>
        )}
      </div>

      {hasForecast && (
        <div className="mt-2 flex items-center gap-2 text-xs text-amber-500/80">
          <span className="inline-block h-0.5 w-4 border-t-2 border-dashed border-amber-500" />
          Experimental Kronos forecast (dashed) with uncertainty band — not financial advice.
        </div>
      )}
    </div>
  );
}
