import numpy as np
from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.core.logging import logger
from app.data.backtest import per_anchor_metrics
from app.data.duckdb_repo import DuckDBRepo
from app.models.api_models import BacktestMetricsResponse, BacktestReplayResponse

router = APIRouter(tags=["backtest"])

VALID_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}


def _supported(interval: str) -> bool:
    return interval in set(settings.backtest_interval_list)


def _check_symbol(symbol: str) -> None:
    if symbol not in VALID_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Invalid symbol. Must be one of {sorted(VALID_SYMBOLS)}")


@router.get("/backtest/replay", response_model=BacktestReplayResponse)
def get_replay(symbol: str = Query(...), interval: str = Query("1h")) -> BacktestReplayResponse:
    _check_symbol(symbol)
    if not _supported(interval):
        return BacktestReplayResponse(symbol=symbol, interval=interval, supported=False, anchors=[])

    rows = []
    try:
        with DuckDBRepo() as repo:
            rows = repo.query(
                """SELECT anchor_id, anchor_time_utc, anchor_close, step, forecast_time_utc,
                          pred_close, pred_close_low, pred_close_high, actual_close
                   FROM v_asset_backtest_forecasts
                   WHERE symbol = :symbol AND interval = :interval
                   ORDER BY anchor_id, step""",
                {"symbol": symbol, "interval": interval},
            )
            candles = repo.query(
                """SELECT open_time_utc, open, high, low, close
                   FROM v_market_candles WHERE symbol = :symbol AND interval = :interval
                   ORDER BY open_time_utc""",
                {"symbol": symbol, "interval": interval},
            )
    except Exception as e:
        logger.warning(f"Backtest replay query failed (may be ungenerated): {e}")
        return BacktestReplayResponse(symbol=symbol, interval=interval, supported=True, anchors=[])

    by_time = {c["open_time_utc"]: c for c in candles}
    times_sorted = [c["open_time_utc"] for c in candles]
    idx = {t: i for i, t in enumerate(times_sorted)}

    anchors: dict[int, dict] = {}
    for r in rows:
        a = anchors.setdefault(r["anchor_id"], {
            "anchor_id": r["anchor_id"], "anchor_time_utc": r["anchor_time_utc"],
            "anchor_close": r["anchor_close"], "forecast": [], "_pred": [], "_lo": [], "_hi": [], "_act": [],
        })
        a["forecast"].append({"t": r["forecast_time_utc"], "pred": r["pred_close"],
                              "lo": r["pred_close_low"], "hi": r["pred_close_high"]})
        a["_pred"].append(r["pred_close"]); a["_lo"].append(r["pred_close_low"])
        a["_hi"].append(r["pred_close_high"]); a["_act"].append(r["actual_close"])

    horizon = settings.prediction_horizon_map.get(interval, settings.prediction_horizon)
    out = []
    for a in anchors.values():
        m = per_anchor_metrics(a["anchor_close"], np.array(a["_pred"]), np.array(a["_lo"]),
                               np.array(a["_hi"]), np.array(a["_act"]))
        anchor_i = idx.get(a["anchor_time_utc"])
        window = []
        if anchor_i is not None:
            start = max(0, anchor_i - horizon)
            end = min(len(times_sorted), anchor_i + horizon + 1)
            window = [{"t": times_sorted[i], "o": by_time[times_sorted[i]]["open"],
                       "h": by_time[times_sorted[i]]["high"], "l": by_time[times_sorted[i]]["low"],
                       "c": by_time[times_sorted[i]]["close"]} for i in range(start, end)]
        out.append({
            "anchor_id": a["anchor_id"], "anchor_time_utc": a["anchor_time_utc"],
            "anchor_close": a["anchor_close"], "dir": m["dir"], "mape": m["mape"],
            "coverage": m["coverage"], "candles": window, "forecast": a["forecast"],
        })
    out.sort(key=lambda x: x["anchor_id"])
    return BacktestReplayResponse(symbol=symbol, interval=interval, supported=True, anchors=out)


@router.get("/backtest/metrics", response_model=BacktestMetricsResponse)
def get_metrics(symbol: str = Query(...), interval: str = Query("1h")) -> BacktestMetricsResponse:
    _check_symbol(symbol)
    empty = BacktestMetricsResponse(symbol=symbol, interval=interval, supported=_supported(interval),
                                    n_anchors=0, directional_pct=0.0, mape=0.0, band_coverage=0.0,
                                    band_nominal=round(settings.prediction_band_high - settings.prediction_band_low, 6),
                                    horizon=[])
    if not _supported(interval):
        return empty
    try:
        with DuckDBRepo() as repo:
            m = repo.query("""SELECT * FROM v_asset_backtest_metrics
                              WHERE symbol = :symbol AND interval = :interval""",
                           {"symbol": symbol, "interval": interval})
            h = repo.query("""SELECT step, mae_pct, coverage FROM v_asset_backtest_horizon
                              WHERE symbol = :symbol AND interval = :interval ORDER BY step""",
                           {"symbol": symbol, "interval": interval})
    except Exception as e:
        logger.warning(f"Backtest metrics query failed (may be ungenerated): {e}")
        return empty
    if not m:
        return empty
    row = m[0]
    return BacktestMetricsResponse(
        symbol=symbol, interval=interval, supported=True, n_anchors=row["n_anchors"],
        directional_pct=row["directional_pct"], mape=row["mape"], band_coverage=row["band_coverage"],
        band_nominal=row["band_nominal"], horizon=h,
    )
