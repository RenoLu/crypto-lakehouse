#!/usr/bin/env python3
"""Generate Kronos price forecasts and write the gold predictions table.

Requires the optional `predict` install extra (pip install -e ".[predict]").
The first run downloads the Kronos-small weights from the Hugging Face Hub.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from rich.console import Console

from app.core.config import settings
from app.core.logging import logger
from app.data.predictions import compute_price_predictions, write_gold_price_predictions

console = Console()


def main() -> None:
    console.print("[bold green]=== Building Price Predictions (Kronos) ===[/bold green]")

    try:
        df = compute_price_predictions(settings.silver_path)
    except Exception as e:
        console.print(f"[red]Prediction failed:[/red] {e}")
        logger.error(f"Prediction failed: {e}")
        raise

    if df.is_empty():
        console.print("[yellow]No predictions produced (insufficient silver data?).[/yellow]")
        return

    output = write_gold_price_predictions(df)
    n_series = df.select(["symbol", "interval"]).unique().height
    console.print(f"[green]Wrote {len(df)} prediction rows ({n_series} series) to[/green] {output}")


if __name__ == "__main__":
    main()
