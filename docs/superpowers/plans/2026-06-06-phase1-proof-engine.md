# Phase 1 — Proof Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the verifiable forecast track record (immutable live log + out-of-sample backtest, both scored against realized prices and compared to a naive baseline) and a public Track Record page, ending at a go/no-go gate that decides whether the Kronos forecasts are good enough to monetize.

**Architecture:** Two scored sources feed one record. (1) The existing walk-forward **backtest** (`backend/app/data/backtest.py`) gains a hard *post-Kronos-cutoff guard* (no training-data contamination) and a *naive-baseline* column. (2) A new **immutable, append-only live forecast log** captures every forecast before its outcome is known; a new **scoring engine** joins matured forecasts to realized silver candles; a new **rollup** aggregates accuracy + baseline. A new **/track-record** API and a React **Track Record** card surface both. A **gate** script renders the monetize / don't-monetize verdict, fee-aware.

**Tech Stack:** Python 3.11+, Polars, DuckDB, FastAPI, pytest (existing patterns); React 18 + Vite + TypeScript + lightweight-charts (frontend); GitHub Actions (scheduling). Kronos/torch behind the existing `[predict]` extra.

**Spec:** `docs/superpowers/specs/2026-06-06-monetization-design.md` (Phase 1 only; Phases 2–3 out of scope).

---

## ⚠️ Critical caveat for the executor

The lakehouse currently runs largely on **synthetic data** (Binance.US is geo-blocked in CI, so `ingest_market_data.py` falls back to `generate_synthetic_data.py`). **A track record computed on synthetic data is meaningless** — the gate verdict only counts on *real* post-cutoff market data. Treat "ensure real post-cutoff history is ingested" (Task 11 note) as a precondition for trusting the gate, not an afterthought.

---

## File Structure

**Modify (existing):**
- `backend/app/core/config.py` — add `kronos_train_cutoff_utc`, fee/gate settings.
- `backend/app/data/backtest.py` — cutoff guard + baseline metric.
- `backend/app/data/predictions.py` — emit provenance columns (`forecast_id`, `anchor_close`, `prev_close`, ...) and append to the immutable log.
- `backend/app/data/lake_paths.py` — new dirs for log/outcomes/rollup.
- `backend/app/data/duckdb_repo.py` — new views.
- `backend/app/models/api_models.py` — track-record response models.
- `backend/app/main.py` — register the track-record router.
- `Makefile`, `.github/workflows/refresh-data.yml` — wire the new steps.
- `frontend/src/api/client.ts`, `frontend/src/pages/Dashboard.tsx` — surface the record + waitlist.

**Create (new):**
- `backend/app/data/scoring.py` — score matured live forecasts → outcomes (idempotent).
- `backend/app/data/track_record.py` — rollup + baseline + fee-aware gate decision.
- `backend/app/api/routes_track_record.py` — `/track-record/summary`.
- `scripts/build_scoring.py`, `scripts/build_track_record.py`, `scripts/evaluate_gate.py`.
- `backend/tests/test_cutoff_guard.py`, `test_baseline_metric.py`, `test_forecast_log.py`, `test_scoring.py`, `test_track_record.py`, `test_gate.py`, `test_track_record_api.py`.
- `frontend/src/components/TrackRecord.tsx`, `frontend/src/components/WaitlistHero.tsx`.

---

## Task 1: Record the Kronos training cutoff

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `docs/superpowers/specs/2026-06-06-monetization-design.md` (fill §11 open item)

- [ ] **Step 1: Confirm the cutoff**

Fetch the model card and paper and look for the training-data end date:
- `https://huggingface.co/NeoQuasar/Kronos-small`
- `https://arxiv.org/abs/2508.02739`

Record the most precise training-data **end date** stated. If none is stated, use the conservative default below (paper submitted Aug 2025 ⇒ treat anything at/before 2025-08 as potentially in-training) and document the assumption.

- [ ] **Step 2: Add the setting**

In `backend/app/core/config.py`, after the backtest settings block (after line 47 `backtest_sample_count`), add:

```python
    # Honesty boundary: only data strictly AFTER this UTC date is out-of-sample
    # for Kronos (it was pretrained on history up to ~here). Confirmed against the
    # model card / arXiv:2508.02739; conservative default = post-paper.
    kronos_train_cutoff_utc: str = "2025-09-01"

    # Go/no-go gate economics
    taker_fee_pct: float = 0.001            # 0.1% per side
    gate_min_band_coverage_ratio: float = 0.8  # observed/nominal coverage must be >= this
```

- [ ] **Step 3: Document the decision**

In the spec's §11, replace the "Exact Kronos training cutoff date" open item with the confirmed value and the source URL.

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/config.py docs/superpowers/specs/2026-06-06-monetization-design.md
git commit -m "feat(config): record Kronos training cutoff + gate economics"
```

---

## Task 2: Post-cutoff eligibility helper + backtest guard

**Files:**
- Modify: `backend/app/data/backtest.py`
- Test: `backend/tests/test_cutoff_guard.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cutoff_guard.py
import polars as pl
import pytest

pd = pytest.importorskip("pandas")
from app.data import backtest as bt


def test_eligible_anchor_lo_skips_pre_cutoff_targets():
    # 10 hourly bars; cutoff after the 5th bar. With horizon 2, an anchor t means
    # targets at indices t..t+1; the FIRST eligible t is the one whose targets are
    # all strictly after the cutoff.
    times = [f"2026-01-0{1}T0{h}:00:00+00:00" for h in range(10)]
    # cutoff equals the 5th timestamp (index 4); targets must be index >= 5
    lo = bt.eligible_anchor_lo(times, cutoff_utc="2026-01-01T04:00:00+00:00")
    assert lo == 5


def test_eligible_anchor_lo_all_eligible_when_cutoff_in_past():
    times = [f"2026-01-01T0{h}:00:00+00:00" for h in range(5)]
    assert bt.eligible_anchor_lo(times, cutoff_utc="2020-01-01T00:00:00+00:00") == 0


def test_compute_backtest_raises_without_cutoff(tmp_path, monkeypatch):
    monkeypatch.setattr(bt.settings, "kronos_train_cutoff_utc", "")
    with pytest.raises(ValueError, match="cutoff"):
        bt.compute_backtest(tmp_path / "silver")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest backend/tests/test_cutoff_guard.py -v`
Expected: FAIL (`eligible_anchor_lo` not defined).

- [ ] **Step 3: Implement the helper + guard**

In `backend/app/data/backtest.py`, add this helper after `select_anchors` (after line 57):

```python
def eligible_anchor_lo(times: list[str], cutoff_utc: str) -> int:
    """Index of the first bar strictly after `cutoff_utc`. An anchor t is
    out-of-sample only if its forecast targets (index t..t+h-1) are all after the
    cutoff, i.e. t >= this index. `times` is the ascending open_time_utc list."""
    cutoff = pd.Timestamp(cutoff_utc)
    ts = pd.to_datetime(times, utc=True, format="ISO8601")
    for i, t in enumerate(ts):
        if t > cutoff:
            return i
    return len(times)
```

Then in `compute_backtest`, immediately after `full = pl.scan_parquet(...).collect()` (after line 134), add the guard:

```python
    cutoff = settings.kronos_train_cutoff_utc
    if not cutoff:
        raise ValueError(
            "kronos_train_cutoff_utc is unset; refusing to run a backtest that could "
            "score data Kronos trained on (contamination)."
        )
