# Backtesting & Model Accuracy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a walk-forward backtest that re-runs Kronos at past anchor points, stores forecasts + accuracy metrics as gold tables, and surfaces a "Replay" mode on the main chart (past forecast vs. realized) plus an aggregate accuracy strip.

**Architecture:** A CI script (`build_backtest.py`) → `compute_backtest()` reads silver candles, picks ~96 anchors per (symbol, interval), batch-forecasts each with the existing Kronos path, and writes three gold parquet tables (`asset_backtest_forecasts`, `asset_backtest_metrics`, `asset_backtest_horizon`). DuckDB views expose them; `routes_backtest.py` serves `/backtest/replay` (per-anchor forecast + realized candle window from silver) and `/backtest/metrics` (aggregate scorecard). The frontend `AssetChart` gains a Live|Replay toggle, an anchor scrubber, and a `BacktestStrip` aggregate readout. Inference is precomputed and served read-only (Render can't run torch).

**Tech Stack:** Python 3.14, polars, duckdb, numpy/pandas, torch (vendored Kronos, `[predict]` extra), FastAPI/pydantic; React 18 + TypeScript + lightweight-charts v5; pytest; GitHub Actions.

**Metric definitions (used throughout):**
- **directional** (per anchor): `sign(pred_close[-1] - anchor_close) == sign(actual_close[-1] - anchor_close)`; aggregate = mean over anchors.
- **mape**: mean over (anchor, step) of `|pred_close - actual_close| / actual_close`.
- **band coverage**: fraction of (anchor, step) where `pred_close_low <= actual_close <= pred_close_high`; nominal = `band_high - band_low` (0.8).
- **error-by-horizon**: per step `s`, mean over anchors of `|pred-actual|/actual` (`mae_pct`) and coverage.

---

### Task 1: Config + lake paths for the backtest

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/data/lake_paths.py`
- Test: `backend/tests/test_backtest.py` (new)

- [ ] **Step 1: Add backtest settings.** In `backend/app/core/config.py`, after the
  `prediction_modes` line (currently line 41), add:

```python
    # Backtest (walk-forward accuracy; uses the `predict` extra, run in CI)
    backtest_intervals: str = "1h,1d"   # scope: skip 1m/5m
    backtest_anchors: int = 96          # past forecast points per (symbol, interval)
    backtest_lookback: int = 256        # history window each anchor conditions on
    backtest_sample_count: int = 8      # fewer than the live 16 to bound CI; band still meaningful
```

And add this property after `prediction_mode_list` (after line 78):

```python
    @property
    def backtest_interval_list(self) -> list[str]:
        return [i.strip() for i in self.backtest_intervals.split(",") if i.strip()]
```

- [ ] **Step 2: Add gold dir helpers.** In `backend/app/data/lake_paths.py`, after
  `gold_price_predictions_dir` (line 42), add:

```python
def gold_backtest_forecasts_dir() -> Path:
    return settings.gold_path / "asset_backtest_forecasts"


def gold_backtest_metrics_dir() -> Path:
    return settings.gold_path / "asset_backtest_metrics"


def gold_backtest_horizon_dir() -> Path:
    return settings.gold_path / "asset_backtest_horizon"
```

- [ ] **Step 3: Commit.**

```bash
git add backend/app/core/config.py backend/app/data/lake_paths.py
git commit -m "feat(backtest): config scope + gold path helpers"
```

---

### Task 2: Pure helpers — anchor selection + metric math (TDD)

These are torch-free and fully unit-tested. They live in `backend/app/data/backtest.py`.

**Files:**
- Create: `backend/app/data/backtest.py`
- Test: `backend/tests/test_backtest.py`

- [ ] **Step 1: Write failing tests.** Create `backend/tests/test_backtest.py`:

```python
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
```

- [ ] **Step 2: Run tests, verify they fail.**

Run: `cd backend && python -m pytest tests/test_backtest.py -v`
Expected: FAIL (`module app.data.backtest has no attribute select_anchors` / import error).

- [ ] **Step 3: Implement the pure helpers.** Create `backend/app/data/backtest.py`:

```python
"""Walk-forward backtest of Kronos forecasts -> gold accuracy tables.

Mirrors predictions.py: a compute_* function that reads silver + write_gold_*
functions. Inference runs as a CI batch job, never in the request path. Requires
the `predict` extra (torch). Pure helpers (anchor selection + metric math) are
torch-free and unit-tested directly.
"""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

from app.core.config import settings
from app.core.logging import logger
from app.data.lake_paths import (
    ensure_dir,
    gold_backtest_forecasts_dir,
    gold_backtest_horizon_dir,
    gold_backtest_metrics_dir,
)
from app.data.predictions import INTERVAL_DELTA, PRICE_COLS

FORECASTS_SCHEMA = {
    "symbol": pl.Utf8, "interval": pl.Utf8, "anchor_id": pl.Int64,
    "anchor_time_utc": pl.Utf8, "anchor_close": pl.Float64,
    "step": pl.Int64, "forecast_time_utc": pl.Utf8,
    "pred_close": pl.Float64, "pred_close_low": pl.Float64, "pred_close_high": pl.Float64,
    "actual_close": pl.Float64,
}
METRICS_SCHEMA = {
    "symbol": pl.Utf8, "interval": pl.Utf8, "n_anchors": pl.Int64,
    "directional_pct": pl.Float64, "mape": pl.Float64,
    "band_coverage": pl.Float64, "band_nominal": pl.Float64,
    "horizon": pl.Int64, "generated_at_utc": pl.Utf8,
}
HORIZON_SCHEMA = {
    "symbol": pl.Utf8, "interval": pl.Utf8, "step": pl.Int64,
    "mae_pct": pl.Float64, "coverage": pl.Float64,
}


def select_anchors(n_bars: int, lookback: int, horizon: int, n_anchors: int) -> list[int]:
    """Evenly spaced anchor indices t where bars[t-lookback:t] (history) and
    bars[t:t+horizon] (future) both exist. t in [lookback, n_bars - horizon]."""
    lo, hi = lookback, n_bars - horizon
    if hi < lo:
        return []
    span = hi - lo
    if span + 1 <= n_anchors:
        return list(range(lo, hi + 1))
    return sorted({int(round(lo + span * i / (n_anchors - 1))) for i in range(n_anchors)})


def _band_nominal() -> float:
    return round(settings.prediction_band_high - settings.prediction_band_low, 6)


def per_anchor_metrics(anchor_close: float, pred: np.ndarray, lo: np.ndarray,
                       hi: np.ndarray, actual: np.ndarray) -> dict:
    """Directional / MAPE / band-coverage for a single anchor's forecast."""
    dir_correct = bool(np.sign(pred[-1] - anchor_close) == np.sign(actual[-1] - anchor_close))
    mape = float(np.mean(np.abs(pred - actual) / actual))
    coverage = float(np.mean((actual >= lo) & (actual <= hi)))
    return {"dir": dir_correct, "mape": mape, "coverage": coverage}


def aggregate_metrics(per: list[dict]) -> tuple[dict, list[dict]]:
    """Aggregate across anchors. `per` items have arrays pred/lo/hi/actual + anchor_close."""
    if not per:
        return ({"n_anchors": 0, "directional_pct": 0.0, "mape": 0.0,
                 "band_coverage": 0.0, "band_nominal": _band_nominal()}, [])
    dirs, mapes, covs = [], [], []
    horizon = len(per[0]["actual"])
    step_err = [[] for _ in range(horizon)]
    step_cov = [[] for _ in range(horizon)]
    for a in per:
        m = per_anchor_metrics(a["anchor_close"], a["pred"], a["lo"], a["hi"], a["actual"])
        dirs.append(1.0 if m["dir"] else 0.0)
        mapes.append(m["mape"])
        covs.append(m["coverage"])
        for s in range(horizon):
            step_err[s].append(abs(a["pred"][s] - a["actual"][s]) / a["actual"][s])
            step_cov[s].append(1.0 if (a["lo"][s] <= a["actual"][s] <= a["hi"][s]) else 0.0)
    agg = {
        "n_anchors": len(per),
        "directional_pct": float(np.mean(dirs)),
        "mape": float(np.mean(mapes)),
        "band_coverage": float(np.mean(covs)),
        "band_nominal": _band_nominal(),
    }
    horizon_curve = [
        {"step": s + 1, "mae_pct": float(np.mean(step_err[s])), "coverage": float(np.mean(step_cov[s]))}
        for s in range(horizon)
    ]
    return agg, horizon_curve
```

- [ ] **Step 4: Run tests, verify they pass.**

Run: `cd backend && python -m pytest tests/test_backtest.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit.**

```bash
git add backend/app/data/backtest.py backend/tests/test_backtest.py
git commit -m "feat(backtest): anchor selection + metric helpers (TDD)"
```

---

### Task 3: Walk-forward `compute_backtest` + writers (TDD with stub predictor)

**Files:**
- Modify: `backend/app/data/backtest.py`
- Test: `backend/tests/test_backtest.py`

- [ ] **Step 1: Write a failing integration test** using a stub predictor (no torch).
  Append to `backend/tests/test_backtest.py`:

```python
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
```

- [ ] **Step 2: Run, verify it fails.**

Run: `cd backend && python -m pytest tests/test_backtest.py::test_compute_backtest_produces_three_tables -v`
Expected: FAIL (`compute_backtest` not defined).

- [ ] **Step 3: Implement `compute_backtest` + writers.** Append to
  `backend/app/data/backtest.py` (note: `from app.ml.kronos_loader import get_predictor`
  is imported at module level so the test can monkeypatch `bt.get_predictor`):

```python
from app.ml.kronos_loader import get_predictor  # noqa: E402  (top of file with other imports)


def _series_anchor_inputs(sdf: pl.DataFrame, interval: str, lookback: int, horizon: int, anchors: list[int]):
    """Build batchable per-anchor inputs + the realized actual_close window."""
    delta = INTERVAL_DELTA[interval]
    x_dfs, x_tss, y_tss, meta = [], [], [], []
    closes = sdf["close"].to_numpy()
    times = sdf["open_time_utc"].to_list()
    for t in anchors:
        hist = sdf.slice(t - lookback, lookback)
        x_dfs.append(hist.select(PRICE_COLS).to_pandas())
        x_ts = pd.Series(pd.to_datetime(hist["open_time_utc"].to_list(), utc=True, format="ISO8601"))
        x_tss.append(x_ts)
        last = x_ts.iloc[-1]
        y_tss.append(pd.Series([last + delta * (i + 1) for i in range(horizon)]))
        meta.append({
            "anchor_id": t, "anchor_time_utc": times[t - 1], "anchor_close": float(closes[t - 1]),
            "actual": closes[t:t + horizon].astype(float),
            "forecast_time_utc": [times[t + i] for i in range(horizon)],
        })
    return x_dfs, x_tss, y_tss, meta


def compute_backtest(silver_root: Path):
    """Walk-forward backtest for each (symbol, interval) in scope. Returns
    (forecasts_df, metrics_df, horizon_df)."""
    all_files = list((silver_root / "market_candles").rglob("*.parquet"))
    if not all_files:
        logger.warning("No silver parquet for backtest")
        return (pl.DataFrame(schema=FORECASTS_SCHEMA),
                pl.DataFrame(schema=METRICS_SCHEMA), pl.DataFrame(schema=HORIZON_SCHEMA))

    full = pl.scan_parquet([str(f) for f in all_files]).collect()
    n_samples = max(1, settings.backtest_sample_count)
    lookback = settings.backtest_lookback
    q_lo, q_hi = settings.prediction_band_low, settings.prediction_band_high
    horizon_map = settings.prediction_horizon_map
    predictor = get_predictor()
    generated_at = datetime.now(UTC).isoformat()

    f_rows, m_rows, h_rows = [], [], []
    for interval in settings.backtest_interval_list:
        horizon = horizon_map.get(interval, settings.prediction_horizon)
        for symbol in settings.symbols:
            sdf = (full.filter((pl.col("symbol") == symbol) & (pl.col("interval") == interval))
                   .sort("open_time_utc"))
            anchors = select_anchors(sdf.height, lookback, horizon, settings.backtest_anchors)
            if not anchors:
                logger.warning(f"No backtest anchors for {symbol}/{interval} ({sdf.height} bars)")
                continue
            x_dfs, x_tss, y_tss, meta = _series_anchor_inputs(sdf, interval, lookback, horizon, anchors)

            passes = [
                predictor.predict_batch(df_list=x_dfs, x_timestamp_list=x_tss, y_timestamp_list=y_tss,
                                        pred_len=horizon, T=settings.prediction_temperature, top_k=0,
                                        top_p=settings.prediction_top_p, sample_count=1,
                                        verbose=False, sample_logits=True)
                for _ in range(n_samples)
            ]

            per = []
            for i, mt in enumerate(meta):
                stack = np.stack([passes[p][i]["close"].to_numpy() for p in range(n_samples)])
                pred = np.median(stack, axis=0)
                lo = np.quantile(stack, q_lo, axis=0)
                hi = np.quantile(stack, q_hi, axis=0)
                per.append({"pred": pred, "lo": lo, "hi": hi, "actual": mt["actual"],
                            "anchor_close": mt["anchor_close"]})
                for s in range(horizon):
                    f_rows.append({
                        "symbol": symbol, "interval": interval, "anchor_id": mt["anchor_id"],
                        "anchor_time_utc": mt["anchor_time_utc"], "anchor_close": mt["anchor_close"],
                        "step": s + 1, "forecast_time_utc": mt["forecast_time_utc"][s],
                        "pred_close": float(pred[s]), "pred_close_low": float(lo[s]),
                        "pred_close_high": float(hi[s]), "actual_close": float(mt["actual"][s]),
                    })

            agg, curve = aggregate_metrics(per)
            m_rows.append({"symbol": symbol, "interval": interval, "horizon": horizon,
                           "generated_at_utc": generated_at, **agg})
            for c in curve:
                h_rows.append({"symbol": symbol, "interval": interval, **c})
            logger.info(f"Backtest {symbol}/{interval}: {len(anchors)} anchors, dir={agg['directional_pct']:.2f}")

    return (pl.DataFrame(f_rows, schema=FORECASTS_SCHEMA),
            pl.DataFrame(m_rows, schema=METRICS_SCHEMA),
            pl.DataFrame(h_rows, schema=HORIZON_SCHEMA))


def _write(df: pl.DataFrame, dir_fn, name: str) -> Path:
    if df.is_empty():
        logger.warning(f"No {name} to write")
        return Path("")
    out = ensure_dir(dir_fn()) / f"{name}.parquet"
    df.write_parquet(str(out))
    logger.info(f"Wrote {out} ({len(df)} rows)")
    return out


def write_gold_backtest(forecasts: pl.DataFrame, metrics: pl.DataFrame, horizon: pl.DataFrame) -> None:
    _write(forecasts, gold_backtest_forecasts_dir, "asset_backtest_forecasts")
    _write(metrics, gold_backtest_metrics_dir, "asset_backtest_metrics")
    _write(horizon, gold_backtest_horizon_dir, "asset_backtest_horizon")
```

Move the `from app.ml.kronos_loader import get_predictor` line up to the import block (with the
other `from app.data...` imports) so `bt.get_predictor` is patchable.

- [ ] **Step 4: Run the full backtest test file, verify pass.**

Run: `cd backend && python -m pytest tests/test_backtest.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit.**

```bash
git add backend/app/data/backtest.py backend/tests/test_backtest.py
git commit -m "feat(backtest): walk-forward compute + gold writers (TDD stub predictor)"
```

---

### Task 4: Build script

**Files:**
- Create: `scripts/build_backtest.py`

- [ ] **Step 1: Create the script** (mirrors `scripts/build_predictions.py`):

```python
#!/usr/bin/env python3
"""Walk-forward backtest of Kronos forecasts -> gold backtest tables.

Requires the `predict` extra (pip install -e ".[predict]"). Heavy: re-runs the
model at many past anchors. Intended for a dedicated CI workflow.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from rich.console import Console

from app.core.config import settings
from app.core.logging import logger
from app.data.backtest import compute_backtest, write_gold_backtest

console = Console()


def main() -> None:
    console.print("[bold green]=== Building Backtest (Kronos walk-forward) ===[/bold green]")
    try:
        forecasts, metrics, horizon = compute_backtest(settings.silver_path)
    except Exception as e:
        console.print(f"[red]Backtest failed:[/red] {e}")
        logger.error(f"Backtest failed: {e}")
        raise
    if metrics.is_empty():
        console.print("[yellow]No backtest produced (insufficient silver data?).[/yellow]")
        return
    write_gold_backtest(forecasts, metrics, horizon)
    console.print(f"[green]Backtest: {forecasts.height} forecast rows, {metrics.height} series[/green]")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit.**

```bash
git add scripts/build_backtest.py
git commit -m "feat(backtest): build_backtest.py entrypoint"
```

---

### Task 5: DuckDB views

**Files:**
- Modify: `backend/app/data/duckdb_repo.py:16-54`

- [ ] **Step 1: Add the three views.** In `_create_views`, after the `gold_predictions`
  local (line 24) add the paths, and add three entries to the `views` dict (after
  `v_asset_price_predictions`):

```python
        gold_bt_forecasts = str(gold_root / "asset_backtest_forecasts" / "*.parquet")
        gold_bt_metrics = str(gold_root / "asset_backtest_metrics" / "*.parquet")
        gold_bt_horizon = str(gold_root / "asset_backtest_horizon" / "*.parquet")
```

```python
            "v_asset_backtest_forecasts": f"""
                CREATE OR REPLACE VIEW v_asset_backtest_forecasts AS
                SELECT * FROM read_parquet('{gold_bt_forecasts}', hive_partitioning=true)
            """,
            "v_asset_backtest_metrics": f"""
                CREATE OR REPLACE VIEW v_asset_backtest_metrics AS
                SELECT * FROM read_parquet('{gold_bt_metrics}', hive_partitioning=true)
            """,
            "v_asset_backtest_horizon": f"""
                CREATE OR REPLACE VIEW v_asset_backtest_horizon AS
                SELECT * FROM read_parquet('{gold_bt_horizon}', hive_partitioning=true)
            """,
```

- [ ] **Step 2: Commit.**

```bash
git add backend/app/data/duckdb_repo.py
git commit -m "feat(backtest): duckdb views for backtest tables"
```

---

### Task 6: API — models + `/backtest/replay` and `/backtest/metrics` (TDD)

The replay endpoint reads the forecasts table, groups by anchor, computes per-anchor
dir/mape/coverage (reusing `per_anchor_metrics`), and attaches a realized candle window from
`v_market_candles` for the chart.

**Files:**
- Modify: `backend/app/models/api_models.py`
- Create: `backend/app/api/routes_backtest.py`
- Modify: `backend/app/main.py:8-15,95-103`
- Test: `backend/tests/test_backtest_api.py` (new)

- [ ] **Step 1: Add response models.** Append to `backend/app/models/api_models.py`:

```python
class BacktestReplayResponse(BaseModel):
    symbol: str
    interval: str
    supported: bool
    anchors: list[dict]


class BacktestMetricsResponse(BaseModel):
    symbol: str
    interval: str
    supported: bool
    n_anchors: int
    directional_pct: float
    mape: float
    band_coverage: float
    band_nominal: float
    horizon: list[dict]
```

- [ ] **Step 2: Write failing API tests.** Create `backend/tests/test_backtest_api.py`:

```python
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
```

- [ ] **Step 3: Run, verify they fail.**

Run: `cd backend && python -m pytest tests/test_backtest_api.py -v`
Expected: FAIL (404 — routes not registered).

- [ ] **Step 4: Implement the routes.** Create `backend/app/api/routes_backtest.py`:

```python
import numpy as np
from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.core.logging import logger
from app.data.backtest import per_anchor_metrics
from app.data.duckdb_repo import DuckDBRepo
from app.models.api_models import BacktestMetricsResponse, BacktestReplayResponse

router = APIRouter(tags=["backtest"])

VALID_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}


def _supported(interval: str) -> bool:
    return interval in set(settings.backtest_interval_list)


def _check_symbol(symbol: str) -> None:
    if symbol not in VALID_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Invalid symbol. Must be one of {sorted(VALID_SYMBOLS)}")


@router.get("/backtest/replay", response_model=BacktestReplayResponse)
def get_replay(symbol: str = Query(...), interval: str = Query("1h")) -> BacktestReplayResponse:
    _check_symbol(symbol)
    if not _supported(interval):
        return BacktestReplayResponse(symbol=symbol, interval=interval, supported=False, anchors=[])

    rows = []
    try:
        with DuckDBRepo() as repo:
            rows = repo.query(
                """SELECT anchor_id, anchor_time_utc, anchor_close, step, forecast_time_utc,
                          pred_close, pred_close_low, pred_close_high, actual_close
                   FROM v_asset_backtest_forecasts
                   WHERE symbol = :symbol AND interval = :interval
                   ORDER BY anchor_id, step""",
                {"symbol": symbol, "interval": interval},
            )
            # Realized candles for context windows come from silver.
            candles = repo.query(
                """SELECT open_time_utc, open, high, low, close
                   FROM v_market_candles WHERE symbol = :symbol AND interval = :interval
                   ORDER BY open_time_utc""",
                {"symbol": symbol, "interval": interval},
            )
    except Exception as e:
        logger.warning(f"Backtest replay query failed (may be ungenerated): {e}")
        return BacktestReplayResponse(symbol=symbol, interval=interval, supported=True, anchors=[])

    by_time = {c["open_time_utc"]: c for c in candles}
    times_sorted = [c["open_time_utc"] for c in candles]
    idx = {t: i for i, t in enumerate(times_sorted)}

    anchors: dict[int, dict] = {}
    for r in rows:
        a = anchors.setdefault(r["anchor_id"], {
            "anchor_id": r["anchor_id"], "anchor_time_utc": r["anchor_time_utc"],
            "anchor_close": r["anchor_close"], "forecast": [], "_pred": [], "_lo": [], "_hi": [], "_act": [],
        })
        a["forecast"].append({"t": r["forecast_time_utc"], "pred": r["pred_close"],
                              "lo": r["pred_close_low"], "hi": r["pred_close_high"]})
        a["_pred"].append(r["pred_close"]); a["_lo"].append(r["pred_close_low"])
        a["_hi"].append(r["pred_close_high"]); a["_act"].append(r["actual_close"])

    horizon = settings.prediction_horizon_map.get(interval, settings.prediction_horizon)
    out = []
    for a in anchors.values():
        m = per_anchor_metrics(a["anchor_close"], np.array(a["_pred"]), np.array(a["_lo"]),
                               np.array(a["_hi"]), np.array(a["_act"]))
        # context candle window: `horizon` bars before the anchor through the forecast end
        anchor_i = idx.get(a["anchor_time_utc"])
        window = []
        if anchor_i is not None:
            start = max(0, anchor_i - horizon)
            end = min(len(times_sorted), anchor_i + horizon + 1)
            window = [{"t": times_sorted[i], "o": by_time[times_sorted[i]]["open"],
                       "h": by_time[times_sorted[i]]["high"], "l": by_time[times_sorted[i]]["low"],
                       "c": by_time[times_sorted[i]]["close"]} for i in range(start, end)]
        out.append({
            "anchor_id": a["anchor_id"], "anchor_time_utc": a["anchor_time_utc"],
            "anchor_close": a["anchor_close"], "dir": m["dir"], "mape": m["mape"],
            "coverage": m["coverage"], "candles": window, "forecast": a["forecast"],
        })
    out.sort(key=lambda x: x["anchor_id"])
    return BacktestReplayResponse(symbol=symbol, interval=interval, supported=True, anchors=out)


@router.get("/backtest/metrics", response_model=BacktestMetricsResponse)
def get_metrics(symbol: str = Query(...), interval: str = Query("1h")) -> BacktestMetricsResponse:
    _check_symbol(symbol)
    empty = BacktestMetricsResponse(symbol=symbol, interval=interval, supported=_supported(interval),
                                    n_anchors=0, directional_pct=0.0, mape=0.0, band_coverage=0.0,
                                    band_nominal=round(settings.prediction_band_high - settings.prediction_band_low, 6),
                                    horizon=[])
    if not _supported(interval):
        return empty
    try:
        with DuckDBRepo() as repo:
            m = repo.query("""SELECT * FROM v_asset_backtest_metrics
                              WHERE symbol = :symbol AND interval = :interval""",
                           {"symbol": symbol, "interval": interval})
            h = repo.query("""SELECT step, mae_pct, coverage FROM v_asset_backtest_horizon
                              WHERE symbol = :symbol AND interval = :interval ORDER BY step""",
                           {"symbol": symbol, "interval": interval})
    except Exception as e:
        logger.warning(f"Backtest metrics query failed (may be ungenerated): {e}")
        return empty
    if not m:
        return empty
    row = m[0]
    return BacktestMetricsResponse(
        symbol=symbol, interval=interval, supported=True, n_anchors=row["n_anchors"],
        directional_pct=row["directional_pct"], mape=row["mape"], band_coverage=row["band_coverage"],
        band_nominal=row["band_nominal"], horizon=h,
    )
```

- [ ] **Step 5: Register the router.** In `backend/app/main.py`, add the import next to the other
  route imports (after line 15):

```python
from app.api.routes_backtest import router as backtest_router
```

and include it after `predictions_router` (after line 102):

```python
app.include_router(backtest_router, prefix="")
```

- [ ] **Step 6: Run API tests, verify pass.**

Run: `cd backend && python -m pytest tests/test_backtest_api.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit.**

```bash
git add backend/app/api/routes_backtest.py backend/app/models/api_models.py backend/app/main.py backend/tests/test_backtest_api.py
git commit -m "feat(backtest): /backtest/replay + /backtest/metrics API (TDD)"
```

---

### Task 7: Generate a first backtest snapshot locally

**Files:** (data output only)

- [ ] **Step 1: Run the backtest** with the venv (Standard depth; takes a while on CPU). For a
  quick first pass you may lower anchors via env:

Run: `cd "C:\Coding Space\crypto-lakehouse" && PYTHONPATH=backend BACKTEST_ANCHORS=24 .venv/Scripts/python.exe scripts/build_backtest.py`
Expected: writes `data/lakehouse/gold/asset_backtest_{forecasts,metrics,horizon}/*.parquet`; logs per-series directional %.

- [ ] **Step 2: Restart backend and smoke-test the endpoints.**

Run: `cd "C:\Coding Space\crypto-lakehouse" && PYTHONPATH=backend POLLING_ENABLED=false .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000 &`
then `curl "http://localhost:8000/backtest/metrics?symbol=BTCUSDT&interval=1h"` and
`curl "http://localhost:8000/backtest/replay?symbol=BTCUSDT&interval=1h"`.
Expected: metrics with directional_pct/mape/band_coverage near sane ranges, horizon curve; replay with anchors each having `candles` + `forecast`.

- [ ] **Step 3: Commit the snapshot** (parquet is gitignored — force-add like predictions).

```bash
git add -f data/lakehouse/gold/asset_backtest_forecasts data/lakehouse/gold/asset_backtest_metrics data/lakehouse/gold/asset_backtest_horizon
git commit -m "chore(data): first backtest snapshot"
```

---

### Task 8: Frontend API client

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add types + fetchers.** Append to `frontend/src/api/client.ts` (uses the existing
  `fetchApi` helper):

```typescript
export interface BacktestStep { t: string; pred: number; lo: number; hi: number; }
export interface BacktestCandle { t: string; o: number; h: number; l: number; c: number; }
export interface BacktestAnchor {
  anchor_id: number;
  anchor_time_utc: string;
  anchor_close: number;
  dir: boolean;
  mape: number;
  coverage: number;
  candles: BacktestCandle[];
  forecast: BacktestStep[];
}
export interface BacktestReplay {
  symbol: string; interval: string; supported: boolean; anchors: BacktestAnchor[];
}
export interface BacktestHorizonPoint { step: number; mae_pct: number; coverage: number; }
export interface BacktestMetrics {
  symbol: string; interval: string; supported: boolean; n_anchors: number;
  directional_pct: number; mape: number; band_coverage: number; band_nominal: number;
  horizon: BacktestHorizonPoint[];
}

export async function getBacktestReplay(symbol: string, interval: string) {
  return fetchApi<BacktestReplay>(`/backtest/replay?symbol=${symbol}&interval=${interval}`);
}
export async function getBacktestMetrics(symbol: string, interval: string) {
  return fetchApi<BacktestMetrics>(`/backtest/metrics?symbol=${symbol}&interval=${interval}`);
}
```

- [ ] **Step 2: Commit.**

```bash
git add frontend/src/api/client.ts
git commit -m "feat(backtest): frontend api client"
```

---

### Task 9: `BacktestStrip` aggregate component

**Files:**
- Create: `frontend/src/components/BacktestStrip.tsx`

- [ ] **Step 1: Create the component** (stat cells + a CSS-bar error-by-horizon sparkline; theme
  tokens reused):

```tsx
import { BacktestMetrics } from '../api/client';

const pct = (x: number) => `${(x * 100).toFixed(0)}%`;

export default function BacktestStrip({ m }: { m: BacktestMetrics | null }) {
  if (!m || !m.supported || m.n_anchors === 0) return null;
  const maxErr = Math.max(...m.horizon.map(h => h.mae_pct), 1e-9);
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 font-mono text-[11px]">
      <span className="text-term-muted">over {m.n_anchors} backtested forecasts</span>
      <span className="text-term-muted">dir <span className="text-term-text">{pct(m.directional_pct)}</span></span>
      <span className="text-term-muted">MAPE <span className="text-term-text">{(m.mape * 100).toFixed(2)}%</span></span>
      <span className="text-term-muted">
        band <span className="text-term-text">{pct(m.band_coverage)}</span>
        <span className="text-term-muted"> /{pct(m.band_nominal)}</span>
      </span>
      <span className="flex items-end gap-0.5" title="error by horizon">
        {m.horizon.map(h => (
          <span key={h.step} className="w-1 bg-term-accent/70"
                style={{ height: `${4 + (h.mae_pct / maxErr) * 14}px` }} />
        ))}
      </span>
    </div>
  );
}
```

- [ ] **Step 2: Commit.**

```bash
git add frontend/src/components/BacktestStrip.tsx
git commit -m "feat(backtest): aggregate accuracy strip component"
```

---

### Task 10: `AssetChart` Live | Replay mode + scrubber

Extend the existing chart: a view toggle, replay data fetch, an anchor scrubber, and a render path
that draws the selected anchor's realized candles + forecast overlay (reusing the band-mask series).

**Files:**
- Modify: `frontend/src/components/AssetChart.tsx`

- [ ] **Step 1: Imports + state.** Update the client import (line 19) to add the new symbols, and
  add `BacktestStrip`:

```tsx
import { getCandles, getForecast, getBacktestReplay, getBacktestMetrics,
         CandleData, ForecastPoint, BacktestReplay, BacktestMetrics, BacktestAnchor } from '../api/client';
import BacktestStrip from './BacktestStrip';
```

Add state (after line 124, `const [hasForecast...]`):

```tsx
  const [view, setView] = useState<'live' | 'replay'>('live');
  const [replay, setReplay] = useState<BacktestReplay | null>(null);
  const [metrics, setMetrics] = useState<BacktestMetrics | null>(null);
  const [anchorIdx, setAnchorIdx] = useState(0);
  const replaySupported = ['1h', '1d'].includes(interval);
```

- [ ] **Step 2: Replay render helper.** Add near `forecastLine` (after line 112):

```tsx
function bandFromAnchor(a: BacktestAnchor, pick: (s: BacktestReplay['anchors'][0]['forecast'][0]) => number): AreaData<UTCTimestamp>[] {
  return a.forecast.map(s => ({ time: toSeconds(s.t), value: pick(s) }))
    .sort((p, q) => (p.time as number) - (q.time as number));
}
```

- [ ] **Step 3: Fetch replay data when entering replay mode** (new effect after the theme effect,
  before the live data effect):

```tsx
  useEffect(() => {
    if (view !== 'replay' || !replaySupported) { setReplay(null); setMetrics(null); return; }
    let cancelled = false;
    setLoading(true);
    Promise.all([getBacktestReplay(symbol, interval), getBacktestMetrics(symbol, interval)])
      .then(([rep, met]) => {
        if (cancelled) return;
        setReplay(rep); setMetrics(met);
        setAnchorIdx(rep.anchors.length ? rep.anchors.length - 1 : 0);
      })
      .catch(() => { if (!cancelled) { setReplay(null); setMetrics(null); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [view, symbol, interval, replaySupported, tick]);
```

- [ ] **Step 4: Render the selected anchor** (new effect; draws candles + forecast + band for the
  chosen anchor). Add after Step 3's effect:

```tsx
  useEffect(() => {
    if (view !== 'replay' || !replay || !replay.anchors.length) return;
    const a = replay.anchors[Math.min(anchorIdx, replay.anchors.length - 1)];
    candleRef.current?.setData(a.candles.map(c => ({
      time: toSeconds(c.t), open: c.o, high: c.h, low: c.l, close: c.c,
    })));
    volumeRef.current?.setData([]);
    const central: LineData<UTCTimestamp>[] = a.forecast
      .map(s => ({ time: toSeconds(s.t), value: s.pred }))
      .sort((p, q) => (p.time as number) - (q.time as number));
    forecastRef.current?.setData(central);
    bandHighRef.current?.setData(bandFromAnchor(a, s => s.hi));
    bandLowRef.current?.setData(bandFromAnchor(a, s => s.lo));
    chartRef.current?.timeScale().fitContent();
    setHasForecast(true);
    setCount(a.candles.length);
    lastBarRef.current = null;
    setLegend(null);
  }, [view, replay, anchorIdx]);
```

- [ ] **Step 5: Guard the live effect** so it doesn't fight replay mode. Change the live data
  effect's first lines (line 220-222) to early-return in replay:

```tsx
  useEffect(() => {
    if (view === 'replay') return;
    setLoading(true);
    let cancelled = false;
```

and add `view` to its dependency array (line 274): `}, [symbol, interval, fmode, lookback, tick, view]);`

- [ ] **Step 6: Add the Live|Replay toggle + scrubber to the controls row.** In the controls
  `<div>` (after the Lookback control block, before the `count` span at line 309), add:

```tsx
        <div className="flex items-center gap-2">
          <span className={labelCls}>Mode</span>
          <div className="flex overflow-hidden rounded-sm border border-term-border">
            {(['live', 'replay'] as const).map(v => (
              <button key={v} onClick={() => setView(v)}
                className={`px-2.5 py-1 font-mono text-xs ${view === v ? 'bg-term-accent text-term-bg' : 'bg-term-bg text-term-muted hover:text-term-text'}`}>
                {v === 'live' ? 'Live' : 'Replay'}
              </button>
            ))}
          </div>
        </div>
```

- [ ] **Step 7: Add the scrubber + per-forecast readout** below the chart container (after the
  closing `</div>` of the `h-[440px]` block at line 340, before the `hasForecast` block). Render
  only in replay:

```tsx
      {view === 'replay' && !replaySupported && (
        <div className="mt-2 font-mono text-[11px] text-term-muted">Backtest available for 1h / 1d.</div>
      )}
      {view === 'replay' && replaySupported && replay && replay.anchors.length > 0 && (() => {
        const a = replay.anchors[Math.min(anchorIdx, replay.anchors.length - 1)];
        return (
          <div className="mt-2">
            <div className="flex items-center gap-3 font-mono text-[11px]">
              <button className="px-2 text-term-muted hover:text-term-text"
                onClick={() => setAnchorIdx(i => Math.max(0, i - 1))}>◀</button>
              <input type="range" min={0} max={replay.anchors.length - 1} value={anchorIdx}
                onChange={e => setAnchorIdx(Number(e.target.value))} className="flex-1 accent-term-accent" />
              <button className="px-2 text-term-muted hover:text-term-text"
                onClick={() => setAnchorIdx(i => Math.min(replay.anchors.length - 1, i + 1))}>▶</button>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-4 font-mono text-[11px]">
              <span className="text-term-muted">forecast @ {a.anchor_time_utc.slice(0, 16).replace('T', ' ')}</span>
              <span className={a.dir ? 'text-term-up' : 'text-term-down'}>dir {a.dir ? '✓' : '✗'}</span>
              <span className="text-term-muted">MAPE <span className="text-term-text">{(a.mape * 100).toFixed(2)}%</span></span>
              <span className="text-term-muted">in-band <span className="text-term-text">{(a.coverage * 100).toFixed(0)}%</span></span>
            </div>
            <BacktestStrip m={metrics} />
          </div>
        );
      })()}
```

- [ ] **Step 8: Build to typecheck.**

Run: `cd frontend && npm run build`
Expected: `tsc -b && vite build` succeeds, no TS errors.

- [ ] **Step 9: Commit.**

```bash
git add frontend/src/components/AssetChart.tsx frontend/dist
git commit -m "feat(backtest): Live|Replay mode, scrubber, accuracy readout on chart"
```

---

### Task 11: CI workflow (weekly backtest)

**Files:**
- Create: `.github/workflows/backtest.yml`

- [ ] **Step 1: Create the workflow** (separate from the 12h refresh):

```yaml
name: Refresh backtest snapshot

# Walk-forward accuracy backtest (heavy: re-runs Kronos at ~96 past anchors per
# series). Runs weekly on a free runner and commits the gold backtest tables so
# Render can serve /backtest/* read-only.

on:
  schedule:
    - cron: "0 6 * * 0"   # Sundays 06:00 UTC
  workflow_dispatch: {}

permissions:
  contents: write

concurrency:
  group: backtest
  cancel-in-progress: false

jobs:
  backtest:
    runs-on: ubuntu-latest
    timeout-minutes: 240
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - name: Cache Hugging Face weights
        uses: actions/cache@v4
        with:
          path: ~/.cache/huggingface
          key: hf-kronos-small-v1
      - name: Install (with predict extra)
        run: pip install -e ".[predict]"
      - name: Build backtest
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: python scripts/build_backtest.py
      - name: Commit snapshot to main
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -f data/lakehouse/gold/asset_backtest_forecasts data/lakehouse/gold/asset_backtest_metrics data/lakehouse/gold/asset_backtest_horizon
          if git diff --cached --quiet; then
            echo "No backtest changes to commit."
          else
            git commit -m "chore(data): refresh backtest snapshot [skip ci]"
            git push
          fi
```

- [ ] **Step 2: Commit.**

```bash
git add .github/workflows/backtest.yml
git commit -m "ci(backtest): weekly backtest snapshot workflow"
```

---

### Task 12: Full verification + ship

**Files:** (none — verification + deploy)

- [ ] **Step 1: Full test suite.**

Run: `cd "C:\Coding Space\crypto-lakehouse" && .venv/Scripts/python.exe -m pytest backend/tests/ -q`
Expected: all pass (existing 33 + new backtest unit/API tests).

- [ ] **Step 2: Visual verify** (backend on 8000 + dev server on 5173) with Playwright: toggle
  Replay, scrub anchors, confirm the realized candles + dashed forecast + shaded band render, the
  per-forecast readout + aggregate strip populate, the 1m/5m note shows, in both light and dark.

- [ ] **Step 3: Final frontend build + push to prod.**

```bash
cd frontend && npm run build
cd .. && git add -A && git add -f frontend/dist data/lakehouse/gold/asset_backtest_forecasts data/lakehouse/gold/asset_backtest_metrics data/lakehouse/gold/asset_backtest_horizon
git commit -m "feat: model-accuracy backtest (Replay mode + accuracy API/snapshot)"
git push origin master
```

- [ ] **Step 4: Verify prod** once Render/Vercel redeploy: `curl
  https://crypto-lakehouse.onrender.com/backtest/metrics?symbol=BTCUSDT&interval=1h` returns real
  numbers, and `crypto-lakehouse.vercel.app` shows Replay mode working.

- [ ] **Step 5: Add the `HF_TOKEN` note.** Remind the user the weekly workflow needs the existing
  `HF_TOKEN` GitHub secret (already used by `refresh-data.yml`).

---

## Self-Review

**Spec coverage:** centerpiece replay overlay (Task 10) ✓; Live|Replay placement on main chart
(Task 10) ✓; directional/MAPE/band/horizon metrics (Tasks 2–3, surfaced in 9–10) ✓; walk-forward
engine reusing the Kronos path (Task 3) ✓; 3 gold tables + lake paths + views (Tasks 1, 3, 5) ✓;
`/backtest/replay` + `/backtest/metrics` API (Task 6) ✓; weekly CI (Task 11) ✓; stub-predictor unit
tests + API tests (Tasks 2, 3, 6) ✓; 1m/5m "supported:false" note (Tasks 6, 10) ✓; scope 3×{1h,1d}
sampled lookback 256 (Task 1 config) ✓.

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `compute_backtest` returns `(forecasts, metrics, horizon)` used identically in
Tasks 3/4/7; `per_anchor_metrics(anchor_close, pred, lo, hi, actual)` signature matches both its
test (Task 2) and the API caller (Task 6); `BacktestAnchor` fields (`candles`, `forecast`, `dir`,
`mape`, `coverage`) match the API output (Task 6) and the chart consumer (Task 10);
`BacktestMetrics` fields match `BacktestStrip` (Task 9) and the metrics endpoint (Task 6).

**Note on candle window:** the replay endpoint sources realized candles from `v_market_candles`
(silver has full history) keyed by `anchor_time_utc`, so old anchors render correctly without storing
OHLC in the backtest table.
