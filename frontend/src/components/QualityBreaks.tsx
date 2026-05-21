import { useEffect, useState } from 'react';
import { getQualityBreaks, QualityBreak } from '../api/client';

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: 'bg-red-900/50 text-red-300 border-red-700',
  ERROR: 'bg-red-800/30 text-red-400 border-red-800',
  WARNING: 'bg-yellow-800/30 text-yellow-400 border-yellow-700',
  INFO: 'bg-blue-800/30 text-blue-400 border-blue-700',
};

export default function QualityBreaks() {
  const [breaks, setBreaks] = useState<QualityBreak[]>([]);
  const [filter, setFilter] = useState<string>('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getQualityBreaks(filter === 'all' ? undefined : filter)
      .then(data => setBreaks(data))
      .catch(() => setBreaks([]))
      .finally(() => setLoading(false));
  }, [filter]);

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white">Data Quality Breaks</h3>
        <select
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="rounded border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
        >
          <option value="all">All</option>
          <option value="CRITICAL">Critical</option>
          <option value="ERROR">Error</option>
          <option value="WARNING">Warning</option>
          <option value="INFO">Info</option>
        </select>
      </div>

      {loading ? (
        <div className="py-8 text-center text-gray-500">Loading...</div>
      ) : breaks.length === 0 ? (
        <div className="py-8 text-center text-gray-500">No quality breaks found</div>
      ) : (
        <div className="max-h-[400px] overflow-y-auto space-y-2">
          {breaks.map((b, i) => (
            <div key={i} className="rounded border border-gray-700 bg-gray-800/50 p-3">
              <div className="flex items-center gap-2">
                <span className={`rounded border px-2 py-0.5 text-xs font-medium ${SEVERITY_COLORS[b.severity] || 'bg-gray-700 text-gray-300'}`}>
                  {b.severity}
                </span>
                <span className="text-sm font-medium text-gray-200">{b.check_name}</span>
                <span className="ml-auto text-xs text-gray-500">{b.symbol}</span>
              </div>
              <p className="mt-1 text-sm text-gray-400">{b.description}</p>
              <p className="mt-1 text-xs text-gray-500">{b.suggested_action}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
