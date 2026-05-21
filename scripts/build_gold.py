#!/usr/bin/env python3
"""Build gold layer analytics metrics from silver data."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from rich.console import Console

from app.core.config import settings
from app.core.logging import logger
from app.data.gold_metrics import (
    compute_asset_daily_metrics,
    compute_asset_intraday_metrics,
    compute_portfolio_exposures,
    write_gold_daily_metrics,
    write_gold_intraday_metrics,
    write_gold_portfolio_exposures,
)
from app.data.seed_portfolio import load_portfolio_positions

console = Console()


def main() -> None:
    console.print("[bold green]=== Building Gold Layer ===[/bold green]")

    console.print("[dim]Computing daily metrics...[/dim]")
    daily = compute_asset_daily_metrics(settings.silver_path)
    if not daily.is_empty():
        write_gold_daily_metrics(daily)
        console.print(f"  [green]OK[/green] Daily metrics: {len(daily)} rows")
    else:
        console.print("  [yellow]SKIP[/yellow] No daily metrics (no silver data)")

    console.print("[dim]Computing intraday metrics...[/dim]")
    intraday = compute_asset_intraday_metrics(settings.silver_path)
    if not intraday.is_empty():
        write_gold_intraday_metrics(intraday)
        console.print(f"  [green]OK[/green] Intraday metrics: {len(intraday)} rows")
    else:
        console.print("  [yellow]SKIP[/yellow] No intraday metrics")

    console.print("[dim]Computing portfolio exposures...[/dim]")
    positions = load_portfolio_positions()
    if not daily.is_empty() and not positions.is_empty():
        exposures = compute_portfolio_exposures(daily, positions)
        if not exposures.is_empty():
            write_gold_portfolio_exposures(exposures)
            console.print(f"  [green]OK[/green] Portfolio exposures: {len(exposures)} rows")
        else:
            console.print("  [yellow]SKIP[/yellow] No exposure data computed")
    else:
        console.print("  [yellow]SKIP[/yellow] Missing daily metrics or positions")

    console.print("\n[bold green]Gold layer build complete[/bold green]")


if __name__ == "__main__":
    main()
