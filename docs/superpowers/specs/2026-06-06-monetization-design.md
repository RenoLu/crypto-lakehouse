# Monetization Design — Transparency-First Crypto Forecast Track Record

> Status: **design / approved for planning**. Date: 2026-06-06.
> Working name: TBD.

## 1. Goal

Turn the crypto-lakehouse project into a source of **direct product revenue** by selling
Kronos price **forecasts to retail crypto traders**, differentiated by a **public,
verifiable, continuously-scored track record**. Competitors ask traders to *trust* their
signals; this product *shows* every forecast and how it actually performed.

The forecasting engine (Kronos) already exists. The product being built is the **trust
layer** around it: an immutable forecast log, a scoring engine, and a public record.

### Decisions locked during brainstorming

- **Monetization type:** direct product revenue (a real product people pay to use).
- **Wedge:** forecast signals for retail traders (not a data API, dashboard SaaS, or
  white-label infra — those are possible later expansions).
- **Positioning:** transparency-first verifiable track record. Free shows the proven
  record; paid unlocks real-time forecasts + alerts.
- **Investment scope:** moderate build — tens of $/month, steady part-time effort over
  months; real accounts, tiers, alert delivery, and durable data infra.
- **Approach:** "Proof engine first, monetize second" (Approach A), with an out-of-sample
  backtest folded in as internal validation + secondary proof.
- **Reconstruct AND record forward:** build a reconstructed out-of-sample backtest *and*
  run a live immutable forward log; both feed one continuously-scored public record.
- **Auth:** managed provider (Clerk or Supabase Auth), email magic-link + Google OAuth;
  tier/entitlement stored in our own DB keyed to the auth user ID.

## 2. The honesty constraint that shapes everything

`NeoQuasar/Kronos-small` is a **pretrained foundation model** (paper "Kronos: A Foundation
Model for the Language of Financial Markets", arXiv:2508.02739, Aug 2025). It was trained on
historical financial data, including crypto, up to ~its mid-2025 cutoff.

Consequence: **any backtest on data the model trained on is contaminated** — the model has
effectively seen the answers, producing inflated, indefensible accuracy. A
transparency-first product cannot publish such numbers.

Therefore:
- The **reconstructed backtest is restricted to data after Kronos's training cutoff** (a
  genuinely out-of-sample window, roughly mid-2025 → present, ~6–12 months available now).
- Step zero of implementation is **confirming the exact cutoff** from the model card/paper;
  the system is designed around whatever it actually is.
- A backtest is internal validation + *secondary*, fully-disclosed proof. It is **not**
  externally verifiable (anyone can fake a backtest). The **live forward record is the
  headline trust artifact**, because it is provably published before the outcome is known.

The live forward record does **not** require a long wait: short horizons (1h, 1d) resolve
fast, so across BTC/ETH/SOL × intervals the log accumulates hundreds of scored,
published-before-known forecasts within days. The accumulation window is about covering
market regimes for statistical weight, not about individual forecasts resolving.

## 3. Product & Offering

### Core artifact — the public Track Record page (free)

- **Reconstructed backtest:** out-of-sample only (post-cutoff), with methodology + scoring
  code linked.
- **Live forward record:** every forecast logged immutably *before* the outcome, scored
  once the bar resolves.
- **Headline metrics:** directional accuracy, error (MAE / MAPE on close), and **band
  calibration** (how often actuals landed inside the stated band).
- Always sliced by asset and horizon, always "as-of," never overwritten.

### Tiers

| Tier | Price (tunable) | Gets |
|------|-----------------|------|
| **Free** | $0 | Full track-record page; resolved/delayed forecasts (already gradable); 1 asset live. The funnel + the trust. |
| **Pro** | ~$19–29/mo (annual discount) | Real-time forecasts, all assets/intervals; calibrated uncertainty bands + directional confidence; alerts (email/Telegram) on high-confidence forecasts or band breaches. |
| **API (later)** | usage-based | Programmatic access — a bridge to the dev/quant segment later. |

**The deliberate gate is *time*:** free sees only forecasts that are already resolved/delayed;
paid sees them at generation time, when they have real-time value.

### Coverage at launch

BTC, ETH, SOL (already wired). Headline horizons **1h and 1d**; 1m/5m secondary.

## 4. Architecture & Components

