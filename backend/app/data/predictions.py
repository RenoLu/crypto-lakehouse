"""Kronos price forecasting -> gold/asset_price_predictions.

Mirrors the gold_metrics pattern: a compute_* function that reads silver and a
write_gold_* function. Inference is run as a batch job (pipeline / script), never
in the request path. Requires the optional `predict` install extra (torch etc.).
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

from app.core.config import settings
from app.core.logging import logger
from app.data.lake_paths import ensure_dir, gold_price_predictions_dir
from app.ml.kronos_loader import get_predictor

PRICE_COLS = ["open", "high", "low", "close", "volume"]

INTERVAL_DELTA = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
}

PREDICTION_SCHEMA = {
    "symbol": pl.Utf8,
    "interval": pl.Utf8,
    "generated_at_utc": pl.Utf8,
    "forecast_time_utc": pl.Utf8,
    "step": pl.Int64,
    "pred_open": pl.Float64,
    "pred_high": pl.Float64,
    "pred_low": pl.Float64,
    "pred_close": pl.Float64,
    "pred_volume": pl.Float64,
    "pred_close_low": pl.Float64,
    "pred_close_high": pl.Float64,
}

MIN_HISTORY = 2  # need at least a couple of bars to normalize/forecast


def _build_interval_inputs(full: pl.DataFrame, interval: str, lookback: int, horizon: int):
    """Build batchable inputs (metas, x_dfs, x_timestamps, y_timestamps) for a
    single interval — every symbol shares the same horizon, so they can be
    forecast together in one predict_batch call."""
    delta = INTERVAL_DELTA.get(interval)
    if delta is None:
        logger.warning(f"Unsupported prediction interval {interval}; skipping")
        return [], [], [], []

    metas, x_dfs, x_tss, y_tss = [], [], [], []
    for symbol in settings.symbols:
        sdf = (
            full.filter((pl.col("symbol") == symbol) & (pl.col("interval") == interval))
            .sort("open_time_utc")
            .tail(lookback)
        )
        if sdf.height < MIN_HISTORY:
            logger.warning(f"Not enough history for {symbol}/{interval} ({sdf.height} rows); skipping")
            continue

        x_df = sdf.select(PRICE_COLS).to_pandas()
        # format="ISO8601" tolerates mixed precision (with/without microseconds)
        x_ts = pd.Series(pd.to_datetime(sdf["open_time_utc"].to_list(), utc=True, format="ISO8601"))
        last = x_ts.iloc[-1]
        y_ts = pd.Series([last + delta * (i + 1) for i in range(horizon)])

        metas.append((symbol, interval))
        x_dfs.append(x_df)
        x_tss.append(x_ts)
        y_tss.append(y_ts)

    return metas, x_dfs, x_tss, y_tss


def compute_price_predictions(silver_root: Path) -> pl.DataFrame:
    """Forecast each configured symbol/interval with Kronos and return a tidy
    DataFrame. Uses low-temperature Monte-Carlo sampling and robust statistics:
    the median for the central path and quantiles for the uncertainty band, so
    the band stays calibrated instead of ballooning on outlier trajectories."""
    all_files = list((silver_root / "market_candles").rglob("*.parquet"))
    if not all_files:
        logger.warning("No silver parquet files found for predictions")
        return pl.DataFrame(schema=PREDICTION_SCHEMA)

    full = pl.scan_parquet([str(f) for f in all_files]).collect()
    if full.is_empty():
        return pl.DataFrame(schema=PREDICTION_SCHEMA)

    lookback = settings.prediction_lookback
    n_samples = max(1, settings.prediction_sample_count)
    temperature = settings.prediction_temperature
    top_p = settings.prediction_top_p
    q_lo = settings.prediction_band_low
    q_hi = settings.prediction_band_high
    horizon_map = settings.prediction_horizon_map
    default_horizon = settings.prediction_horizon

    predictor = get_predictor()
    generated_at = datetime.now(UTC).isoformat()
    rows: list[dict] = []

    # Forecast one interval at a time: same horizon per interval keeps the batch
    # valid and lets each interval use its own (bounded) horizon.
    for interval in settings.prediction_interval_list:
        horizon = horizon_map.get(interval, default_horizon)
        metas, x_dfs, x_tss, y_tss = _build_interval_inputs(full, interval, lookback, horizon)
        if not metas:
            continue

        # predict_batch needs equal historical length across the batch.
        common = min(len(x) for x in x_dfs)
        x_dfs = [x.iloc[-common:].reset_index(drop=True) for x in x_dfs]
        x_tss = [t.iloc[-common:].reset_index(drop=True) for t in x_tss]

        # Monte-Carlo: independent low-temperature single-sample trajectories.
        passes = []
        for _ in range(n_samples):
            passes.append(
                predictor.predict_batch(
                    df_list=x_dfs,
                    x_timestamp_list=x_tss,
                    y_timestamp_list=y_tss,
                    pred_len=horizon,
                    T=temperature,
                    top_k=0,
                    top_p=top_p,
                    sample_count=1,
                    verbose=False,
                )
            )
        logger.info(f"{interval}: {n_samples} samples x {len(metas)} series (horizon {horizon})")

        for i, (symbol, _) in enumerate(metas):
            def stack(col: str) -> np.ndarray:
                return np.stack([passes[p][i][col].to_numpy() for p in range(n_samples)])

            med_open = np.median(stack("open"), axis=0)
            med_high = np.median(stack("high"), axis=0)
            med_low = np.median(stack("low"), axis=0)
            med_vol = np.median(stack("volume"), axis=0)
            closes = stack("close")
            med_close = np.median(closes, axis=0)
            band_low = np.quantile(closes, q_lo, axis=0)
            band_high = np.quantile(closes, q_hi, axis=0)
            y_ts = y_tss[i]

            for step in range(horizon):
                rows.append({
                    "symbol": symbol,
                    "interval": interval,
                    "generated_at_utc": generated_at,
                    "forecast_time_utc": y_ts.iloc[step].isoformat(),
                    "step": step + 1,
                    "pred_open": float(med_open[step]),
                    "pred_high": float(med_high[step]),
                    "pred_low": float(med_low[step]),
                    "pred_close": float(med_close[step]),
                    "pred_volume": float(med_vol[step]),
                    "pred_close_low": float(band_low[step]),
                    "pred_close_high": float(band_high[step]),
                })

    logger.info(f"Computed {len(rows)} prediction rows")
    return pl.DataFrame(rows, schema=PREDICTION_SCHEMA)


def write_gold_price_predictions(df: pl.DataFrame) -> Path:
    if df.is_empty():
        logger.warning("No price predictions to write")
        return Path("")

    target_dir = ensure_dir(gold_price_predictions_dir())
    output_path = target_dir / "asset_price_predictions.parquet"
    df.write_parquet(str(output_path))
    logger.info(f"Wrote gold price predictions: {output_path} ({len(df)} rows)")
    return output_path
