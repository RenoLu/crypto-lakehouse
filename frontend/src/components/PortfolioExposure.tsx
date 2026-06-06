import { useEffect, useRef, useState } from 'react';
import { getPortfolioExposures } from '../api/client';
import type { PortfolioExposure as PortfolioExposureData } from '../api/client';
import { useRefresh } from '../refresh';

const COLORS = ['#f5a524', '#26d07c', '#3b82f6', '#a855f7', '#f6465d', '#06b6d4'];

const label = (s: string) => (s === 'CASH' ? 'Cash' : s.replace('USDT', ''));

export default function PortfolioExposure() {
  const { tick } = useRefresh();
  const [exposures, setExposures] = useState<PortfolioExposureData[]>([]);
  const [loading, setLoading] = useState(true);
  const prevNav = useRef<number | null>(null);

  useEffect(() => {
    getPortfolioExposures()
      .then(setExposures)
      .catch(() => setExposures([]))
      .finally(() => setLoading(false));
  }, [tick]);

  if (loading) return <div className="py-8 text-center font-mono text-sm text-term-muted">Loading…</div>;
  if (!exposures.length) return <div className="py-8 text-center font-mono text-sm text-term-muted">No portfolio data</div>;

  const nav = exposures[0]?.total_nav ?? 0;
  const navFlash = prevNav.current != null && nav !== prevNav.current ? (nav > prevNav.current ? 'up' : 'down') : '';
  prevNav.current = nav;

  return (
    <div>
      <div className="mb-3 flex items-baseline justify-between">
        <span className="font-mono text-xs uppercase tracking-wider text-term-muted">Total NAV</span>
        <span
          key={`nav-${tick}`}
          className={`px-1 font-mono text-lg font-semibold text-term-text ${
            navFlash === 'up' ? 'flash-up' : navFlash === 'down' ? 'flash-down' : ''
          }`}
        >
          ${nav.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
      </div>

      <div className="mb-4 flex h-2 overflow-hidden rounded-sm bg-term-bg">
        {exposures.map((e, i) => (
          <div
            key={e.symbol}
            className="transition-[width] duration-700 ease-out"
            style={{ width: `${e.allocation_pct}%`, backgroundColor: COLORS[i % COLORS.length] }}
          />
        ))}
      </div>

      <table className="w-full font-mono text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wider text-term-muted">
            <th className="pb-2 font-medium">Asset</th>
            <th className="pb-2 text-right font-medium">Alloc</th>
            <th className="pb-2 text-right font-medium">Value</th>
            <th className="pb-2 text-right font-medium">24h P&L</th>
          </tr>
        </thead>
        <tbody>
          {exposures.map((e, i) => (
            <tr key={e.symbol} className="border-t border-term-border/60">
              <td className="py-1.5 text-term-text">
                <span className="mr-2 inline-block h-2 w-2 rounded-sm align-middle" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                {label(e.symbol)}
              </td>
              <td className="py-1.5 text-right text-term-text">{e.allocation_pct.toFixed(1)}%</td>
              <td className="py-1.5 text-right text-term-text">
                ${e.market_value.toLocaleString('en-US', { maximumFractionDigits: 0 })}
              </td>
              <td className={`py-1.5 text-right ${e.daily_pnl >= 0 ? 'text-term-up' : 'text-term-down'}`}>
                {e.daily_pnl >= 0 ? '+' : ''}{e.daily_pnl.toLocaleString('en-US', { maximumFractionDigits: 0 })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
