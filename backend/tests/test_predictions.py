from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings

# Prediction tests exercise predictions.py, which imports pandas/numpy from the
# optional [predict] extra. Skip the whole module cleanly on a base install.
pytest.importorskip("pandas")

import pandas as pd  # noqa: E402
from app.data import predictions  # noqa: E402
from app.data.predictions import PREDICTION_SCHEMA, compute_price_predictions  # noqa: E402


class _StubPredictor:
    """Stand-in for KronosPredictor. Each pass returns a distinct constant close
    (100, 101, 102, ...) so we can verify the quantile band over many samples."""

    def __init__(self) -> None:
        self.calls = 0

    def predict_batch(self, df_list, x_timestamp_list, y_timestamp_list, pred_len, **kwargs):
        base = 100.0 + self.calls
        out = []
        for y_ts in y_timestamp_list:
            out.append(
                pd.DataFrame(
                    {
                        "open": [base] * pred_len,
                        "high": [base] * pred_len,
                        "low": [base] * pred_len,
                        "close": [base] * pred_len,
                        "volume": [10.0] * pred_len,
                        "amount": [1000.0] * pred_len,
                    },
                    index=pd.Index(list(y_ts)),
                )
            )
        self.calls += 1
        return out


def _seed_silver(root: Path, interval: str = "1h", delta_min: int = 60, n: int = 12) -> None:
    market = root / "market_candles" / "source=binance" / "symbol=BTCUSDT" / f"interval={interval}" / "date=2025-01-01"
    market.mkdir(parents=True)
    start = datetime(2025, 1, 1, tzinfo=UTC)
    rows = []
    for i in range(n):
        # Mixed-precision ISO timestamps (some with microseconds, some without),
        # as the synthetic generator produces — must still parse.
        extra = timedelta(microseconds=597000) if i % 2 else timedelta()
        ts = (start + timedelta(minutes=delta_min * i) + extra).isoformat()
        rows.append({
            "source": "binance", "symbol": "BTCUSDT", "base_asset": "BTC", "quote_asset": "USDT",
            "interval": interval, "open_time_utc": ts, "close_time_utc": ts,
            "open": 100.0 + i, "high": 105.0 + i, "low": 95.0 + i, "close": 102.0 + i,
            "volume": 1000.0, "quote_volume": 100000.0, "trade_count": 500,
            "ingestion_time_utc": ts,
        })
    pl.DataFrame(rows).write_parquet(str(market / "candles.parquet"))


def test_compute_price_predictions_percentile_band(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "default_symbols", "BTCUSDT")
    monkeypatch.setattr(settings, "prediction_intervals", "1h")
    monkeypatch.setattr(settings, "prediction_horizons", "1h:3")
    monkeypatch.setattr(settings, "prediction_lookback", 10)
    monkeypatch.setattr(settings, "prediction_sample_count", 5)  # closes -> [100..104]
    monkeypatch.setattr(settings, "prediction_band_low", 0.1)
    monkeypatch.setattr(settings, "prediction_band_high", 0.9)
    monkeypatch.setattr(predictions, "get_predictor", lambda: _StubPredictor())

    silver_root = tmp_path / "silver"
    _seed_silver(silver_root)

    df = compute_price_predictions(silver_root)

    assert df.height == 3  # 1 symbol x 1 interval x horizon
    expected = {
        "symbol", "interval", "generated_at_utc", "forecast_time_utc", "step",
        "pred_open", "pred_high", "pred_low", "pred_close", "pred_volume",
        "pred_close_low", "pred_close_high",
    }
    assert expected.issubset(set(df.columns))
    assert df["step"].to_list() == [1, 2, 3]

    for r in df.iter_rows(named=True):
        # Central = median of [100..104] = 102.
        assert r["pred_close"] == pytest.approx(102.0)
        assert r["pred_close_low"] <= r["pred_close"] <= r["pred_close_high"]
        # Band uses the 10th/90th percentile, NOT the raw min/max — so it sits
        # strictly inside [100, 104] (this is what fails on the old min/max code).
        assert r["pred_close_low"] > 100.0
        assert r["pred_close_high"] < 104.0

    # forecast timestamps advance by the interval delta, starting after the last bar
    times = pd.to_datetime(df["forecast_time_utc"].to_list(), utc=True)
    assert (times[1] - times[0]) == pd.Timedelta(hours=1)
    assert times[0] > pd.Timestamp("2025-01-01T11:00:00", tz="UTC")


def test_compute_covers_all_configured_intervals(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "default_symbols", "BTCUSDT")
    monkeypatch.setattr(settings, "prediction_intervals", "5m,1h")
    monkeypatch.setattr(settings, "prediction_horizons", "5m:2,1h:3")  # per-interval horizons
    monkeypatch.setattr(settings, "prediction_lookback", 10)
    monkeypatch.setattr(settings, "prediction_sample_count", 3)
    monkeypatch.setattr(predictions, "get_predictor", lambda: _StubPredictor())

    silver_root = tmp_path / "silver"
    _seed_silver(silver_root, interval="1h", delta_min=60)
    _seed_silver(silver_root, interval="5m", delta_min=5)

    df = compute_price_predictions(silver_root)

    assert set(df["interval"].unique().to_list()) == {"5m", "1h"}
    assert df.filter(pl.col("interval") == "5m").height == 2  # per-interval horizon
    assert df.filter(pl.col("interval") == "1h").height == 3


def _seed_predictions_gold(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "lakehouse_root", str(tmp_path))
    monkeypatch.setattr(settings, "duckdb_path", str(tmp_path / "test.duckdb"))
    gdir = settings.gold_path / "asset_price_predictions"
    gdir.mkdir(parents=True)
    rows = [{
        "symbol": "BTCUSDT", "interval": "1h",
        "generated_at_utc": "2025-01-01T12:00:00+00:00",
        "forecast_time_utc": f"2025-01-01T{12 + s}:00:00+00:00", "step": s + 1,
        "pred_open": 100.0, "pred_high": 102.0, "pred_low": 98.0, "pred_close": 101.0 + s,
        "pred_volume": 10.0, "pred_close_low": 100.0 + s, "pred_close_high": 102.0 + s,
    } for s in range(3)]
    pl.DataFrame(rows, schema=PREDICTION_SCHEMA).write_parquet(str(gdir / "asset_price_predictions.parquet"))


def test_forecast_endpoint_returns_seeded_predictions(tmp_path, monkeypatch):
    _seed_predictions_gold(monkeypatch, tmp_path)
    from app.main import app

    with TestClient(app) as client:
        resp = client.get("/predictions/forecast?symbol=BTCUSDT&interval=1h")

    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "BTCUSDT"
    assert body["interval"] == "1h"
    assert body["count"] == 3
    assert body["generated_at_utc"] == "2025-01-01T12:00:00+00:00"
    assert [row["step"] for row in body["data"]] == [1, 2, 3]
    assert body["data"][0]["pred_close"] == 101.0


def test_forecast_endpoint_rejects_unknown_symbol(tmp_path, monkeypatch):
    _seed_predictions_gold(monkeypatch, tmp_path)
    from app.main import app

    with TestClient(app) as client:
        resp = client.get("/predictions/forecast?symbol=DOGEUSDT&interval=1h")

    assert resp.status_code == 400
