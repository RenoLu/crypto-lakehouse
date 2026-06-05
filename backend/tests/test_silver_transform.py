import json
from datetime import UTC, datetime

import polars as pl

from app.core.config import settings
from app.data.silver_transform import build_silver_for_symbol_interval, transform_klines_to_silver


def _kline(open_time_ms: int, close: str = "105") -> dict:
    return {
        "open_time": open_time_ms,
        "open": "100",
        "high": "110",
        "low": "90",
        "close": close,
        "close_time": open_time_ms + 3_599_999,
        "volume": "1000",
        "quote_volume": "100000",
        "trade_count": 500,
    }


def test_transform_dedupes_duplicate_open_time_candles():
    # Overlapping bronze snapshots produce the same candle multiple times. The
    # silver transform must collapse them to one row per open_time while keeping
    # a genuinely distinct timestamp.
    t0 = 1_735_689_600_000  # 2025-01-01T00:00:00Z
    t1 = 1_735_693_200_000  # 2025-01-01T01:00:00Z
    klines = [_kline(t0, close="105"), _kline(t0, close="106"), _kline(t1)]

    df = transform_klines_to_silver("BTCUSDT", "1h", klines)

    assert df.height == 2
    assert df["open_time_utc"].n_unique() == 2
    # Last occurrence wins (freshest snapshot for a still-forming candle).
    t0_close = df.filter(pl.col("open_time_utc").str.starts_with("2025-01-01T00:00:00"))["close"][0]
    assert t0_close == 106.0


def test_build_silver_is_idempotent_across_run_dates(tmp_path, monkeypatch):
    # Silver is partitioned by run-date, so building the same bronze on two
    # different days must not leave duplicate candles across stale partitions.
    monkeypatch.setattr(settings, "lakehouse_root", str(tmp_path))

    bronze_dir = (
        settings.bronze_path / "binance" / "klines" / "symbol=BTCUSDT" / "interval=1h" / "date=2025-01-01"
    )
    bronze_dir.mkdir(parents=True)
    klines = [_kline(1_735_689_600_000), _kline(1_735_693_200_000)]
    (bronze_dir / "part-1.json").write_text(json.dumps({"data": klines}))

    build_silver_for_symbol_interval("BTCUSDT", "1h", settings.bronze_path, dt=datetime(2025, 1, 1, tzinfo=UTC))
    build_silver_for_symbol_interval("BTCUSDT", "1h", settings.bronze_path, dt=datetime(2025, 1, 2, tzinfo=UTC))

    files = list((settings.silver_path / "market_candles").rglob("*.parquet"))
    df = pl.read_parquet([str(f) for f in files])
    assert df.height == 2
    assert df["open_time_utc"].n_unique() == 2
