from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from app.core.config import settings
from app.core.logging import logger
from app.data.lake_paths import ensure_dir, gold_quality_breaks_dir

QUALITY_SCHEMA = {
    "check_name": pl.Utf8,
    "severity": pl.Utf8,
    "dataset": pl.Utf8,
    "symbol": pl.Utf8,
    "interval": pl.Utf8,
    "event_time_utc": pl.Utf8,
    "description": pl.Utf8,
    "detected_at_utc": pl.Utf8,
    "suggested_action": pl.Utf8,
}


def _break_row(
    check_name: str,
    severity: str,
    dataset: str,
    symbol: str,
    interval: str,
    event_time: str,
    description: str,
    suggested_action: str,
) -> dict:
    return {
        "check_name": check_name,
        "severity": severity,
        "dataset": dataset,
        "symbol": symbol,
        "interval": interval,
        "event_time_utc": event_time,
        "description": description,
        "detected_at_utc": datetime.now(UTC).isoformat(),
        "suggested_action": suggested_action,
    }


def check_duplicate_candles(df: pl.DataFrame) -> list[dict]:
    breaks = []
    dupes = df.group_by(["symbol", "interval", "open_time_utc"]).agg(pl.len().alias("count")).filter(pl.col("count") > 1)
    for row in dupes.iter_rows(named=True):
        breaks.append(_break_row(
            check_name="duplicate_candle",
            severity="ERROR",
            dataset="silver.market_candles",
            symbol=row["symbol"],
            interval=row["interval"],
            event_time=row["open_time_utc"],
            description=f"Duplicate candle found: {row['count']} records for {row['symbol']}/{row['interval']} at {row['open_time_utc']}",
            suggested_action="Remove duplicate records and re-run silver transform",
        ))
    return breaks


def check_null_ohlcv(df: pl.DataFrame) -> list[dict]:
    breaks = []
    for col in ["open", "high", "low", "close", "volume"]:
        nulls = df.filter(pl.col(col).is_null())
        for row in nulls.iter_rows(named=True):
            breaks.append(_break_row(
                check_name="null_ohlcv",
                severity="CRITICAL",
                dataset="silver.market_candles",
                symbol=row["symbol"],
                interval=row["interval"],
                event_time=row["open_time_utc"],
                description=f"Null value in {col} for {row['symbol']}/{row['interval']} at {row['open_time_utc']}",
                suggested_action="Investigate source data; exclude or backfill if transient",
            ))
    return breaks


def check_negative_prices(df: pl.DataFrame) -> list[dict]:
    breaks = []
    for col in ["open", "high", "low", "close"]:
        neg = df.filter(pl.col(col) < 0)
        for row in neg.iter_rows(named=True):
            breaks.append(_break_row(
                check_name="negative_price",
                severity="CRITICAL",
                dataset="silver.market_candles",
                symbol=row["symbol"],
                interval=row["interval"],
                event_time=row["open_time_utc"],
                description=f"Negative {col}={row[col]} for {row['symbol']}/{row['interval']} at {row['open_time_utc']}",
                suggested_action="Reject record; verify source API response",
            ))
    return breaks


def check_negative_volume(df: pl.DataFrame) -> list[dict]:
    breaks = []
    neg = df.filter(pl.col("volume") < 0)
    for row in neg.iter_rows(named=True):
        breaks.append(_break_row(
            check_name="negative_volume",
            severity="ERROR",
            dataset="silver.market_candles",
            symbol=row["symbol"],
            interval=row["interval"],
            event_time=row["open_time_utc"],
            description=f"Negative volume={row['volume']} for {row['symbol']}/{row['interval']} at {row['open_time_utc']}",
            suggested_action="Reject record; verify source data integrity",
        ))
    return breaks


def check_high_low(df: pl.DataFrame) -> list[dict]:
    breaks = []
    invalid = df.filter(pl.col("high") < pl.col("low"))
    for row in invalid.iter_rows(named=True):
        breaks.append(_break_row(
            check_name="high_less_than_low",
            severity="CRITICAL",
            dataset="silver.market_candles",
            symbol=row["symbol"],
            interval=row["interval"],
            event_time=row["open_time_utc"],
            description=f"High ({row['high']}) < Low ({row['low']}) for {row['symbol']}/{row['interval']} at {row['open_time_utc']}",
            suggested_action="Reject record; data corruption likely",
        ))
    return breaks


def check_open_close_range(df: pl.DataFrame) -> list[dict]:
    breaks = []
    invalid = df.filter(
        (pl.col("open") < pl.col("low")) |
        (pl.col("open") > pl.col("high")) |
        (pl.col("close") < pl.col("low")) |
        (pl.col("close") > pl.col("high"))
    )
    for row in invalid.iter_rows(named=True):
        breaks.append(_break_row(
            check_name="open_close_outside_range",
            severity="ERROR",
            dataset="silver.market_candles",
            symbol=row["symbol"],
            interval=row["interval"],
            event_time=row["open_time_utc"],
            description=f"Open/Close outside High-Low range for {row['symbol']}/{row['interval']} at {row['open_time_utc']}",
            suggested_action="Reject record; verify source data",
        ))
    return breaks