```

And inside the per-symbol loop, after `sdf = (...).sort("open_time_utc")` and before `anchors = select_anchors(...)` (around line 148), restrict the anchor range to post-cutoff bars:

```python
            times = sdf["open_time_utc"].to_list()
            lo = eligible_anchor_lo(times, cutoff)
            eligible = sdf.slice(lo)  # only bars whose targets are out-of-sample
            if eligible.height <= lookback + horizon:
                logger.warning(f"Not enough post-cutoff bars for {symbol}/{interval}")
                continue
            sdf = eligible
```

(The existing `select_anchors(sdf.height, ...)` and `_series_anchor_inputs(sdf, ...)` lines below then operate on the post-cutoff slice unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest backend/tests/test_cutoff_guard.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/data/backtest.py backend/tests/test_cutoff_guard.py
git commit -m "feat(backtest): hard post-cutoff guard to keep the record out-of-sample"
```

---

## Task 3: Naive-baseline directional metric (backtest)

**Files:**
- Modify: `backend/app/data/backtest.py`
- Test: `backend/tests/test_baseline_metric.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_baseline_metric.py
import numpy as np
import pytest

pytest.importorskip("pandas")
from app.data import backtest as bt


def test_baseline_directional_persistence():
    # prev->anchor went UP (100->101); persistence predicts UP.
    # actual_last 105 > anchor 101 -> actually UP -> baseline correct.
    assert bt.baseline_directional(prev_close=100.0, anchor_close=101.0, actual_last=105.0) is True
    # prev->anchor UP but actual DOWN -> baseline wrong.
    assert bt.baseline_directional(prev_close=100.0, anchor_close=101.0, actual_last=99.0) is False


def test_aggregate_includes_baseline():
    per = [
        {"pred": np.array([102.0]), "lo": np.array([100.0]), "hi": np.array([103.0]),
         "actual": np.array([102.0]), "anchor_close": 100.0, "prev_close": 99.0},
        {"pred": np.array([98.0]), "lo": np.array([97.0]), "hi": np.array([101.0]),
         "actual": np.array([96.0]), "anchor_close": 100.0, "prev_close": 101.0},
    ]
    agg, _ = bt.aggregate_metrics(per)
    assert "baseline_directional_pct" in agg
    assert 0.0 <= agg["baseline_directional_pct"] <= 1.0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest backend/tests/test_baseline_metric.py -v`
Expected: FAIL (`baseline_directional` not defined / key missing).

- [ ] **Step 3: Implement**

In `backend/app/data/backtest.py`:

Add the pure helper after `per_anchor_metrics` (after line 70):

```python
def baseline_directional(prev_close: float, anchor_close: float, actual_last: float) -> bool:
    """Persistence baseline: predict the next move repeats the last observed move
    (sign of anchor_close - prev_close), score against the realized last step."""
    pred_dir = np.sign(anchor_close - prev_close)
    actual_dir = np.sign(actual_last - anchor_close)
    return bool(pred_dir == actual_dir)
```

Add `baseline_directional_pct` to `METRICS_SCHEMA` (after `directional_pct` on line 36):

```python
    "directional_pct": pl.Float64, "baseline_directional_pct": pl.Float64,
```

In `aggregate_metrics`, extend the empty-return dict and the aggregate dict. Replace the empty return (lines 76-77) with:

```python
        return ({"n_anchors": 0, "directional_pct": 0.0, "baseline_directional_pct": 0.0,
                 "mape": 0.0, "band_coverage": 0.0, "band_nominal": _band_nominal()}, [])
```

Add a baseline accumulator: after `dirs, mapes, covs = [], [], []` (line 78) add `bdirs = []`, then inside the `for a in per:` loop (after line 85 `covs.append(...)`) add:

```python
        bdirs.append(1.0 if baseline_directional(a["prev_close"], a["anchor_close"], a["actual"][-1]) else 0.0)
```

And add to the `agg` dict (after `"directional_pct": float(np.mean(dirs)),` line 92):

```python
        "baseline_directional_pct": float(np.mean(bdirs)),
```

- [ ] **Step 4: Thread `prev_close` into the per-anchor records**

In `_series_anchor_inputs`, the `meta.append({...})` block (lines 117-121) adds `anchor_close`. Add `prev_close` alongside it:

```python
            "prev_close": float(closes[t - 2]) if t >= 2 else float(closes[t - 1]),
```

In `compute_backtest`, where `per.append({...})` is built (lines 168-169), add `prev_close`:

```python
                per.append({"pred": pred, "lo": lo, "hi": hi, "actual": mt["actual"],
                            "anchor_close": mt["anchor_close"], "prev_close": mt["prev_close"]})
```

- [ ] **Step 5: Run tests (incl. the existing backtest suite for regressions)**

Run: `.venv/Scripts/python -m pytest backend/tests/test_baseline_metric.py backend/tests/test_backtest.py -v`
Expected: PASS (new tests pass; existing `test_compute_backtest_produces_three_tables` still passes — note it sets a recent synthetic date 2026-01-01 which is post-cutoff, so the guard keeps anchors).

- [ ] **Step 6: Commit**

```bash
git add backend/app/data/backtest.py backend/tests/test_baseline_metric.py
git commit -m "feat(backtest): persistence baseline directional accuracy column"
```

---

## Task 4: Immutable, append-only live forecast log

**Files:**
- Modify: `backend/app/data/lake_paths.py`, `backend/app/data/predictions.py`
- Test: `backend/tests/test_forecast_log.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_forecast_log.py
import polars as pl
import pytest

from app.data import predictions as pr


def test_forecast_id_is_deterministic():
    a = pr.forecast_id("BTCUSDT", "1h", "sampled", 256, "2026-06-06T00:00:00+00:00")
    b = pr.forecast_id("BTCUSDT", "1h", "sampled", 256, "2026-06-06T00:00:00+00:00")
    c = pr.forecast_id("ETHUSDT", "1h", "sampled", 256, "2026-06-06T00:00:00+00:00")
    assert a == b and a != c


def test_append_forecast_log_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr(pr.settings, "gold_path", tmp_path / "gold", raising=False)
    df1 = pl.DataFrame({"forecast_id": ["x"], "generated_at_utc": ["2026-06-06T00:00:00+00:00"]})
    df2 = pl.DataFrame({"forecast_id": ["y"], "generated_at_utc": ["2026-06-06T01:00:00+00:00"]})
    p1 = pr.append_forecast_log(df1)
    p2 = pr.append_forecast_log(df2)
    assert p1 != p2  # distinct files, nothing overwritten
    combined = pl.read_parquet(str((tmp_path / "gold" / "forecast_log" / "*.parquet")))
    assert set(combined["forecast_id"]) == {"x", "y"}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest backend/tests/test_forecast_log.py -v`
Expected: FAIL (`forecast_id` / `append_forecast_log` not defined).

- [ ] **Step 3: Add the path helper**

In `backend/app/data/lake_paths.py`, add after `gold_price_predictions_dir` (after line 42):

