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
    """Each pass returns a distinct constant close (100, 101, ...) so we can verify
    the quantile band. Records the last sample_logits flag it was called with."""

    def __init__(self) -> None:
        self.calls = 0
        self.last_sample_logits = None

    def predict_batch(self, df_list, x_timestamp_list, y_timestamp_list, pred_len, **kwargs):
        self.last_sample_logits = kwargs.get("sample_logits", True)
        base = 100.0 + self.calls
        out = []
        for y_ts in y_timestamp_list:
            out.append(
                pd.DataFrame(
                    {
                        "open": [base] * pred_len, "high": [base] * pred_len, "low": [base] * pred_len,
                        "close": [base] * pred_len, "volume": [10.0] * pred_len, "amount": [1000.0] * pred_len,
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
        extra = timedelta(microseconds=597000) if i % 2 else timedelta()  # mixed precision
        ts = (start + timedelta(minutes=delta_min * i) + extra).isoformat()
        rows.append({
            "source": "binance", "symbol": "BTCUSDT", "base_asset": "BTC", "quote_asset": "USDT",
            "interval": interval, "open_time_utc": ts, "close_time_utc": ts,
            "open": 100.0 + i, "high": 105.0 + i, "low": 95.0 + i, "close": 102.0 + i,
            "volume": 1000.0, "quote_volume": 100000.0, "trade_count": 500, "ingestion_time_utc": ts,
        })
    pl.DataFrame(rows).write_parquet(str(market / "candles.parquet"))


def _base(monkeypatch):
    monkeypatch.setattr(settings, "default_symbols", "BTCUSDT")
    monkeypatch.setattr(settings, "prediction_intervals", "1h")
    monkeypatch.setattr(settings, "prediction_horizons", "1h:3")
    monkeypatch.setattr(settings, "prediction_lookbacks", "10")


def test_sampled_band_and_dims(tmp_path, monkeypatch):
    _base(monkeypatch)
    monkeypatch.setattr(settings, "prediction_modes", "sampled")
    monkeypatch.setattr(settings, "prediction_sample_count", 5)
    monkeypatch.setattr(settings, "prediction_band_low", 0.1)
    monkeypatch.setattr(settings, "prediction_band_high", 0.9)
    monkeypatch.setattr(settings, "prediction_band_scales", "")  # isolate from calibration widening
    monkeypatch.setattr(predictions, "get_predictor", lambda: _StubPredictor())
    _seed_silver(tmp_path / "silver")

    df = compute_price_predictions(tmp_path / "silver")

    assert df.height == 3
    assert df["mode"].unique().to_list() == ["sampled"]
    assert df["lookback"].unique().to_list() == [10]
    for r in df.iter_rows(named=True):
        assert r["pred_close"] == pytest.approx(102.0)  # median of [100..104]
        assert r["pred_close_low"] > 100.0   # 10th percentile, not the min
        assert r["pred_close_high"] < 104.0  # 90th percentile, not the max


def test_band_scale_widens_band(tmp_path, monkeypatch):
    """A per-interval band scale widens the band around the central path (the
    empirical calibration to ~80% coverage)."""
    _base(monkeypatch)
    monkeypatch.setattr(settings, "prediction_modes", "sampled")
    monkeypatch.setattr(settings, "prediction_sample_count", 5)
    monkeypatch.setattr(settings, "prediction_band_low", 0.1)
    monkeypatch.setattr(settings, "prediction_band_high", 0.9)
    monkeypatch.setattr(settings, "prediction_band_scales", "1h:5.0")  # 5x widening
    monkeypatch.setattr(predictions, "get_predictor", lambda: _StubPredictor())
    _seed_silver(tmp_path / "silver")

    df = compute_price_predictions(tmp_path / "silver")

    for r in df.iter_rows(named=True):
        central = r["pred_close"]
        assert central == pytest.approx(102.0)
        # raw 10/90 percentiles of [100..104] are 100.4 / 103.6; widened 5x around 102
        assert r["pred_close_low"] == pytest.approx(102.0 - 5 * (102.0 - 100.4))   # 94.0
        assert r["pred_close_high"] == pytest.approx(102.0 + 5 * (103.6 - 102.0))  # 110.0
        assert r["pred_close_low"] < central < r["pred_close_high"]


def test_deterministic_mode_no_band(tmp_path, monkeypatch):
    _base(monkeypatch)
    monkeypatch.setattr(settings, "prediction_modes", "deterministic")
    stub = _StubPredictor()
    monkeypatch.setattr(predictions, "get_predictor", lambda: stub)
    _seed_silver(tmp_path / "silver")

    df = compute_price_predictions(tmp_path / "silver")

    assert df.height == 3
    assert df["mode"].unique().to_list() == ["deterministic"]
    assert stub.last_sample_logits is False  # greedy decode was requested
    for r in df.iter_rows(named=True):
        assert r["pred_close_low"] == r["pred_close"] == r["pred_close_high"]  # no band


def test_covers_modes_and_lookbacks(tmp_path, monkeypatch):
    _base(monkeypatch)
    monkeypatch.setattr(settings, "prediction_horizons", "1h:2")
    monkeypatch.setattr(settings, "prediction_lookbacks", "8,10")
    monkeypatch.setattr(settings, "prediction_modes", "sampled,deterministic")
    monkeypatch.setattr(settings, "prediction_sample_count", 3)
    monkeypatch.setattr(predictions, "get_predictor", lambda: _StubPredictor())
    _seed_silver(tmp_path / "silver")

    df = compute_price_predictions(tmp_path / "silver")

    combos = {(r["mode"], r["lookback"]) for r in df.iter_rows(named=True)}
    assert combos == {("sampled", 8), ("sampled", 10), ("deterministic", 8), ("deterministic", 10)}


def test_covers_all_intervals(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "default_symbols", "BTCUSDT")
    monkeypatch.setattr(settings, "prediction_intervals", "5m,1h")
    monkeypatch.setattr(settings, "prediction_horizons", "5m:2,1h:3")
    monkeypatch.setattr(settings, "prediction_lookbacks", "10")
    monkeypatch.setattr(settings, "prediction_modes", "sampled")
    monkeypatch.setattr(settings, "prediction_sample_count", 3)
    monkeypatch.setattr(predictions, "get_predictor", lambda: _StubPredictor())
    silver = tmp_path / "silver"
    _seed_silver(silver, interval="1h", delta_min=60)
    _seed_silver(silver, interval="5m", delta_min=5)

    df = compute_price_predictions(silver)

    assert set(df["interval"].unique().to_list()) == {"5m", "1h"}
    assert df.filter(pl.col("interval") == "5m").height == 2
    assert df.filter(pl.col("interval") == "1h").height == 3


def _seed_predictions_gold(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "lakehouse_root", str(tmp_path))
    monkeypatch.setattr(settings, "duckdb_path", str(tmp_path / "test.duckdb"))
    gdir = settings.gold_path / "asset_price_predictions"
    gdir.mkdir(parents=True)
    rows = [{
        "symbol": "BTCUSDT", "interval": "1h", "mode": "sampled", "lookback": 256,
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
    assert body["mode"] == "sampled"      # default
    assert body["lookback"] == 256        # default
    assert body["count"] == 3
    assert [row["step"] for row in body["data"]] == [1, 2, 3]
    assert body["data"][0]["pred_close"] == 101.0


def test_forecast_endpoint_rejects_unknown_symbol(tmp_path, monkeypatch):
    _seed_predictions_gold(monkeypatch, tmp_path)
    from app.main import app

    with TestClient(app) as client:
        resp = client.get("/predictions/forecast?symbol=DOGEUSDT&interval=1h")

    assert resp.status_code == 400
