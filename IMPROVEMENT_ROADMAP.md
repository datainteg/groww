# Improvement Roadmap — Groww AI Trading System
_Priorities: accuracy, real-time correctness, trading results, safety._

## Executive Summary

This is a single-broker (Groww) AI options-scalping system for Indian index F&O (NIFTY/BANKNIFTY/SENSEX/FINNIFTY): a Flask REST backend + APScheduler workers, MongoDB + Redis, and a React/Zustand polling frontend. It is capable of placing real-money orders (EXECUTION_MODE switchable to LIVE per user).

The single most important fact: the system as committed is NOT safe to run against a live account today. Real broker credentials are checked into the repository — a Groww API SECRET and a live-scope access token (backend/groww/GrowwAPI.py, backend/groww/env), plus a live Redis Cloud password and Telegram bot token (backend/.env) — and there is no .gitignore anywhere in the repo. The encryption key that protects all stored broker credentials defaults to a hardcoded constant. These must be rotated immediately, before any further work.

Against the user's stated priorities, two structural defects dominate. (1) ACCURACY/RESULTS: the auto-trading core is effectively inert and the signals it would produce are statistically unsound. The confidence gate has a units mismatch — strategies store min_confidence as a percent (e.g. 70) while the engine compares against a 0-1 fraction (verified at trading_engine.py:162 vs decision_engine.py:128) — so API-created strategies never fire. Even when they do, "confidence" is a weighted sum that is not a probability, is inflated by volatility regardless of direction (decision_engine.py:127), double-counts correlated indicators, and is computed on still-forming candles over mis-bucketed timeframes (a UTC-vs-IST double-fault). (2) REAL-TIME: under any production WSGI server the scheduler never starts (app.py:133-138 is __main__-only and commented "Optional"), so candle sync, direction, auto-entries, and SL/target monitoring all silently do nothing — open live positions would be unmanaged. All market data is REST-polled (no streaming), analysis runs on incomplete bars, and direction is cached as a Python repr string that other workers cannot read.

The codebase shows real engineering care (graceful Redis degradation, empty-data sync guard, numpy-aware JSON, an atomic kill switch), but the trading-critical paths are broken in ways that would either prevent trading entirely or trade on wrong/stale data. Recommended sequence: (A) emergency credential rotation + secret hygiene, (B) make the engine actually run and actually gate correctly, (C) fix the timezone/closed-candle data foundation, (D) overhaul signal fusion for calibrated, regime-aware, cost-aware signals, (E) harden live-order safety (fail-closed locks, input validation, LIVE step-up).

## Quick Wins
- Add a .gitignore (.env, *.env, backend/groww/env, *.key) and remove tracked secret files — but ONLY after rotating the committed credentials, since deletion does not un-leak history.
- Normalize min_confidence at the gate in trading_engine.py:162 ('if min_conf > 1: min_conf /= 100.0') to restore auto-trading; add one unit test for the 0.72-vs-70 boundary. Effort S, very high leverage.
- Add AUTO_EXIT_HOUR=15 / AUTO_EXIT_MINUTE=15 to config.py so is_auto_exit_time() (time_utils.py:32-38) stops crashing and auto-exit actually fires.
- Add the ownership guard 'if str(strategy["user_id"]) != user_id: return 403' to GET/PUT/DELETE /strategy/<id> (strategy_routes.py:116-145), mirroring the existing pattern in trade_routes.py:248.
- Guard Trades.tsx:407-408 SL/target with optional chaining (trade.stop_loss?.toFixed(2) ?? '-') so one malformed open trade cannot crash the entire positions table mid-session.
- Guard the Risk/Reward divide-by-zero in Signals.tsx:297 (return 'N/A' when SL distance is 0) to stop showing Infinity/NaN.
- Switch the per-minute candle job from full delete+insert sync_candles to the upsert sync_realtime path (scheduler.py:199 / candle_service.py:212-220) to remove the empty-collection race window.
- Replace CORS wildcard+credentials with an explicit origin allowlist and remove the manual preflight/after_request overrides (app.py:53-79); fixes duplicate Access-Control-Allow-Origin headers too.
- Serialize the direction Redis value with json.dumps/json.loads instead of str(dict) (direction_scheduler.py:139) so multi-worker reads work.
- Add max_instances=1 to reconcile_orders_job and a 'if not is_market_open(): return' guard (scheduler.py:73-79,266-288).
- Change is_market_open close comparison from '<=' to strict '<' (time_utils.py:28) so signals do not fire in the 15:30 closing-auction minute.
- Fix get_quote symbol split to split('_', 1) (market_routes.py:313-318) and the OHLC parser split(':', 1) (groww_client.py:168-189) so option contracts and colon-bearing values parse correctly.

