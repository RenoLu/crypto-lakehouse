import { useEffect, useState } from 'react';
import { getQualityBreaks, QualityBreak } from '../api/client';
import { useRefresh } from '../refresh';

const SEV: Record<string, string> = {
  CRITICAL: 'bg-term-down/20 text-term-down border-term-down/40',
  ERROR: 'bg-term-down/10 text-term-down border-term-down/30',
  WARNING: 'bg-term-accent/15 text-term-accent border-term-accent/40',
  INFO: 'bg-blue-500/10 text-blue-300 border-blue-500/30',
};

export default function QualityBreaks() {
  const { tick } = useRefresh();
  const [breaks, setBreaks] = useState<QualityBreak[]>([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getQualityBreaks(filter === 'all' ? undefined : filter)
      .then(setBreaks)
      .catch(() => setBreaks([]))
      .finally(() => setLoading(false));
  }, [filter, tick]);

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <span className="font-mono text-xs uppercase tracking-wider text-term-muted">{breaks.length} breaks</span>
        <select
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="rounded-sm border border-term-border bg-term-bg px-2 py-1 font-mono text-xs text-term-text focus:border-term-accent focus:outline-none"
        >
          <option value="all">all</option>
          <option value="CRITICAL">critical</option>
          <option value="ERROR">error</option>
          <option value="WARNING">warning</option>
          <option value="INFO">info</option>
        </select>
      </div>

      {loading ? (
        <div className="py-8 text-center font-mono text-sm text-term-muted">Loading…</div>
      ) : breaks.length === 0 ? (
        <div className="py-8 text-center font-mono text-sm text-term-muted">No quality breaks ✓</div>
      ) : (
        <div className="max-h-[360px] space-y-1.5 overflow-y-auto pr-1">
          {breaks.map((b, i) => (
            <div key={i} className="rounded-sm border border-term-border bg-term-bg/40 p-2.5">
              <div className="flex items-center gap-2">
                <span className={`rounded-sm border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide ${SEV[b.severity] || 'border-term-border text-term-muted'}`}>
                  {b.severity}
                </span>
                <span className="font-mono text-xs text-term-text">{b.check_name}</span>
                <span className="ml-auto font-mono text-[10px] text-term-muted">{b.symbol}</span>
              </div>
              <p className="mt-1 text-xs text-term-muted">{b.description}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
