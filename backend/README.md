# Backend — AI Trading API (Flask + Groww)

Flask REST API + APScheduler workers for the Groww NIFTY F&O trading system.
MongoDB for state/candles, Redis for LTP cache / locks / scheduler heartbeat.
PAPER and LIVE execution. **Real data only** (no mock candles).

See the repo root [README](../README.md) for the full picture; this covers the API + ops.

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env          # fill strong SECRET_KEY / JWT_SECRET_KEY / ENCRYPTION_KEY
docker compose up -d redis    # (from repo root) local Redis
# MongoDB expected on mongodb://localhost:27017/
```

`config.validate()` refuses to start with insecure default secrets when not in DEBUG, and
blocks `DEBUG + LIVE`. **`ENCRYPTION_KEY` must be fixed** — it encrypts the Groww token in Mongo.

## Run
```bash
python app.py             # API on :5000 (dev). Use gunicorn in prod.
python run_scheduler.py   # background workers (one process; Redis leader-locked)
python -m pytest          # tests
```

## Key modules
- `routes/` — `auth`, `market`, `strategy`, `trade`, `settings`, `instruments`
- `services/` — `groww_client` (REST + retry/backoff + 401 kill-switch), `candle_service`
  (IST, closed-candle), `scheduler`, `trading_engine`, `paper_broker`, `direction_scheduler`
- `analysis/` — indicators, `decision_engine` (regime-weighted net-score), `regime`,
  `calibration`, `options_engine`, `data_quality`, `live_monitor`, `timeframe_aggregator`
- `backtest/` — `cost_model` (Indian F&O charges), `engine` (bar-close, no look-ahead),
  `metrics`, `walk_forward`
- `utils/` — `risk_manager`, `position_sizing`, `encryption`, `time_utils`

## Groww token (daily)
Tokens reset ~6 AM IST and live **per-user in MongoDB**. Connect via
`POST /api/auth/update-groww-credentials` (key + secret → mints + stores the token).
The key needs **`live_data-basic`** scope (Live Data subscription) for LTP/quotes/candles, and
a **static IP** registered with Groww for order placement.
- `GET /api/auth/me` → `needs_groww_refresh`, `token_generated_at`
- `GET /api/auth/groww-status` → live "is the token working" check

## API reference (JWT bearer unless noted)

**Health (no auth):** `GET /api/health`

**Auth:** `POST /register`, `POST /login`, `GET /me`, `PUT /profile` (change password →
clears first-login flag), `POST /update-groww-credentials`, `POST /refresh-token`,
`GET /groww-status`, `POST /logout` (JTI blocklist)

**Market:** `GET /market/status`, `/market/indices`, `/market/ltp/{symbol}`,
`/market/quote/{symbol}`, `/market/option-chain/{underlying}`, `/market/direction/{symbol}`

**Strategy:** `POST /strategy/create`, `GET /strategy/list`, `GET|PUT|DELETE /strategy/{id}`
(ownership-checked), `POST /strategy/{id}/start|stop`, `GET /strategy/decision`,
`GET /strategy/candles/{symbol}`, `POST /strategy/candles/{symbol}/sync`

**Trade:** `POST /trade/place-order` (validated; lock fails-closed for LIVE),
`GET /trade/positions`, `GET /trade/daily-pnl`, `POST /trade/quick-trade`, `GET /trade/limits`

**Settings:** `GET|PUT /settings/`, `PUT /settings/mode` (LIVE needs a verified token),
`POST /settings/kill-switch`

Import `postman_collection.json` for ready-made requests.

## Notes
- Market time is IST; signals use **closed candles only**; daily P&L uses the IST day.
- A single default user is seeded with a default password and **must change it on first login**.
- Off-hours/weekends, a manual candle sync pulls the **last trading session** (e.g. Friday).