```python
def gold_forecast_log_dir() -> Path:
    return settings.gold_path / "forecast_log"


def gold_forecast_outcomes_dir() -> Path:
    return settings.gold_path / "forecast_outcomes"


def gold_track_record_dir() -> Path:
    return settings.gold_path / "track_record_metrics"
```

- [ ] **Step 4: Implement the log functions in predictions.py**

In `backend/app/data/predictions.py`, add imports at the top (extend the existing `lake_paths` import on line 20 and add `hashlib`):

```python
import hashlib
from app.data.lake_paths import ensure_dir, gold_forecast_log_dir, gold_price_predictions_dir
```

Add near the top after `MIN_HISTORY` (after line 49):

```python
def forecast_id(symbol: str, interval: str, mode: str, lookback: int, generated_at: str) -> str:
    raw = f"{symbol}|{interval}|{mode}|{lookback}|{generated_at}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _params_hash() -> str:
    raw = (f"{settings.prediction_temperature}|{settings.prediction_top_p}|"
           f"{settings.prediction_sample_count}|{settings.prediction_band_low}|"
           f"{settings.prediction_band_high}")
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def append_forecast_log(df: pl.DataFrame) -> Path:
    """Append a run's forecasts to the immutable log as a NEW file. Never
    overwrites: the file name is derived from the run's max generated_at."""
    if df.is_empty():
        logger.warning("No forecasts to append to the log")
        return Path("")
    target_dir = ensure_dir(gold_forecast_log_dir())
    stamp = str(df["generated_at_utc"].max()).replace(":", "").replace("-", "").replace("+", "p").replace(".", "_")
    out = target_dir / f"forecast_log_{stamp}.parquet"
    if out.exists():
        logger.warning(f"Forecast log file already exists, skipping append: {out}")
        return out
    df.write_parquet(str(out))
    logger.info(f"Appended {len(df)} rows to forecast log: {out}")
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest backend/tests/test_forecast_log.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/data/lake_paths.py backend/app/data/predictions.py backend/tests/test_forecast_log.py
git commit -m "feat(predictions): immutable append-only forecast log"
```

---

## Task 5: Emit provenance columns and write the log from the pipeline

**Files:**
- Modify: `backend/app/data/predictions.py`
- Test: `backend/tests/test_predictions.py` (add a case)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_predictions.py`:

```python
def test_compute_emits_provenance_and_anchor(monkeypatch, tmp_path):
    import polars as pl, numpy as np, pandas as pd
    from app.data import predictions as pr

    # tiny silver dataset, 300 hourly bars for one symbol
    base = tmp_path / "silver" / "market_candles" / "source=binance" / "symbol=BTCUSDT" / "interval=1h" / "date=2026-06-01"
    base.mkdir(parents=True, exist_ok=True)
    ts = pd.date_range("2026-05-01", periods=300, freq="h", tz="UTC")
    price = np.linspace(100, 130, 300)
    pl.DataFrame({
        "symbol": ["BTCUSDT"] * 300, "interval": ["1h"] * 300,
        "open_time_utc": [t.isoformat() for t in ts],
        "open": price, "high": price + 1, "low": price - 1, "close": price,
        "volume": np.full(300, 10.0), "quote_volume": np.full(300, 1.0), "trade_count": [1] * 300,
    }).write_parquet(str(base / "candles.parquet"))

    class Stub:
        def predict_batch(self, df_list, x_timestamp_list, y_timestamp_list, pred_len, **kw):
            return [pd.DataFrame({c: np.full(pred_len, float(df["close"].iloc[-1]) + 1)
                                  for c in ["open", "high", "low", "close", "volume"]}) for df in df_list]

    monkeypatch.setattr(pr, "get_predictor", lambda: Stub())
    monkeypatch.setattr(pr.settings, "prediction_intervals", "1h")
    monkeypatch.setattr(pr.settings, "default_symbols", "BTCUSDT")
    monkeypatch.setattr(pr.settings, "prediction_lookbacks", "256")
    monkeypatch.setattr(pr.settings, "prediction_modes", "deterministic")

    df = pr.compute_price_predictions(tmp_path / "silver")
    for col in ("forecast_id", "source", "anchor_close", "prev_close", "model_version", "horizon"):
        assert col in df.columns
    assert (df["source"] == "live").all()
    assert df["anchor_close"].n_unique() >= 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest backend/tests/test_predictions.py::test_compute_emits_provenance_and_anchor -v`
Expected: FAIL (columns missing).

- [ ] **Step 3: Extend the schema and `_emit`**

In `backend/app/data/predictions.py`, extend `PREDICTION_SCHEMA` (insert after line 33 `"interval": pl.Utf8,`):

```python
    "forecast_id": pl.Utf8,
    "source": pl.Utf8,
    "model_version": pl.Utf8,
    "params_hash": pl.Utf8,
    "horizon": pl.Int64,
    "prev_close": pl.Float64,
    "anchor_close": pl.Float64,
```

Replace `_emit` (lines 86-96) with a version that stamps provenance + anchor:

```python
def _emit(rows, symbol, interval, mode, lookback, generated_at, y_ts, horizon,
          prev_close, anchor_close, o, h, l, c, v, blo, bhi):
    fid = forecast_id(symbol, interval, mode, lookback, generated_at)
    for step in range(horizon):
        rows.append({
            "symbol": symbol, "interval": interval,
            "forecast_id": fid, "source": "live",
            "model_version": settings.prediction_model, "params_hash": _params_hash(),
            "horizon": horizon, "prev_close": prev_close, "anchor_close": anchor_close,
            "mode": mode, "lookback": lookback,
            "generated_at_utc": generated_at,
            "forecast_time_utc": y_ts.iloc[step].isoformat(),
            "step": step + 1,
            "pred_open": float(o[step]), "pred_high": float(h[step]), "pred_low": float(l[step]),
            "pred_close": float(c[step]), "pred_volume": float(v[step]),
            "pred_close_low": float(blo[step]), "pred_close_high": float(bhi[step]),
        })
```

- [ ] **Step 4: Pass anchor/prev into `_emit` from `_build_interval_inputs` + call sites**

In `_build_interval_inputs`, the `metas.append((symbol, interval))` (line 78) must carry the last two closes. Change it to:

```python
        closes = sdf["close"].to_list()
        prev_close = float(closes[-2]) if len(closes) >= 2 else float(closes[-1])
        anchor_close = float(closes[-1])
        metas.append((symbol, interval, prev_close, anchor_close))
```

Update both `_emit` call sites in `compute_price_predictions` to unpack the wider meta tuple and pass the closes. For the deterministic branch (lines 144-149) change the loop header and call:

```python
                    for i, (symbol, _, prev_close, anchor_close) in enumerate(metas):
                        d = preds[i]
                        c = d["close"].to_numpy()
                        _emit(rows, symbol, interval, mode, lookback, generated_at, y_tss[i], horizon,
                              prev_close, anchor_close,
                              d["open"].to_numpy(), d["high"].to_numpy(), d["low"].to_numpy(), c,
                              d["volume"].to_numpy(), c, c)
