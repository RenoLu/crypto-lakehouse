from fastapi import APIRouter, HTTPException, Query

from app.data.duckdb_repo import DuckDBRepo
from app.models.api_models import CandleResponse

router = APIRouter(tags=["market-data"])

VALID_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "CASH"}
VALID_INTERVALS = {"1m", "5m", "1h", "1d"}


@router.get("/market/candles", response_model=CandleResponse)
def get_candles(
    symbol: str = Query(..., description="Trading pair symbol, e.g. BTCUSDT"),
    interval: str = Query("1h", description="Candle interval: 1m, 5m, 1h, 1d"),
    limit: int = Query(200, ge=1, le=5000, description="Number of candles to return"),
) -> CandleResponse:
    if symbol not in VALID_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Invalid symbol. Must be one of {sorted(VALID_SYMBOLS)}")
    if interval not in VALID_INTERVALS:
        raise HTTPException(status_code=400, detail=f"Invalid interval. Must be one of {sorted(VALID_INTERVALS)}")

    with DuckDBRepo() as repo:
        sql = """
            SELECT open_time_utc, close_time_utc, open, high, low, close, volume, quote_volume, trade_count
            FROM v_market_candles
            WHERE symbol = :symbol AND interval = :interval
            ORDER BY open_time_utc DESC
            LIMIT :limit
        """
        try:
            rows = repo.query(sql, {"symbol": symbol, "interval": interval, "limit": limit})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Query failed: {e}") from e

    rows.reverse()
    return CandleResponse(
        symbol=symbol,
        interval=interval,
        count=len(rows),
        data=rows,
    )