## Critical Risks
- LIVE BROKER CREDENTIALS COMMITTED: backend/groww/GrowwAPI.py:4-5 contains a real Groww API key AND secret (verified: secret 'ogv(...'); the secret can mint fresh live-order tokens indefinitely). backend/groww/env:3 holds a live access token whose JWT payload includes 'order-basic,live_data-basic' scope. backend/.env:16,28 leak a live Redis Cloud password and Telegram bot token. No .gitignore exists. Treat the live account, Redis instance, and bot as compromised until rotated.
- Credential encryption key defaults to a hardcoded constant (config.py:33 'default-32-byte-key-for-dev-only!'; used in encryption.py:15). Anyone with the codebase + a MongoDB dump can decrypt every user's stored broker secrets and place live orders. encryption.decrypt() also silently returns '' on failure (encryption.py:34), masking key-mismatch/tampering as benign 'token expired' errors.
- Scheduler does not start under WSGI (app.py:133-138, __main__-only and commented 'Optional'). In production there is NO heartbeat, candle sync, direction engine, auto-entry, or SL/target monitoring — open live positions would be left completely unmonitored.
- Auto-trading is silently disabled by the min_confidence units mismatch (trading_engine.py:162 fraction vs stored percent), so API-created strategies never fire; the only paths that trade are manual ones with hardcoded confidence. Users may believe automation is working when it is inert.
- Confidence is not a calibrated probability and is biased toward volatile/choppy regimes (volatility added to confidence regardless of direction, decision_engine.py:127). Combined with computing indicators on still-forming candles over mis-bucketed (UTC-vs-IST) timeframes, signals repaint and win-rate cannot be reasoned about — the system can place real-money trades on statistically unsound, unstable signals.
- Fail-open trade lock (trade_routes.py:22-27): during a Redis outage (which often coincides with volatility) all duplicate-order protection vanishes for LIVE orders, with a non-unique lock identifier and non-atomic release; double-clicks/retries can place multiple real-money orders.
- Switching an account to LIVE money mode requires no re-auth, no confirmation, and no valid-token check (settings_routes.py:81-98). A single stolen/forged JWT (logout is a no-op, no blocklist) can flip a user to LIVE and place real orders within the 24h window.
- Daily P&L / loss-limit boundary uses UTC midnight while trades may be IST-stamped (mongodb.py:255-259), and start_strategy ignores overall loss / max_concurrent_trades limits (strategy_routes.py:155-158) — portfolio-level risk stops can be undercounted or bypassed, defeating the loss-limit kill condition.

## Prioritized Improvements

### 1. Security / Secrets (safety)  `[goal: safety] [effort: M]`

**Problem:** Live broker credentials are committed: Groww API SECRET and live-order-scope token (backend/groww/GrowwAPI.py:4-5, backend/groww/env:3, both verified to contain real values), live Redis Cloud password and Telegram bot token (backend/.env:16,28), and the credential-encryption key defaults to a hardcoded constant (config.py:33). No .gitignore exists anywhere in the repo. The API secret can mint fresh live-trading tokens indefinitely.

