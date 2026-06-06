"""Walk-forward backtest of Kronos forecasts -> gold accuracy tables.

Mirrors predictions.py: a compute_* function that reads silver + write_gold_*
functions. Inference runs as a CI batch job, never in the request path. Requires
the `predict` extra (torch). Pure helpers (anchor selection + metric math) are
torch-free and unit-tested directly.
"""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

from app.core.config import settings
from app.core.logging import logger
from app.data.lake_paths import (
    ensure_dir,
    gold_backtest_forecasts_dir,
    gold_backtest_horizon_dir,
    gold_backtest_metrics_dir,
)
from app.data.predictions import INTERVAL_DELTA, PRICE_COLS
from app.ml.kronos_loader import get_predictor

FORECASTS_SCHEMA = {
    "symbol": pl.Utf8, "interval": pl.Utf8, "anchor_id": pl.Int64,
    "anchor_time_utc": pl.Utf8, "anchor_close": pl.Float64,
    "step": pl.Int64, "forecast_time_utc": pl.Utf8,
    "pred_close": pl.Float64, "pred_close_low": pl.Float64, "pred_close_high": pl.Float64,
    "actual_close": pl.Float64,
}
METRICS_SCHEMA = {
    "symbol": pl.Utf8, "interval": pl.Utf8, "n_anchors": pl.Int64,
    "directional_pct": pl.Float64, "mape": pl.Float64,
    "band_coverage": pl.Float64, "band_nominal": pl.Float64,
    "horizon": pl.Int64, "generated_at_utc": pl.Utf8,
}
HORIZON_SCHEMA = {
    "symbol": pl.Utf8, "interval": pl.Utf8, "step": pl.Int64,
    "mae_pct": pl.Float64, "coverage": pl.Float64,
}


