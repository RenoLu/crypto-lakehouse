from pathlib import Path

import polars as pl

from app.core.logging import logger
from app.data.lake_paths import (
    ensure_dir,
    gold_daily_metrics_dir,
    gold_intraday_metrics_dir,
    gold_portfolio_exposures_dir,
    gold_portfolio_positions_dir,
)


def compute_asset_daily_metrics(silver_root: Path) -> pl.DataFrame:
    all_files = list((silver_root / "market_candles").rglob("*.parquet"))
    if not all_files:
        logger.warning("No silver parquet files found")
        return pl.DataFrame()

    df = pl.scan_parquet([str(f) for f in all_files]).collect()

    if df.is_empty():
        return df

    df = df.with_columns([
        pl.col("open_time_utc").str.to_datetime("%Y-%m-%dT%H:%M:%S%.f%z").dt.date().alias("date"),
    ])

    daily = df.group_by(["symbol", "date"]).agg([
        pl.col("open").first().alias("open"),
        pl.col("high").max().alias("high"),
        pl.col("low").min().alias("low"),
        pl.col("close").last().alias("close"),
        pl.col("volume").sum().alias("volume"),
        pl.col("quote_volume").sum().alias("quote_volume"),
        pl.col("trade_count").sum().alias("trade_count"),
    ])

    daily = daily.sort(["symbol", "date"])

    daily = daily.with_columns([
        (pl.col("close") / pl.col("close").shift(1).over("symbol") - 1).alias("daily_return"),
        (pl.col("high") - pl.col("low")).alias("high_low_range"),
        (pl.col("volume") * pl.col("close")).alias("dollar_volume"),
    ])

    daily = daily.with_columns([
        pl.col("daily_return").rolling_std(window_size=7, min_samples=1).over("symbol").alias("volatility_7d"),
        pl.col("daily_return").rolling_std(window_size=30, min_samples=1).over("symbol").alias("volatility_30d"),
        pl.col("close").rolling_mean(window_size=7).over("symbol").alias("sma_7"),
        pl.col("close").rolling_mean(window_size=30).over("symbol").alias("sma_30"),
    ])

    daily = daily.with_columns([
        (pl.col("close") / pl.col("close").cum_max().over("symbol") - 1).alias("drawdown"),
    ])

    daily = daily.with_columns([
        pl.when(pl.col("volume") > 0)
        .then(pl.col("quote_volume") / pl.col("volume"))
        .otherwise(pl.col("close"))
        .alias("vwap_approx"),
    ])

    daily = daily.with_columns([
        pl.when(pl.col("volume") > 0)
        .then(pl.col("volume") / pl.col("volume").rolling_mean(window_size=7).over("symbol"))
        .otherwise(0.0)
        .alias("liquidity_proxy"),
    ])

    for col in ["daily_return", "volatility_7d", "volatility_30d", "drawdown"]:
        daily = daily.with_columns([
            pl.col(col).fill_nan(None),
        ])

    return daily


def compute_asset_intraday_metrics(silver_root: Path) -> pl.DataFrame:
    all_files = list((silver_root / "market_candles").rglob("*.parquet"))
    if not all_files:
        return pl.DataFrame()

    df = pl.scan_parquet([str(f) for f in all_files]).collect()
    if df.is_empty():
        return df

    df = df.with_columns([
        pl.col("open_time_utc").str.to_datetime("%Y-%m-%dT%H:%M:%S%.f%z").alias("open_time"),
    ])

    intraday = df.with_columns([
        ((pl.col("high") - pl.col("low")) / pl.col("low") * 100).alias("intraday_range_pct"),
        ((pl.col("close") - pl.col("open")) / pl.col("open") * 100).alias("intraday_return_pct"),
        (pl.col("volume") * pl.col("close")).alias("dollar_volume"),
    ])

    return intraday


def compute_portfolio_exposures(
    daily_metrics: pl.DataFrame,
    portfolio_positions: pl.DataFrame,
) -> pl.DataFrame:
    if daily_metrics.is_empty() or portfolio_positions.is_empty():
        return pl.DataFrame()

    latest_date = daily_metrics["date"].max()
    latest = daily_metrics.filter(pl.col("date") == latest_date)

    merged = portfolio_positions.join(
        latest.select(["symbol", "close", "daily_return"]),
        on="symbol",
        how="left",
    )

    merged = merged.with_columns([
        pl.when(pl.col("symbol") == "CASH")
        .then(pl.col("quantity"))
        .otherwise(pl.col("quantity") * pl.col("close").fill_null(1.0))
        .alias("market_value"),
    ])

    merged = merged.with_columns([
        pl.when(pl.col("symbol") == "CASH")
        .then(0.0)
        .otherwise(pl.col("daily_return").fill_null(0.0))
        .alias("daily_return"),
    ])

    total_nav = merged["market_value"].sum()
    if total_nav > 0:
        merged = merged.with_columns([
            (pl.col("market_value") / total_nav * 100).alias("allocation_pct"),
            (pl.col("market_value") * pl.col("daily_return")).alias("daily_pnl"),
        ])

    merged = merged.with_columns([
        pl.lit(total_nav).alias("total_nav"),
        pl.lit(latest_date.isoformat() if latest_date else None).alias("as_of_date"),
    ])

    return merged


def write_gold_daily_metrics(df: pl.DataFrame) -> Path:
    if df.is_empty():
        logger.warning("No daily metrics to write")
        return Path("")

    target_dir = ensure_dir(gold_daily_metrics_dir())
    output_path = target_dir / "asset_daily_metrics.parquet"
    df.write_parquet(str(output_path))
    logger.info(f"Wrote gold daily metrics: {output_path} ({len(df)} rows)")
    return output_path


def write_gold_intraday_metrics(df: pl.DataFrame) -> Path:
    if df.is_empty():
        return Path("")

    target_dir = ensure_dir(gold_intraday_metrics_dir())
    output_path = target_dir / "asset_intraday_metrics.parquet"
    df.write_parquet(str(output_path))
    logger.info(f"Wrote gold intraday metrics: {output_path} ({len(df)} rows)")
    return output_path


def write_gold_portfolio_positions(df: pl.DataFrame) -> Path:
    if df.is_empty():
        return Path("")

    target_dir = ensure_dir(gold_portfolio_positions_dir())
    output_path = target_dir / "portfolio_positions.parquet"
    df.write_parquet(str(output_path))
    logger.info(f"Wrote gold portfolio positions: {output_path} ({len(df)} rows)")
    return output_path


def write_gold_portfolio_exposures(df: pl.DataFrame) -> Path:
    if df.is_empty():
        return Path("")

    target_dir = ensure_dir(gold_portfolio_exposures_dir())
    output_path = target_dir / "portfolio_exposures.parquet"
    df.write_parquet(str(output_path))
    logger.info(f"Wrote gold portfolio exposures: {output_path} ({len(df)} rows)")
    return output_path
