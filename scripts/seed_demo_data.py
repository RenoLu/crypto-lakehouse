#!/usr/bin/env python3
"""Seed demo portfolio data."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from rich.console import Console

from app.data.seed_portfolio import seed_portfolio, write_portfolio_positions

console = Console()


def main() -> None:
    console.print("[bold green]=== Seeding Demo Portfolio ===[/bold green]")

    df = seed_portfolio()
    write_portfolio_positions(df)

    console.print(f"\n[bold green]Seeded {len(df)} positions[/bold green]")
    for row in df.iter_rows(named=True):
        console.print(f"  {row['symbol']}: {row['quantity']} {row['asset_name']}")


if __name__ == "__main__":
    main()