**Change:** Emergency rotation FIRST: revoke/rotate the Groww API key+secret in the Groww console, rotate the Redis password (enable TLS, REDIS_SSL=true + rediss + IP allowlist), and regenerate the Telegram bot token. Then add a .gitignore (.env, *.env, backend/groww/env, *.key), delete these files from the tree, and purge them from git history (git filter-repo/BFG). Generate high-entropy SECRET_KEY/JWT_SECRET_KEY/ENCRYPTION_KEY via a secret manager; remove all insecure defaults from config.py and refuse to start without them. Add a pre-commit secret scanner (gitleaks/trufflehog).

**Impact:** Eliminates the highest-impact risk: unauthorized real-money order placement and full account/data compromise. Until done, the live account must be treated as compromised.

### 2. Live engine / Deployment (realtime)  `[goal: realtime] [effort: M]`

**Problem:** scheduler_service.start() is only called inside app.py's __main__ block (lines 133-138), commented 'Optional: Start scheduler (uncomment if needed)'. Under any WSGI server (gunicorn/uwsgi) the heartbeat, candle sync, aggregation, direction engine, auto-entries, and SL/target monitoring never run. Open live positions would be left unmonitored for stop-loss/target.

**Change:** Start the scheduler from a dedicated worker process/entrypoint (recommended) or from create_app() guarded against the reloader and against multi-worker double-start (single-instance Redis lock). Document the deployment topology: one scheduler process, N API workers reading shared Redis. Add a health check that alerts (Telegram) if no heartbeat tick has occurred in >30s.

**Impact:** Without this, no automated trading, monitoring, or data refresh happens in production regardless of every other fix. This is the gating real-time defect.

### 3. Live engine / Signal gating (results)  `[goal: results] [effort: S]`

**Problem:** min_confidence units mismatch: strategies created via /api/strategy/create store min_confidence as a percent (e.g. 70) but trading_engine.py:162-163 compares the engine's 0-1 fraction confidence against it (default 0.6). Verified: confidence is min()'d to 1.0 at decision_engine.py:128, so '0.72 < 70' is always true and every API-created strategy is silently gated off. Only manual /execute-strategy and /quick-trade (hardcoded confidence) ever trade.

**Change:** Standardize on one scale with a single normalization helper: at read time, 'if min_conf > 1: min_conf /= 100.0'. Make decision_engine confidence units explicit. Add a unit test asserting a 0.72 confidence passes a 70 (=0.70) threshold and fails a 75 threshold. Also align the data-length contract (engine accepts >=20 candles, decision_engine requires >=50 and returns None) and stop swallowing the None/insufficient-data reason.

**Impact:** Directly restores the auto-trading core the user configured. Without it the system simply does not trade as designed, so no accuracy or results improvement is observable.

### 4. Data foundation: timezone + closed-candle (accuracy)  `[goal: accuracy] [effort: L]`

**Problem:** Two compounding defects corrupt every higher-timeframe signal. (a) Timezone double-fault: candle_service stores datetime via naive local time / datetime.fromtimestamp (candle_service.py:106, _get_smart_window:128-164) while TimeframeAggregator interprets epochs as UTC, and the scheduler 1D resample has no IST session anchor (scheduler.py:228-248) — on a UTC host the 09:15 boundary is off by 5h30m, mis-bucketing 5m/15m bars that carry 25%/35% weight. (b) Repaint: indicators are computed on the still-forming current candle (candle_service.py:99-119; timeframe_aggregator.py:80) with no closed-bar gating, so signals flicker BULLISH->gone within a minute.

**Change:** Pick ONE canonical time base: store only the integer epoch (or UTC-aware), and in every consumer build the index with pd.to_datetime(ts, unit='s', utc=True).dt.tz_convert('Asia/Kolkata'); remove the scheduler's df['datetime'] branch. Anchor 1D resample to offset='9h15min'. Add closed-candle gating: drop the forming bar (df.iloc[:-1]) for indicator computation, only mark a higher-tf bar final once now_ist >= bar_start+interval, and use live LTP only as a separate price overlay. Make the backtester replicate the exact bar-close rule.

**Impact:** These are the largest accuracy levers: they fix the inputs every signal is built on. Without them, downstream fusion improvements operate on wrong data.

### 5. Signal fusion / DecisionEngine (accuracy)  `[goal: accuracy] [effort: L]`

