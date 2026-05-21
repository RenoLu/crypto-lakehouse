import { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { getCandles, CandleData } from '../api/client';

const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'];
const INTERVALS = ['1m', '5m', '1h', '1d'];

export default function AssetChart() {
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [interval, setInterval] = useState('1h');
  const [data, setData] = useState<CandleData[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    getCandles(symbol, interval, 200)
      .then(res => setData(res.data))
      .catch(() => setData([]))
      .finally(() => setLoading(false));
  }, [symbol, interval]);

  const chartData = data.map(d => ({
    time: d.open_time_utc.slice(0, 16).replace('T', ' '),
    close: d.close,
    high: d.high,
    low: d.low,
    volume: d.volume,
  }));

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

        <span className="ml-auto text-xs text-gray-500">{data.length} candles</span>
      </div>

      {loading ? (
        <div className="flex h-[300px] items-center justify-center text-gray-500">Loading...</div>
      ) : chartData.length === 0 ? (
        <div className="flex h-[300px] items-center justify-center text-gray-500">No data available</div>
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="time" stroke="#6b7280" tick={{ fontSize: 11 }} />
            <YAxis stroke="#6b7280" tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
              labelStyle={{ color: '#9ca3af' }}
            />
            <Legend />
            <Line type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} dot={false} name="Close" />
            <Line type="monotone" dataKey="high" stroke="#10b981" strokeWidth={1} dot={false} name="High" />
            <Line type="monotone" dataKey="low" stroke="#ef4444" strokeWidth={1} dot={false} name="Low" />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
