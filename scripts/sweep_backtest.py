#!/usr/bin/env python3
"""Sweep backtest config (lookback x temperature) to find accuracy-boosting
settings for the Kronos forecast.

Heavy: re-runs the walk-forward backtest once per variant (read-only — it does
NOT write the gold tables). Measures the RAW model (band calibration disabled)
so coverage reflects native uncertainty. Prints a comparison table; pick the row
with the best directional / MAPE / coverage and fold it into config defaults.

Run:   PYTHONPATH=backend python scripts/sweep_backtest.py
Tune:  SWEEP_ANCHORS=12  SWEEP_LOOKBACKS=256,512  SWEEP_TEMPS=0.4,0.6,0.8
       (fewer anchors = faster but noisier; each variant is a full backtest pass)
"""

import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from rich.console import Console
from rich.table import Table

from app.core.config import settings
from app.data.backtest import compute_backtest

console = Console()


def main() -> None:
    anchors = int(os.environ.get("SWEEP_ANCHORS", "12"))
    lookbacks = [int(x) for x in os.environ.get("SWEEP_LOOKBACKS", "256,512").split(",")]
    temps = [float(x) for x in os.environ.get("SWEEP_TEMPS", "0.4,0.6,0.8").split(",")]

    # Measure the raw model: disable calibration widening so band_coverage reflects
    # native uncertainty (the lever we're trying to improve), and bound the cost.
    settings.prediction_band_scales = ""
    settings.backtest_anchors = anchors

    console.print(
        f"[bold]Sweep[/bold]: lookbacks={lookbacks} temps={temps} anchors={anchors} "
        f"(scope {settings.backtest_interval_list} x {settings.symbols})"
    )

    results = []
    for lb in lookbacks:
        for t in temps:
            settings.backtest_lookback = lb
            settings.prediction_temperature = t
            console.print(f"[dim]  lookback={lb} T={t} ...[/dim]")
            _, metrics, _ = compute_backtest(settings.silver_path)
            if metrics.is_empty():
                console.print("[yellow]  (no metrics — insufficient data?)[/yellow]")
                continue
            rows = metrics.to_dicts()
            results.append({
                "lookback": lb, "temperature": t,
                "directional": statistics.mean(r["directional_pct"] for r in rows),
                "mape": statistics.mean(r["mape"] for r in rows),
                "coverage": statistics.mean(r["band_coverage"] for r in rows),
            })

    table = Table(title="Backtest config sweep — mean across series (raw band)")
    for col in ("lookback", "temperature", "directional", "MAPE", "band cov (target 0.80)"):
        table.add_column(col, justify="right")
    # Best directional first.
    for r in sorted(results, key=lambda x: -x["directional"]):
        table.add_row(
            str(r["lookback"]), f"{r['temperature']:.1f}",
            f"{r['directional']:.1%}", f"{r['mape']:.2%}", f"{r['coverage']:.2f}",
        )
    console.print(table)
    console.print(
        "[dim]Note: pick by directional + MAPE; coverage tells you how much band "
        "widening (prediction_band_scales) that config still needs to reach 0.80.[/dim]"
    )


if __name__ == "__main__":
    main()