**Problem:** Confidence is not a probability and is structurally biased. volatility_factor is added to confidence regardless of direction (decision_engine.py:111,127 — verified), biasing entries toward choppy regimes; correlated oscillators (RSI/Stoch/Williams/CCI) and VWAP are double/triple-counted (lines 99-124,201,239,266); volume is attributed to whichever side is already winning (119-124); a flat +0.3 pattern floor lets one weak pattern read high-conviction (191-194); the 0.70 gate is hard to reach for clean trends; and the Bollinger regime override reads a key never produced (227-232, dead code).

**Change:** Compute a net directional score = bullish_weighted - bearish_weighted and map it through a logistic/Platt calibration fit on historical forward returns so 'confidence' equals empirical P(win); threshold on that. Remove volatility from the numerator (use it only for regime selection + SL width + sizing). Collapse correlated families to one orthogonal vote each (trend / oscillator / volume-flow / volatility / structure). Use real OBV/MFI direction for volume confirmation/veto. Drop the +0.3 pattern floor and weight patterns by historical hit-rate. Fix or remove the Bollinger override (add a producer/consumer key test).

**Impact:** Turns 'confidence' into something calibratable and removes systematic biases, the core of the user's accuracy goal. Best done after the data foundation (rank 4) is correct.

### 6. Regime-aware weighting + cost-aware expectancy (results)  `[goal: results] [effort: L]`

**Problem:** Weights are static, so trend and mean-reversion indicators vote together in all regimes (decision_engine.py:54-60,99-124), giving mediocre signals in both. Separately, the signal layer has no transaction-cost/slippage/R-multiple model (decision_engine.py:126-173): high directional accuracy can still lose money on option spreads, and setups cannot be ranked by expectancy.

**Change:** Detect regime (ADX/volatility-ratio) BEFORE fusion and select a weight profile: in TRENDING up-weight trend/structure/ADX and disable counter-trend oscillator votes; in RANGING up-weight oscillator fades at S/R and down-weight breakout/trend. Attach an expected-move estimate (ATR + option spread) and gate on positive net expectancy, not just direction confidence. Calibrate confidence against forward P&L net of modeled costs in the backtester.

**Impact:** Directly targets best trading RESULTS — moves the objective from win-rate to expectancy after costs, the only metric that pays.

### 7. Live-order safety controls (safety)  `[goal: safety] [effort: M]`

**Problem:** Multiple guardrails are missing on the real-money path: the Redis trade lock is fail-open with a non-unique str(time.time()) identifier and a non-atomic GET-then-DELETE release (trade_routes.py:22-45, verified); order endpoints lack input validation on quantity/type/numeric fields (trade_routes.py:89-140,523-595); switching to LIVE mode needs no re-auth/confirmation and no valid-token check (settings_routes.py:81-98); start_strategy ignores max_concurrent_trades / overall loss limits (strategy_routes.py:155-158); is_auto_exit_time references config.AUTO_EXIT_HOUR/MINUTE that do not exist (time_utils.py:32-38), crashing the auto-exit safety feature.

**Change:** Fail CLOSED for LIVE locks (reject if Redis down); use uuid4 identifiers and a Lua/atomic release; add idempotency keys per logical order. Add strict server-side order validation (positive int qty within max lots, allowlisted enums, numeric bounds) before the broker call. Require step-up auth + valid non-expired token before enabling LIVE, log/alert mode changes. Enforce can_overall_trade in start_strategy. Add AUTO_EXIT_HOUR/MINUTE to config and verify auto-exit fires.

**Impact:** Prevents duplicate/oversized real-money orders and unmanaged positions — the concrete financial-loss vectors once the system trades live.

### 8. Token health + HTTP resilience (realtime)  `[goal: realtime] [effort: M]`

**Problem:** Groww token expiry is never tracked or refreshed: update_groww_credentials saves token_generated_at but not expiry (auth_routes.py:278-281), _load_token never checks expiry, and a 401 is logged but never triggers refresh or halt (groww_client.py:121-130). There is no retry/backoff on any HTTP call (groww_client.py:85-166) and no rate-limit handling for the 5s x 3-symbol heartbeat. On token expiry or a transient failure the feed silently freezes and the engine evaluates strategies on stale prices.

