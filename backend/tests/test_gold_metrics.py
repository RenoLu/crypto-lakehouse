from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from app.data.gold_metrics import compute_asset_daily_metrics


def _make_candle_df() -> pl.DataFrame:
    rows = []
    for day in range(40):
        ts = datetime(2025, 1, 1, tzinfo=UTC)
        from datetime import timedelta
        ts = ts + timedelta(days=day)
        ts_str = ts.isoformat()
        rows.append({
            "source": "binance",
            "symbol": "BTCUSDT",
            "base_asset": "BTC",
            "quote_asset": "USDT",
            "interval": "1d",
            "open_time_utc": ts_str,
            "close_time_utc": ts_str,
            "open": 100.0 + day,
            "high": 105.0 + day,
            "low": 95.0 + day,
            "close": 102.0 + day,
            "volume": 1000.0,
            "quote_volume": 100000.0,
            "trade_count": 500,
            "ingestion_time_utc": ts_str,
        })
    return pl.DataFrame(rows)


def test_daily_metrics_has_expected_columns(tmp_path: Path):
    silver_root = tmp_path / "silver"
    market_dir = silver_root / "market_candles" / "source=binance" / "symbol=BTCUSDT" / "interval=1d" / "date=2025-01-01"
    market_dir.mkdir(parents=True)

    df = _make_candle_df()
    df.write_parquet(str(market_dir / "candles.parquet"))

    result = compute_asset_daily_metrics(silver_root)
    assert not result.is_empty()
    assert "daily_return" in result.columns
    assert "volatility_7d" in result.columns
    assert "sma_7" in result.columns
    assert "sma_30" in result.columns
    assert "drawdown" in result.columns


def test_daily_return_calculation():
    rows = [
        {
            "source": "binance", "symbol": "BTCUSDT", "base_asset": "BTC", "quote_asset": "USDT",
            "interval": "1d", "open_time_utc": "2025-01-01T00:00:00+00:00", "close_time_utc": "2025-01-01T00:00:00+00:00",
            "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0, "volume": 1000.0,
            "quote_volume": 100000.0, "trade_count": 500, "ingestion_time_utc": "2025-01-01T00:00:00+00:00",
        },
        {
            "source": "binance", "symbol": "BTCUSDT", "base_asset": "BTC", "quote_asset": "USDT",
            "interval": "1d", "open_time_utc": "2025-01-02T00:00:00+00:00", "close_time_utc": "2025-01-02T00:00:00+00:00",
            "open": 100.0, "high": 115.0, "low": 98.0, "close": 110.0, "volume": 1000.0,
            "quote_volume": 100000.0, "trade_count": 500, "ingestion_time_utc": "2025-01-02T00:00:00+00:00",
        },
    ]
    pl.DataFrame(rows)

    assert rows[1]["close"] / rows[0]["close"] - 1 == pytest.approx(0.1, rel=1e-6)
