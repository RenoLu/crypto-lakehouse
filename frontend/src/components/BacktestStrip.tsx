import { BacktestMetrics } from '../api/client';

const pct = (x: number) => `${(x * 100).toFixed(0)}%`;

export default function BacktestStrip({ m }: { m: BacktestMetrics | null }) {
  if (!m || !m.supported || m.n_anchors === 0) return null;
  const maxErr = Math.max(...m.horizon.map(h => h.mae_pct), 1e-9);
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 font-mono text-[11px]">
      <span className="text-term-muted">over {m.n_anchors} backtested forecasts</span>
      <span className="text-term-muted">dir <span className="text-term-text">{pct(m.directional_pct)}</span></span>
      <span className="text-term-muted">MAPE <span className="text-term-text">{(m.mape * 100).toFixed(2)}%</span></span>
      <span className="text-term-muted">
        band <span className="text-term-text">{pct(m.band_coverage)}</span>
        <span className="text-term-muted"> /{pct(m.band_nominal)}</span>
      </span>
      <span className="flex items-end gap-0.5" title="error by horizon">
        {m.horizon.map(h => (
          <span key={h.step} className="w-1 bg-term-accent/70"
                style={{ height: `${4 + (h.mae_pct / maxErr) * 14}px` }} />
        ))}
      </span>
    </div>
  );
}