```

For the sampled branch (lines 159-168):

```python
                    for i, (symbol, _, prev_close, anchor_close) in enumerate(metas):
                        def stack(col: str, idx=i) -> np.ndarray:
                            return np.stack([passes[p][idx][col].to_numpy() for p in range(n_samples)])

                        closes = stack("close")
                        _emit(rows, symbol, interval, mode, lookback, generated_at, y_tss[i], horizon,
                              prev_close, anchor_close,
                              np.median(stack("open"), axis=0), np.median(stack("high"), axis=0),
                              np.median(stack("low"), axis=0), np.median(closes, axis=0),
                              np.median(stack("volume"), axis=0),
                              np.quantile(closes, q_lo, axis=0), np.quantile(closes, q_hi, axis=0))
```

- [ ] **Step 5: Append to the log in the writer**

Change `write_gold_price_predictions` (lines 175-184) to ALSO append to the immutable log (keep the snapshot overwrite for the existing chart):

```python
def write_gold_price_predictions(df: pl.DataFrame) -> Path:
    if df.is_empty():
        logger.warning("No price predictions to write")
        return Path("")
    target_dir = ensure_dir(gold_price_predictions_dir())
    output_path = target_dir / "asset_price_predictions.parquet"
    df.write_parquet(str(output_path))  # latest snapshot (existing chart reads this)
    append_forecast_log(df)             # immutable record (scoring reads this)
    logger.info(f"Wrote gold price predictions: {output_path} ({len(df)} rows)")
    return output_path
```

- [ ] **Step 6: Run tests (new + existing predictions suite)**

Run: `.venv/Scripts/python -m pytest backend/tests/test_predictions.py -v`
Expected: PASS (new test passes; existing tests still pass — if an existing test asserts an exact column set, update it to use `>=`/subset comparison).

- [ ] **Step 7: Commit**

```bash
git add backend/app/data/predictions.py backend/tests/test_predictions.py
git commit -m "feat(predictions): provenance + anchor columns, append to immutable log"
```

---

## Task 6: Live scoring engine (matured forecasts → outcomes)

**Files:**
- Create: `backend/app/data/scoring.py`
- Test: `backend/tests/test_scoring.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_scoring.py
import polars as pl
import pytest
from app.data import scoring


def _log_row(fid, ftime, step, anchor=100.0, prev=99.0, pred=101.0):
    return {"forecast_id": fid, "source": "live", "symbol": "BTCUSDT", "interval": "1h",
            "mode": "sampled", "lookback": 256, "horizon": 1, "generated_at_utc": "2026-09-02T00:00:00+00:00",
            "forecast_time_utc": ftime, "step": step, "prev_close": prev, "anchor_close": anchor,
            "pred_close": pred, "pred_close_low": pred - 2, "pred_close_high": pred + 2}


def test_score_joins_actuals_and_skips_unmatured():
    log = pl.DataFrame([
        _log_row("a", "2026-09-02T01:00:00+00:00", 1),  # has an actual
        _log_row("b", "2999-01-01T00:00:00+00:00", 1),  # future: no actual yet
    ])
    actuals = pl.DataFrame({"symbol": ["BTCUSDT"], "interval": ["1h"],
                            "open_time_utc": ["2026-09-02T01:00:00+00:00"], "close": [101.5]})
    out = scoring.score_forecasts(log, actuals, already_scored=set())
    assert out.height == 1
    r = out.row(0, named=True)
    assert r["forecast_id"] == "a"
    assert r["actual_close"] == 101.5
    assert r["abs_error"] == pytest.approx(0.5)


def test_score_is_idempotent():
    log = pl.DataFrame([_log_row("a", "2026-09-02T01:00:00+00:00", 1)])
    actuals = pl.DataFrame({"symbol": ["BTCUSDT"], "interval": ["1h"],
                            "open_time_utc": ["2026-09-02T01:00:00+00:00"], "close": [101.5]})
    out = scoring.score_forecasts(log, actuals, already_scored={("a", 1)})
    assert out.height == 0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest backend/tests/test_scoring.py -v`
Expected: FAIL (`scoring` module missing).

- [ ] **Step 3: Implement `scoring.py`**

```python
# backend/app/data/scoring.py
"""Score matured live forecasts against realized silver candles -> outcomes.

Append-only and idempotent: only forecast rows whose forecast_time has passed,
have a realized actual, and are not already scored, are written."""

from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from app.core.logging import logger
from app.data.lake_paths import (
    ensure_dir, gold_forecast_log_dir, gold_forecast_outcomes_dir,
)

OUTCOMES_SCHEMA = {
    "forecast_id": pl.Utf8, "source": pl.Utf8, "symbol": pl.Utf8, "interval": pl.Utf8,
    "mode": pl.Utf8, "lookback": pl.Int64, "horizon": pl.Int64, "step": pl.Int64,
    "generated_at_utc": pl.Utf8, "forecast_time_utc": pl.Utf8,
    "prev_close": pl.Float64, "anchor_close": pl.Float64,
    "pred_close": pl.Float64, "pred_close_low": pl.Float64, "pred_close_high": pl.Float64,
    "actual_close": pl.Float64, "abs_error": pl.Float64, "pct_error": pl.Float64,
    "in_band": pl.Boolean, "scored_at_utc": pl.Utf8,
}

_KEEP = ["forecast_id", "source", "symbol", "interval", "mode", "lookback", "horizon",
         "step", "generated_at_utc", "forecast_time_utc", "prev_close", "anchor_close",
         "pred_close", "pred_close_low", "pred_close_high"]


def score_forecasts(log: pl.DataFrame, actuals: pl.DataFrame, already_scored: set) -> pl.DataFrame:
    """Pure: join log rows to realized closes, drop unmatured/already-scored,
    compute per-step error + band coverage."""
    if log.is_empty():
        return pl.DataFrame(schema=OUTCOMES_SCHEMA)
    act = actuals.select([
        pl.col("symbol"), pl.col("interval"),
        pl.col("open_time_utc").alias("forecast_time_utc"), pl.col("close").alias("actual_close"),
    ])
    joined = log.select(_KEEP).join(act, on=["symbol", "interval", "forecast_time_utc"], how="inner")
    if joined.is_empty():
        return pl.DataFrame(schema=OUTCOMES_SCHEMA)
    scored_at = datetime.now(UTC).isoformat()
    out = joined.with_columns([
        (pl.col("pred_close") - pl.col("actual_close")).abs().alias("abs_error"),
        ((pl.col("pred_close") - pl.col("actual_close")).abs() / pl.col("actual_close")).alias("pct_error"),
        ((pl.col("actual_close") >= pl.col("pred_close_low")) &
         (pl.col("actual_close") <= pl.col("pred_close_high"))).alias("in_band"),
        pl.lit(scored_at).alias("scored_at_utc"),
    ])
    if already_scored:
        keys = out.select(["forecast_id", "step"]).rows()
        mask = [k not in already_scored for k in keys]
        out = out.filter(pl.Series(mask))
    return out.select(list(OUTCOMES_SCHEMA.keys()))


def _read_glob(directory: Path, schema: dict) -> pl.DataFrame:
    files = list(directory.rglob("*.parquet"))
    if not files:
        return pl.DataFrame(schema=schema)
    return pl.scan_parquet([str(f) for f in files]).collect()


