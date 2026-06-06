# Backtesting & Model Accuracy — Design

Date: 2026-06-06
Status: Approved (brainstorm) → ready for implementation plan

## Context

The app shows Kronos price forecasts (dashed line + uncertainty band) but gives users no way to
judge how good those forecasts are. We want a feature that **measures and visually demonstrates the
model's accuracy** so users can trust (and contextualize) the forecast.

Key constraint discovered during exploration: the gold `asset_price_predictions` table stores only
the **latest** forecast (`generated_at = now`, overwritten each build) — there is no archive of past
forecasts. So accuracy must come from a **walk-forward backtest**: re-run Kronos at past anchor
points using our existing history (1000 bars/series) and compare each forecast to what actually
happened. Ground truth = the silver candles. Inference is precomputed in CI (Render's free tier
can't run torch — same constraint as the live forecast) and served read-only.

## Goals

- Let users **see** the model was accurate, primarily via a **forecast-replay overlay** on the main
  chart: replay a past forecast vs. the realized price, scrubbable across many past forecasts.
- Back it with four metrics: **directional accuracy**, **MAPE**, **band calibration (coverage)**,
  and **error-by-horizon**.
- Fit the existing medallion + committed-snapshot architecture; serve read-only from Render.

## Non-goals

- Live/production accuracy from accumulated real forecasts (see Future Enhancements — needs weeks of
  data; layered on later).
- Backtesting 1m/5m intervals or the deterministic mode (scope is 1h + 1d, sampled).
- Strategy/PnL backtesting (trading rules) — this is *forecast* accuracy only.

## Decisions (from brainstorming)

- **Centerpiece:** forecast-replay overlay (predicted vs actual on the candlestick chart).
- **Placement:** a **Live | Replay** mode toggle on the existing main chart (reuses `AssetChart`).
- **Metrics:** directional accuracy, MAPE, band calibration, error-by-horizon (all four).
- **Depth:** Standard — ~96 anchors per series; scope **3 symbols × {1h, 1d} × sampled × lookback
  256**; ~576 Kronos forecasts; **weekly** CI on its own workflow (~1–2h on CPU, well within
  GitHub's 6h per-job limit; lowering the backtest sample count, e.g. 16→8, roughly halves it).
- **Band nominal:** 80% (our existing 10/90 quantiles from `prediction_band_low/high`).

## Architecture & data flow

```
silver candles ──► build_backtest.py (walk-forward, CI weekly)
                      │  for each anchor t: Kronos(bars[t-256:t]) → forecast h
                      │  join forecast steps vs realized bars[t:t+h]
                      ▼
   gold/asset_backtest_forecasts   (replay series: pred + band + actual)
   gold/asset_backtest_metrics     (aggregate: dir%, MAPE, coverage, n)
   gold/asset_backtest_horizon     (error & coverage per step → the curve)
                      ▼   DuckDB views (duckdb_repo.py)
   FastAPI: GET /backtest/replay?symbol&interval
            GET /backtest/metrics?symbol&interval
                      ▼
   AssetChart "Replay" mode (read-only, from committed snapshot)
```

## Backtest engine

New `backend/app/data/backtest.py` (compute) + `scripts/build_backtest.py` (entrypoint), reusing the
existing Kronos call path from `backend/app/data/predictions.py`:
`kronos_loader.get_predictor()`, the `_build_interval_inputs(...)` helper, `predict_batch(...)`
(sampled: N low-temp passes → median central + `prediction_band_low/high` quantile band), and
`settings.prediction_horizon_map` for per-interval horizon.

- **Anchor selection:** for each (symbol, interval) in scope, choose ~96 anchor indices `t` evenly
  spaced (stride) over the range where both `t ≥ lookback (256)` and `t + horizon ≤ len(bars)` hold.
- **Per anchor:** condition on `bars[t-256 : t]`, forecast the interval horizon, record per step:
  `pred_close`, `pred_close_low`, `pred_close_high`, and the matching realized `actual_close` from
  `bars[t : t+horizon]`. Also record the `anchor_time_utc` and `anchor_close`.

### Metric definitions

- **Directional accuracy** = over all anchors, % where `sign(pred_close[last] − anchor_close) ==
  sign(actual_close[last] − anchor_close)`. (Per-anchor flag also drives the replay readout.)
- **MAPE** = mean over (anchor, step) of `|pred_close − actual_close| / actual_close`. Per-anchor
  MAPE (over its steps) shown in the replay readout.
- **Band calibration (coverage)** = fraction of (anchor, step) where
  `pred_close_low ≤ actual_close ≤ pred_close_high`. Compared against **band_nominal = 0.8**.
- **Error-by-horizon** = for each step `s`, mean over anchors of `|pred−actual|/actual` (and
  coverage per step), producing the curve.

## Data model (gold, Parquet + DuckDB views)

Add dirs to `backend/app/data/lake_paths.py` and views to `duckdb_repo.py`, mirroring the
predictions table conventions (gitignored parquet, force-added to the snapshot).

- **`asset_backtest_forecasts`** — replay series:
  `symbol, interval, anchor_id (int), anchor_time_utc, anchor_close, step, forecast_time_utc,
  pred_close, pred_close_low, pred_close_high, actual_close`.
- **`asset_backtest_metrics`** — one row per (symbol, interval):
  `symbol, interval, n_anchors, directional_pct, mape, band_coverage, band_nominal, horizon,
  generated_at_utc`.
- **`asset_backtest_horizon`** — error curve:
  `symbol, interval, step, mae_pct, coverage`.

## API

New `backend/app/api/routes_backtest.py` + response models in `api_models.py`. Validate
`symbol ∈ settings.symbols` and `interval ∈ {1h, 1d}` (the backtested scope); for 1m/5m return an
empty payload with a `supported: false` flag so the UI can show a tidy note. Errors return empty
(consistent with `routes_predictions.py`).

- `GET /backtest/replay?symbol&interval` →
  `{ symbol, interval, supported, anchors: [ { anchor_id, anchor_time_utc, anchor_close, dir (bool),
  mape, coverage, forecast: [ {t, pred, lo, hi} ], actual: [ {t, close} ] } ] }`.
  Frontend scrubs anchors client-side. Payload ≈ 96 anchors × ~24 steps × 2 series → a few hundred
  KB; acceptable.
- `GET /backtest/metrics?symbol&interval` →
  `{ symbol, interval, supported, n_anchors, directional_pct, mape, band_coverage, band_nominal,
  horizon: [ {step, mae_pct, coverage} ] }`.

## UI — Replay mode on the main chart

In `frontend/src/components/AssetChart.tsx` (+ `frontend/src/api/client.ts` for the two calls):

- A **Live | Replay** segmented toggle beside the existing Probabilistic/Deterministic + lookback
  controls.
- **Replay mode:**
  - Fetch `/backtest/replay` for the current symbol+interval. If `interval ∉ {1h,1d}` show a tidy
    "Backtest available for 1h / 1d" note and leave Live mode active for the chart.
  - Render the realized **candles** around the selected anchor + that anchor's **dashed forecast +
    shaded uncertainty band** (reuse the existing two-area band-mask trick; theme-aware bg/mask).
  - A **scrubber** (slider + ◀ ▶) across the ~96 anchors; changing it re-renders the overlay.
  - **Per-forecast readout:** `dir ✓/✗ · MAPE 1.8% · in-band 92%` for the selected anchor.
  - A compact **aggregate strip** (from `/backtest/metrics`): directional %, MAPE, band coverage
    (vs 80% nominal), and a small **error-by-horizon sparkline** — the trust headline.
- Live mode is unchanged (current behavior). Replay respects the light/dark theme like the rest of
  the chart.

## CI

New `.github/workflows/backtest.yml`: **weekly cron + `workflow_dispatch`**, decoupled from the 12h
`refresh-data.yml`. Steps: checkout → setup-python → cache HF weights → `pip install -e ".[predict]"`
→ `python scripts/build_backtest.py` → commit the three `data/lakehouse/gold/asset_backtest_*`
tables (`git add -f`, `[skip ci]`). Uses the `HF_TOKEN` secret. ~1–2h at Standard depth (within
GitHub's 6h per-job limit); a dedicated `backtest_sample_count` (e.g. 8) can roughly halve it
without affecting the live forecast's quality.

## Testing

- **Unit (no torch):** test the metric math in `backtest.py` with a **stub predictor**
  (monkeypatch `predict_batch`) over a tiny deterministic synthetic series — assert directional %,
  MAPE, coverage, and the horizon curve match hand-computed values; assert anchor selection respects
  the lookback/horizon bounds. Guard heavy imports with `pytest.importorskip` as `test_predictions`
  does.
- **API:** endpoint tests for `/backtest/replay` and `/backtest/metrics` (supported + unsupported
  interval) against a small fixture gold table.
- **Frontend:** manual verification via Playwright screenshots — Replay toggle, scrubbing, readout,
  aggregate strip — in both light and dark themes; confirm the band renders and the 1m/5m note shows.

## Future enhancements (out of scope now)

- **Live accuracy (Approach C):** archive each scheduled live forecast and score it against realized
  prices as time passes — true production accuracy with no re-running of the model. Layer on top of
  this backtest UI once enough data has accumulated.
- Extend backtest scope to 5m and to the deterministic mode; add a "deep" weekly tier.

## Verification (end-to-end)

1. `python scripts/build_backtest.py` locally → three gold tables populated for BTC/ETH/SOL × {1h,1d}.
2. `curl /backtest/metrics?symbol=BTCUSDT&interval=1h` → sane directional_pct (0–1), mape, coverage
   near 0.8, and a horizon curve that grows with step; `/backtest/replay` returns ~96 anchors each
   with aligned forecast+actual series.
3. `make test` green (incl. new backtest unit + API tests; base install still collects).
4. UI: Replay toggle overlays a past forecast vs actual, scrubber moves across anchors, readout +
   aggregate strip populate; 1m/5m shows the note; works in light and dark. Screenshot-verified.
5. Ship: commit code + a first backtest snapshot to `master` (Render + Vercel auto-deploy); confirm
   `/backtest/*` on prod and the Replay UI on `crypto-lakehouse.vercel.app`.
