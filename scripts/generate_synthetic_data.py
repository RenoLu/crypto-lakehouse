#!/usr/bin/env python3
"""Generate realistic synthetic market data for demo when Binance is unavailable."""

import json
import random
import uuid
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from rich.console import Console

from app.data.bronze_writer import write_bronze_klines
from app.core.logging import logger

console = Console()

SYMBOL_PRICES = {
    "BTCUSDT": {"base": 104000, "volatility": 0.02},
    "ETHUSDT": {"base": 2500, "volatility": 0.025},
    "SOLUSDT": {"base": 165, "volatility": 0.035},
}

INTERVAL_MINUTES = {"1m": 1, "5m": 5, "1h": 60, "1d": 1440}


def generate_klines(symbol: str, interval: str, count: int = 1000) -> list[dict]:
    config = SYMBOL_PRICES[symbol]
    minutes = INTERVAL_MINUTES[interval]
    base = config["base"]
    price = base
    # Treat the configured volatility as a *daily* figure and scale per bar by
    # sqrt-of-time, so a 1m bar moves far less than a 1d bar (realistic), instead
    # of a flat 2% on every interval.
    vol = config["volatility"] * (minutes / 1440.0) ** 0.5
    reversion = 0.01  # mild mean reversion toward base keeps the 1000-step walk bounded

    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=minutes * count)

    klines = []
    for i in range(count):
        ts = start + timedelta(minutes=minutes * i)
        open_time = int(ts.timestamp() * 1000)
        close_time = int((ts + timedelta(minutes=minutes)).timestamp() * 1000)

        drift = reversion * (base - price) / price  # pull back toward base
        change = drift + random.gauss(0, vol)
        o = price
        c = price * (1 + change)
        h = max(o, c) * (1 + abs(random.gauss(0, vol * 0.5)))
        l = min(o, c) * (1 - abs(random.gauss(0, vol * 0.5)))
        volume = random.uniform(100, 10000) * (100000 / price)

        klines.append({
            "open_time": open_time,
            "open": f"{o:.2f}",
            "high": f"{h:.2f}",
            "low": f"{l:.2f}",
            "close": f"{c:.2f}",
            "volume": f"{volume:.2f}",
            "close_time": close_time,
            "quote_volume": f"{volume * c:.2f}",
            "trade_count": random.randint(50, 5000),
            "taker_buy_base_volume": f"{volume * 0.55:.2f}",
            "taker_buy_quote_volume": f"{volume * c * 0.55:.2f}",
        })

        price = c

    return klines


def main() -> None:
    console.print("[bold yellow]=== Generating Synthetic Market Data ===[/bold yellow]")
    console.print("[dim]Binance API is geo-restricted. Using realistic synthetic data.[/dim]\n")

    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    intervals = ["1m", "5m", "1h", "1d"]
    total = 0

    for symbol in symbols:
        for interval in intervals:
            klines = generate_klines(symbol, interval, count=1000)
            request_params = {"symbol": symbol, "interval": interval, "limit": 1000, "source": "synthetic"}
            write_bronze_klines(symbol, interval, klines, request_params)
            total += len(klines)
            console.print(f"  [green]OK[/green] {symbol}/{interval}: {len(klines)} candles")

    console.print(f"\n[bold green]Generated {total} synthetic records[/bold green]")


if __name__ == "__main__":
    main()