def compute_outcomes(silver_root: Path) -> pl.DataFrame:
    """Read the whole forecast log + existing outcomes + silver actuals; return
    only NEW outcomes (idempotent)."""
    log_files = list(gold_forecast_log_dir().rglob("*.parquet"))
    if not log_files:
        logger.warning("No forecast log to score")
        return pl.DataFrame(schema=OUTCOMES_SCHEMA)
    log = pl.scan_parquet([str(f) for f in log_files]).collect()

    silver_files = list((silver_root / "market_candles").rglob("*.parquet"))
    if not silver_files:
        return pl.DataFrame(schema=OUTCOMES_SCHEMA)
    actuals = pl.scan_parquet([str(f) for f in silver_files]).select(
        ["symbol", "interval", "open_time_utc", "close"]).collect()

    existing = _read_glob(gold_forecast_outcomes_dir(), OUTCOMES_SCHEMA)
    already = set(existing.select(["forecast_id", "step"]).rows()) if existing.height else set()
    return score_forecasts(log, actuals, already)


def write_outcomes(df: pl.DataFrame) -> Path:
    if df.is_empty():
        logger.info("No new outcomes to write")
        return Path("")
    target_dir = ensure_dir(gold_forecast_outcomes_dir())
    stamp = datetime.now(UTC).isoformat().replace(":", "").replace("-", "").replace(".", "_").replace("+", "p")
    out = target_dir / f"outcomes_{stamp}.parquet"
    df.write_parquet(str(out))
    logger.info(f"Wrote {len(df)} new outcomes: {out}")
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest backend/tests/test_scoring.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/data/scoring.py backend/tests/test_scoring.py
git commit -m "feat(scoring): idempotent live-forecast scoring engine"
```

---

## Task 7: Track-record rollup + fee-aware gate decision

**Files:**
- Create: `backend/app/data/track_record.py`
- Test: `backend/tests/test_track_record.py`, `backend/tests/test_gate.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_track_record.py
import polars as pl
from app.data import track_record as tr


def _outcome(fid, step, horizon, anchor, prev, pred, actual, lo, hi):
    return {"forecast_id": fid, "source": "live", "symbol": "BTCUSDT", "interval": "1h",
            "mode": "sampled", "lookback": 256, "horizon": horizon, "step": step,
            "generated_at_utc": "2026-09-02T00:00:00+00:00",
            "forecast_time_utc": f"2026-09-02T0{step}:00:00+00:00",
            "prev_close": prev, "anchor_close": anchor, "pred_close": pred,
            "pred_close_low": lo, "pred_close_high": hi, "actual_close": actual,
            "abs_error": abs(pred - actual), "pct_error": abs(pred - actual) / actual,
            "in_band": lo <= actual <= hi, "scored_at_utc": "2026-09-02T05:00:00+00:00"}


def test_rollup_directional_and_baseline():
    # one forecast, horizon 1: model predicts up (101>100), actual up (102) -> correct.
    # baseline: prev 99 -> anchor 100 = up, actual up -> baseline also correct.
    out = pl.DataFrame([_outcome("a", 1, 1, 100.0, 99.0, 101.0, 102.0, 99.0, 103.0)])
    roll = tr.rollup(out)
    r = roll.row(0, named=True)
    assert r["n_forecasts"] == 1
    assert r["directional_accuracy"] == 1.0
    assert r["baseline_directional_accuracy"] == 1.0
    assert r["band_coverage"] == 1.0
```

```python
# backend/tests/test_gate.py
from app.data import track_record as tr


def test_gate_passes_when_edge_beats_fees_and_baseline():
    d = tr.gate_decision(directional_accuracy=0.62, baseline=0.50,
                         avg_move_pct=0.02, band_coverage=0.78, band_nominal=0.8,
                         taker_fee_pct=0.001, min_coverage_ratio=0.8)
    assert d["pass"] is True
    assert d["net_edge_pct"] > 0


def test_gate_fails_when_fees_eat_the_edge():
    d = tr.gate_decision(directional_accuracy=0.505, baseline=0.50,
                         avg_move_pct=0.002, band_coverage=0.78, band_nominal=0.8,
                         taker_fee_pct=0.001, min_coverage_ratio=0.8)
    assert d["pass"] is False


