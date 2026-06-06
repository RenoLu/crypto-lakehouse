import { useEffect, useRef, useState } from 'react';
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  AreaSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
  type CandlestickData,
  type HistogramData,
  type LineData,
  type AreaData,
} from 'lightweight-charts';
import { getCandles, getForecast, getBacktestReplay, getBacktestMetrics,
         CandleData, ForecastPoint, BacktestReplay, BacktestMetrics, BacktestAnchor } from '../api/client';
import { useRefresh } from '../refresh';
import { useTheme } from '../theme';
import CoinIcon from './CoinIcon';
import BacktestStrip from './BacktestStrip';

const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'];
const INTERVALS = ['1m', '5m', '1h', '1d'];

const CHART_BG = '#0d121c';
const GRID = '#141c2a';
const AXIS_TEXT = '#69748a';
const AXIS_BORDER = '#1b2433';
const UP = '#26d07c';
const DOWN = '#f6465d';
const UP_VOL = 'rgba(38, 208, 124, 0.45)';
const DOWN_VOL = 'rgba(246, 70, 93, 0.45)';
const FORECAST = '#f5a524';
const BAND_FILL = 'rgba(245, 165, 36, 0.16)';

// Theme-dependent chart chrome (candle/forecast/band colors stay constant —
// they read fine on both themes). The band mask must match the chart bg.
function themeColors(theme: string) {
  return theme === 'light'
    ? { bg: '#ffffff', grid: '#e6eaf0', text: '#6e7888', border: '#dee3ea' }
    : { bg: CHART_BG, grid: GRID, text: AXIS_TEXT, border: AXIS_BORDER };
}

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
  return { time: toSeconds(d.open_time_utc), value: d.volume, color: d.close >= d.open ? UP_VOL : DOWN_VOL };
}

// lightweight-charts requires strictly-ascending, unique timestamps. The source
// data can contain duplicate/out-of-order bars, so collapse by timestamp and sort.
function dedupeSorted(data: CandleData[]): CandleData[] {
  const byTime = new Map<number, CandleData>();
  for (const d of data) byTime.set(Math.floor(Date.parse(d.open_time_utc) / 1000), d);
  return [...byTime.entries()].sort((a, b) => a[0] - b[0]).map(([, d]) => d);
}

function toLegend(d: CandleData): Legend {
  return {
    time: fmtTime(Date.parse(d.open_time_utc) / 1000),
    open: d.open, high: d.high, low: d.low, close: d.close, volume: d.volume,
    up: d.close >= d.open,
  };
}

// A forecast series that connects from the last actual close. Only keeps points
// strictly after the last bar (ascending), so a stale forecast yields an empty
// overlay instead of a crash.
function forecastLine(
  last: CandleData | undefined,
  forecast: ForecastPoint[],
  pick: (f: ForecastPoint) => number,
): LineData<UTCTimestamp>[] {
  if (!last) return [];
  const anchorTime = toSeconds(last.open_time_utc);
  const pts = forecast
    .map(f => ({ time: toSeconds(f.forecast_time_utc), value: pick(f) }))
    .filter(p => p.time > anchorTime)
    .sort((a, b) => a.time - b.time);
  if (pts.length === 0) return [];
  return [{ time: anchorTime, value: last.close }, ...pts];
}

function bandFromAnchor(a: BacktestAnchor, pick: (s: BacktestAnchor['forecast'][0]) => number): AreaData<UTCTimestamp>[] {
  return a.forecast.map(s => ({ time: toSeconds(s.t), value: pick(s) }))
    .sort((p, q) => (p.time as number) - (q.time as number));
}

