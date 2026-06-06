# Development Plan — Groww AI Trading System

Sprint-wise execution plan derived from `ARCHITECTURE_ANALYSIS.md`, `ISSUES.md` (310 findings),
and `IMPROVEMENT_ROADMAP.md` (14 ranked improvements).

**Ordering rule:** safety → make it run & gate → fix data foundation → fix signals →
harden live path → tests → frontend → real-time upgrade. **Backend is done before frontend.**

Legend: `[USER]` = action you must do in an external console (I cannot). `[CODE]` = I implement.
Each task lists the roadmap rank (R#), key files, and an acceptance check.

---

## Sprint 0 — Safety & Secrets  (BLOCKING — nothing ships live until done)
Goal: stop credential leakage; refuse to run with insecure config. (Roadmap R1, R11 partial)

| # | Task | Files | Type | Accept |
|---|------|-------|------|--------|
|0.1| Rotate Groww API key+secret | Groww console | [USER] | old secret revoked |
|0.2| Rotate Redis Cloud password, enable TLS + IP allowlist | Redis console | [USER] | new `rediss://` URL |
|0.3| Regenerate Telegram bot token | BotFather | [USER] | old token dead |
|0.4| Add `.gitignore` (`.env`, `*.env`, `backend/groww/env`, `*.key`, `__pycache__/`, `node_modules/`, `backtest_output/`) | repo root | [CODE] | secrets untracked |
|0.5| Remove tracked secret files from working tree; move real values to local-only `.env` | `backend/.env`, `backend/groww/env`, `backend/groww/GrowwAPI.py` | [CODE] | no secrets in tracked files |
|0.6| Purge secrets from git history | git filter-repo / BFG | [USER]/[CODE] | history clean |
|0.7| Remove insecure config defaults; refuse start if secret missing or == default when not DEBUG | `backend/config.py:14,18,33` | [CODE] | app raises on default secret in prod |
|0.8| Add pre-commit secret scanner (gitleaks) | `.pre-commit-config.yaml` | [CODE] | scanner blocks secrets |

> Note: repo is currently **not a git repo** (`Is a git repository: false`). If history purge
> matters, init git + first clean commit AFTER 0.4/0.5. Otherwise 0.6 is moot.

---

## Sprint 1 — Make the Engine Run & Gate Correctly  (BACKEND)
Goal: the auto-trading core actually executes and actually evaluates. (Roadmap R2, R3, R14)

| # | Task | Files | Accept |
|---|------|-------|--------|
|1.1| Normalize `min_confidence` (percent vs 0–1) at the gate via one helper | `services/trading_engine.py:162`, `analysis/decision_engine.py:128` | unit: 0.72 passes 70, fails 75 |
|1.2| Add `AUTO_EXIT_HOUR`/`AUTO_EXIT_MINUTE` to config; fix `is_auto_exit_time()` | `config.py`, `utils/time_utils.py:32-38` | no AttributeError; auto-exit fires 15:15 |
|1.3| Delete `trading_engine_fixed.py` + `trading_engine_backup.py`; keep one engine | `services/` | one engine; imports unchanged |
|1.4| `execution_mode` single source of truth (users collection only) | `routes/settings_routes.py:53-98`, `trade_routes.py:50-57` | settings reads users; no dual write |
|1.5| Start scheduler under WSGI: dedicated entrypoint + reloader/double-start guard | `app.py:133-138`, `services/scheduler.py` | scheduler runs under gunicorn; single instance |
|1.6| Heartbeat health: alert if no tick > 30s | `services/scheduler.py` | Telegram alert on stalled feed |
|1.7| Market-close strict `<`; fix symbol/OHLC split maxsplit | `time_utils.py:28`, `market_routes.py:313`, `groww_client.py:185` | no 15:30 signals; option quotes resolve |

---

## Sprint 2 — Data Foundation: Time + Closed Candles  (BACKEND, accuracy)
Goal: every signal computed on correct, IST-aligned, completed bars. (Roadmap R4, R10)

| # | Task | Files | Accept |
|---|------|-------|--------|
|2.1| Single canonical time base: store epoch / UTC-aware; convert to IST in every consumer | `services/candle_service.py:106,128-164`, `analysis/timeframe_aggregator.py`, `scheduler.py:216-248` | 09:15 bar buckets correctly on UTC host |
|2.2| Anchor 1D resample to IST session (`offset='9h15min'`) | `scheduler.py:228-248` | daily OHLC = true session |
|2.3| Closed-candle gating: drop forming bar for indicator math | `candle_service.py:99-119`, `timeframe_aggregator.py:80` | indicators stable within a minute |
|2.4| Incremental candle sync (fetch only new bars; cold-start wide lookback) | `candle_service.py:128-173`, `scheduler.py:199` | ≤2 bars/min fetched, not 7 days |
|2.5| Replace candle `delete_many`+`insert_many` with upsert path | `candle_service.py:212-220`, `scheduler.py:199` | no empty-collection window |
|2.6| Atomic instrument swap (staging collection + rename) | `database/mongodb.py:274-278`, `services/instrument_sync.py:43-44` | instruments never empty mid-sync |

---

## Sprint 3 — HTTP Resilience & Token Health  (BACKEND, realtime)
Goal: feed never silently freezes. (Roadmap R8, R9, R10 partial)

| # | Task | Files | Accept |
|---|------|-------|--------|
|3.1| Retry + backoff + jitter on HTTP; honor 429 Retry-After | `services/groww_client.py:85-166` | transient errors retried |
|3.2| Track Groww token expiry; check before use; on 401 → halt + kill-switch alert | `groww_client.py:50-130`, `routes/auth_routes.py:278-281` | expired token doesn't trade blind |
|3.3| Unify candle fetch through `GrowwClient` (shared session/retry) | `candle_service.py:83` | one HTTP path |
|3.4| Direction cache as JSON (not `str(dict)`); staleness TTL; routes prefer Redis | `services/direction_scheduler.py:139,105`, `market_routes.py:91-94` | multi-worker reads work; stale flagged |
|3.5| VWAP session reset at IST open; stop 5m-as-1m fallback (return low-confidence) | `analysis/market_direction_engine.py:503-509`, `market_routes.py:168-171` | VWAP resets daily; no fake 1m |
|3.6| Cache authenticated client + active user (stop per-tick DB/decrypt) | `services/scheduler.py:40-49,133-138` | no DB hit every 5s |

---

## Sprint 4 — Signal Quality & Results  (BACKEND, accuracy/results)
Goal: confidence becomes a calibrated, regime-aware, cost-aware signal. (Roadmap R5, R6, R13)

| # | Task | Files | Accept |
|---|------|-------|--------|
|4.1| Net directional score (bullish−bearish); remove volatility from confidence numerator | `analysis/decision_engine.py:111,127` | vol no longer inflates confidence |
|4.2| Collapse correlated indicators to one vote per family; real OBV/MFI volume confirm | `decision_engine.py:99-124,201,239,266` | no double-counting |
|4.3| Drop `+0.3` pattern floor; weight patterns by historical hit-rate | `decision_engine.py:191-194` | weak pattern ≠ high conviction |
|4.4| Logistic/Platt calibration → confidence = empirical P(win) | `decision_engine.py`, new `analysis/calibration.py` | confidence calibrates vs forward returns |
|4.5| Regime detection (ADX/vol) → regime-specific weight profiles | `decision_engine.py:54-60`, `market_direction_engine.py` | trend vs range use different weights |
|4.6| Cost/slippage/expectancy gating (not just direction) | `decision_engine.py:126-173` | gate on net expectancy |
|4.7| Per-instrument adaptive thresholds + correct annualization | `analysis/volatility/indicators.py:27-32,129,153` | percentile bands; bar-correct vol |
|4.8| Backtest replicates live bar-close + cost model | `groww/nifty_scalper_bt.py`, `run_backtest.py` | backtest ≈ live decision path |

---

## Sprint 5 — Live-Order Safety & API Hardening  (BACKEND, safety)
Goal: no duplicate/oversized real-money orders; no unauthorized access. (Roadmap R7, R11)

| # | Task | Files | Accept |
|---|------|-------|--------|
|5.1| Fail-**closed** trade lock for LIVE; uuid4 id; atomic (Lua) release; idempotency key | `routes/trade_routes.py:22-45` | Redis down ⇒ LIVE order rejected |
|5.2| Strict server-side order validation (qty int/bounds, enum allowlist) | `trade_routes.py:89-140,523-595` | bad order → 400 |
|5.3| `can_overall_trade` enforced in `start_strategy`; IST daily P&L boundary | `routes/strategy_routes.py:155-158`, `database/mongodb.py:255-259` | portfolio limits enforced |
|5.4| JWT blocklist (Redis JTI) + refresh rotation; real logout | `routes/auth_routes.py:316-320`, `app.py` | logged-out token rejected |
|5.5| Strategy ownership 403 on GET/PUT/DELETE | `routes/strategy_routes.py:116-145` | cross-user blocked |
|5.6| CORS explicit allowlist; remove manual preflight/after_request | `app.py:53-79` | no wildcard+creds |
|5.7| Password rules + login rate-limit (flask-limiter); system data account (no token leak) | `auth_routes.py:45-51`, `market_routes.py:17-35` | brute-force throttled; no shared token |
|5.8| LIVE switch step-up auth + valid-token check; real margins; real reconciliation | `settings_routes.py:81-98`, `trade_routes.py:371-386`, engine | LIVE needs valid token; balance real |

---

## Sprint 6 — Tests  (BACKEND)
Goal: lock in the fixes. (Roadmap R3/R4/R7 verification)

- Bootstrap pytest under `backend/`; mock Groww HTTP (never hit live).
- Tests: confidence units boundary; IST + closed-candle bucketing; risk gating
  (`can_overall_trade`, daily-loss, kill switch); `paper_broker` P&L incl. fees/slippage;
  indicator formulas vs references (RSI/MACD/ATR/VWAP); auth/ownership 403.
- Property-based: `_parse_ohlc_string`, candle formatting, Redis JSON round-trips.

---

## Sprint 7 — Frontend  (after backend is stable)
Goal: correct, non-crashing, staleness-aware UI. (Roadmap R12, plus R13 typing)

| # | Task | Files | Accept |
|---|------|-------|--------|
|7.1| Key decisions by symbol (drop shared `decision` field) | `store/strategy.store.ts:73-91`, Dashboard/Charts | badge matches viewed symbol |
|7.2| `AbortController` on symbol switch | `pages/Charts.tsx:87-113` | no wrong-symbol candles |
|7.3| Proactive + 401-retry JWT refresh with refresh lock | `api/axios.ts:31-38` | no mid-trade logout |
|7.4| Null-guards on SL/target; R/R zero-guard; SELL P&L sign | `pages/Trades.tsx:407-408`, `Signals.tsx:297`, `Dashboard.tsx:519` | no crash; correct P&L |
|7.5| Poll indices/decision on Dashboard; show data-age/staleness badge | `pages/Dashboard.tsx`, stores | reference price fresh |
|7.6| Exit-trade UI for open positions | Trades page | user can close trades |
|7.7| Tighten API/store types (nullable prices, per-symbol decision map) | `types/index.ts`, `store/*.ts` | compile-time null safety |

---

## Sprint 8 — Real-Time Upgrade  (stretch)
Goal: move off REST polling. (Roadmap R8/R9 extension)

- Groww WebSocket/streaming feed → tick accumulation → live-candle formation
  (`timeframe_aggregator.LiveCandle` already scaffolded).
- Frontend SSE/WebSocket for push updates instead of polling.

---

## Execution notes
- One sprint at a time; each ends green (tests/manual check) before the next.
- Sprint 0 secret rotation is **yours**; I do the code side in parallel.
- I will keep a live todo list mirroring the active sprint.
