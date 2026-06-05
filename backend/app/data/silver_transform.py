import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from app.core.logging import logger
from app.data.lake_paths import ensure_dir, silver_candles_dir, silver_symbol_interval_dir


def transform_klines_to_silver(
    symbol: str,
    interval: str,
    klines: list[dict],
    ingestion_time: datetime | None = None,
) -> pl.DataFrame:
    ing_time = ingestion_time or datetime.now(UTC)

    base = symbol.replace("USDT", "")
    quote = "USDT"

    rows = []
    for k in klines:
        open_time_ms = int(k["open_time"])
        close_time_ms = int(k["close_time"])

        rows.append({
            "source": "binance",
            "symbol": symbol,
            "base_asset": base,
            "quote_asset": quote,
            "interval": interval,
            "open_time_utc": datetime.fromtimestamp(open_time_ms / 1000, tz=UTC).isoformat(),
            "close_time_utc": datetime.fromtimestamp(close_time_ms / 1000, tz=UTC).isoformat(),
            "open": float(k["open"]),
            "high": float(k["high"]),
            "low": float(k["low"]),
            "close": float(k["close"]),
            "volume": float(k["volume"]),
            "quote_volume": float(k["quote_volume"]),
            "trade_count": int(k["trade_count"]),
            "ingestion_time_utc": ing_time.isoformat(),
        })

    df = pl.DataFrame(rows, schema={
        "source": pl.Utf8,
        "symbol": pl.Utf8,
        "base_asset": pl.Utf8,
        "quote_asset": pl.Utf8,
        "interval": pl.Utf8,
        "open_time_utc": pl.Utf8,
        "close_time_utc": pl.Utf8,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Float64,
        "quote_volume": pl.Float64,
        "trade_count": pl.Int64,
        "ingestion_time_utc": pl.Utf8,
    })

    # Overlapping bronze snapshots (each ingest re-fetches the same recent window)
    # produce duplicate candles. Silver is the conformed layer, so collapse to one
    # row per candle, keeping the freshest ingestion. This keeps the build idempotent.
    df = (
        df.sort("ingestion_time_utc")
        .unique(subset=["symbol", "interval", "open_time_utc"], keep="last", maintain_order=True)
        .sort("open_time_utc")
    )

    return df


def write_silver_candles(
    symbol: str,
    interval: str,
    df: pl.DataFrame,
    dt: datetime | None = None,
) -> Path:
    if df.is_empty():
        logger.warning("No data to write for silver candles")
        return Path("")

    target_dir = silver_candles_dir(symbol, interval, dt.date() if dt else None)
    ensure_dir(target_dir)

    output_path = target_dir / "candles.parquet"
    df.write_parquet(str(output_path))

    logger.info(f"Wrote silver candles: {output_path} ({len(df)} rows)")
    return output_path


def load_bronze_klines(bronze_root: Path, symbol: str, interval: str) -> list[dict]:
    pattern = f"symbol={symbol}/interval={interval}"
    search_path = bronze_root / "binance" / "klines"

    all_klines = []
    for json_file in sorted(search_path.rglob("part-*.json")):
        normalized = str(json_file).replace("\\", "/")
        if pattern not in normalized:
            continue
        with open(json_file) as f:
            payload = json.load(f)
        all_klines.extend(payload.get("data", []))

    logger.info(f"Loaded {len(all_klines)} bronze klines for {symbol}/{interval}")
    return all_klines


def build_silver_for_symbol_interval(
    symbol: str,
    interval: str,
    bronze_root: Path,
    dt: datetime | None = None,
) -> Path:
    klines = load_bronze_klines(bronze_root, symbol, interval)
    if not klines:
        logger.warning(f"No bronze data found for {symbol}/{interval}")
        return Path("")

    df = transform_klines_to_silver(symbol, interval, klines, ingestion_time=dt)

    # Silver is fully derived from bronze. Clear any prior silver for this
    # symbol/interval (including stale run-date partitions) so each rebuild
    # produces one deduplicated snapshot instead of accumulating duplicates.
    shutil.rmtree(silver_symbol_interval_dir(symbol, interval), ignore_errors=True)

    return write_silver_candles(symbol, interval, df, dt=dt)
