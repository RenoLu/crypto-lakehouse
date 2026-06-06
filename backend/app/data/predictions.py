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


def _build_series_inputs(silver_root: Path):
    """Return parallel lists (meta, x_df, x_timestamp, y_timestamp) for every
    symbol/interval that has enough history, plus the per-series y timestamps."""
    all_files = list((silver_root / "market_candles").rglob("*.parquet"))
    if not all_files:
        logger.warning("No silver parquet files found for predictions")
        return [], [], [], []

    full = pl.scan_parquet([str(f) for f in all_files]).collect()
    if full.is_empty():
        return [], [], [], []

    horizon = settings.prediction_horizon
    lookback = settings.prediction_lookback

    metas, x_dfs, x_tss, y_tss = [], [], [], []
    for symbol in settings.symbols:
        for interval in settings.prediction_interval_list:
            delta = INTERVAL_DELTA.get(interval)
            if delta is None:
                logger.warning(f"Unsupported prediction interval {interval}; skipping")
                continue

            sdf = (
                full.filter((pl.col("symbol") == symbol) & (pl.col("interval") == interval))
                .sort("open_time_utc")
                .tail(lookback)
            )
            if sdf.height < MIN_HISTORY:
                logger.warning(f"Not enough history for {symbol}/{interval} ({sdf.height} rows); skipping")
                continue

            x_df = sdf.select(PRICE_COLS).to_pandas()
            x_ts = pd.Series(pd.to_datetime(sdf["open_time_utc"].to_list(), utc=True))
            last = x_ts.iloc[-1]
            y_ts = pd.Series([last + delta * (i + 1) for i in range(horizon)])

            metas.append((symbol, interval))
            x_dfs.append(x_df)
            x_tss.append(x_ts)
            y_tss.append(y_ts)

    return metas, x_dfs, x_tss, y_tss


def compute_price_predictions(silver_root: Path) -> pl.DataFrame:
    """Forecast the next `prediction_horizon` bars for each configured
    symbol/interval and return a tidy DataFrame of predictions with an
    uncertainty band derived from independent stochastic passes."""
    metas, x_dfs, x_tss, y_tss = _build_series_inputs(silver_root)
    if not metas:
        return pl.DataFrame(schema=PREDICTION_SCHEMA)

    # predict_batch needs equal historical length across the batch.
    common = min(len(x) for x in x_dfs)
    x_dfs = [x.iloc[-common:].reset_index(drop=True) for x in x_dfs]
    x_tss = [t.iloc[-common:].reset_index(drop=True) for t in x_tss]

    horizon = settings.prediction_horizon
    n_samples = max(1, settings.prediction_sample_count)

    predictor = get_predictor()

    # Run N independent single-sample passes to build a Monte-Carlo band.
    passes = []
    for p in range(n_samples):
        preds = predictor.predict_batch(
            df_list=x_dfs,
            x_timestamp_list=x_tss,
            y_timestamp_list=y_tss,
            pred_len=horizon,
            T=1.0,
            top_k=0,
            top_p=0.9,
            sample_count=1,
            verbose=False,
        )
        passes.append(preds)
        logger.info(f"Prediction pass {p + 1}/{n_samples} complete ({len(metas)} series)")

    generated_at = datetime.now(UTC).isoformat()
    rows = []
    for i, (symbol, interval) in enumerate(metas):
        opens = np.stack([passes[p][i]["open"].to_numpy() for p in range(n_samples)])
        highs = np.stack([passes[p][i]["high"].to_numpy() for p in range(n_samples)])
        lows = np.stack([passes[p][i]["low"].to_numpy() for p in range(n_samples)])
        closes = np.stack([passes[p][i]["close"].to_numpy() for p in range(n_samples)])
        vols = np.stack([passes[p][i]["volume"].to_numpy() for p in range(n_samples)])

        mean_close = closes.mean(axis=0)
        low_close = closes.min(axis=0)
        high_close = closes.max(axis=0)
        y_ts = y_tss[i]

        for step in range(horizon):
            rows.append({
                "symbol": symbol,
                "interval": interval,
                "generated_at_utc": generated_at,
                "forecast_time_utc": y_ts.iloc[step].isoformat(),
                "step": step + 1,
                "pred_open": float(opens[:, step].mean()),
                "pred_high": float(highs[:, step].mean()),
                "pred_low": float(lows[:, step].mean()),
                "pred_close": float(mean_close[step]),
                "pred_volume": float(vols[:, step].mean()),
                "pred_close_low": float(low_close[step]),
                "pred_close_high": float(high_close[step]),
            })

    logger.info(f"Computed {len(rows)} prediction rows for {len(metas)} series")
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
