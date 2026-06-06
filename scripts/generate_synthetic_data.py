#!/usr/bin/env python3
"""Generate realistic synthetic market data for demo when Binance is unavailable.

All intervals for a symbol are derived from a SINGLE underlying 1-minute price
path, then aggregated (OHLC resampling) into 1m/5m/1h/1d bars. This guarantees
the latest price is consistent across every interval — a 1d bar is a true
aggregate of the same minutes that make up the 1h/5m/1m bars, exactly like real
market data.

(Previously each interval was an independent random walk from the same base, so
the "current price" diverged wildly by interval — e.g. 1d ended at ~82k while 1h
sat at ~104k for BTC.)
"""

import sys
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from rich.console import Console

from app.data.bronze_writer import write_bronze_klines

console = Console()

SYMBOL_PRICES = {
    "BTCUSDT": {"base": 104000, "volatility": 0.02},
    "ETHUSDT": {"base": 2500, "volatility": 0.025},
    "SOLUSDT": {"base": 165, "volatility": 0.035},
}

INTERVAL_MINUTES = {"1m": 1, "5m": 5, "1h": 60, "1d": 1440}
BAR_COUNT = 1000          # bars emitted per interval
REVERSION = 0.000004      # per-minute mean reversion toward base; tiny so the
                          # year-long path can still wander a realistic amount


def generate_master_path(symbol: str, length: int) -> list[float]:
    """One minute-resolution price path. Coarser bars aggregate slices of this."""
    config = SYMBOL_PRICES[symbol]
    base = config["base"]
    vol_min = config["volatility"] * (1 / 1440) ** 0.5  # daily vol scaled to 1 min
    price = float(base)
    path: list[float] = []
    for _ in range(length):
        drift = REVERSION * (base - price) / price
        price *= 1 + drift + random.gauss(0, vol_min)
        path.append(price)
    return path


def aggregate_klines(symbol: str, interval: str, master: list[float], now: datetime) -> list[dict]:
    """Resample the tail of the master minute-path into BAR_COUNT OHLC bars."""
    minutes = INTERVAL_MINUTES[interval]
    vol_min = SYMBOL_PRICES[symbol]["volatility"] * (1 / 1440) ** 0.5
    span = BAR_COUNT * minutes
    tail = master[-span:]                      # most recent `span` minutes
    start = now - timedelta(minutes=span)

    klines = []
    for b in range(BAR_COUNT):
        chunk = tail[b * minutes:(b + 1) * minutes]
        ts = start + timedelta(minutes=b * minutes)
        open_time = int(ts.timestamp() * 1000)
        close_time = int((ts + timedelta(minutes=minutes)).timestamp() * 1000)

        o = chunk[0]
        c = chunk[-1]
        hi = max(chunk) * (1 + abs(random.gauss(0, vol_min * 0.3)))
        lo = min(chunk) * (1 - abs(random.gauss(0, vol_min * 0.3)))
        volume = random.uniform(100, 10000) * (100000 / c) * (minutes ** 0.5)

        klines.append({
            "open_time": open_time,
            "open": f"{o:.2f}",
            "high": f"{hi:.2f}",
            "low": f"{lo:.2f}",
            "close": f"{c:.2f}",
            "volume": f"{volume:.2f}",
            "close_time": close_time,
            "quote_volume": f"{volume * c:.2f}",
            "trade_count": random.randint(50, 5000),
            "taker_buy_base_volume": f"{volume * 0.55:.2f}",
            "taker_buy_quote_volume": f"{volume * c * 0.55:.2f}",
        })
    return klines


def main() -> None:
    console.print("[bold yellow]=== Generating Synthetic Market Data ===[/bold yellow]")
    console.print("[dim]One underlying path per symbol -> consistent across intervals.[/dim]\n")

    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    intervals = ["1m", "5m", "1h", "1d"]
    master_length = BAR_COUNT * max(INTERVAL_MINUTES.values())
    now = datetime.now(timezone.utc)
    total = 0

    for symbol in symbols:
        master = generate_master_path(symbol, master_length)
        for interval in intervals:
            klines = aggregate_klines(symbol, interval, master, now)
            request_params = {"symbol": symbol, "interval": interval, "limit": BAR_COUNT, "source": "synthetic"}
            write_bronze_klines(symbol, interval, klines, request_params)
            total += len(klines)
            console.print(
                f"  [green]OK[/green] {symbol}/{interval}: {len(klines)} candles "
                f"(last close ~{float(klines[-1]['close']):,.2f})"
            )

    console.print(f"\n[bold green]Generated {total} synthetic records[/bold green]")


if __name__ == "__main__":
    main()
