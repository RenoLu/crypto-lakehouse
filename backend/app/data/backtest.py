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
