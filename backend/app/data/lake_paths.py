from datetime import UTC, date, datetime
from pathlib import Path

from app.core.config import settings


def bronze_kline_dir(symbol: str, interval: str, dt: date | None = None) -> Path:
    d = dt or datetime.now(UTC).date()
    return settings.bronze_path / "binance" / "klines" / f"symbol={symbol}" / f"interval={interval}" / f"date={d.isoformat()}"


def silver_symbol_interval_dir(symbol: str, interval: str) -> Path:
    return settings.silver_path / "market_candles" / "source=binance" / f"symbol={symbol}" / f"interval={interval}"


def silver_candles_dir(symbol: str, interval: str, dt: date | None = None) -> Path:
    d = dt or datetime.now(UTC).date()
    return silver_symbol_interval_dir(symbol, interval) / f"date={d.isoformat()}"


def gold_daily_metrics_dir() -> Path:
    return settings.gold_path / "asset_daily_metrics"


def gold_intraday_metrics_dir() -> Path:
    return settings.gold_path / "asset_intraday_metrics"


def gold_portfolio_positions_dir() -> Path:
    return settings.gold_path / "portfolio_positions"


def gold_portfolio_exposures_dir() -> Path:
    return settings.gold_path / "portfolio_exposures"


def gold_quality_breaks_dir() -> Path:
    return settings.gold_path / "data_quality_breaks"


def gold_price_predictions_dir() -> Path:
    return settings.gold_path / "asset_price_predictions"


def gold_asset_reference_path() -> Path:
    return settings.silver_path / "asset_reference" / "asset_reference.parquet"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