def select_anchors(n_bars: int, lookback: int, horizon: int, n_anchors: int) -> list[int]:
    """Evenly spaced anchor indices t where bars[t-lookback:t] (history) and
    bars[t:t+horizon] (future) both exist. t in [lookback, n_bars - horizon]."""
    lo, hi = lookback, n_bars - horizon
    if hi < lo:
        return []
    span = hi - lo
    if n_anchors <= 1:
        return [lo + span // 2]
    if span + 1 <= n_anchors:
        return list(range(lo, hi + 1))
    return sorted({int(round(lo + span * i / (n_anchors - 1))) for i in range(n_anchors)})


def _band_nominal() -> float:
    return round(settings.prediction_band_high - settings.prediction_band_low, 6)


def per_anchor_metrics(anchor_close: float, pred: np.ndarray, lo: np.ndarray,
                       hi: np.ndarray, actual: np.ndarray) -> dict:
    """Directional / MAPE / band-coverage for a single anchor's forecast."""
    dir_correct = bool(np.sign(pred[-1] - anchor_close) == np.sign(actual[-1] - anchor_close))
    mape = float(np.mean(np.abs(pred - actual) / actual))
    coverage = float(np.mean((actual >= lo) & (actual <= hi)))
    return {"dir": dir_correct, "mape": mape, "coverage": coverage}


def aggregate_metrics(per: list[dict]) -> tuple[dict, list[dict]]:
    """Aggregate across anchors. `per` items have arrays pred/lo/hi/actual + anchor_close."""
    if not per:
        return ({"n_anchors": 0, "directional_pct": 0.0, "mape": 0.0,
                 "band_coverage": 0.0, "band_nominal": _band_nominal()}, [])
    dirs, mapes, covs = [], [], []
    horizon = len(per[0]["actual"])
    step_err = [[] for _ in range(horizon)]
    step_cov = [[] for _ in range(horizon)]
    for a in per:
        m = per_anchor_metrics(a["anchor_close"], a["pred"], a["lo"], a["hi"], a["actual"])
        dirs.append(1.0 if m["dir"] else 0.0)
        mapes.append(m["mape"])
        covs.append(m["coverage"])
        for s in range(horizon):
            step_err[s].append(abs(a["pred"][s] - a["actual"][s]) / a["actual"][s])
            step_cov[s].append(1.0 if (a["lo"][s] <= a["actual"][s] <= a["hi"][s]) else 0.0)
    agg = {
        "n_anchors": len(per),
        "directional_pct": float(np.mean(dirs)),
        "mape": float(np.mean(mapes)),
        "band_coverage": float(np.mean(covs)),
        "band_nominal": _band_nominal(),
    }
    horizon_curve = [
        {"step": s + 1, "mae_pct": float(np.mean(step_err[s])), "coverage": float(np.mean(step_cov[s]))}
        for s in range(horizon)
    ]
    return agg, horizon_curve


def _series_anchor_inputs(sdf: pl.DataFrame, interval: str, lookback: int, horizon: int, anchors: list[int]):
    """Build batchable per-anchor inputs + the realized actual_close window."""
    delta = INTERVAL_DELTA[interval]
    x_dfs, x_tss, y_tss, meta = [], [], [], []
    closes = sdf["close"].to_numpy()
    times = sdf["open_time_utc"].to_list()
    for t in anchors:
        hist = sdf.slice(t - lookback, lookback)
        x_dfs.append(hist.select(PRICE_COLS).to_pandas())
        x_ts = pd.Series(pd.to_datetime(hist["open_time_utc"].to_list(), utc=True, format="ISO8601"))
        x_tss.append(x_ts)
        last = x_ts.iloc[-1]
        y_tss.append(pd.Series([last + delta * (i + 1) for i in range(horizon)]))
        meta.append({
            "anchor_id": t, "anchor_time_utc": times[t - 1], "anchor_close": float(closes[t - 1]),
            "actual": closes[t:t + horizon].astype(float),
            "forecast_time_utc": [times[t + i] for i in range(horizon)],
        })
    return x_dfs, x_tss, y_tss, meta


def compute_backtest(silver_root: Path):
    """Walk-forward backtest for each (symbol, interval) in scope. Returns
    (forecasts_df, metrics_df, horizon_df)."""
    all_files = list((silver_root / "market_candles").rglob("*.parquet"))
    if not all_files:
        logger.warning("No silver parquet for backtest")
        return (pl.DataFrame(schema=FORECASTS_SCHEMA),
                pl.DataFrame(schema=METRICS_SCHEMA), pl.DataFrame(schema=HORIZON_SCHEMA))

    full = pl.scan_parquet([str(f) for f in all_files]).collect()
    n_samples = max(1, settings.backtest_sample_count)
    lookback = settings.backtest_lookback
    q_lo, q_hi = settings.prediction_band_low, settings.prediction_band_high
    horizon_map = settings.prediction_horizon_map
    predictor = get_predictor()
    generated_at = datetime.now(UTC).isoformat()

    f_rows, m_rows, h_rows = [], [], []
    for interval in settings.backtest_interval_list:
        horizon = horizon_map.get(interval, settings.prediction_horizon)
        for symbol in settings.symbols:
            sdf = (full.filter((pl.col("symbol") == symbol) & (pl.col("interval") == interval))
                   .sort("open_time_utc"))
            anchors = select_anchors(sdf.height, lookback, horizon, settings.backtest_anchors)
            if not anchors:
                logger.warning(f"No backtest anchors for {symbol}/{interval} ({sdf.height} bars)")
                continue
            x_dfs, x_tss, y_tss, meta = _series_anchor_inputs(sdf, interval, lookback, horizon, anchors)

            passes = [
                predictor.predict_batch(df_list=x_dfs, x_timestamp_list=x_tss, y_timestamp_list=y_tss,
                                        pred_len=horizon, T=settings.prediction_temperature, top_k=0,
                                        top_p=settings.prediction_top_p, sample_count=1,
                                        verbose=False, sample_logits=True)
                for _ in range(n_samples)
            ]

            per = []
            for i, mt in enumerate(meta):
                stack = np.stack([passes[p][i]["close"].to_numpy() for p in range(n_samples)])
                pred = np.median(stack, axis=0)
                lo = np.quantile(stack, q_lo, axis=0)
                hi = np.quantile(stack, q_hi, axis=0)
                per.append({"pred": pred, "lo": lo, "hi": hi, "actual": mt["actual"],
                            "anchor_close": mt["anchor_close"]})
                for s in range(horizon):
                    f_rows.append({
                        "symbol": symbol, "interval": interval, "anchor_id": mt["anchor_id"],
                        "anchor_time_utc": mt["anchor_time_utc"], "anchor_close": mt["anchor_close"],
                        "step": s + 1, "forecast_time_utc": mt["forecast_time_utc"][s],
                        "pred_close": float(pred[s]), "pred_close_low": float(lo[s]),
                        "pred_close_high": float(hi[s]), "actual_close": float(mt["actual"][s]),
                    })

            agg, curve = aggregate_metrics(per)
            m_rows.append({"symbol": symbol, "interval": interval, "horizon": horizon,
                           "generated_at_utc": generated_at, **agg})
            for c in curve:
                h_rows.append({"symbol": symbol, "interval": interval, **c})
            logger.info(f"Backtest {symbol}/{interval}: {len(anchors)} anchors, dir={agg['directional_pct']:.2f}")

    return (pl.DataFrame(f_rows, schema=FORECASTS_SCHEMA),
            pl.DataFrame(m_rows, schema=METRICS_SCHEMA),
            pl.DataFrame(h_rows, schema=HORIZON_SCHEMA))


def _write(df: pl.DataFrame, dir_fn, name: str) -> Path:
    if df.is_empty():
        logger.warning(f"No {name} to write")
        return Path("")
    out = ensure_dir(dir_fn()) / f"{name}.parquet"
    df.write_parquet(str(out))
    logger.info(f"Wrote {out} ({len(df)} rows)")
    return out


def write_gold_backtest(forecasts: pl.DataFrame, metrics: pl.DataFrame, horizon: pl.DataFrame) -> None:
    _write(forecasts, gold_backtest_forecasts_dir, "asset_backtest_forecasts")
    _write(metrics, gold_backtest_metrics_dir, "asset_backtest_metrics")
    _write(horizon, gold_backtest_horizon_dir, "asset_backtest_horizon")
