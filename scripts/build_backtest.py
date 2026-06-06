#!/usr/bin/env python3
"""Walk-forward backtest of Kronos forecasts -> gold backtest tables.

Requires the `predict` extra (pip install -e ".[predict]"). Heavy: re-runs the
model at many past anchors. Intended for a dedicated CI workflow.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from rich.console import Console

from app.core.config import settings
from app.core.logging import logger
from app.data.backtest import compute_backtest, write_gold_backtest

console = Console()


def main() -> None:
    console.print("[bold green]=== Building Backtest (Kronos walk-forward) ===[/bold green]")
    try:
        forecasts, metrics, horizon = compute_backtest(settings.silver_path)
    except Exception as e:
        console.print(f"[red]Backtest failed:[/red] {e}")
        logger.error(f"Backtest failed: {e}")
        raise
    if metrics.is_empty():
        console.print("[yellow]No backtest produced (insufficient silver data?).[/yellow]")
        return
    write_gold_backtest(forecasts, metrics, horizon)
    console.print(f"[green]Backtest: {forecasts.height} forecast rows, {metrics.height} series[/green]")


if __name__ == "__main__":
    main()