**Change:** Persist groww_token_expiry; check is_token_expired() in _load_token. On 401, broadcast a kill-switch-level Telegram alert, set a 'data_feed_dead' Redis flag, and halt heartbeat/sync. Add exponential backoff+jitter (3 retries, 0.5/1/2s) on ConnectionError/Timeout/5xx, honour Retry-After / 60s cooldown on 429. Add a 5-min token-health probe (get_margins).

**Impact:** Prevents the system from silently trading on hours-old data — a direct real-time-correctness and safety win.

### 9. Cross-process direction + staleness (realtime)  `[goal: realtime] [effort: M]`

**Problem:** Direction is written to Redis as str(result) (Python repr, not JSON) at direction_scheduler.py:139, so other Flask workers cannot parse it and fall back to a slow on-demand path that substitutes 5m candles for 1m (market_routes.py:91-94,168-171; direction_scheduler.py:105) — silently degrading the 20%/35%-weighted timeframe inputs. The in-process direction cache never expires (serves stale UP/DOWN with a current timestamp after market close or sync failure). VWAP is a multi-day cumulative sum with no session reset (market_direction_engine.py:503-509).

**Change:** Serialize direction with json.dumps(result, default=str) and read with json.loads; make routes prefer Redis so any worker serves it (or run direction as a single dedicated process). Track per-symbol last_update and mark/drop results stale when now-last_update exceeds ~15s (or market closed); surface an as_of timestamp + staleness badge to the frontend. Reset VWAP at each IST session start. When real 1m data is absent, return a degraded/low-confidence flag instead of feeding 5m as 1m.

**Impact:** Makes real-time direction actually work in multi-worker production and stops confident-but-dead signals — accuracy + realtime.

### 10. Data integrity: atomic swaps + incremental sync (accuracy/results)  `[goal: results] [effort: M]`

**Problem:** Both instrument sync (mongodb.py:274-278; instrument_sync.py:43-44) and the 60s candle sync (candle_service.py:212-220; scheduler.py:199-204 calls full delete+insert sync_candles, not the upsert sync_realtime) use delete_many+insert_many, creating windows where the collection is empty — during which ATM strike resolution and direction analysis fail. The candle sync also refetches 7 days (~2,625 bars) every minute for 1-2 new bars, risking Groww rate-limit bans; and candle_service uses its own raw requests path divergent from GrowwClient.

**Change:** Use a two-collection staging swap (write instruments_staging, then rename) for instruments. Switch the per-minute candle job to the existing upsert path (sync_realtime / bulk_write UpdateOne upsert=True) and never delete in the live path. Make candle sync incremental: track last_candle_ts per symbol in Redis and fetch only since then, falling back to a wide lookback only on cold start. Inject GrowwClient into CandleService for unified retry/session pooling.

**Impact:** Removes silent missed entries/failed exits from empty-collection windows and the rate-limit ban risk that would blind the whole system.

### 11. API auth & access control (safety)  `[goal: safety] [effort: M]`

**Problem:** JWT logout is a no-op (no blocklist; auth_routes.py:316-320) so a stolen 24h token stays valid; GET/PUT/DELETE /strategy/<id> lack ownership checks (strategy_routes.py:116-145) letting any user widen another's SL or delete strategies; CORS uses wildcard origin with credentials and re-stamps duplicate headers (app.py:53-79); no password-strength validation or login rate-limit (auth_routes.py:45-51); get_data_client leaks one user's Groww token to paper users (market_routes.py:17-35); instrument sync is open to any user (instruments_routes.py:10-14).

**Change:** Add a Redis JTI blocklist + token_in_blocklist_loader and refresh-token rotation. Add the ownership check 'if str(strategy['user_id']) != user_id: 403' to all three strategy handlers (mirror trade_routes.py:248). Replace CORS '*' with an explicit allowlist and drop the manual preflight/after_request overrides. Enforce min password length + flask-limiter (5/min) on login/register. Replace get_data_client cross-user token traversal with a system data account or cached Redis/Mongo data. Gate instrument sync behind an admin role + rate limit.