def test_gate_fails_when_not_beating_baseline():
    d = tr.gate_decision(directional_accuracy=0.55, baseline=0.58,
                         avg_move_pct=0.05, band_coverage=0.8, band_nominal=0.8,
                         taker_fee_pct=0.001, min_coverage_ratio=0.8)
    assert d["pass"] is False
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest backend/tests/test_track_record.py backend/tests/test_gate.py -v`
Expected: FAIL (`track_record` module missing).

- [ ] **Step 3: Implement `track_record.py`**

```python
# backend/app/data/track_record.py
"""Aggregate scored outcomes into the public track-record metrics, and render the
go/no-go gate decision (fee-aware, baseline-relative)."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import polars as pl

from app.core.config import settings
from app.core.logging import logger
from app.data.lake_paths import ensure_dir, gold_forecast_outcomes_dir, gold_track_record_dir

ROLLUP_SCHEMA = {
    "symbol": pl.Utf8, "interval": pl.Utf8, "mode": pl.Utf8, "lookback": pl.Int64,
    "source": pl.Utf8, "n_forecasts": pl.Int64,
    "directional_accuracy": pl.Float64, "baseline_directional_accuracy": pl.Float64,
    "mape": pl.Float64, "band_coverage": pl.Float64, "band_nominal": pl.Float64,
    "avg_move_pct": pl.Float64, "generated_at_utc": pl.Utf8,
}


def rollup(outcomes: pl.DataFrame) -> pl.DataFrame:
    """One row per (symbol, interval, mode, lookback, source). Directional metrics
    use the LAST step of each forecast (its full horizon)."""
    if outcomes.is_empty():
        return pl.DataFrame(schema=ROLLUP_SCHEMA)
    generated_at = datetime.now(UTC).isoformat()
    band_nominal = round(settings.prediction_band_high - settings.prediction_band_low, 6)
    rows = []
    group_cols = ["symbol", "interval", "mode", "lookback", "source"]
    for key, g in outcomes.group_by(group_cols, maintain_order=True):
        last = g.filter(pl.col("step") == pl.col("horizon"))
        n = last.height
        if n == 0:
            continue
        anchor = last["anchor_close"].to_numpy()
        prev = last["prev_close"].to_numpy()
        pred = last["pred_close"].to_numpy()
        actual = last["actual_close"].to_numpy()
        dir_ok = np.sign(pred - anchor) == np.sign(actual - anchor)
        base_ok = np.sign(anchor - prev) == np.sign(actual - anchor)
        rows.append({
            "symbol": key[0], "interval": key[1], "mode": key[2], "lookback": key[3],
            "source": key[4], "n_forecasts": n,
            "directional_accuracy": float(np.mean(dir_ok)),
            "baseline_directional_accuracy": float(np.mean(base_ok)),
            "mape": float(g["pct_error"].mean()),
            "band_coverage": float(g["in_band"].mean()),
            "band_nominal": band_nominal,
            "avg_move_pct": float(np.mean(np.abs(actual - anchor) / anchor)),
            "generated_at_utc": generated_at,
        })
    return pl.DataFrame(rows, schema=ROLLUP_SCHEMA)


def gate_decision(directional_accuracy: float, baseline: float, avg_move_pct: float,
                  band_coverage: float, band_nominal: float, taker_fee_pct: float,
                  min_coverage_ratio: float) -> dict:
    """A directional trade earns ~avg_move_pct when right, loses it when wrong, and
    pays a round-trip fee. Pass requires positive net edge, beating the baseline,
    and a calibrated band."""
    round_trip_fee = 2 * taker_fee_pct
    net_edge = (2 * directional_accuracy - 1) * avg_move_pct - round_trip_fee
    beats_baseline = directional_accuracy > baseline
    calibrated = band_nominal > 0 and (band_coverage / band_nominal) >= min_coverage_ratio
    return {
        "pass": bool(net_edge > 0 and beats_baseline and calibrated),
        "net_edge_pct": net_edge, "beats_baseline": beats_baseline, "calibrated": calibrated,
    }


def compute_track_record(outcomes_root: Path | None = None) -> pl.DataFrame:
    directory = outcomes_root or gold_forecast_outcomes_dir()
    files = list(directory.rglob("*.parquet"))
    if not files:
        logger.warning("No outcomes to roll up")
        return pl.DataFrame(schema=ROLLUP_SCHEMA)
    outcomes = pl.scan_parquet([str(f) for f in files]).collect()
    return rollup(outcomes)


def write_track_record(df: pl.DataFrame) -> Path:
    if df.is_empty():
        logger.warning("No track-record metrics to write")
        return Path("")
    out = ensure_dir(gold_track_record_dir()) / "track_record_metrics.parquet"
    df.write_parquet(str(out))  # rollup is recomputable, so overwrite is fine
    logger.info(f"Wrote track-record metrics: {out} ({len(df)} rows)")
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest backend/tests/test_track_record.py backend/tests/test_gate.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/data/track_record.py backend/tests/test_track_record.py backend/tests/test_gate.py
git commit -m "feat(track-record): rollup with baseline + fee-aware gate decision"
```

---

## Task 8: DuckDB views for the new gold tables

**Files:**
- Modify: `backend/app/data/duckdb_repo.py`

- [ ] **Step 1: Add the views**

In `_create_views`, add three path strings after `gold_bt_horizon` (after line 27):

```python
        gold_forecast_log = str(gold_root / "forecast_log" / "*.parquet")
        gold_forecast_outcomes = str(gold_root / "forecast_outcomes" / "*.parquet")
        gold_track_record = str(gold_root / "track_record_metrics" / "*.parquet")
```

And three entries in the `views` dict (after the `v_asset_backtest_horizon` entry, line 61):

```python
            "v_forecast_log": f"""
                CREATE OR REPLACE VIEW v_forecast_log AS
                SELECT * FROM read_parquet('{gold_forecast_log}', hive_partitioning=true)
            """,
            "v_forecast_outcomes": f"""
                CREATE OR REPLACE VIEW v_forecast_outcomes AS
                SELECT * FROM read_parquet('{gold_forecast_outcomes}', hive_partitioning=true)
            """,
            "v_track_record_metrics": f"""
                CREATE OR REPLACE VIEW v_track_record_metrics AS
                SELECT * FROM read_parquet('{gold_track_record}', hive_partitioning=true)
            """,
```

- [ ] **Step 2: Verify it imports and views build (no parquet yet → warnings are fine)**

Run: `.venv/Scripts/python -c "from app.data.duckdb_repo import DuckDBRepo; r=DuckDBRepo(); r.close(); print('ok')"`
Expected: prints `ok` (per-view warnings for missing parquet are expected and handled).

- [ ] **Step 3: Commit**

```bash
git add backend/app/data/duckdb_repo.py
git commit -m "feat(duckdb): views for forecast log, outcomes, track-record metrics"
```

---

## Task 9: Track-record API endpoint

**Files:**
- Modify: `backend/app/models/api_models.py`, `backend/app/main.py`
- Create: `backend/app/api/routes_track_record.py`
- Test: `backend/tests/test_track_record_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_track_record_api.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_track_record_summary_shape_when_empty():
    # No gold parquet in the test env -> endpoint must degrade to empty, not 500.
    res = client.get("/track-record/summary?symbol=BTCUSDT&interval=1h")
    assert res.status_code == 200
    body = res.json()
    assert body["symbol"] == "BTCUSDT"
    assert "live" in body and "backtest" in body
    assert isinstance(body["live"], list) and isinstance(body["backtest"], list)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest backend/tests/test_track_record_api.py -v`
Expected: FAIL (404 — route not registered).

- [ ] **Step 3: Add the response model**

In `backend/app/models/api_models.py`, append:

```python
class TrackRecordResponse(BaseModel):
    symbol: str
    interval: str
    live: list[dict]
    backtest: list[dict]
```

- [ ] **Step 4: Implement the route**

```python
# backend/app/api/routes_track_record.py
from fastapi import APIRouter, HTTPException, Query

from app.core.logging import logger
from app.data.duckdb_repo import DuckDBRepo
from app.models.api_models import TrackRecordResponse

router = APIRouter(tags=["track-record"])

VALID_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}


@router.get("/track-record/summary", response_model=TrackRecordResponse)
def get_summary(symbol: str = Query(...), interval: str = Query("1h")) -> TrackRecordResponse:
    if symbol not in VALID_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Invalid symbol. Must be one of {sorted(VALID_SYMBOLS)}")
    live, backtest = [], []
    try:
        with DuckDBRepo() as repo:
            live = repo.query(
                """SELECT symbol, interval, mode, lookback, n_forecasts, directional_accuracy,
                          baseline_directional_accuracy, mape, band_coverage, band_nominal,
                          avg_move_pct, generated_at_utc
                   FROM v_track_record_metrics WHERE symbol = :symbol AND interval = :interval""",
                {"symbol": symbol, "interval": interval},
            )
            backtest = repo.query(
                """SELECT symbol, interval, n_anchors, directional_pct, baseline_directional_pct,
                          mape, band_coverage, band_nominal, horizon, generated_at_utc
                   FROM v_asset_backtest_metrics WHERE symbol = :symbol AND interval = :interval""",
                {"symbol": symbol, "interval": interval},
            )
    except Exception as e:
        logger.warning(f"Track-record query failed (tables may be ungenerated): {e}")
    return TrackRecordResponse(symbol=symbol, interval=interval, live=live, backtest=backtest)
```

- [ ] **Step 5: Register the router**

In `backend/app/main.py`, add the import next to the other routers (after line 16):

```python
from app.api.routes_track_record import router as track_record_router
```

And include it (after line 104 `app.include_router(backtest_router, prefix="")`):

```python
app.include_router(track_record_router, prefix="")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest backend/tests/test_track_record_api.py -v`
Expected: PASS (1 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes_track_record.py backend/app/models/api_models.py backend/app/main.py backend/tests/test_track_record_api.py
git commit -m "feat(api): /track-record/summary (live + backtest)"
```

---

## Task 10: Pipeline scripts + Makefile targets

**Files:**
- Create: `scripts/build_scoring.py`, `scripts/build_track_record.py`, `scripts/evaluate_gate.py`
- Modify: `Makefile`

- [ ] **Step 1: Write `build_scoring.py`**

First open `scripts/build_predictions.py` and copy its exact import/bootstrap preamble (how it puts `backend/` on the path and constructs the `rich` `Console`). Match it exactly — the snippet below assumes the `sys.path.insert` style; if `build_predictions.py` relies on the editable install instead, drop the `sys.path` line.

```python
# scripts/build_scoring.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from rich.console import Console  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.data.scoring import compute_outcomes, write_outcomes  # noqa: E402

console = Console()


def main() -> None:
    console.print("[bold green]=== Scoring matured forecasts ===[/bold green]")
    new = compute_outcomes(settings.silver_path)
    if new.is_empty():
        console.print("[yellow]No newly-matured forecasts to score.[/yellow]")
        return
    out = write_outcomes(new)
    console.print(f"[green]Scored {len(new)} new forecast-steps -> {out}[/green]")


if __name__ == "__main__":
    main()
```

(Confirm the `sys.path` / import pattern against an existing script such as `scripts/build_predictions.py` and match it exactly — some scripts rely on `pyproject` editable install instead of the `sys.path` insert.)

- [ ] **Step 2: Write `build_track_record.py`**

```python
# scripts/build_track_record.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from rich.console import Console  # noqa: E402

from app.data.track_record import compute_track_record, write_track_record  # noqa: E402

console = Console()


def main() -> None:
    console.print("[bold green]=== Rolling up track record ===[/bold green]")
    df = compute_track_record()
    if df.is_empty():
        console.print("[yellow]No outcomes to roll up yet.[/yellow]")
        return
    out = write_track_record(df)
    console.print(f"[green]Wrote {len(df)} rollup rows -> {out}[/green]")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write `evaluate_gate.py`**

```python
# scripts/evaluate_gate.py
"""Print the go/no-go verdict from the out-of-sample record."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.data.track_record import compute_track_record, gate_decision  # noqa: E402