Two stores: **Store A** = the lakehouse (Parquet on ADLS, append-only) for the record;
**Store B** = a transactional DB (Postgres) for users, billing, prefs. **User PII and
billing never go in the lakehouse.**

### Proof engine

- **Forecaster** *(exists — `backend/app/data/predictions.py`)* — runs Kronos, produces
  forecast rows. **Change:** `write_gold_price_predictions` flips from overwrite → append to
  the immutable log. Depends on: silver candles, Kronos.
- **Forecast log** *(new, Store A, immutable)* — append-only store of every forecast, tagged
  `source = live | backtest`. Never mutated.
- **Backtest engine** *(new — `backtest.py`)* — walk-forward, point-in-time, restricted to
  post-cutoff dates. For each historical T: slice candles ≤ T, forecast, append rows with
  `source=backtest`. Depends on: Forecaster, silver history, confirmed Kronos cutoff.
- **Scoring engine** *(new — `scoring.py`)* — once `forecast_time` has passed, joins forecast
  rows to realized silver candles and appends outcomes (directional hit, error, band
  coverage). Scheduled. Idempotent. Depends on: forecast log, silver candles.
- **Track-record API** *(new — `routes_track_record.py`)* — serves aggregated public metrics
  (free) and gated real-time forecasts (paid) from the same store via an entitlement check.

### Commerce layer

- **Accounts/auth** *(new)* — managed provider (Clerk/Supabase Auth); magic-link + Google.
- **Billing** *(new)* — Stripe Checkout + webhook → sets a user's `tier`. The webhook is the
  single source of entitlement truth.
- **Alerts** *(new)* — worker that notifies Pro users on new high-confidence forecasts or
  band breaches (email + Telegram). Depends on: forecast log, accounts.

### Durable infra (Azure migration, now load-bearing)

- Forecast log + outcomes → **ADLS Gen2** (durability is a trust requirement; losing the log
  = losing the product).
- **API** on Container Apps; **Forecaster / Backtest / Scoring** as scheduled Container Apps
  Jobs. API only reads → stays stateless + scale-to-zero.
- The *minimum* durable store lands in Phase 1; the full Azure migration is Phase 3.

**Key design decision:** backtest and live forecasts share one schema and store, separated
only by a `source` flag — so the same scoring code, track-record page, and API serve both.

## 5. Data Model

### Store A — lakehouse (Parquet on ADLS, append-only)

