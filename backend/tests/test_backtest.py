import numpy as np
import polars as pl
import pytest

pd = pytest.importorskip("pandas")  # part of the [predict] extra
from app.data import backtest as bt


def test_select_anchors_respects_bounds_and_count():
    # 1000 bars, lookback 256, horizon 24 -> valid t in [256, 976]
    anchors = bt.select_anchors(n_bars=1000, lookback=256, horizon=24, n_anchors=96)
    assert len(anchors) == 96
    assert anchors == sorted(anchors)
    assert len(set(anchors)) == len(anchors)  # unique
    assert min(anchors) >= 256
    assert max(anchors) <= 1000 - 24


def test_select_anchors_caps_to_available_positions():
    # Only a handful of valid positions -> return at most that many, unique.
    anchors = bt.select_anchors(n_bars=260, lookback=256, horizon=2, n_anchors=96)
    assert anchors == [256, 257, 258]


def test_per_anchor_metrics_directional_mape_coverage():
    anchor_close = 100.0
    pred = np.array([101.0, 102.0])     # predicts up
    lo = np.array([100.0, 100.0])
    hi = np.array([103.0, 101.5])       # step 2 actual 104 will be OUT of band
    actual = np.array([101.0, 104.0])   # actually up -> directional correct
    m = bt.per_anchor_metrics(anchor_close, pred, lo, hi, actual)
    assert m["dir"] is True
    # mape = mean(|101-101|/101, |102-104|/104) = mean(0, 0.01923) = 0.009615
    assert m["mape"] == pytest.approx((0 + abs(102 - 104) / 104) / 2, rel=1e-6)
    # coverage: step1 100<=101<=103 True; step2 100<=104<=101.5 False -> 0.5
    assert m["coverage"] == pytest.approx(0.5)


def test_aggregate_metrics_and_horizon_curve():
    # Two anchors, horizon 2.
    per = [
        {"pred": np.array([101.0, 102.0]), "lo": np.array([100.0, 100.0]),
         "hi": np.array([103.0, 103.0]), "actual": np.array([101.0, 102.0]), "anchor_close": 100.0},
        {"pred": np.array([99.0, 98.0]), "lo": np.array([97.0, 97.0]),
         "hi": np.array([101.0, 99.0]), "actual": np.array([99.0, 96.0]), "anchor_close": 100.0},
    ]
    agg, horizon = bt.aggregate_metrics(per)
    assert agg["n_anchors"] == 2
    assert 0.0 <= agg["directional_pct"] <= 1.0
    assert agg["band_nominal"] == pytest.approx(0.8)
    assert [h["step"] for h in horizon] == [1, 2]
    # step1 errors: |101-101|/101=0, |99-99|/99=0 -> mae_pct 0
    assert horizon[0]["mae_pct"] == pytest.approx(0.0)


def _make_silver(tmp_path, symbols=("BTCUSDT",), interval="1h", n=400):
    """Write a tiny silver parquet dataset shaped like market_candles."""
    base = tmp_path / "silver" / "market_candles"
    for sym in symbols:
        d = base / "source=binance" / f"symbol={sym}" / f"interval={interval}" / "date=2026-01-01"
        d.mkdir(parents=True, exist_ok=True)
        ts = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
        price = np.linspace(100, 140, n)
        pl.DataFrame({
            "symbol": [sym] * n, "interval": [interval] * n,
            "open_time_utc": [t.isoformat() for t in ts],
            "open": price, "high": price + 1, "low": price - 1, "close": price,
            "volume": np.full(n, 10.0), "quote_volume": np.full(n, 1000.0), "trade_count": [5] * n,
        }).write_parquet(str(d / "candles.parquet"))
    return tmp_path / "silver"


class _StubPredictor:
    """predict_batch returns, per input df, a horizon-length frame trending up
    from the last close so forecasts are deterministic and torch-free."""
    def predict_batch(self, df_list, x_timestamp_list, y_timestamp_list, pred_len, **kw):
        out = []
        for df in df_list:
            last = float(df["close"].iloc[-1])
            vals = np.array([last * (1 + 0.001 * (i + 1)) for i in range(pred_len)])
            out.append(pd.DataFrame({"open": vals, "high": vals, "low": vals, "close": vals,
                                     "volume": np.full(pred_len, 10.0)}))
        return out


def test_compute_backtest_produces_three_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(bt, "get_predictor", lambda: _StubPredictor())
    monkeypatch.setattr(bt.settings, "backtest_intervals", "1h")
    monkeypatch.setattr(bt.settings, "default_symbols", "BTCUSDT")
    monkeypatch.setattr(bt.settings, "backtest_anchors", 10)
    monkeypatch.setattr(bt.settings, "backtest_lookback", 256)
    monkeypatch.setattr(bt.settings, "backtest_sample_count", 2)

    silver = _make_silver(tmp_path, n=400)
    forecasts, metrics, horizon = bt.compute_backtest(silver)

    assert set(forecasts.columns) >= set(bt.FORECASTS_SCHEMA.keys())
    assert metrics.height == 1  # one (symbol, interval)
    row = metrics.row(0, named=True)
    assert 0.0 <= row["directional_pct"] <= 1.0
    assert row["n_anchors"] == 10
    assert horizon.height == int(bt.settings.prediction_horizon_map.get("1h", 24))
    # forecasts carry aligned actuals
    assert forecasts.filter(pl.col("actual_close").is_null()).height == 0