console = Console()


def main() -> None:
    roll = compute_track_record()
    if roll.is_empty():
        console.print("[yellow]No track record yet — cannot evaluate the gate.[/yellow]")
        return
    table = Table(title="Go/No-Go Gate (out-of-sample, fee-aware)")
    for col in ("symbol", "interval", "n", "dir", "baseline", "coverage", "net_edge%", "PASS"):
        table.add_column(col)
    any_pass = False
    for r in roll.iter_rows(named=True):
        d = gate_decision(
            directional_accuracy=r["directional_accuracy"], baseline=r["baseline_directional_accuracy"],
            avg_move_pct=r["avg_move_pct"], band_coverage=r["band_coverage"],
            band_nominal=r["band_nominal"], taker_fee_pct=settings.taker_fee_pct,
            min_coverage_ratio=settings.gate_min_band_coverage_ratio,
        )
        any_pass = any_pass or d["pass"]
        table.add_row(r["symbol"], r["interval"], str(r["n_forecasts"]),
                      f"{r['directional_accuracy']:.3f}", f"{r['baseline_directional_accuracy']:.3f}",
                      f"{r['band_coverage']:.2f}", f"{d['net_edge_pct'] * 100:.3f}",
                      "[green]YES[/green]" if d["pass"] else "[red]no[/red]")
    console.print(table)
    console.print(f"\n[bold]{'PROCEED to Phase 2' if any_pass else 'DO NOT monetize yet'}[/bold]")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add Makefile targets**

In `Makefile`, add to `.PHONY` and add targets near `predict:` (after line ~ the `predict` target):

```makefile
score:
	$(PYTHON) scripts/build_scoring.py

track-record:
	$(PYTHON) scripts/build_track_record.py

gate:
	$(PYTHON) scripts/evaluate_gate.py
```

- [ ] **Step 5: Smoke-test the scripts run (empty data → graceful messages)**

Run: `.venv/Scripts/python scripts/build_scoring.py && .venv/Scripts/python scripts/build_track_record.py && .venv/Scripts/python scripts/evaluate_gate.py`
Expected: each prints its "no data yet" message without error (exit 0).

- [ ] **Step 6: Commit**

```bash
git add scripts/build_scoring.py scripts/build_track_record.py scripts/evaluate_gate.py Makefile
git commit -m "feat(scripts): scoring, rollup, and go/no-go gate runners"
```

---

## Task 11: Wire the live record + scoring into CI

**Files:**
- Modify: `.github/workflows/refresh-data.yml`

> **Real-data note:** the record is only meaningful on real post-cutoff prices. Before relying on the gate, ensure `ingest_market_data.py` is pulling real Binance history from a non-geo-blocked source (e.g. run the ingest from an allowed region/runner, or set `BINANCE_BASE_URL` to a reachable endpoint). Until then the pipeline still runs, but `evaluate_gate.py` output is not trustworthy.

- [ ] **Step 1: Add the new pipeline steps**

In `.github/workflows/refresh-data.yml`, in the "Build snapshot" run block (lines 47-53), after `python scripts/build_predictions.py`, append:

```yaml
          python scripts/build_backtest.py        # out-of-sample reconstructed record
          python scripts/build_scoring.py         # score matured live forecasts
          python scripts/build_track_record.py    # roll up live accuracy + baseline
          python scripts/evaluate_gate.py         # print the verdict in CI logs
```

- [ ] **Step 2: Commit the new gold tables**

In the "Commit snapshot to main" step (lines 55-65), the `git add -f` line currently adds `data/lakehouse/silver data/lakehouse/gold`. `forecast_log`, `forecast_outcomes`, and `track_record_metrics` live under `gold/`, so they are already included. Confirm `.gitignore` does not exclude them; if it does, add explicit un-ignores. No code change needed beyond verifying.

- [ ] **Step 3: Validate the workflow YAML**

Run: `.venv/Scripts/python -c "import yaml; yaml.safe_load(open('.github/workflows/refresh-data.yml')); print('valid yaml')"`
Expected: prints `valid yaml`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/refresh-data.yml
git commit -m "ci: append immutable log, backtest, score, rollup, and gate each run"
```

---

## Task 12: Track Record card (frontend)

**Files:**
- Modify: `frontend/src/api/client.ts`, `frontend/src/pages/Dashboard.tsx`
- Create: `frontend/src/components/TrackRecord.tsx`

- [ ] **Step 1: Add the API client function**

In `frontend/src/api/client.ts`, add an interface and a fetch function (follow the existing `getForecast` pattern + `fetchApi<T>`):

```typescript
export interface TrackRecordRow {
  symbol: string; interval: string; mode?: string; lookback?: number;
  n_forecasts?: number; n_anchors?: number;
  directional_accuracy?: number; directional_pct?: number;
  baseline_directional_accuracy?: number; baseline_directional_pct?: number;
  mape: number; band_coverage: number; band_nominal: number;
}

export interface TrackRecordResponse {
  symbol: string; interval: string;
  live: TrackRecordRow[]; backtest: TrackRecordRow[];
}

export function getTrackRecord(symbol: string, interval = '1h'): Promise<TrackRecordResponse> {
  return fetchApi<TrackRecordResponse>(`/track-record/summary?symbol=${symbol}&interval=${interval}`);
}
```

- [ ] **Step 2: Create the component**

```tsx
// frontend/src/components/TrackRecord.tsx
import { useEffect, useState } from 'react';
import { getTrackRecord, TrackRecordResponse } from '../api/client';
import { useRefresh } from '../refresh';

