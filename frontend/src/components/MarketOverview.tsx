import { useEffect, useState } from 'react';
import { getCandles, getQualityBreaks } from '../api/client';
import { TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react';

interface PriceCard {
  symbol: string;
  label: string;
  price: number | null;
  change: number | null;
}

export default function MarketOverview() {
  const [prices, setPrices] = useState<PriceCard[]>([
    { symbol: 'BTCUSDT', label: 'BTC', price: null, change: null },
    { symbol: 'ETHUSDT', label: 'ETH', price: null, change: null },
    { symbol: 'SOLUSDT', label: 'SOL', price: null, change: null },
  ]);
  const [qualityBreaks, setQualityBreaks] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const results = await Promise.allSettled(
          prices.map(p => getCandles(p.symbol, '1d', 2))
        );

        const updated = prices.map((p, i) => {
          const result = results[i];
          if (result.status === 'fulfilled' && result.value.data.length > 0) {
            const latest = result.value.data[result.value.data.length - 1];
            const prev = result.value.data.length > 1 ? result.value.data[result.value.data.length - 2] : null;
            const change = prev ? ((latest.close - prev.close) / prev.close) * 100 : null;
            return { ...p, price: latest.close, change };
          }
          return p;
        });
        setPrices(updated);
      } catch {
        // Prices will remain null
      }

      try {
        const breaks = await getQualityBreaks();
        setQualityBreaks(breaks.length);
      } catch {
        // Quality breaks will remain 0
      }

      setLoading(false);
    }
    loadData();
  }, []);

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
      {prices.map(p => (
        <div key={p.symbol} className="rounded-lg border border-gray-800 bg-gray-900 p-4">
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold text-white">{p.label}</span>
            {p.change !== null && (
              <span className={`text-xs font-medium ${p.change >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {p.change >= 0 ? <TrendingUp className="inline h-3 w-3" /> : <TrendingDown className="inline h-3 w-3" />}
                {p.change >= 0 ? '+' : ''}{p.change?.toFixed(2)}%
              </span>
            )}
          </div>
          <div className="mt-2 text-2xl font-bold text-white">
            {loading ? (
              <span className="text-gray-600">--</span>
            ) : p.price ? (
              `$${p.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
            ) : (
              <span className="text-gray-600">N/A</span>
            )}
          </div>
        </div>
      ))}

      <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold text-white">Quality</span>
          {qualityBreaks > 0 ? (
            <AlertTriangle className="h-4 w-4 text-yellow-400" />
          ) : (
            <span className="h-2 w-2 rounded-full bg-green-400" />
          )}
        </div>
        <div className="mt-2 text-2xl font-bold text-white">
          {loading ? <span className="text-gray-600">--</span> : qualityBreaks}
        </div>
        <div className="text-xs text-gray-400">breaks</div>
      </div>
    </div>
  );
}
