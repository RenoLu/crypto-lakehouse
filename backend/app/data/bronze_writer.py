import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.core.logging import logger
from app.data.lake_paths import bronze_kline_dir, ensure_dir


def write_bronze_klines(
    symbol: str,
    interval: str,
    klines: list[dict],
    request_params: dict,
    dt: datetime | None = None,
) -> Path:
    ingestion_time = dt or datetime.now(UTC)
    target_dir = bronze_kline_dir(symbol, interval, ingestion_time.date())
    ensure_dir(target_dir)

    metadata = {
        "source": "binance",
        "endpoint": "/api/v3/klines",
        "symbol": symbol,
        "interval": interval,
        "ingestion_time_utc": ingestion_time.isoformat(),
        "request_params": request_params,
        "response_count": len(klines),
    }

    payload = {
        "metadata": metadata,
        "data": klines,
    }

    part_id = str(uuid.uuid4())[:8]
    output_path = target_dir / f"part-{part_id}.json"

    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)

    logger.info(f"Wrote bronze klines: {output_path} ({len(klines)} records)")
    return output_path


def write_bronze_ticker(
    symbol: str,
    ticker: dict,
    dt: datetime | None = None,
) -> Path:
    ingestion_time = dt or datetime.now(UTC)
    target_dir = settings.bronze_path / "binance" / "ticker" / f"symbol={symbol}" / f"date={ingestion_time.date().isoformat()}"
    ensure_dir(target_dir)

    metadata = {
        "source": "binance",
        "endpoint": "/api/v3/ticker/24hr",
        "symbol": symbol,
        "ingestion_time_utc": ingestion_time.isoformat(),
        "request_params": {"symbol": symbol},
        "response_count": 1,
    }

    payload = {
        "metadata": metadata,
        "data": [ticker],
    }

    part_id = str(uuid.uuid4())[:8]
    output_path = target_dir / f"part-{part_id}.json"

    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)

    logger.info(f"Wrote bronze ticker: {output_path}")
    return output_path


def write_bronze_trades(
    symbol: str,
    trades: list[dict],
    dt: datetime | None = None,
) -> Path:
    ingestion_time = dt or datetime.now(UTC)
    target_dir = settings.bronze_path / "binance" / "trades" / f"symbol={symbol}" / f"date={ingestion_time.date().isoformat()}"
    ensure_dir(target_dir)

    metadata = {
        "source": "binance",
        "endpoint": "/api/v3/trades",
        "symbol": symbol,
        "ingestion_time_utc": ingestion_time.isoformat(),
        "request_params": {"symbol": symbol},
        "response_count": len(trades),
    }

    payload = {
        "metadata": metadata,
        "data": trades,
    }

    part_id = str(uuid.uuid4())[:8]
    output_path = target_dir / f"part-{part_id}.json"

    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)

    logger.info(f"Wrote bronze trades: {output_path} ({len(trades)} records)")
    return output_path


from app.core.config import settings  # noqa: E402