def check_stale_prices(df: pl.DataFrame, threshold_hours: int = 24) -> list[dict]:
    breaks = []
    now = datetime.now(UTC)

    latest = df.group_by("symbol").agg(pl.col("open_time_utc").max().alias("latest"))
    for row in latest.iter_rows(named=True):
        try:
            latest_time = datetime.fromisoformat(row["latest"])
            if latest_time.tzinfo is None:
                latest_time = latest_time.replace(tzinfo=UTC)
            age_hours = (now - latest_time).total_seconds() / 3600
            if age_hours > threshold_hours:
                breaks.append(_break_row(
                    check_name="stale_price",
                    severity="WARNING",
                    dataset="silver.market_candles",
                    symbol=row["symbol"],
                    interval="all",
                    event_time=row["latest"],
                    description=f"Stale price for {row['symbol']}: last data {age_hours:.1f}h ago (threshold: {threshold_hours}h)",
                    suggested_action="Check data ingestion pipeline; verify API connectivity",
                ))
        except (ValueError, TypeError):
            pass
    return breaks


def check_return_outliers(df: pl.DataFrame, threshold: float = 0.5) -> list[dict]:
    breaks = []
    daily = df.with_columns([
        pl.col("open_time_utc").str.to_datetime("%Y-%m-%dT%H:%M:%S%.f%z").dt.date().alias("date"),
    ])

    daily_agg = daily.group_by(["symbol", "date"]).agg([
        pl.col("close").first().alias("open_price"),
        pl.col("close").last().alias("close_price"),
    ])

    daily_agg = daily_agg.with_columns([
        ((pl.col("close_price") / pl.col("open_price")) - 1).alias("daily_return"),
    ])

    outliers = daily_agg.filter(pl.col("daily_return").abs() > threshold)
    for row in outliers.iter_rows(named=True):
        breaks.append(_break_row(
            check_name="return_outlier",
            severity="WARNING",
            dataset="gold.asset_daily_metrics",
            symbol=row["symbol"],
            interval="1d",
            event_time=str(row["date"]),
            description=f"Extreme daily return {row['daily_return']:.2%} for {row['symbol']} on {row['date']}",
            suggested_action="Verify with external source; may indicate flash crash or data error",
        ))
    return breaks


def check_missing_asset_reference(df: pl.DataFrame, valid_symbols: set[str] | None = None) -> list[dict]:
    breaks = []
    symbols = valid_symbols or set(settings.symbols)
    found_symbols = set(df["symbol"].unique().to_list())
    missing = symbols - found_symbols
    for sym in missing:
        breaks.append(_break_row(
            check_name="missing_asset_reference",
            severity="INFO",
            dataset="silver.asset_reference",
            symbol=sym,
            interval="n/a",
            event_time="",
            description=f"No data found for expected symbol {sym}",
            suggested_action="Check if symbol is still active on exchange",
        ))
    return breaks


def run_all_checks(silver_root: Path | None = None) -> list[dict]:
    root = silver_root or settings.silver_path
    all_files = list((root / "market_candles").rglob("*.parquet"))
    if not all_files:
        logger.warning("No silver parquet files found for quality checks")
        return []

    df = pl.scan_parquet([str(f) for f in all_files]).collect()
    if df.is_empty():
        return []

    all_breaks = []
    all_breaks.extend(check_duplicate_candles(df))
    all_breaks.extend(check_null_ohlcv(df))
    all_breaks.extend(check_negative_prices(df))
    all_breaks.extend(check_negative_volume(df))
    all_breaks.extend(check_high_low(df))
    all_breaks.extend(check_open_close_range(df))
    all_breaks.extend(check_stale_prices(df))
    all_breaks.extend(check_return_outliers(df))
    all_breaks.extend(check_missing_asset_reference(df))

    logger.info(f"Quality checks complete: {len(all_breaks)} breaks found")
    return all_breaks


def write_quality_breaks(breaks: list[dict]) -> Path:
    target_dir = ensure_dir(gold_quality_breaks_dir())
    output_path = target_dir / "data_quality_breaks.parquet"

    df = pl.DataFrame(schema=QUALITY_SCHEMA) if not breaks else pl.DataFrame(breaks, schema=QUALITY_SCHEMA)

    df.write_parquet(str(output_path))
    logger.info(f"Wrote quality breaks: {output_path} ({len(breaks)} breaks)")
    return output_path


def load_quality_breaks() -> pl.DataFrame:
    target_dir = gold_quality_breaks_dir()
    files = list(target_dir.glob("*.parquet"))
    if not files:
        return pl.DataFrame(schema=QUALITY_SCHEMA)
    return pl.scan_parquet([str(f) for f in files]).collect()
