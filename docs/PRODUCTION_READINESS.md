# Production Readiness

How this system runs safely across PAPER, SHADOW, and controlled-LIVE.

## Modes
| Mode | Orders | Data | How |
|------|--------|------|-----|
| **PAPER** | simulated (paper broker) | real | `EXECUTION_MODE=PAPER` (default) |
| **SHADOW** | none — signals evaluated + logged, no auto orders | live | `EXECUTION_MODE=LIVE` + `AUTO_TRADING_ENABLED=false` |
| **LIVE** | real broker orders | live | `EXECUTION_MODE=LIVE` + `AUTO_TRADING_ENABLED=true` + all gates below |

## What must pass before LIVE auto-entry
LIVE auto-entry is blocked unless **all** hold (enforced by `services/trade_safety.py` +
`TradingEngine`/scheduler):
- `AUTO_TRADING_ENABLED=true`
- Redis healthy (lock + leader election)
- Groww token fresh (has `live_data-basic` scope)
- reconciliation healthy (broker == DB)
- data quality healthy (fresh, gap-free closed candles)
- kill switch off
- calibration model present if `REQUIRE_CALIBRATION_FOR_LIVE=true` (default)
- risk limits allow entry (daily loss/profit, max concurrent, max orders/day)
- strategy validated: walk-forward PASS + OPTION_PREMIUM backtest + PAPER evidence

## Requirements
- **Redis** — required for LIVE (locks + single-leader scheduler). If Redis is down in LIVE,
  the scheduler does **not** lead and the trade lock **fails closed** (no orders).
- **Groww token** — per-user, stored encrypted in Mongo, **expires ~6 AM IST daily**. Re-mint
  via Profile each morning. Needs the **Live Data** subscription for LTP/quotes/candles.
- **MongoDB** — state, candles, trades, backtests, reconciliation reports.

## Safety behavior
- **Kill switch** — blocks all new entries instantly; toggle in Safety Center; shown in the
  global banner. Exits are always allowed.
- **Reconciliation** — broker vs DB every minute (+ manual `POST /api/trade/reconciliation/run`).
  LIVE mismatch → kill switch + `reconcile_blocked` + Telegram alert; never auto-corrects.
- **Order lifecycle** — `order_reference_id` is generated **before** the broker call. A LIVE order
  with an unconfirmed fill is recorded `PENDING_RECONCILE` (never opened at an invented LTP).
- **Data quality** — LIVE fails **closed** on missing/stale/invalid candles or a checker crash.

## Backtesting
- **INDEX_PROXY** — directional only (assumes option delta≈1; costs on a realistic proxy premium).
  **Never** live-ready.
- **OPTION_PREMIUM** — real strike candles (decide on index, fill/exit on option premium). Requires
  the strike's candles synced; fails if option/index alignment < 80%.
- **Verdict** — every run gets a grade (A–F) + `paper_ready` + `live_candidate` (OPTION_PREMIUM +
  walk-forward PASS only). `live_ready` is never auto-true.
- **Walk-forward** PASS = pooled OOS expectancy > 0, PF ≥ 1.15, stability ≥ 0.6, ≥ 30 OOS trades.

## Calibration
`_log_signal` stores `calibration_features` per signal; `label_signals` labels forward outcomes;
`POST /api/backtest/calibrate` fits the p_win model to `backend/models/calibration.json`. Saving a
model does **not** enable LIVE — gates above still apply.

## Daily operating checklist
1. Start MongoDB + Redis (`docker compose up -d redis`).
2. `python run_scheduler.py` (one process) + `python app.py` (API).
3. Log in → Profile → re-mint Groww token (verify `/api/auth/groww-status`).
4. Sync instruments + candles.
5. Check Safety Center: scheduler healthy, token fresh, reconciliation clean, kill switch off.
6. Stay in PAPER/SHADOW unless every LIVE gate is satisfied (see `LIVE_TRADING_CHECKLIST.md`).
