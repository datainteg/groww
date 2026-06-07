# LIVE Trading Checklist

Do **not** enable LIVE auto-trading until every box is checked. LIVE is disabled by default.

## Infrastructure
- [ ] MongoDB healthy
- [ ] Redis healthy (`docker compose up -d redis`) — **required** for LIVE
- [ ] `python run_scheduler.py` running (single leader)
- [ ] API under gunicorn; `DEBUG=false`
- [ ] Strong, stable `SECRET_KEY` / `JWT_SECRET_KEY` / `ENCRYPTION_KEY`
- [ ] `CORS_ORIGINS` set to real (non-localhost) origins

## Broker / data
- [ ] Groww token fresh today (`/api/auth/groww-status` → working)
- [ ] Token role includes `live_data-basic`
- [ ] Static IP registered with Groww (SEBI order requirement)
- [ ] Instruments synced
- [ ] Index candles synced (fresh, gap-free)
- [ ] OPTION_PREMIUM candles available for the traded strikes

## Validation (per strategy)
- [ ] OPTION_PREMIUM backtest grade ≥ B, `paper_ready=true`
- [ ] Walk-forward PASS (pooled OOS expectancy > 0, PF ≥ 1.15, stability ≥ 0.6, ≥ 30 trades)
- [ ] Calibration model fitted (if `REQUIRE_CALIBRATION_FOR_LIVE=true`)
- [ ] Ran in PAPER and results match expectations

## Safety
- [ ] Reconciliation healthy (Safety Center → no mismatch)
- [ ] Kill switch OFF
- [ ] Risk limits set: max daily loss / profit, max concurrent, max orders/day, risk per trade
- [ ] Scheduler leader + heartbeat healthy

## Enable (only after all above)
- [ ] Settings → switch to LIVE (type `GO LIVE`)
- [ ] `AUTO_TRADING_ENABLED=true` (server env)
- [ ] Start with the smallest possible size
- [ ] Watch the first trades manually; keep the kill switch one tap away
