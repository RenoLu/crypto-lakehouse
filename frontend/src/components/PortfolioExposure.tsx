import { useEffect, useState } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { getPortfolioExposures } from '../api/client';
import type { PortfolioExposure as PortfolioExposureData } from '../api/client';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4'];

export default function PortfolioExposure() {
  const [exposures, setExposures] = useState<PortfolioExposureData[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalNav, setTotalNav] = useState(0);

  useEffect(() => {
    getPortfolioExposures()
      .then(data => {
        setExposures(data);
        if (data.length > 0) setTotalNav(data[0].total_nav);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const pieData = exposures.map(e => ({
    name: e.symbol === 'CASH' ? 'Cash' : e.symbol.replace('USDT', ''),
    value: e.allocation_pct,
  }));

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <h3 className="mb-4 text-lg font-semibold text-white">Portfolio Allocation</h3>

      {loading ? (
        <div className="flex h-[250px] items-center justify-center text-gray-500">Loading...</div>
      ) : pieData.length === 0 ? (
        <div className="flex h-[250px] items-center justify-center text-gray-500">No portfolio data</div>
      ) : (
        <>
          <div className="mb-2 text-sm text-gray-400">
            Total NAV: <span className="font-semibold text-white">${totalNav.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
          </div>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
                label={({ name, value }) => `${name} ${value.toFixed(1)}%`}
              >
                {pieData.map((_, i) => (
                  <Cell key={`cell-${i}`} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
              />
            </PieChart>
          </ResponsiveContainer>

          <div className="mt-2 space-y-1">
            {exposures.map(e => (
              <div key={e.symbol} className="flex items-center justify-between text-sm">
                <span className="text-gray-300">{e.symbol === 'CASH' ? 'Cash' : e.symbol.replace('USDT', '')}</span>
                <span className="text-white font-medium">{e.allocation_pct.toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
