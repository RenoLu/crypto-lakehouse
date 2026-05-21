import asyncio
import random
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.logging import logger
from app.data.binance_client import BinanceClient
from app.data.bronze_writer import write_bronze_klines
from app.data.retention import cleanup_old_data, get_dir_size_mb
from app.data.gold_metrics import (
    compute_asset_daily_metrics,
    compute_asset_intraday_metrics,
    compute_portfolio_exposures,
    write_gold_daily_metrics,
    write_gold_intraday_metrics,
    write_gold_portfolio_exposures,
)
from app.data.quality_checks import run_all_checks, write_quality_breaks
from app.data.seed_portfolio import load_portfolio_positions
from app.data.silver_transform import build_silver_for_symbol_interval

SYMBOL_PRICES = {
    "BTCUSDT": {"base": 104000, "volatility": 0.002},
    "ETHUSDT": {"base": 2500, "volatility": 0.0025},
    "SOLUSDT": {"base": 165, "volatility": 0.0035},
}

INTERVAL_MINUTES = {"1m": 1, "5m": 5, "1h": 60, "1d": 1440}


def _generate_incremental_klines(symbol: str, interval: str, count: int = 50) -> list[dict]:
    config = SYMBOL_PRICES.get(symbol, {"base": 1000, "volatility": 0.01})
    minutes = INTERVAL_MINUTES.get(interval, 60)
    vol = config["volatility"]

    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=minutes * count)

    price = config["base"] + random.gauss(0, config["base"] * vol * count)

    klines = []
    for i in range(count):
        ts = start + timedelta(minutes=minutes * i)
        open_time = int(ts.timestamp() * 1000)
        close_time = int((ts + timedelta(minutes=minutes)).timestamp() * 1000)

        change = random.gauss(0, vol)
        o = price
        c = price * (1 + change)
        h = max(o, c) * (1 + abs(random.gauss(0, vol * 0.5)))
        l = min(o, c) * (1 - abs(random.gauss(0, vol * 0.5)))
        volume = random.uniform(100, 10000) * (100000 / max(price, 1))

        klines.append({
            "open_time": open_time,
            "open": f"{o:.2f}",
            "high": f"{h:.2f}",
            "low": f"{l:.2f}",
            "close": f"{c:.2f}",
            "volume": f"{volume:.2f}",
            "close_time": close_time,
            "quote_volume": f"{volume * c:.2f}",
            "trade_count": random.randint(50, 5000),
            "taker_buy_base_volume": f"{volume * 0.55:.2f}",
            "taker_buy_quote_volume": f"{volume * c * 0.55:.2f}",
        })
        price = c

    return klines


async def run_pipeline_once() -> dict:
    symbols = settings.symbols
    intervals = settings.intervals
    limit = settings.candle_limit
    total_records = 0
    errors = []

    for symbol in symbols:
        for interval in intervals:
            try:
                client = BinanceClient()
                try:
                    klines = client.get_klines(symbol, interval, limit=limit)
                    source = "binance"
                finally:
                    client.close()

                if not klines:
                    klines = _generate_incremental_klines(symbol, interval, count=50)
                    source = "synthetic"
            except Exception:
                klines = _generate_incremental_klines(symbol, interval, count=50)
                source = "synthetic"

            if klines:
                request_params = {"symbol": symbol, "interval": interval, "limit": limit, "source": source}
                write_bronze_klines(symbol, interval, klines, request_params)
                total_records += len(klines)

    silver_files = 0
    for symbol in symbols:
        for interval in intervals:
            try:
                output = build_silver_for_symbol_interval(symbol, interval, settings.bronze_path)
                if output and output.exists():
                    silver_files += 1
            except Exception as e:
                errors.append(f"Silver build failed {symbol}/{interval}: {e}")

    daily = compute_asset_daily_metrics(settings.silver_path)
    intraday = compute_asset_intraday_metrics(settings.silver_path)
    positions = load_portfolio_positions()

    gold_writes = 0
    if not daily.is_empty():
        write_gold_daily_metrics(daily)
        gold_writes += 1
    if not intraday.is_empty():
        write_gold_intraday_metrics(intraday)
        gold_writes += 1
    if not daily.is_empty() and not positions.is_empty():
        exposures = compute_portfolio_exposures(daily, positions)
        if not exposures.is_empty():
            write_gold_portfolio_exposures(exposures)
            gold_writes += 1

    breaks = run_all_checks(settings.silver_path)
    write_quality_breaks(breaks)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "records_ingested": total_records,
        "silver_files": silver_files,
        "gold_datasets": gold_writes,
        "quality_breaks": len(breaks),
        "errors": errors[:5],
    }


async def polling_loop(interval_seconds: int = 60) -> None:
    logger.info(f"Background polling started (interval={interval_seconds}s)")
    while True:
        try:
            cleanup = cleanup_old_data(max_size_mb=400.0)
            if cleanup["cleaned"]:
                logger.info(f"Retention cleanup: freed {cleanup['freed_mb']} MB")

            current_size = get_dir_size_mb(settings.lakehouse_path)
            logger.info(f"Storage usage: {current_size:.1f} MB")

            result = await asyncio.to_thread(run_pipeline_once)
            logger.info(
                f"Pipeline complete: {result['records_ingested']} records, "
                f"{result['silver_files']} silver files, "
                f"{result['gold_datasets']} gold datasets, "
                f"{result['quality_breaks']} quality breaks"
            )
            if result["errors"]:
                for err in result["errors"]:
                    logger.warning(f"  Pipeline error: {err}")
        except Exception as e:
            logger.error(f"Background pipeline failed: {e}")

        await asyncio.sleep(interval_seconds)
