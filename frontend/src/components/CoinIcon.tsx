// Inline coin marks (no network, crisp at any size). Accepts "BTC" or "BTCUSDT".
const key = (s: string) => s.replace('USDT', '').toUpperCase();

export default function CoinIcon({
  symbol,
  size = 18,
  className = '',
}: {
  symbol: string;
  size?: number;
  className?: string;
}) {
  const k = key(symbol);

  if (k === 'BTC') {
    return (
      <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden>
        <circle cx="16" cy="16" r="16" fill="#f7931a" />
        <text x="16" y="22" textAnchor="middle" fontSize="18" fontWeight="700" fill="#fff" fontFamily="Arial, sans-serif">₿</text>
      </svg>
    );
  }

  if (k === 'ETH') {
    return (
      <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden>
        <circle cx="16" cy="16" r="16" fill="#627eea" />
        <g fill="#fff">
          <path fillOpacity="0.602" d="M16 4v8.87l7.5 3.35z" />
          <path d="M16 4L8.5 16.22 16 12.87z" />
          <path fillOpacity="0.602" d="M16 21.97V28l7.5-10.38z" />
          <path d="M16 28v-6.03l-7.5-4.35z" />
          <path fillOpacity="0.2" d="M16 20.57l7.5-4.35L16 12.87z" />
          <path fillOpacity="0.602" d="M8.5 16.22l7.5 4.35v-7.7z" />
        </g>
      </svg>
    );
  }

  if (k === 'SOL') {
    return (
      <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden>
        <circle cx="16" cy="16" r="16" fill="#0b0b0f" />
        <g fill="#14f195">
          <polygon points="10,9.5 24,9.5 21,12 7,12" />
          <polygon points="7,14.5 21,14.5 24,17 10,17" />
          <polygon points="10,19.5 24,19.5 21,22 7,22" />
        </g>
      </svg>
    );
  }

  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden>
      <circle cx="16" cy="16" r="16" fill="#334155" />
    </svg>
  );
}
