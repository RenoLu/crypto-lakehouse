from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.core.logging import logger
from app.data.duckdb_repo import DuckDBRepo
from app.models.api_models import PredictionResponse

router = APIRouter(tags=["predictions"])

VALID_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
VALID_INTERVALS = {"1m", "5m", "1h", "1d"}


@router.get("/predictions/forecast", response_model=PredictionResponse)
def get_forecast(
    symbol: str = Query(..., description="Trading pair symbol, e.g. BTCUSDT"),
    interval: str = Query("1h", description="Forecast interval: 1m, 5m, 1h, 1d"),
    mode: str = Query("sampled", description="Forecast mode: sampled (band) or deterministic"),
    lookback: int = Query(256, description="History window the model conditioned on"),
) -> PredictionResponse:
    if symbol not in VALID_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Invalid symbol. Must be one of {sorted(VALID_SYMBOLS)}")
    if interval not in VALID_INTERVALS:
        raise HTTPException(status_code=400, detail=f"Invalid interval. Must be one of {sorted(VALID_INTERVALS)}")

    valid_modes = set(settings.prediction_mode_list) or {"sampled", "deterministic"}
    if mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Must be one of {sorted(valid_modes)}")
    valid_lookbacks = set(settings.prediction_lookback_list) or {256, 512}
    if lookback not in valid_lookbacks:
        raise HTTPException(status_code=400, detail=f"Invalid lookback. Must be one of {sorted(valid_lookbacks)}")

    sql = """
        SELECT symbol, interval, mode, lookback, generated_at_utc, forecast_time_utc, step,
               pred_open, pred_high, pred_low, pred_close, pred_volume,
               pred_close_low, pred_close_high
        FROM v_asset_price_predictions
        WHERE symbol = :symbol AND interval = :interval AND mode = :mode AND lookback = :lookback
        ORDER BY forecast_time_utc
    """
    try:
        with DuckDBRepo() as repo:
            rows = repo.query(sql, {"symbol": symbol, "interval": interval, "mode": mode, "lookback": lookback})
    except Exception as e:
        # The view/parquet may not exist yet (predictions not generated). Treat as empty.
        logger.warning(f"Forecast query failed (predictions may be ungenerated): {e}")
        rows = []

    generated = rows[0]["generated_at_utc"] if rows else None
    return PredictionResponse(
        symbol=symbol,
        interval=interval,
        mode=mode,
        lookback=lookback,
        count=len(rows),
        generated_at_utc=generated,
        data=rows,
    )
