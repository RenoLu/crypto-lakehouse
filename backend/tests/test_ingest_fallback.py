"""When live ingestion yields nothing, the pipeline must fall back to synthetic
data so the snapshot/deploy never breaks (all-or-nothing, never a mix)."""

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import ingest_market_data  # noqa: E402
import generate_synthetic_data  # noqa: E402


def test_ingest_falls_back_to_synthetic_on_total_failure(monkeypatch):
    called = {"synthetic": False}

    def fake_synthetic_main():
        called["synthetic"] = True

    def boom(self, *args, **kwargs):
        raise RuntimeError("exchange unreachable / geo-blocked")

    # Force every live fetch to fail and stub the synthetic generator so the
    # test does no network I/O and writes no files.
    monkeypatch.setattr(generate_synthetic_data, "main", fake_synthetic_main)
    monkeypatch.setattr(ingest_market_data.BinanceClient, "get_klines", boom)

    ingest_market_data.main()

    assert called["synthetic"] is True


def test_ingest_does_not_fall_back_when_data_present(monkeypatch):
    called = {"synthetic": False, "written": 0}

    def fake_synthetic_main():
        called["synthetic"] = True

    one_kline = [{
        "open_time": 0, "open": "1", "high": "2", "low": "1", "close": "1.5",
        "volume": "10", "close_time": 1, "quote_volume": "15", "trade_count": 3,
        "taker_buy_base_volume": "5", "taker_buy_quote_volume": "7",
    }]

    monkeypatch.setattr(generate_synthetic_data, "main", fake_synthetic_main)
    monkeypatch.setattr(ingest_market_data.BinanceClient, "get_klines", lambda self, *a, **k: one_kline)
    # Don't touch the real lakehouse on disk.
    monkeypatch.setattr(ingest_market_data, "write_bronze_klines", lambda *a, **k: called.__setitem__("written", called["written"] + 1))

    ingest_market_data.main()

    assert called["synthetic"] is False
    assert called["written"] > 0
