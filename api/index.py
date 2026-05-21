import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from mangum import Mangum

from app.main import app
from app.core.config import settings

for d in [
    settings.bronze_path,
    settings.silver_path / "market_candles",
    settings.gold_path / "asset_daily_metrics",
    settings.gold_path / "asset_intraday_metrics",
    settings.gold_path / "portfolio_positions",
    settings.gold_path / "portfolio_exposures",
    settings.gold_path / "data_quality_breaks",
    settings.duckdb_db_path.parent,
]:
    d.mkdir(parents=True, exist_ok=True)

handler = Mangum(app)