**Forecast log** (extends today's prediction schema):
```
forecast_id, source(live|backtest), model_version, params_hash,
symbol, interval, mode, lookback, horizon,
generated_at_utc, forecast_time_utc, step,
pred_open, pred_high, pred_low, pred_close, pred_volume,
pred_close_low, pred_close_high   (band)
```

**Outcomes** (written by scoring job, one row per forecast row, after the bar resolves):
```
forecast_id, symbol, interval, forecast_time_utc, step,
actual_open, actual_high, actual_low, actual_close,
directional_correct(bool), abs_error_close, pct_error_close,
in_band(bool), scored_at_utc
```

**Metrics rollup** (recomputable, powers the public page):
```
symbol, interval, horizon, source, window,
n, directional_accuracy, mae, mape, band_coverage,
baseline_directional_accuracy   ← always shown
```
The **baseline column is permanent and always displayed**: directional accuracy is
meaningless unless shown against a naive random-walk baseline (~50%). Beating the baseline
net of fees is the only claim that matters.

### Store B — Postgres

**Users & entitlement:**
```
user_id(from auth), email, tier(free|pro),
stripe_customer_id, stripe_subscription_id, sub_status, current_period_end,
created_at
```

**Alert prefs:**
```
user_id, channels(email|telegram), telegram_chat_id,
assets[], min_confidence, dedup_state
```

## 6. Data Flow, Cadence & Error Handling

### Live path (scheduled jobs, chained)

1. **Ingest** → silver candles *(exists)*.
2. **Forecast** (after ingest) → appends `source=live` rows. Cadence matches horizon.
3. **Score** → finds passed-but-unscored forecast rows → joins to actuals → appends
   outcomes. Idempotent.
4. **Rollup** → recomputes metrics (incl. baseline).
5. **Alert worker** → new live forecasts clearing a user's threshold → notify Pro users.

### Backtest path (one-time, re-runnable)

1. Confirm Kronos cutoff → **hard guard: refuse to run on any date ≤ cutoff.**
2. Walk-forward over post-cutoff silver history → append `source=backtest` rows.
3. Same scoring + rollup runs over them (actuals already exist).

### Entitlement gate

The free/paid gate is **time**, implemented in one place: the API filters forecasts by
`generated_at_utc` vs. now and the caller's tier. Same data, one filter, no duplicate paths.

### Billing flow

Sign-up (auth provider) → `user` row, `tier=free` → upgrade via Stripe Checkout → webhook
sets `tier=pro` + sub IDs → every gated call checks `tier`/`sub_status` in Postgres →
cancellation/expiry webhook downgrades.

### Error handling (the failure modes that matter)

- **Forecast/ingest job fails** → nothing appended (append-only = no half-written
  corruption); emit a job-failure alert.
- **Missing actuals** (silver gap) → outcome stays `pending`, never guessed. The record
  never fabricates.
- **Stripe webhooks** → dedup by event ID (idempotent); webhook is the only writer of
  entitlement.
- **Backtest contamination** → the pre-cutoff guard hard-fails rather than silently
  producing inflated numbers.
- **Scoring re-runs** → safe by construction (only fills missing outcomes).

Throughline: **append-only + idempotent + the record never fabricates or back-fills
outcomes.** That is what makes "transparency-first" technically true.

## 7. Phasing

- **Phase 1 — Proof engine, no payments.** Confirm Kronos cutoff → flip forecast write to
  append-only immutable log (on the simplest durable store for now) → build scoring +
  outcomes + metrics rollup → build backtest engine and seed the post-cutoff historical
  record → ship the public Track Record page → start the live forward log on schedule → add
  a landing page + waitlist.
  - **Go/no-go gate:** does Kronos beat the naive baseline, net of fees, on the out-of-sample
    record, with calibrated bands? If no → stop or pivot **before** building commerce.
- **Phase 2 — Commerce (only past the gate).** Managed auth + accounts → Stripe billing +
  entitlement gating → real-time access for Pro (time-gate) → alerts (email + Telegram) →
  launch paid.
- **Phase 3 — Durability/scale.** Full Azure migration (log/outcomes → ADLS, API → Container
  Apps, jobs scheduled). May overlap Phase 2.

## 8. Legal / Compliance

**Highest non-technical risk.** Selling crypto forecasts to retail can be read as investment
advice. Mitigations baked into the design:

- Position strictly as **informational/educational, not financial advice**.
- Forecasts + probabilities only; never personalized "buy now" calls; never handle user funds.
- Prominent disclaimers + ToS + risk warning at signup; "past performance ≠ future results"
  shown throughout.
- The transparency-first posture is itself compliance-friendly (no guarantees, no
  cherry-picking).

**Action required:** the founder is US-based; the informational-only lane is lower-burden,
but a **real lawyer must review the ToS and the advice line before the first payment**. This
spec is not legal advice.

## 9. Testing

- **Integrity invariants** (credibility-critical): append-only never mutates a row; scoring
  is idempotent (re-run → identical outcomes); **no-lookahead** — a backtest forecast at T
  provably uses only data ≤ T; the **pre-cutoff guard rejects** contaminated runs.
- **Scoring math** unit tests on fixtures (directional, MAE/MAPE, band coverage, baseline).
- **Entitlement**: time-gate gives free vs. Pro the correct forecasts; Stripe webhook → tier
  transitions (test mode).
- Existing **33 tests stay green**.

## 10. Success Metrics

- **Phase 1 (validation):** out-of-sample directional accuracy **vs. baseline**, band
  calibration near nominal, sufficient sample size.
- **Phase 2 (business):** waitlist→signup→paid conversion, free→Pro rate, churn, MRR.

## 11. Open Questions / To Confirm

- Exact Kronos training cutoff date (model card/paper) — gates the backtest window.
- Final pricing within the $19–29/mo band; annual discount %.
- Managed auth provider choice: Clerk vs Supabase Auth (Supabase also supplies Store B
  Postgres, the tidy path).
- Minimum durable store for the Phase-1 log before the full Azure migration.
- Alert channel priority (email first vs Telegram first).
- Product name.

## 12. Out of Scope (for now)

- Data/forecast API as a paid product (wedge #2), hosted dashboard SaaS, white-label infra.
- Additional exchanges/assets beyond BTC/ETH/SOL.
- Managed funds, personalized advice, automated trade execution.
- Azure OpenAI assistant upgrade (assistant stays template-tier).
