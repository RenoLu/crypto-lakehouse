#!/usr/bin/env python3
"""Ingest market data from Binance public endpoints into the bronze layer."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from datetime import datetime, timezone

from rich.console import Console

from app.core.config import settings
from app.core.logging import logger
from app.data.binance_client import BinanceClient
from app.data.bronze_writer import write_bronze_klines

console = Console()


def main() -> None:
    console.print("[bold green]=== Market Data Ingestion ===[/bold green]")

    symbols = settings.symbols
    intervals = settings.intervals
    limit = settings.candle_limit

    console.print(f"Symbols: {symbols}")
    console.print(f"Intervals: {intervals}")
    console.print(f"Limit per request: {limit}")

    total_records = 0

    with BinanceClient() as client:
        for symbol in symbols:
            for interval in intervals:
                try:
                    klines = client.get_klines(symbol, interval, limit=limit)
                    if klines:
                        request_params = {"symbol": symbol, "interval": interval, "limit": limit}
                        write_bronze_klines(symbol, interval, klines, request_params)
                        total_records += len(klines)
                        console.print(f"  [green]OK[/green] {symbol}/{interval}: {len(klines)} candles")
                    else:
                        console.print(f"  [yellow]EMPTY[/yellow] {symbol}/{interval}: no data")
                except Exception as e:
                    console.print(f"  [red]FAIL[/red] {symbol}/{interval}: {e}")
                    logger.error(f"Failed to ingest {symbol}/{interval}: {e}")

    if total_records == 0:
        # Total outage (exchange unreachable / IP geo-blocked). Fall back to the
        # synthetic generator so the snapshot stays internally consistent
        # (all-or-nothing: never mix real + synthetic across intervals).
        console.print(
            "[bold red]No live data ingested[/bold red] "
            f"(base_url={settings.binance_base_url}). Falling back to synthetic data."
        )
        logger.warning("Live ingestion returned 0 records; using synthetic fallback")
        import generate_synthetic_data

        generate_synthetic_data.main()
        return

    console.print(f"\n[bold green]Ingestion complete: {total_records} total records[/bold green]")


if __name__ == "__main__":
    main()