export default function AssetChart() {
  const { tick } = useRefresh();
  const { theme } = useTheme();
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [interval, setInterval] = useState('1h');
  const [fmode, setFmode] = useState('sampled');
  const [lookback, setLookback] = useState(256);
  const [loading, setLoading] = useState(false);
  const [count, setCount] = useState(0);
  const [legend, setLegend] = useState<Legend | null>(null);
  const [hasForecast, setHasForecast] = useState(false);
  const [view, setView] = useState<'live' | 'replay'>('live');
  const [replay, setReplay] = useState<BacktestReplay | null>(null);
  const [metrics, setMetrics] = useState<BacktestMetrics | null>(null);
  const [anchorIdx, setAnchorIdx] = useState(0);
  const replaySupported = ['1h', '1d'].includes(interval);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const forecastRef = useRef<ISeriesApi<'Line'> | null>(null);
  const bandHighRef = useRef<ISeriesApi<'Area'> | null>(null);
  const bandLowRef = useRef<ISeriesApi<'Area'> | null>(null);
  const lastBarRef = useRef<Legend | null>(null);

  // Create the chart once on mount.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: CHART_BG },
        textColor: AXIS_TEXT,
        fontSize: 11,
        fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
        attributionLogo: false,
      },
      grid: { vertLines: { color: GRID }, horzLines: { color: GRID } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: AXIS_BORDER },
      timeScale: { borderColor: AXIS_BORDER, timeVisible: true, secondsVisible: false },
    });

    // Band areas are added first so they sit behind candles + the central line.
    // The "high" area fills amber down to baseline; the "low" area re-fills with
    // the chart background to mask everything below the low edge — net effect is a
    // shaded band between low and high (lightweight-charts has no native band).
    const areaCommon = { lineWidth: 1 as const, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false };
    const bandHigh = chart.addSeries(AreaSeries, { ...areaCommon, topColor: BAND_FILL, bottomColor: BAND_FILL, lineColor: 'rgba(0,0,0,0)' });
    const bandLow = chart.addSeries(AreaSeries, { ...areaCommon, topColor: CHART_BG, bottomColor: CHART_BG, lineColor: 'rgba(0,0,0,0)' });

    const candle = chart.addSeries(CandlestickSeries, {
      upColor: UP, downColor: DOWN, borderUpColor: UP, borderDownColor: DOWN, wickUpColor: UP, wickDownColor: DOWN,
    });

    const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: '' });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

    const forecast = chart.addSeries(LineSeries, {
      color: FORECAST, lineWidth: 2, lineStyle: LineStyle.Dashed,
      lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
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
        open: c.open, high: c.high, low: c.low, close: c.close,
        volume: v?.value ?? 0, up: c.close >= c.open,
      });
    });

    chartRef.current = chart;
    candleRef.current = candle;
    volumeRef.current = volume;
    forecastRef.current = forecast;
    bandHighRef.current = bandHigh;
    bandLowRef.current = bandLow;

    return () => {
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volumeRef.current = null;
      forecastRef.current = null;
      bandHighRef.current = null;
      bandLowRef.current = null;
    };
  }, []);

  // Re-theme the chart (and the band-mask color) when the theme changes.
  useEffect(() => {
    const c = themeColors(theme);
    chartRef.current?.applyOptions({
      layout: { background: { type: ColorType.Solid, color: c.bg }, textColor: c.text },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.border },
      timeScale: { borderColor: c.border },
    });
    bandLowRef.current?.applyOptions({ topColor: c.bg, bottomColor: c.bg });
  }, [theme]);

  // Fetch backtest replay data when in replay mode.
  useEffect(() => {
    if (view !== 'replay' || !replaySupported) { setReplay(null); setMetrics(null); return; }
    let cancelled = false;
    setLoading(true);
    Promise.all([getBacktestReplay(symbol, interval), getBacktestMetrics(symbol, interval)])
      .then(([rep, met]) => {
        if (cancelled) return;
        setReplay(rep); setMetrics(met);
        setAnchorIdx(rep.anchors.length ? rep.anchors.length - 1 : 0);
      })
      .catch(() => { if (!cancelled) { setReplay(null); setMetrics(null); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [view, symbol, interval, replaySupported, tick]);

  // Render the selected anchor when scrubbing through replay.
  useEffect(() => {
    if (view !== 'replay' || !replay || !replay.anchors.length) return;
    const a = replay.anchors[Math.min(anchorIdx, replay.anchors.length - 1)];
    candleRef.current?.setData(a.candles.map(c => ({
      time: toSeconds(c.t), open: c.o, high: c.h, low: c.l, close: c.c,
    })));
    volumeRef.current?.setData([]);
    const central: LineData<UTCTimestamp>[] = a.forecast
      .map(s => ({ time: toSeconds(s.t), value: s.pred }))
      .sort((p, q) => (p.time as number) - (q.time as number));
    forecastRef.current?.setData(central);
    bandHighRef.current?.setData(bandFromAnchor(a, s => s.hi));
    bandLowRef.current?.setData(bandFromAnchor(a, s => s.lo));
    chartRef.current?.timeScale().fitContent();
    setHasForecast(true);
    setCount(a.candles.length);
    lastBarRef.current = null;
    setLegend(null);
  }, [view, replay, anchorIdx]);

  // Reload candles + forecast on control change or auto-refresh tick.
  useEffect(() => {
    if (view === 'replay') return;
    setLoading(true);
    let cancelled = false;

    Promise.all([
      getCandles(symbol, interval, 200),
      getForecast(symbol, interval, fmode, lookback).catch(() => ({ data: [] as ForecastPoint[] })),
    ])
      .then(([candleRes, forecastRes]) => {
        if (cancelled) return;
        const clean = dedupeSorted(candleRes.data);
        candleRef.current?.setData(clean.map(toCandle));
        volumeRef.current?.setData(clean.map(toVolume));

        const last = clean[clean.length - 1];
        const fc = forecastRes.data ?? [];
        try {
          const line = forecastLine(last, fc, f => f.pred_close);
          forecastRef.current?.setData(line);
          if (fmode === 'deterministic') {
            bandHighRef.current?.setData([]);
            bandLowRef.current?.setData([]);
          } else {
            bandHighRef.current?.setData(forecastLine(last, fc, f => f.pred_close_high) as AreaData<UTCTimestamp>[]);
            bandLowRef.current?.setData(forecastLine(last, fc, f => f.pred_close_low) as AreaData<UTCTimestamp>[]);
          }
          setHasForecast(line.length > 0);
        } catch {
          forecastRef.current?.setData([]);
          bandHighRef.current?.setData([]);
          bandLowRef.current?.setData([]);
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
        bandHighRef.current?.setData([]);
        bandLowRef.current?.setData([]);
        setHasForecast(false);
        setCount(0);
        lastBarRef.current = null;
        setLegend(null);
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [symbol, interval, fmode, lookback, tick, view]);

  const selectCls =
    'rounded-sm border border-term-border bg-term-bg px-2.5 py-1 font-mono text-xs text-term-text focus:border-term-accent focus:outline-none';
  const labelCls = 'font-mono text-[10px] uppercase tracking-wider text-term-muted';

  return (
    <div className="rounded-sm border border-term-border bg-term-panel p-3 shadow-panel">
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex items-center gap-2">
          <span className={labelCls}>Asset</span>
          <select value={symbol} onChange={e => setSymbol(e.target.value)} className={selectCls}>
            {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <span className={labelCls}>Interval</span>
          <select value={interval} onChange={e => setInterval(e.target.value)} className={selectCls}>
            {INTERVALS.map(i => <option key={i} value={i}>{i}</option>)}
          </select>
        </div>
        {/* Forecast mode + Lookback select the precomputed LIVE forecast variant;
            the backtest is fixed (sampled, lookback 256), so hide them in Replay. */}
        {view === 'live' && (
          <>
            <div className="flex items-center gap-2">
              <span className={labelCls}>Forecast</span>
              <select value={fmode} onChange={e => setFmode(e.target.value)} className={selectCls}>
                <option value="sampled">Probabilistic</option>
                <option value="deterministic">Deterministic</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <span className={labelCls}>Lookback</span>
              <select value={lookback} onChange={e => setLookback(Number(e.target.value))} className={selectCls}>
                <option value={256}>256</option>
                <option value={512}>512</option>
              </select>
            </div>
          </>
        )}
        <div className="flex items-center gap-2">
          <span className={labelCls}>Mode</span>
          <div className="flex overflow-hidden rounded-sm border border-term-border">
            {(['live', 'replay'] as const).map(v => (
              <button key={v} onClick={() => setView(v)}
                className={`px-2.5 py-1 font-mono text-xs ${view === v ? 'bg-term-accent text-term-bg' : 'bg-term-bg text-term-muted hover:text-term-text'}`}>
                {v === 'live' ? 'Live' : 'Replay'}
              </button>
            ))}
          </div>
        </div>
        <span className="ml-auto font-mono text-xs text-term-muted">{count} candles</span>
      </div>

      <div className="relative h-[440px] w-full">
        <div ref={containerRef} className="absolute inset-0" />

        {legend && (
          <div className="pointer-events-none absolute left-2 top-2 z-10 flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-xs">
            <span className="flex items-center gap-1.5 font-semibold text-term-text">
              <CoinIcon symbol={symbol} size={14} />{symbol}
            </span>
            <span className="text-term-muted">{legend.time}</span>
            <span className="text-term-muted">O <span className="text-term-text">{fmtPrice(legend.open)}</span></span>
            <span className="text-term-muted">H <span className="text-term-text">{fmtPrice(legend.high)}</span></span>
            <span className="text-term-muted">L <span className="text-term-text">{fmtPrice(legend.low)}</span></span>
            <span className="text-term-muted">C <span className={legend.up ? 'text-term-up' : 'text-term-down'}>{fmtPrice(legend.close)}</span></span>
            <span className={legend.up ? 'text-term-up' : 'text-term-down'}>{changePct(legend)}</span>
            <span className="text-term-muted">Vol <span className="text-term-text">{fmtVol(legend.volume)}</span></span>
          </div>
        )}

        {loading && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-term-panel/60 font-mono text-sm text-term-muted">
            Loading…
          </div>
        )}
        {!loading && count === 0 && (
          <div className="absolute inset-0 flex items-center justify-center font-mono text-sm text-term-muted">
            No data available
          </div>
        )}
      </div>

      {view === 'replay' && !replaySupported && (
        <div className="mt-2 font-mono text-[11px] text-term-muted">Backtest available for 1h / 1d.</div>
      )}
      {view === 'replay' && replaySupported && replay && replay.anchors.length > 0 && (() => {
        const a = replay.anchors[Math.min(anchorIdx, replay.anchors.length - 1)];
        return (
          <div className="mt-2">
            <div className="flex items-center gap-3 font-mono text-[11px]">
              <button className="px-2 text-term-muted hover:text-term-text"
                onClick={() => setAnchorIdx(i => Math.max(0, i - 1))}>◀</button>
              <input type="range" min={0} max={replay.anchors.length - 1} value={anchorIdx}
                onChange={e => setAnchorIdx(Number(e.target.value))} className="flex-1 accent-term-accent" />
              <button className="px-2 text-term-muted hover:text-term-text"
                onClick={() => setAnchorIdx(i => Math.min(replay.anchors.length - 1, i + 1))}>▶</button>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-4 font-mono text-[11px]">
              <span className="text-term-muted">forecast @ {a.anchor_time_utc.slice(0, 16).replace('T', ' ')}</span>
              <span className={a.dir ? 'text-term-up' : 'text-term-down'}>dir {a.dir ? '✓' : '✗'}</span>
              <span className="text-term-muted">MAPE <span className="text-term-text">{(a.mape * 100).toFixed(2)}%</span></span>
              <span className="text-term-muted">in-band <span className="text-term-text">{(a.coverage * 100).toFixed(0)}%</span></span>
            </div>
            <BacktestStrip m={metrics} />
          </div>
        );
      })()}

      {hasForecast && (
        <div className="mt-2 flex items-center gap-2 font-mono text-[11px] text-term-accent/80">
          <span className="inline-block h-0 w-4 border-t-2 border-dashed border-term-accent" />
          Kronos forecast (dashed){fmode === 'sampled' ? ' · shaded uncertainty band' : ' · most-likely path'} — experimental, not financial advice.
        </div>
      )}
    </div>
  );
}
