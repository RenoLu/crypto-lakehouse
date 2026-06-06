from fastapi import APIRouter, HTTPException, Query

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
) -> PredictionResponse:
    if symbol not in VALID_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Invalid symbol. Must be one of {sorted(VALID_SYMBOLS)}")
    if interval not in VALID_INTERVALS:
        raise HTTPException(status_code=400, detail=f"Invalid interval. Must be one of {sorted(VALID_INTERVALS)}")

    sql = """
        SELECT symbol, interval, generated_at_utc, forecast_time_utc, step,
               pred_open, pred_high, pred_low, pred_close, pred_volume,
               pred_close_low, pred_close_high
        FROM v_asset_price_predictions
        WHERE symbol = :symbol AND interval = :interval
        ORDER BY forecast_time_utc
    """
    try:
        with DuckDBRepo() as repo:
            rows = repo.query(sql, {"symbol": symbol, "interval": interval})
    except Exception as e:
        # The view/parquet may not exist yet (predictions not generated). Treat as empty.
        logger.warning(f"Forecast query failed (predictions may be ungenerated): {e}")
        rows = []

    generated = rows[0]["generated_at_utc"] if rows else None
    return PredictionResponse(
        symbol=symbol,
        interval=interval,
        count=len(rows),
        generated_at_utc=generated,
        data=rows,
    )
