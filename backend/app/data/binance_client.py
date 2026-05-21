import json
from datetime import UTC, datetime

import httpx

from app.core.config import settings
from app.core.logging import logger

VALID_INTERVALS = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"}


class BinanceClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.binance_base_url
        self.client = httpx.Client(base_url=self.base_url, timeout=30.0)

    def get_klines(self, symbol: str, interval: str, limit: int | None = None) -> list[dict]:
        interval = interval.lower()
        if interval not in VALID_INTERVALS:
            raise ValueError(f"Invalid interval: {interval}. Must be one of {sorted(VALID_INTERVALS)}")

        params: dict[str, str | int] = {"symbol": symbol, "interval": interval}
        if limit:
            params["limit"] = min(limit, settings.candle_limit)

        logger.info(f"Fetching klines: symbol={symbol} interval={interval} limit={params.get('limit')}")
        resp = self.client.get("/api/v3/klines", params=params)
        resp.raise_for_status()

        raw = resp.json()
        klines = []
        for k in raw:
            klines.append({
                "open_time": k[0],
                "open": k[1],
                "high": k[2],
                "low": k[3],
                "close": k[4],
                "volume": k[5],
                "close_time": k[6],
                "quote_volume": k[7],
                "trade_count": k[8],
                "taker_buy_base_volume": k[9],
                "taker_buy_quote_volume": k[10],
            })

        logger.info(f"Received {len(klines)} klines for {symbol}/{interval}")
        return klines

    def get_ticker_24hr(self, symbol: str) -> dict:
        logger.info(f"Fetching 24hr ticker: {symbol}")
        resp = self.client.get("/api/v3/ticker/24hr", params={"symbol": symbol})
        resp.raise_for_status()
        return resp.json()

    def get_exchange_info(self, symbols: list[str] | None = None) -> dict:
        params: dict = {}
        if symbols:
            params["symbols"] = json.dumps(symbols)
        logger.info(f"Fetching exchange info for {len(symbols) if symbols else 'all'} symbols")
        resp = self.client.get("/api/v3/exchangeInfo", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_recent_trades(self, symbol: str, limit: int = 500) -> list[dict]:
        logger.info(f"Fetching recent trades: {symbol}")
        resp = self.client.get("/api/v3/trades", params={"symbol": symbol, "limit": min(limit, 1000)})
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "BinanceClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()


def ms_to_utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)
