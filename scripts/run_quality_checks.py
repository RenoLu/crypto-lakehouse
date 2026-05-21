#!/usr/bin/env python3
"""Run all data quality checks and persist results."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from rich.console import Console
from rich.table import Table

from app.core.config import settings
from app.core.logging import logger
from app.data.quality_checks import run_all_checks, write_quality_breaks

console = Console()


def main() -> None:
    console.print("[bold green]=== Running Data Quality Checks ===[/bold green]")

    breaks = run_all_checks(settings.silver_path)

    severity_counts = {}
    for b in breaks:
        sev = b["severity"]
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    table = Table(title=f"Quality Results: {len(breaks)} breaks found")
    table.add_column("Severity", style="bold")
    table.add_column("Count")

    for sev in ["CRITICAL", "ERROR", "WARNING", "INFO"]:
        count = severity_counts.get(sev, 0)
        color = {"CRITICAL": "red", "ERROR": "red", "WARNING": "yellow", "INFO": "blue"}.get(sev, "white")
        table.add_row(f"[{color}]{sev}[/{color}]", str(count))

    console.print(table)

    if breaks:
        console.print("\n[bold]Top Breaks:[/bold]")
        for b in breaks[:10]:
            color = {"CRITICAL": "red", "ERROR": "red", "WARNING": "yellow", "INFO": "blue"}.get(b["severity"], "white")
            console.print(f"  [{color}]{b['severity']}[/{color}] {b['check_name']}: {b['description']}")

    output = write_quality_breaks(breaks)
    console.print(f"\n[bold green]Results written to: {output}[/bold green]")

    critical = severity_counts.get("CRITICAL", 0)
    errors = severity_counts.get("ERROR", 0)
    if critical > 0:
        console.print(f"\n[bold red]CRITICAL: {critical} critical breaks require immediate attention[/bold red]")
    elif errors > 0:
        console.print(f"\n[bold yellow]WARNING: {errors} errors found[/bold yellow]")
    else:
        console.print("\n[bold green]All quality checks passed[/bold green]")


if __name__ == "__main__":
    main()
