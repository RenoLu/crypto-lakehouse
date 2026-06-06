"""Kronos price forecasting -> gold/asset_price_predictions.

Mirrors the gold_metrics pattern: a compute_* function that reads silver and a
write_gold_* function. Inference is run as a batch job (pipeline / script), never
in the request path. Requires the optional `predict` install extra (torch etc.).

Forecasts are precomputed for each (symbol, interval, mode, lookback) variant so
the read API/UI can select among them without re-running the model.
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
    "mode": pl.Utf8,
    "lookback": pl.Int64,
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
    single interval + lookback — every symbol shares the same horizon, so they can
    be forecast together in one predict_batch call."""
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


def _emit(rows, symbol, interval, mode, lookback, generated_at, y_ts, horizon, o, h, l, c, v, blo, bhi):
    for step in range(horizon):
        rows.append({
            "symbol": symbol, "interval": interval, "mode": mode, "lookback": lookback,
            "generated_at_utc": generated_at,
            "forecast_time_utc": y_ts.iloc[step].isoformat(),
            "step": step + 1,
            "pred_open": float(o[step]), "pred_high": float(h[step]), "pred_low": float(l[step]),
            "pred_close": float(c[step]), "pred_volume": float(v[step]),
            "pred_close_low": float(blo[step]), "pred_close_high": float(bhi[step]),
        })


def compute_price_predictions(silver_root: Path) -> pl.DataFrame:
    """Forecast each (symbol, interval, mode, lookback) variant. `sampled` uses
    low-temperature Monte-Carlo with a median central path + percentile band;
    `deterministic` uses a single greedy (argmax) path with no band."""
    all_files = list((silver_root / "market_candles").rglob("*.parquet"))
    if not all_files:
        logger.warning("No silver parquet files found for predictions")
        return pl.DataFrame(schema=PREDICTION_SCHEMA)

    full = pl.scan_parquet([str(f) for f in all_files]).collect()
    if full.is_empty():
        return pl.DataFrame(schema=PREDICTION_SCHEMA)

    n_samples = max(1, settings.prediction_sample_count)
    temperature = settings.prediction_temperature
    top_p = settings.prediction_top_p
    q_lo = settings.prediction_band_low
    q_hi = settings.prediction_band_high
    horizon_map = settings.prediction_horizon_map
    default_horizon = settings.prediction_horizon
    lookbacks = settings.prediction_lookback_list or [settings.prediction_lookback]
    modes = settings.prediction_mode_list or ["sampled"]

    predictor = get_predictor()
    generated_at = datetime.now(UTC).isoformat()
    rows: list[dict] = []

    for interval in settings.prediction_interval_list:
        horizon = horizon_map.get(interval, default_horizon)
        for lookback in lookbacks:
            metas, x_dfs, x_tss, y_tss = _build_interval_inputs(full, interval, lookback, horizon)
            if not metas:
                continue
            # predict_batch needs equal historical length across the batch.
            common = min(len(x) for x in x_dfs)
            x_dfs = [x.iloc[-common:].reset_index(drop=True) for x in x_dfs]
            x_tss = [t.iloc[-common:].reset_index(drop=True) for t in x_tss]

            for mode in modes:
                if mode == "deterministic":
                    preds = predictor.predict_batch(
                        df_list=x_dfs, x_timestamp_list=x_tss, y_timestamp_list=y_tss,
                        pred_len=horizon, T=temperature, top_k=0, top_p=top_p,
                        sample_count=1, verbose=False, sample_logits=False,
                    )
                    for i, (symbol, _) in enumerate(metas):
                        d = preds[i]
                        c = d["close"].to_numpy()
                        _emit(rows, symbol, interval, mode, lookback, generated_at, y_tss[i], horizon,
                              d["open"].to_numpy(), d["high"].to_numpy(), d["low"].to_numpy(), c,
                              d["volume"].to_numpy(), c, c)  # deterministic -> band == central
                else:  # sampled
                    passes = [
                        predictor.predict_batch(
                            df_list=x_dfs, x_timestamp_list=x_tss, y_timestamp_list=y_tss,
                            pred_len=horizon, T=temperature, top_k=0, top_p=top_p,
                            sample_count=1, verbose=False, sample_logits=True,
                        )
                        for _ in range(n_samples)
                    ]
                    for i, (symbol, _) in enumerate(metas):
                        def stack(col: str, idx=i) -> np.ndarray:
                            return np.stack([passes[p][idx][col].to_numpy() for p in range(n_samples)])

                        closes = stack("close")
                        _emit(rows, symbol, interval, mode, lookback, generated_at, y_tss[i], horizon,
                              np.median(stack("open"), axis=0), np.median(stack("high"), axis=0),
                              np.median(stack("low"), axis=0), np.median(closes, axis=0),
                              np.median(stack("volume"), axis=0),
                              np.quantile(closes, q_lo, axis=0), np.quantile(closes, q_hi, axis=0))
            logger.info(f"{interval} lookback={lookback}: {modes} ({len(metas)} series, horizon {horizon})")

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