**Impact:** Closes account-takeover and cross-user-tampering paths that, on a live-order system, translate to unauthorized trades.

### 12. Frontend real-time correctness (realtime)  `[goal: realtime] [effort: M]`

**Problem:** Shared single 'decision' field in the Zustand store (strategy.store.ts:73-91) races between Charts/Dashboard so the Dashboard signal badge can show BANKNIFTY's signal while viewing NIFTY; no AbortController on rapid symbol switches (Charts.tsx:87-113) renders wrong-symbol candles; no JWT refresh ejects users mid-session with open trades (axios.ts:31-38); Trades.tsx:407-408 calls .toFixed on possibly-null SL/target, crashing the entire positions table (no UI to exit live trades); R/R divides by zero (Signals.tsx:297); Dashboard SELL P&L uses wrong sign (Dashboard.tsx:519); indices/decision are not polled on Dashboard so the primary reference price goes stale.

**Change:** Key all decisions by symbol (drop the shared field) and label the symbol the badge belongs to. Add AbortController to Charts loadData. Implement proactive + 401-retry JWT refresh with a refresh lock. Guard SL/target with optional chaining + store-level normalization. Guard R/R against zero SL distance. Normalize SELL side multiplier on Dashboard. Add fetchIndices polling at the market interval; stamp/show data age.

**Impact:** Prevents the trader from seeing the wrong symbol's signal or a crashed positions table mid-trade — direct realtime-correctness and operational-safety wins.

### 13. Per-instrument calibration + correct annualization (accuracy)  `[goal: accuracy] [effort: M]`

**Problem:** All indicator thresholds are hardcoded and non-adaptive across instruments/timeframes (volatility/indicators.py:27-32,131-136,296-303), so NIFTY rarely reaches a HIGH volatility regime while a wide-ranging symbol is permanently HIGH. Intraday volatility is annualized with sqrt(252) ignoring bars-per-day (volatility/indicators.py:129,153,213,265-318), so the volatility regime, India-VIX proxy and implied-vol proxy are on the wrong scale; GARCH adds no real conditional-vol value. Pivots/Fibonacci are computed from a single recent bar/fixed lookback, not the prior session (support_resistance/indicators.py:9-41).

**Change:** Replace absolute cutoffs with rolling per-symbol, per-timeframe percentile/z-score bands. Use bar-correct annualization (periods_per_year = 252 * bars_per_day) or threshold raw per-bar vol percentiles; fit EWMA/GARCH lambda from data or drop the label. Compute classic pivots from the prior session's HLC and anchor Fibonacci to detected swing highs/lows.

**Impact:** Improves cross-symbol accuracy and makes volatility-keyed logic (regime, sizing) meaningful instead of mis-scaled.

### 14. Code hygiene: engine duplication & dual source of truth (maintainability)  `[goal: maintainability] [effort: S]`

**Problem:** Three near-identical engines exist (trading_engine.py, trading_engine_fixed.py, trading_engine_backup.py) with none guarded; the live file's own docstring says 'FIXED VERSION', so a developer will naturally edit trading_engine_fixed.py and see no effect, and the backup's broken LTP logic is a landmine. Separately, execution_mode is stored in BOTH users and settings collections (settings_routes.py:53-78), a dual source of truth that can make the system trade in a different mode than the user configured. reconcile_positions is a no-op stub that the scheduler advertises as a 'safety net'.

**Change:** Delete trading_engine_fixed.py and trading_engine_backup.py (rely on VCS for history); keep exactly one engine. Make users.execution_mode the single source of truth and remove it from the settings collection. Implement real reconciliation (match broker open positions to DB OPEN trades, close orphans, flag unknown broker positions) or remove the misleading job and docstring.

**Impact:** Prevents silently editing the wrong file (reintroducing fixed bugs) and removes a mode-confusion path that can cause unintended live trading.
