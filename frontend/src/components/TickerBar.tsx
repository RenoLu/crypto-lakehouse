import { useEffect, useRef, useState } from 'react';
import { getCandles, getQualityBreaks } from '../api/client';
import { useRefresh } from '../refresh';
import CoinIcon from './CoinIcon';

const ASSETS = [
  { symbol: 'BTCUSDT', label: 'BTC' },
  { symbol: 'ETHUSDT', label: 'ETH' },
  { symbol: 'SOLUSDT', label: 'SOL' },
];

interface Item {
  label: string;
  price: number | null;
  change: number | null;
  flash?: 'up' | 'down';
}

const fmt = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 2 });

export default function TickerBar() {
  const { tick } = useRefresh();
  const [items, setItems] = useState<Item[]>(ASSETS.map(a => ({ label: a.label, price: null, change: null })));
  const [breaks, setBreaks] = useState<number | null>(null);
  const prevPrices = useRef<Record<string, number>>({});

  useEffect(() => {
    let cancelled = false;
    Promise.all(ASSETS.map(a => getCandles(a.symbol, '1d', 2).catch(() => null))).then(res => {
      if (cancelled) return;
      setItems(ASSETS.map((a, i) => {
        const r = res[i];
        if (r && r.data.length) {
          const last = r.data[r.data.length - 1];
          const prev = r.data.length > 1 ? r.data[r.data.length - 2] : null;
          const change = prev ? ((last.close - prev.close) / prev.close) * 100 : null;
          const seen = prevPrices.current[a.label];
          const flash = seen != null && last.close !== seen ? (last.close > seen ? 'up' : 'down') : undefined;
          prevPrices.current[a.label] = last.close;
          return { label: a.label, price: last.close, change, flash };
        }
        return { label: a.label, price: null, change: null };
      }));
    });
    getQualityBreaks()
      .then(b => { if (!cancelled) setBreaks(b.length); })
      .catch(() => { if (!cancelled) setBreaks(null); });
    return () => { cancelled = true; };
  }, [tick]);

  return (
    <div className="flex flex-wrap items-stretch divide-x divide-term-border overflow-hidden rounded-sm border border-term-border bg-term-panel font-mono shadow-panel">
      {items.map(it => (
        <div key={it.label} className="coin-tile flex min-w-[160px] flex-1 items-center gap-2.5 px-4 py-2.5 transition-colors">
          <CoinIcon symbol={it.label} size={20} className="coin-spin" />
          <span className="text-sm font-semibold text-term-text">{it.label}</span>
          <div className="ml-auto text-right leading-tight">
            <div
              key={`${it.label}-${tick}`}
              className={`inline-block px-1 text-sm text-term-text ${
                it.flash === 'up' ? 'flash-up' : it.flash === 'down' ? 'flash-down' : ''
              }`}
            >
              {it.price != null ? `$${fmt(it.price)}` : '—'}
            </div>
            {it.change != null && (
              <div className={`text-xs ${it.change >= 0 ? 'text-term-up' : 'text-term-down'}`}>
                {it.change >= 0 ? '▲' : '▼'} {it.change >= 0 ? '+' : ''}{it.change.toFixed(2)}%
              </div>
            )}
          </div>
        </div>
      ))}
      <div className="flex min-w-[140px] items-center gap-2.5 px-4 py-2.5">
        <span className="text-sm font-semibold text-term-text">DATA</span>
        <span className={`blip h-1.5 w-1.5 rounded-full ${breaks ? 'bg-term-accent' : 'bg-term-up'}`} />
        <span className="text-sm text-term-text">{breaks == null ? '—' : breaks}</span>
        <span className="text-xs text-term-muted">breaks</span>
      </div>
    </div>
  );
}
