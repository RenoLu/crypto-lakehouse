const API_BASE = import.meta.env.VITE_API_URL || '';

export interface CandleData {
  open_time_utc: string;
  close_time_utc: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  quote_volume: number;
  trade_count: number;
}

export interface DailyMetric {
  symbol: string;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  quote_volume: number;
  trade_count: number;
  daily_return: number | null;
  high_low_range: number;
  dollar_volume: number;
  volatility_7d: number | null;
  volatility_30d: number | null;
  sma_7: number | null;
  sma_30: number | null;
  drawdown: number | null;
  vwap_approx: number | null;
  liquidity_proxy: number | null;
}

export interface PortfolioExposure {
  symbol: string;
  asset_name: string;
  quantity: number;
  market_value: number;
  allocation_pct: number;
  daily_pnl: number;
  total_nav: number;
}

export interface QualityBreak {
  check_name: string;
  severity: string;
  dataset: string;
  symbol: string;
  interval: string;
  event_time_utc: string;
  description: string;
  detected_at_utc: string;
  suggested_action: string;
}

export interface AssistantResponse {
  question: string;
  answer: string;
  query_used: string;
  rows: Record<string, unknown>[];
  warnings: string[];
}

async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function getHealth() {
  return fetchApi<{ status: string; version: string; timestamp: string }>('/health');
}

export async function getCandles(symbol: string, interval: string = '1h', limit: number = 200) {
  return fetchApi<{ symbol: string; interval: string; count: number; data: CandleData[] }>(
    `/market/candles?symbol=${symbol}&interval=${interval}&limit=${limit}`
  );
}

export async function getDailyMetrics(symbol: string, limit: number = 90) {
  return fetchApi<{ symbol: string; count: number; data: DailyMetric[] }>(
    `/analytics/daily-metrics?symbol=${symbol}&limit=${limit}`
  );
}

export async function getPortfolioExposures() {
  return fetchApi<PortfolioExposure[]>('/portfolio/exposures');
}

export async function getQualityBreaks(severity?: string, symbol?: string) {
  const params = new URLSearchParams();
  if (severity) params.set('severity', severity);
  if (symbol) params.set('symbol', symbol);
  return fetchApi<QualityBreak[]>(`/quality/breaks?${params.toString()}`);
}

export async function askAssistant(question: string) {
  const res = await fetch(`${API_BASE}/assistant/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    throw new Error(`Assistant error: ${res.status}`);
  }
  return res.json() as Promise<AssistantResponse>;
}
