import polars as pl

from app.data.quality_checks import (
    check_duplicate_candles,
    check_high_low,
    check_negative_prices,
    check_open_close_range,
    check_return_outliers,
    check_stale_prices,
)


def _make_candle(symbol: str = "BTCUSDT", interval: str = "1h", open_time: str = "2025-01-01T00:00:00+00:00",
                 o: float = 100.0, h: float = 110.0, lo: float = 90.0, c: float = 105.0, v: float = 1000.0) -> dict:
    return {
        "source": "binance",
        "symbol": symbol,
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "interval": interval,
        "open_time_utc": open_time,
        "close_time_utc": "2025-01-01T01:00:00+00:00",
        "open": o,
        "high": h,
        "low": lo,
        "close": c,
        "volume": v,
        "quote_volume": v * 100.0,
        "trade_count": 500,
        "ingestion_time_utc": "2025-01-01T00:00:00+00:00",
    }


def test_duplicate_candles_detected():
    rows = [
        _make_candle(open_time="2025-01-01T00:00:00+00:00"),
        _make_candle(open_time="2025-01-01T00:00:00+00:00"),
        _make_candle(open_time="2025-01-01T01:00:00+00:00"),
    ]
    df = pl.DataFrame(rows)
    breaks = check_duplicate_candles(df)
    assert len(breaks) == 1
    assert breaks[0]["check_name"] == "duplicate_candle"
    assert breaks[0]["severity"] == "ERROR"


def test_no_duplicate_candles():
    rows = [
        _make_candle(open_time="2025-01-01T00:00:00+00:00"),
        _make_candle(open_time="2025-01-01T01:00:00+00:00"),
    ]
    df = pl.DataFrame(rows)
    breaks = check_duplicate_candles(df)
    assert len(breaks) == 0


def test_negative_prices_detected():
    rows = [_make_candle(o=-50.0, h=110.0, lo=90.0, c=105.0)]
    df = pl.DataFrame(rows)
    breaks = check_negative_prices(df)
    assert len(breaks) == 1
    assert breaks[0]["check_name"] == "negative_price"
    assert breaks[0]["severity"] == "CRITICAL"


def test_high_less_than_low_detected():
    rows = [_make_candle(o=100.0, h=90.0, lo=110.0, c=105.0)]
    df = pl.DataFrame(rows)
    breaks = check_high_low(df)
    assert len(breaks) == 1
    assert breaks[0]["check_name"] == "high_less_than_low"


def test_open_close_outside_range():
    rows = [_make_candle(o=80.0, h=110.0, lo=90.0, c=105.0)]
    df = pl.DataFrame(rows)
    breaks = check_open_close_range(df)
    assert len(breaks) == 1
    assert breaks[0]["check_name"] == "open_close_outside_range"


def test_stale_prices_detected():
    rows = [
        _make_candle(symbol="BTCUSDT", open_time="2020-01-01T00:00:00+00:00"),
        _make_candle(symbol="ETHUSDT", open_time="2025-01-01T00:00:00+00:00"),
    ]
    df = pl.DataFrame(rows)
    breaks = check_stale_prices(df, threshold_hours=24)
    stale_breaks = [b for b in breaks if b["check_name"] == "stale_price"]
    assert len(stale_breaks) >= 1
    symbols_stale = [b["symbol"] for b in stale_breaks]
    assert "BTCUSDT" in symbols_stale


def test_return_outliers_detected():
    rows = [
        _make_candle(symbol="BTCUSDT", open_time="2025-01-01T00:00:00+00:00", o=100.0, c=100.0),
        _make_candle(symbol="BTCUSDT", open_time="2025-01-01T01:00:00+00:00", o=100.0, c=200.0),
    ]
    df = pl.DataFrame(rows)
    breaks = check_return_outliers(df, threshold=0.5)
    assert len(breaks) >= 1
    assert breaks[0]["check_name"] == "return_outlier"
