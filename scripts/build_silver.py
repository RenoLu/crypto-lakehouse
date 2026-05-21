#!/usr/bin/env python3
"""Transform bronze layer data into silver layer Parquet files."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from rich.console import Console

from app.core.config import settings
from app.core.logging import logger
from app.data.silver_transform import build_silver_for_symbol_interval

console = Console()


def main() -> None:
    console.print("[bold green]=== Building Silver Layer ===[/bold green]")

    symbols = settings.symbols
    intervals = settings.intervals
    total_files = 0

    for symbol in symbols:
        for interval in intervals:
            try:
                output = build_silver_for_symbol_interval(
                    symbol=symbol,
                    interval=interval,
                    bronze_root=settings.bronze_path,
                )
                if output and output.exists():
                    total_files += 1
                    console.print(f"  [green]OK[/green] {symbol}/{interval}: {output}")
                else:
                    console.print(f"  [yellow]SKIP[/yellow] {symbol}/{interval}: no bronze data")
            except Exception as e:
                console.print(f"  [red]FAIL[/red] {symbol}/{interval}: {e}")
                logger.error(f"Failed to build silver for {symbol}/{interval}: {e}")

    console.print(f"\n[bold green]Silver build complete: {total_files} files written[/bold green]")


if __name__ == "__main__":
    main()
