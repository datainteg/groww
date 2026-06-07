# AI Trading System — Groww (NIFTY F&O)

An AI-assisted options-trading platform for Indian index F&O (NIFTY / BANKNIFTY / SENSEX)
on the **Groww** broker. Flask + APScheduler backend, MongoDB + Redis, React/TypeScript
mobile-first frontend. Supports **paper** and **live** execution.

> ⚠️ **Real money / educational use.** In `LIVE` mode this places real orders. Markets are
> adversarial and most retail options-scalping is net-negative after costs. Do **not** trade
> live until you have positive net-of-cost expectancy in an honest backtest. Start in PAPER,
> then tiny size. Not financial advice.

---

## Architecture

```
React/TS (Vite, Tailwind, Zustand)  ──HTTP poll──►  Flask REST API  ──►  MongoDB (state, candles, signals)
        mobile-first UI                                   │            ──►  Redis (LTP cache, locks, heartbeat)
                                                          │
                          APScheduler workers (run_scheduler.py) ──► Groww REST API (LTP, candles, orders)
                          • 5s LTP heartbeat  • 1m candle sync + aggregate (IST)
                          • direction engine  • daily maintenance / signal-labeling
                                                          │
        analysis/ : indicators → decision_engine (regime-weighted, net-score) → trading_engine
        backtest/ : cost-aware, bar-close engine + metrics + walk-forward
```

- **All market time is IST.** Signals run on **closed candles only**. Token, candles and
  daily P&L are IST-aware.
- **Real data only** — no mock/synthetic candles. Empty data → the UI prompts a sync.

## Tech stack
- **Backend:** Python 3.10, Flask, flask-jwt-extended, pymongo, redis, APScheduler, pandas/numpy, `ta`
- **Frontend:** React 18, TypeScript, Vite, TailwindCSS, Zustand, lightweight-charts
- **Infra:** MongoDB, Redis (Docker), Groww trade-api

## Prerequisites
- Python 3.10+, Node 18+, MongoDB (local on `:27017`), Docker (for Redis)
- A Groww trade-api account with **Live Data** + **Historical Data** enabled (see below)

## Setup

```bash
# 1) Backend deps
cd backend && pip install -r requirements.txt

# 2) Env — copy and fill (NEVER commit the filled .env)
cp .env.example .env        # set strong SECRET_KEY / JWT_SECRET_KEY / ENCRYPTION_KEY

# 3) Redis (local container)
cd .. && docker compose up -d redis

# 4) Frontend deps
cd frontend && npm install
```

> **ENCRYPTION_KEY must be fixed & stable** — it encrypts the Groww token in MongoDB. If it
> changes, stored tokens can't be decrypted. Set it once in `.env` and don't change it.

## Run (dev)

```bash
# API
cd backend && python app.py                 # http://localhost:5000

# Background workers (recommended as a separate process in prod)
cd backend && python run_scheduler.py

# Frontend
cd frontend && npm run dev                   # http://localhost:3000

# Tests
cd backend && python -m pytest
```

Production: run the API under gunicorn and **one** `run_scheduler.py` process; the scheduler
uses a Redis leader-lock so only one instance drives the jobs.

## Daily Groww token (important)

Groww access tokens **reset every day ~6 AM IST** and are stored **per-user in MongoDB**
(not in `.env`). Each morning:

1. Log in → **Profile → update Groww credentials** (API key + secret) → a fresh token is minted into Mongo.
2. The app tracks freshness via `token_generated_at` + the 6 AM rule; a stale token shows a
   **"showing older data — update"** banner and auto-opens the reconnect modal.
3. Verify with `/api/auth/groww-status` (live check).

Your Groww API key needs, in the token `role`:
- **`live_data-basic`** — for LTP / quotes / historical candles (a Live Data subscription on Groww).
- a **static IP** registered (SEBI compliance) for **placing orders** — must be the IP of the
  machine running the backend.

If market data 403s, the token is missing `live_data` scope — enable it on Groww and re-mint.

## First login
A single default user is seeded with a default password and is **forced to change it on first
login**. Add Groww credentials from Profile after.

## Project layout
```
backend/
  app.py              Flask app factory (config.validate fail-fast, CORS allowlist, JWT)
  run_scheduler.py    dedicated background-worker entrypoint
  config.py           env config + insecure-default guard
  routes/             auth, market, strategy, trade, settings, instruments
  services/           groww_client, candle_service, trading_engine, scheduler, paper_broker, ...
  analysis/           indicators (momentum/volatility/support_resistance/patterns),
                      decision_engine, market_direction_engine, regime, calibration,
                      options_engine, data_quality, live_monitor, timeframe_aggregator
  backtest/           cost_model, engine (bar-close), metrics, walk_forward
  utils/              risk_manager, position_sizing, encryption, time_utils, checksum
  tests/              pytest suite
frontend/src/         api, store (zustand), pages, components (layout, common, ...)
docker-compose.yml    local Redis
```

## Status
Hardened across secrets, scheduler-under-WSGI, IST data foundation, HTTP resilience +
token-health, calibrated regime-aware signal fusion, live-order safety, a pytest suite, and a
cost-aware backtest engine. Accuracy work is gated on out-of-sample backtest expectancy before
any live trading.

## Security notes
- Never commit `.env` / tokens. `.gitignore` covers them; a pre-existing leaked key in git
  history must be **rotated** at the broker.
- `LIVE` mode requires a verified token; the trade lock fails **closed** for live orders.

See [backend/README.md](backend/README.md) for the API reference, and
`backend/postman_collection.json` for an importable request collection.
