import pytest

pytest.importorskip("pandas")
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_replay_unsupported_interval_returns_supported_false():
    r = client.get("/backtest/replay", params={"symbol": "BTCUSDT", "interval": "5m"})
    assert r.status_code == 200
    body = r.json()
    assert body["supported"] is False
    assert body["anchors"] == []


def test_metrics_unsupported_interval_returns_supported_false():
    r = client.get("/backtest/metrics", params={"symbol": "BTCUSDT", "interval": "1m"})
    assert r.status_code == 200
    assert r.json()["supported"] is False


def test_replay_bad_symbol_400():
    r = client.get("/backtest/replay", params={"symbol": "NOPE", "interval": "1h"})
    assert r.status_code == 400


def test_metrics_supported_interval_shape():
    # No backtest parquet in test env -> empty but well-formed, supported True.
    r = client.get("/backtest/metrics", params={"symbol": "BTCUSDT", "interval": "1h"})
    assert r.status_code == 200
    body = r.json()
    assert body["supported"] is True
    assert "directional_pct" in body and "horizon" in body
