from fastapi import APIRouter, HTTPException, Query

from app.data.duckdb_repo import DuckDBRepo
from app.models.api_models import DailyMetricsResponse

router = APIRouter(tags=["analytics"])


@router.get("/analytics/daily-metrics", response_model=DailyMetricsResponse)
def get_daily_metrics(
    symbol: str = Query(..., description="Asset symbol"),
    limit: int = Query(90, ge=1, le=365, description="Number of days"),
) -> DailyMetricsResponse:
    with DuckDBRepo() as repo:
        sql = f"""
            SELECT symbol, date, open, high, low, close, volume, quote_volume,
                   daily_return, high_low_range, dollar_volume,
                   volatility_7d, volatility_30d, sma_7, sma_30,
                   drawdown, vwap_approx, liquidity_proxy
            FROM v_asset_daily_metrics
            WHERE symbol = '{symbol}'
            ORDER BY date DESC
            LIMIT {limit}
        """
        try:
            rows = repo.query(sql)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Query failed: {e}") from e

    rows.reverse()
    return DailyMetricsResponse(
        symbol=symbol,
        count=len(rows),
        data=rows,
    )
