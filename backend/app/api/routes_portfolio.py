from fastapi import APIRouter, HTTPException

from app.data.duckdb_repo import DuckDBRepo
from app.models.api_models import PortfolioExposure

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio/exposures", response_model=list[PortfolioExposure])
def get_portfolio_exposures() -> list[PortfolioExposure]:
    with DuckDBRepo() as repo:
        sql = """
            SELECT symbol, asset_name, quantity, asset_type, entry_price, entry_date,
                   market_value, allocation_pct, daily_pnl, total_nav, as_of_date
            FROM v_portfolio_exposures
            ORDER BY allocation_pct DESC
        """
        try:
            rows = repo.query(sql)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Query failed: {e}") from e

    exposures = []
    for row in rows:
        exposures.append(PortfolioExposure(
            symbol=row.get("symbol", ""),
            asset_name=row.get("asset_name", ""),
            quantity=float(row.get("quantity", 0) or 0),
            market_value=float(row.get("market_value", 0) or 0),
            allocation_pct=float(row.get("allocation_pct", 0) or 0),
            daily_pnl=float(row.get("daily_pnl", 0) or 0),
            total_nav=float(row.get("total_nav", 0) or 0),
        ))
    return exposures
