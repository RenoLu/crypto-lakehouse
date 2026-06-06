import numpy as np
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