const pct = (v?: number) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`);

export function TrackRecord({ symbol = 'BTCUSDT', interval = '1h' }: { symbol?: string; interval?: string }) {
  const { tick } = useRefresh();
  const [data, setData] = useState<TrackRecordResponse | null>(null);

  useEffect(() => {
    getTrackRecord(symbol, interval).then(setData).catch(() => setData(null));
  }, [symbol, interval, tick]);

  const live = data?.live?.[0];
  const bt = data?.backtest?.[0];

  return (
    <div className="rounded-xl border border-white/10 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-wide">VERIFIED TRACK RECORD — {symbol} {interval}</h2>
        <span className="text-xs opacity-60">out-of-sample · scored vs. realized price</span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-4">
        <Section title="Live (published before outcome)" dir={live?.directional_accuracy}
                 base={live?.baseline_directional_accuracy} cov={live?.band_coverage}
                 nominal={live?.band_nominal} mape={live?.mape} n={live?.n_forecasts} />
        <Section title="Backtest (historical simulation, OOS)" dir={bt?.directional_pct}
                 base={bt?.baseline_directional_pct} cov={bt?.band_coverage}
                 nominal={bt?.band_nominal} mape={bt?.mape} n={bt?.n_anchors} />
      </div>
      <p className="mt-3 text-[11px] leading-relaxed opacity-50">
        Informational only — not financial advice. Past performance does not guarantee future results.
        Backtest is a historical simulation restricted to data after the model's training cutoff.
      </p>
    </div>
  );
}

function Section(p: { title: string; dir?: number; base?: number; cov?: number; nominal?: number; mape?: number; n?: number }) {
  return (
    <div className="rounded-lg bg-white/5 p-3">
      <div className="text-xs opacity-70">{p.title}</div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
        <Stat label="Directional" value={pct(p.dir)} sub={`baseline ${pct(p.base)}`} />
        <Stat label="Band coverage" value={pct(p.cov)} sub={`nominal ${pct(p.nominal)}`} />
        <Stat label="MAPE" value={p.mape == null ? '—' : `${(p.mape * 100).toFixed(2)}%`} />
        <Stat label="Samples" value={p.n == null ? '—' : String(p.n)} />
      </div>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase opacity-50">{label}</div>
      <div className="font-semibold">{value}</div>
      {sub && <div className="text-[11px] opacity-50">{sub}</div>}
    </div>
  );
}
```

(Confirm the `useRefresh` export name/signature in `frontend/src/refresh.tsx` and match it — the Explore report indicates a `tick`-based context.)

- [ ] **Step 3: Mount it in the Dashboard**

In `frontend/src/pages/Dashboard.tsx`, import and render `<TrackRecord />` as a prominent card between `<AssetChart />` and `<TabbedPanel />` (keep the existing fade-up delay pattern).

- [ ] **Step 4: Verify the build**

Run: `cd frontend && npm run build`
Expected: `tsc -b && vite build` completes with no type errors; `dist/` regenerated.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/components/TrackRecord.tsx frontend/src/pages/Dashboard.tsx frontend/dist
git commit -m "feat(frontend): verified Track Record card (live + backtest)"
```

---

## Task 13: Landing hero + waitlist

**Files:**
- Create: `frontend/src/components/WaitlistHero.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`, `frontend/.env.example` (or create), `README` note

> No backend/PII storage in Phase 1. The waitlist posts to a hosted form provider (Formspree/Tally/ConvertKit). Set the endpoint via `VITE_WAITLIST_URL`.

- [ ] **Step 1: Create the hero**

```tsx
// frontend/src/components/WaitlistHero.tsx
import { useState } from 'react';

const WAITLIST_URL = import.meta.env.VITE_WAITLIST_URL || '';

export function WaitlistHero() {
  const [email, setEmail] = useState('');
  const [done, setDone] = useState(false);
  const [err, setErr] = useState('');

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr('');
    if (!WAITLIST_URL) { setErr('Waitlist not configured yet.'); return; }
    try {
      const res = await fetch(WAITLIST_URL, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ email }),
      });
      if (!res.ok) throw new Error(String(res.status));
      setDone(true);
    } catch {
      setErr('Could not submit — please try again.');
    }
  }

  return (
    <div className="rounded-xl border border-white/10 p-6 text-center">
      <h1 className="text-xl font-bold">Crypto forecasts you can actually verify</h1>
      <p className="mx-auto mt-2 max-w-xl text-sm opacity-70">
        Every forecast is logged before the outcome and scored against the real price.
        See the track record below. Get real-time forecasts + alerts when we launch Pro.
      </p>
      {done ? (
        <p className="mt-4 text-sm text-emerald-400">You're on the list. We'll be in touch.</p>
      ) : (
        <form onSubmit={submit} className="mx-auto mt-4 flex max-w-md gap-2">
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                 placeholder="you@email.com"
                 className="flex-1 rounded-lg bg-white/5 px-3 py-2 text-sm outline-none" />
          <button className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-black">
            Join waitlist
          </button>
        </form>
      )}
      {err && <p className="mt-2 text-xs text-red-400">{err}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Mount it at the top of the Dashboard**

In `frontend/src/pages/Dashboard.tsx`, render `<WaitlistHero />` as the first card (above `<TickerBar />`).

- [ ] **Step 3: Document the env var**

Add `VITE_WAITLIST_URL=` to `frontend/.env.example` (create the file if missing) with a comment pointing at the chosen provider.

- [ ] **Step 4: Verify the build**

Run: `cd frontend && npm run build`
Expected: build succeeds; `dist/` regenerated.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/WaitlistHero.tsx frontend/src/pages/Dashboard.tsx frontend/.env.example frontend/dist
git commit -m "feat(frontend): landing hero + hosted waitlist form"
```

---

## Task 14: Full-suite verification + gate dry-run

**Files:** none (verification only)

- [ ] **Step 1: Run the entire backend suite**

Run: `.venv/Scripts/python -m pytest backend/tests -q`
Expected: all tests pass (the original 33 + the ~14 new tests), no failures.

- [ ] **Step 2: End-to-end pipeline on local data**

Run (only if the `[predict]` extra is installed):
```bash
make seed && make ingest && make silver && make gold && make predict && make backtest && make score && make track-record && make gate
```
Expected: `make gate` prints the verdict table. On synthetic data, treat the verdict as a smoke test only (see the real-data caveat).

NOTE: there is no `backtest` Makefile target today — confirm/add one (`backtest:\n\t$(PYTHON) scripts/build_backtest.py`) if missing, mirroring Task 10.

- [ ] **Step 3: Frontend build**

Run: `cd frontend && npm run build`
Expected: clean build.

- [ ] **Step 4: Final commit (if Task 14 added the `backtest` target)**

```bash
git add Makefile
git commit -m "chore: add backtest Makefile target; Phase 1 proof engine complete"
```

---

## Self-Review notes (carried forward)

- **Synthetic-data risk:** the gate is only meaningful on real post-cutoff prices (Task 11 note). This is the single biggest threat to the validity of the whole phase.
- **Two write paths for live forecasts:** the existing snapshot (`asset_price_predictions.parquet`, read by the current chart) is kept; the immutable log is added alongside. They must not diverge in schema — the log is a superset.
- **Existing-test fragility:** `test_predictions.py` may assert an exact column set; switch such assertions to subset checks when the schema widens (Task 5, Step 6).
- **`useRefresh`/`refresh.tsx` and `Dashboard.tsx` exact APIs** must be confirmed against the live (uncommitted) frontend before wiring Tasks 12–13.
