# Confirmed Issues — Groww AI Trading System (FULL)

Total **310** unique issues across 14 analysis passes (8 subsystem deep-reads + cross-cutting).

| Severity | Count |
|---|---|
| critical | 45 |
| high | 114 |
| medium | 115 |
| low | 36 |

_Sorted by severity. High/critical were adversarially verified during the run._

---

## CRITICAL

### CORS wildcard origin combined with credentials allows any site to send credentialed requests
- **Category:** security
- **Location:** `backend/app.py` : 53-79
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** CORS is configured with origins='*' and supports_credentials=True at line 53-57. The after_request hook (lines 74-79) then echoes back whatever Origin header is sent with Access-Control-Allow-Credentials: true. The W3C CORS spec forbids pairing a wildcard origin with credentials, so browsers block this combination. However, by reflecting the origin dynamically (line 65 and 75), an attacker on any origin can craft a credentialed cross-site request that carries the victim's JWT cookie (if cookie-based) or trigger CSRF. The double-implementation (flask-cors AND manual preflight+after_request) duplicates headers, creating inconsistency.
- **Impact:** Any website can make authenticated API calls on behalf of a logged-in user if credentials are stored in cookies, or if the frontend ever switches to cookie-based JWT. It also produces duplicate Access-Control-Allow-Origin headers, causing some strict clients to reject valid responses.
- **Fix:** Set origins to an explicit allowlist (e.g. ['http://localhost:3000', 'https://yourdomain.com']). Remove the manual handle_preflight and after_request overrides and rely solely on flask-cors. Never combine wildcard origin with supports_credentials=True.

### Hardcoded insecure default secrets in config.py are production-ready paths to compromise
- **Category:** security
- **Location:** `backend/config.py` : 14, 18, 33
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** SECRET_KEY defaults to 'dev-secret-key-change-in-production', JWT_SECRET_KEY defaults to 'jwt-secret-key-change-in-production', and ENCRYPTION_KEY defaults to 'default-32-byte-key-for-dev-only!'. If the .env file is missing or the env vars are not set, Flask runs with these well-known strings. An attacker who knows the JWT_SECRET_KEY can forge tokens for any user_id and take over all accounts. The ENCRYPTION_KEY compromise exposes every Groww API key and access token stored in MongoDB.
- **Impact:** Complete account takeover, exposure of all Groww broker credentials stored in the database, and ability to place real trades on behalf of all users.
- **Fix:** Add a startup assertion: if any of these three values matches the insecure default and EXECUTION_MODE is LIVE (or DEBUG is False), raise RuntimeError and refuse to start. Use a secret manager or require mandatory env-var presence enforced at import time.

### JWT token blacklist / revocation is not implemented — logout is a no-op
- **Category:** security
- **Location:** `backend/routes/auth_routes.py` : 316-320
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** The logout endpoint simply returns a success message without invalidating the JWT. flask_jwt_extended provides a token blocklist callback via @jwt.token_in_blocklist_loader, but it is not wired. A token stolen from a logged-out session remains valid until it expires (24 hours, config.py line 19). There is also no refresh-token mechanism — the /refresh-token endpoint issues a new access token without requiring the old one, so any bearer of the old token keeps access for the full 24 h window.
- **Impact:** Stolen JWT tokens give attackers 24-hour access post-logout. For a trading system this means an attacker can place or exit live orders across the entire validity window.
- **Fix:** Implement a Redis-backed token blocklist. In the logout handler, read the JTI claim from the current token and add it to a Redis set with TTL equal to the token expiry. Wire @jwt.token_in_blocklist_loader to check this set. Also implement proper refresh-token rotation.

### Missing ownership check on GET/PUT/DELETE /strategy/<id> — any authenticated user can read or delete another user's strategy
- **Category:** security
- **Location:** `backend/routes/strategy_routes.py` : 116-145
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** get_strategy() (line 116), update_strategy() (line 124), and delete_strategy() (line 139) call db.get_strategy_by_id(strategy_id) and act on the result without comparing strategy['user_id'] to get_jwt_identity(). Only start_strategy and the trade routes check ownership. An attacker can enumerate MongoDB ObjectIDs to read, modify parameters (SL, target), or delete other users' active strategies.
- **Impact:** An attacker can silently widen stop-losses or delete strategies for active live trades, causing unmanaged open positions. Data confidentiality of all strategies is lost.
- **Fix:** After db.get_strategy_by_id(), add: 'if str(strategy.get("user_id")) != user_id: return jsonify({"error": "Unauthorized"}), 403' in all three handlers, mirroring the pattern already used in exit_trade (trade_routes.py line 248) and execute_strategy_trade (line 487).

### No retry or backoff on any HTTP request - single failure silently drops data
- **Category:** realtime
- **Location:** `backend/services/groww_client.py` : 85-166
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** _make_request makes exactly one attempt. A transient network error, a 429 rate-limit response, or a 5xx server error results in immediate failure return with no retry. During live trading this means any 5s heartbeat hit by a transient error produces no LTP update, the 10s Redis TTL expires, and the trading engine receives None for price on the very next evaluate_strategies call.
- **Impact:** Critical: a single failed heartbeat can cause the trading engine to evaluate strategies with stale or absent price data. Cascading effect: missed SL/target triggers, false 'no price' conditions during volatile moves.
- **Fix:** Add exponential backoff with jitter using tenacity or a manual loop: retry up to 3 times on ConnectionError/Timeout/5xx with delays of 0.5s, 1s, 2s. Treat 429 as a special case: honour the Retry-After header or back off 60s.

### 401 Unauthorized is logged but never triggers token refresh - system runs blind
- **Category:** realtime
- **Location:** `backend/services/groww_client.py` : 121-130
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** When the Groww access token expires, every API call returns 401. The code logs 'critical' and returns FAILURE. There is no automatic token refresh, no alert, no scheduler pause, no fallback. The heartbeat (scheduler.py:164) simply prints 'LTP fetch failed' and the direction scheduler (direction_scheduler.py:121) continues reading stale MongoDB data. The system continues 'running' while all live data is frozen.
- **Impact:** All real-time data silently freezes. The trading engine keeps evaluating strategies against the last cached price and stale candles. Orders can be placed on hours-old market data.
- **Fix:** On 401, broadcast a kill-switch-level alert via TelegramAlert.send_kill_switch_alert, set a 'data_feed_dead' flag in Redis, and halt the heartbeat and sync jobs. Implement a token-health check job that runs every 5 minutes, calls a lightweight endpoint (e.g., get_margins), and sends a Telegram alert if it fails.

### sync_and_aggregate_job fetches 7 days of 1m candles every minute - massive bandwidth waste and rate-limit risk
- **Category:** realtime
- **Location:** `backend/services/candle_service.py` : 128-173
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** _get_smart_window always returns a 7-day lookback for interval=1 (line 155). This means every minute, for each of 3 symbols, the system fetches approximately 7 days * 375 candles/day = 2,625 one-minute candles from Groww's historical API. That is 3 full 7-day historical fetches per minute = 180 per hour. The response payload is also large (3 large JSON arrays/minute).
- **Impact:** Extremely high API rate-limit risk against Groww's historical endpoint. Each response carries ~2,625 candles when only 1-2 new ones have formed. Wasteful bandwidth. Groww may throttle or ban the API key. The actual new data needed is at most 2 new 1-minute bars since the last sync.
- **Fix:** Track the last synced timestamp per symbol in Redis (e.g., key 'last_candle_ts:NIFTY:1'). Compute start_time as max(last_ts - 2 * 60, market_open) to fetch only new candles (incremental sync). Fall back to 7-day lookback only on first startup or after a gap of >10 minutes.

### Full sync uses delete_many + insert_many - race window destroys candle data
- **Category:** data-integrity
- **Location:** `backend/services/candle_service.py` : 212-220
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** _save_to_db (line 212) is called in mode='full' from sync_candles. It deletes ALL candles for (symbol, interval) then inserts new ones. There is a window between delete_many and insert_many where the collection is empty. If direction_scheduler or any API route reads candles in this window, it gets an empty list and fails silently (direction_scheduler.py:97 checks len < 50 and returns).
- **Impact:** During the delete-insert gap (milliseconds to seconds under MongoDB load), direction analysis returns None, strategy signals are skipped, active trade monitors get no price update. Under high write load this window can last seconds.
- **Fix:** Replace the delete+insert pattern with the existing upsert_candles path (which uses bulk_write with UpdateOne upsert=True). Never use destructive replacement for live data. The mode='full' distinction should be removed; always use upsert.

### Incomplete last (forming) candle is stored and used for analysis without any guard
- **Category:** accuracy
- **Location:** `backend/services/candle_service.py` : 99-119
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** fetch_candles_from_groww formats every candle returned by the API including the current, still-forming one (e.g., at 10:22:30 the 10:22 candle is incomplete). This incomplete candle is stored in MongoDB and then read by DirectionScheduler._update_direction (direction_scheduler.py:95) and used by analyze_direction as the 'last closed candle'. All technical indicators (RSI, EMA, MACD) computed on the incomplete candle produce wrong values.
- **Impact:** Every signal generated between :00 and :59 of each minute is computed on an unfinished candle. For a scalping system this is the primary source of signal inaccuracy: a candle with close=X at :30 can have a wildly different close at :59.
- **Fix:** After fetching, strip the last candle if its timestamp == current minute floor: `now_floor = int(time.time()) // 60 * 60; candles = [c for c in candles if c['timestamp'] < now_floor]`. Apply this filter in fetch_candles_from_groww before returning.

### instrumentsApi.getCount and marketApi.getLtp do not exist — runtime crashes on every call
- **Category:** correctness
- **Location:** `frontend/src/store/market.store.ts` : 86, 95
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** market.store.ts:86 calls instrumentsApi.getCount() and line 95 calls marketApi.getLtp(). Neither function is defined in market.api.ts. Every call throws a TypeError at runtime, crashing fetchSyncInfo() and getLtp(). syncInfo is never populated so the Strategy page always shows 'No instruments synced'. getLtp always returns 0, breaking any component that relies on live LTP from the store.
- **Impact:** Strategy page permanently shows incorrect sync status. Any component using getLtp receives 0 instead of real LTP. This silently degrades the UI without a visible error because the catch blocks only log to console.
- **Fix:** Add getCount and getLtp to market.api.ts. For getCount: GET /instruments/count returning { total, by_underlying }. For getLtp: GET /market/ltp/:symbol returning { ltp, timestamp }. Alternatively route getLtp through the existing getIndices response and parse it there.

### market.store.ts fetchExpiries reads response.expiries on an already-unwrapped array — always empty
- **Category:** correctness
- **Location:** `frontend/src/store/market.store.ts` : 65
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** instrumentsApi.getExpiries() (market.api.ts:73-76) already unwraps the response and returns a plain string[]. market.store.ts:65 then tries to read .expiries on that array, which is undefined, so the market store's expiries map is always populated with []. Strategy.tsx uses a separate local call to instrumentsApi.getExpiries() directly (line 151-162) which does work, but any component reading useMarketStore().expiries gets []. The store also calls the API each time independently, wasting requests.
- **Impact:** Any future component or utility using useMarketStore().fetchExpiries + useMarketStore().expiries will receive no expiry data. Bugs will appear silently as empty dropdowns.
- **Fix:** Change market.store.ts line 65 to: expiries: { ...state.expiries, [underlying]: Array.isArray(response) ? response : [] }. The instrumentsApi.getExpiries already returns string[] directly.

### No JWT token refresh — 401 mid-session forcibly redirects with open trades
- **Category:** security
- **Location:** `frontend/src/api/axios.ts` : 31-38
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** The 401 handler in axios.ts unconditionally removes the token and redirects to /login. authApi.refreshToken() exists (auth.api.ts:43) but is never called. With 30 s polling active across multiple pages, once the JWT expires the very next background poll fires a 401, wipes localStorage, and immediately navigates away — even if the user has open live trades on screen. There is also no proactive expiry check before firing trade-critical API calls like exitTrade or modifyTrade.
- **Impact:** Critical for live trading: a user with open positions can be ejected from the UI the moment the token expires. The positions remain open with no human oversight.
- **Fix:** Implement a proactive refresh: (1) On app init, decode the JWT exp claim and schedule a refresh 60 s before expiry. (2) In the 401 interceptor, attempt one refresh call first; if it succeeds, retry the original request. Only redirect on a second 401. Use a flag to prevent concurrent refresh calls (refresh lock pattern).

### min_confidence scale mismatch: strategy stores 0-100, engine compares against 0-1 confidence — gate never passes or always passes
- **Category:** correctness
- **Location:** `backend/services/trading_engine.py + backend/routes/strategy_routes.py + backend/analysis/decision_engine.py` : trading_engine.py:162-164; strategy_routes.py:46-48,87; decision_engine.py:127-128
- **Subsystem:** Groww trading-engine wiring, signal/candle data consumption, and dead-code audit (backend/)
- **Detail:** decision_engine returns confidence in [0,1] (analyze() clamps min(confidence,1.0) at L128). strategy_routes validates and stores min_confidence in [50,95] as an integer percent (L46-48, default 70 at L46/87). evaluate_strategies reads `min_confidence = strategy.get('min_confidence', 0.6)` and compares `if confidence < min_confidence: continue` (L162-164). For any user-created strategy, min_confidence is e.g. 70, so `confidence(<=1.0) < 70` is ALWAYS true and NO automated entry ever fires. If min_confidence is absent it defaults to 0.6 (fraction), which works — so behavior silently differs between default and user-configured strategies.
- **Impact:** Automated entries from the scheduler heartbeat are effectively disabled for every strategy created through /api/strategy/create. The auto-trading core does not trade as configured; only manual /execute-strategy and /quick-trade (which hardcode confidence) work.
- **Fix:** Pick one scale. Normalize at the gate: `min_conf = strategy.get('min_confidence', 60); if min_conf > 1: min_conf /= 100.0` before comparing, or have decision_engine return confidence*100. Add a unit test asserting the gate fires for a 0.72 confidence vs a 70 threshold.

### Candle epoch timestamp interpreted inconsistently: server-local in candle_service vs UTC in aggregator (timezone double-fault)
- **Category:** accuracy
- **Location:** `backend/services/candle_service.py; backend/analysis/timeframe_aggregator.py` : candle_service.py:106; timeframe_aggregator.py:64; scheduler.py:216
- **Subsystem:** Real-time price/candle data pipeline (Groww API -> backend cache/Redis/Mongo -> decision & direction engines -> Flask routes -> React/Zustand stores -> chart UI)
- **Detail:** candle_service stores datetime via datetime.fromtimestamp(c[0]).isoformat() which uses the server's LOCAL timezone (naive). The aggregator's aggregate() instead treats the same c[0] epoch as UTC and converts to IST (pd.to_datetime(timestamp, unit='s', utc=True).tz_convert('Asia/Kolkata')). Meanwhile scheduler.sync_and_aggregate_job re-parses the stored naive local 'datetime' string with pd.to_datetime(df['datetime']) (no tz). So the SAME candle is bucketed under two different time bases depending on code path. If the server is not in IST (typical for cloud/UTC hosts), 5m/15m/60m buckets are shifted by the UTC->IST offset (5h30m) relative to the 1m data and relative to the chart's IST formatter, mis-assigning candles to wrong time buckets and wrong sessions.
- **Impact:** Higher-timeframe candles (the 35%-weight 15m trend and 25% 5m structure inputs to the direction engine, and the 5m decision engine) are aligned to the wrong wall-clock buckets. EMA/RSI/VWAP/structure are all computed over mis-bucketed bars, corrupting direction and signal accuracy. On a UTC host the 09:15 session boundary is wrong by 5h30m.
- **Fix:** Pick ONE canonical time base. Store candles as UTC-aware (datetime.fromtimestamp(c[0], tz=timezone.utc)) or keep only the integer epoch and never store a naive isoformat. In every consumer build the index with pd.to_datetime(timestamp, unit='s', utc=True).dt.tz_convert('Asia/Kolkata') consistently. Remove the scheduler's pd.to_datetime(df['datetime']) branch (scheduler.py:215-218) so aggregation always uses the epoch column. Verify against the chart's IST formatter.

### Analysis runs on the still-forming (incomplete) current candle — no closed-candle gating, causes repaint/false signals
- **Category:** realtime
- **Location:** `backend/analysis/market_direction_engine.py; backend/analysis/decision_engine.py; backend/analysis/timeframe_aggregator.py` : market_direction_engine.py:179,207; decision_engine.py:88; timeframe_aggregator.py:80
- **Subsystem:** Real-time price/candle data pipeline (Groww API -> backend cache/Redis/Mongo -> decision & direction engines -> Flask routes -> React/Zustand stores -> chart UI)
- **Detail:** Every engine uses df['close'].iloc[-1] / high.iloc[-5:] etc. on the latest bar, which for the current interval is still forming (e.g. the 09:31-09:35 5m candle at 09:32). The aggregator resamples with closed='left'/label='left' and does NOT drop the in-progress final bucket, so the last aggregated bar mutates every minute. The direction engine recomputes this every 1 second mixing live LTP into an incomplete bar. There is no 'use only closed candles' gate anywhere.
- **Impact:** Indicators (EMA9/21/50/100, RSI, structure HH/HL, candle body strength) flip as the bar fills, producing signal repaint: a BULLISH signal at 09:31 can vanish by 09:34. Strategy entries in evaluate_strategies fire on these unstable values, and chart AI markers jump. This is the classic source of 'looked right then changed' inaccuracy.
- **Fix:** Add closed-candle gating: for indicator computation drop the last (forming) bar of each timeframe (df.iloc[:-1]) and only treat a higher-tf bar as final once now_ist >= bar_start + interval. Use live LTP only as a separate 'current price vs last closed level' overlay, not blended into iloc[-1] of the bar series. Emit signals only on bar close transitions.

### Live Groww broker access token committed in repository (backend/groww/env)
- **Category:** security
- **Location:** `backend/groww/env` : 3
- **Subsystem:** Groww Trading Platform - Authentication, Secrets Management & Order Execution
- **Detail:** A complete, live Groww access token (a signed ES256 JWT) is committed in plaintext. Decoding the embedded sub claim reveals role 'order-basic,live_data-basic,non_trading-basic,order_read_only-basic' plus vendorIntegrationKey, userAccountId, deviceId and sessionId. Anyone with repo access can use this token directly against api.groww.in to read account data and place REAL orders until it expires.
- **Impact:** Direct unauthorized real-money order placement and account data exfiltration on the owner's live brokerage account. This is the highest-impact finding given EXECUTION_MODE=LIVE capability.
- **Fix:** Immediately revoke/invalidate this token in the Groww developer console and rotate the API key/secret. Delete backend/groww/env from the repo and purge it from git history (git filter-repo/BFG). Never commit tokens; load them at runtime from a secrets manager. Add the file to .gitignore.

### Hardcoded live API key and plaintext API secret in source (GrowwAPI.py)
- **Category:** security
- **Location:** `backend/groww/GrowwAPI.py` : 4-5
- **Subsystem:** Groww Trading Platform - Authentication, Secrets Management & Order Execution
- **Detail:** A live api_key JWT (line 4) and the raw API secret 'ogv(PHrIw_!Z5fpQZ0K3U57puYJ5pNZU' (line 5) are hardcoded. The secret is the long-lived credential used by checksum.py:generate_checksum to mint fresh access tokens, so it is more dangerous than a single short-lived token. run_backtest.py:17 also embeds a live ACCESS_TOKEN.
- **Impact:** With the API secret an attacker can continuously generate new live access tokens and place real orders indefinitely, even after individual tokens expire. Full account compromise.
- **Fix:** Revoke and rotate the API key/secret in Groww immediately. Remove all hardcoded credentials from GrowwAPI.py and run_backtest.py; read from environment/secrets manager. Purge from git history. Treat the secret as fully compromised.

### Committed .env with live Redis Cloud password and live Telegram bot token
- **Category:** security
- **Location:** `backend/.env` : 16, 28
- **Subsystem:** Groww Trading Platform - Authentication, Secrets Management & Order Execution
- **Detail:** backend/.env is committed and contains a real Redis Cloud password (Qf8oTEIOJKG0TOeG4TpIbhaDCIOygPYL) for a publicly addressable host (redis-19899...ec2.cloud.redislabs.com:19899) and a real Telegram bot token (8397795779:AAH...). There is no .gitignore in the repo (Glob for **/.gitignore returned none).
- **Impact:** Attacker can connect to the production Redis instance (containing cached LTPs and trade locks) to read/modify data or disable trade locks; and can fully control the Telegram bot to send forged alerts. Combined with the fail-open trade lock, Redis access could be abused to bypass duplicate-order protection.
- **Fix:** Rotate the Redis password and Telegram bot token now. Remove .env from the repo, add a .gitignore covering .env, *.env, backend/groww/env, and purge history. Restrict the Redis Cloud instance by IP allowlist and require TLS.

### Default/placeholder Flask SECRET_KEY and JWT_SECRET_KEY with insecure fallbacks
- **Category:** security
- **Location:** `backend/.env` : 2, 6
- **Subsystem:** Groww Trading Platform - Authentication, Secrets Management & Order Execution
- **Detail:** .env sets SECRET_KEY=your-secret-key-change-in-production and JWT_SECRET_KEY=your-jwt-secret-key-change-in-production, and config.py:14,18 fall back to equally guessable defaults if unset. The JWT_SECRET_KEY signs the session JWTs used to authorize every order endpoint (HS256). A known/guessable signing key lets an attacker forge a JWT for ANY user_id (create_access_token(identity=user_id), auth_routes.py:88,143) and place live orders or change execution mode on any account.
- **Impact:** Complete authentication bypass: forge tokens for arbitrary users, place real-money orders, switch accounts to LIVE, exfiltrate masked credentials. Catastrophic.
- **Fix:** Generate cryptographically random high-entropy values (e.g. secrets.token_urlsafe(64)) for SECRET_KEY and JWT_SECRET_KEY, store outside the repo, and rotate (which invalidates existing tokens). Remove insecure defaults in config.py so the app refuses to start without real keys in production.

### Encryption key for broker credentials defaults to a hardcoded value; single shared key
- **Category:** security
- **Location:** `backend/utils/encryption.py` : 15-18
- **Subsystem:** Groww Trading Platform - Authentication, Secrets Management & Order Execution
- **Detail:** ENCRYPTION_KEY is not set in .env, so config.py:33 falls back to the hardcoded 'default-32-byte-key-for-dev-only!'. encryption.py derives the Fernet key by SHA-256 of this string. All users' Groww api_key, api_secret and live access_token are encrypted under this single, publicly known key. Anyone with DB access (or who reads the source) can decrypt every stored broker credential.
- **Impact:** Stored broker secrets are effectively plaintext: an attacker with the codebase + a DB dump can decrypt all api_secrets and mint live order tokens for every user.
- **Fix:** Set a strong random ENCRYPTION_KEY from a secrets manager and remove the default. Consider per-user key derivation or envelope encryption (KMS-wrapped data keys). Rotate the key and re-encrypt existing records; treat all currently stored credentials as compromised.

### Confidence is not a probability and the 0.70 gate is mathematically unreachable for clean trends
- **Category:** accuracy
- **Location:** `backend/analysis/decision_engine.py` : 95-131
- **Subsystem:** Groww Decision / Market-Direction Signal Engine
- **Detail:** bullish_score is a weighted sum of per-bucket scores, but each bucket's score is itself <=1 and the weights sum to 1.0 only if ALL five buckets agree on one direction. In practice patterns(0.30), momentum(0.25), S/R(0.15) rarely all point the same way, and volume(0.15) is only added to the leading side. A realistic strong long with momentum score 0.67 and S/R 0.6 agreeing, patterns neutral, yields ~0.25*0.67+0.15*0.6 = 0.26, plus volatility_factor (max 0.15*0.8=0.12) and volume 0.15 = ~0.53 — below 0.70. The 0.70 threshold therefore fires only in rare full-consensus regimes, and confidence does not map to any empirical win probability.
- **Impact:** Either almost no trades fire, or (because trading_engine uses min_confidence 0.6, not 0.70) trades fire on a number that has no probabilistic meaning. Win-rate cannot be reasoned about or calibrated.
- **Fix:** Normalize: compute a net directional score = (bullish_weighted - bearish_weighted) and map through a logistic/Platt calibration fit on historical forward returns so 'confidence' equals empirical P(win). Make the threshold operate on calibrated probability, not raw weighted sum. Align trading_engine min_confidence with the engine's units.

### volatility_factor is added to confidence regardless of direction, inflating the gate in volatile/choppy markets
- **Category:** correctness
- **Location:** `backend/analysis/decision_engine.py` : 111,127
- **Subsystem:** Groww Decision / Market-Direction Signal Engine
- **Detail:** confidence = max(bullish_score, bearish_score) + volatility_factor where volatility_factor = volatility_score * 0.15, and volatility_score is 0.8 in HIGH-vol regime (decision_engine.py:230). High volatility is thus rewarded with up to +0.12 confidence even though it is direction-agnostic. This means the engine becomes MORE likely to cross the threshold precisely in the high-volatility, low-edge regimes where mean-reversion/whipsaw risk is highest.
- **Impact:** Systematically biases entries toward volatile regimes (worst risk-adjusted environment for naked option buying), degrading win-rate and increasing slippage/drawdown.
- **Fix:** Remove volatility from the confidence numerator. Use volatility only as (a) a regime selector that changes which strategy/weights apply, and (b) a position-sizing and SL-width input. If anything, high uncategorized volatility should LOWER confidence in a directional signal.

### Pattern aggregation reads 'direction' but patterns emit 'signal' — patterns contribute ZERO to every decision
- **Category:** correctness
- **Location:** `backend/analysis/decision_engine.py + all pattern files` : decision_engine.py:187-188; patterns emit 'signal' at e.g. candlestick/patterns.py:59,83; primary/patterns.py:45; harmonic/patterns.py:76
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** _analyze_patterns counts p.get('direction')=='BULLISH'/'BEARISH', but every detector returns the key 'signal' (never 'direction'). bullish and bearish therefore always equal 0, so _analyze_patterns always returns (0.5,'NEUTRAL').
- **Impact:** Patterns are weighted 30% (the single largest weight) yet contribute nothing. All 24 candlestick/harmonic/primary patterns are dead weight in the live signal. Massive accuracy loss and the opposite of 'best results'.
- **Fix:** Change decision_engine.py:187-188 to read p.get('signal'). Better: weight by p['confidence'] (which is currently ignored entirely) instead of a raw count, and de-duplicate conflicting patterns.

### All [-1]-based indicators and candlestick patterns repaint on the live forming candle
- **Category:** realtime
- **Location:** `all indicator/pattern files (consumed via decision_engine)` : e.g. momentum/indicators.py:17-23 (RSI), 38-40 (MACD), 56 (Stoch); volatility/indicators.py:48-53 (BB); candlestick/patterns.py:14,46-47,99 (iloc[-1]); support_resistance/indicators.py:11 (pivots)
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** candle_service.get_candles returns the current still-forming 5-min bar as df.iloc[-1] (no completed-bar filter). Every indicator and candlestick pattern keys off [-1], so values change continuously within the 5-min window. A bullish engulfing / close-above-band can appear mid-bar and disappear by close.
- **Impact:** Entries fire on transient intrabar signals that do not exist at bar close — classic repainting. Backtest (on closed bars) will not match live, inflating expected edge and causing real losses in scalping.
- **Fix:** Pass only completed candles to the indicator stack (drop the forming bar, or operate on iloc[-2] for pattern confirmation), or explicitly separate 'forming-bar peek' from 'confirmed signal'. Tag each result with the candle timestamp it was computed on and reject stale frames.

### Look-ahead bias in all swing/peak/trough detectors (centered windows)
- **Category:** realtime
- **Location:** `base.py, harmonic/patterns.py, support_resistance/indicators.py, primary/patterns.py` : base.py:43-45,52-54; harmonic/patterns.py:17-21; support_resistance/indicators.py:133-137 (and 218,259); primary/patterns.py:21-23,71-73,117-119,158-160
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** Peaks/troughs are confirmed by comparing data[i] to data[i+1..i+order] — i.e., future bars. A swing high at index i is only 'known' after 'order' more bars. But detection loops include indices up to len-order, so on each new bar the most recent swing flips as future data arrives — and any pattern anchored on it repaints.
- **Impact:** Swing levels, order blocks, all harmonic patterns, H&S, double tops/bottoms repaint and their 'last swing' moves. A pattern reported now may not have been reportable when those bars were live, again breaking backtest/live parity.
- **Fix:** Treat a pivot as confirmed only 'order' bars after it forms and never include the unconfirmed trailing region; or use causal pivot detection. Document the confirmation lag and exclude the lookahead region from signal generation.

### Pattern weight (30%) is dead: _analyze_patterns reads non-existent 'direction' key
- **Category:** correctness
- **Location:** `backend/analysis/decision_engine.py` : 187-188 (and 99-102)
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** _analyze_patterns counts bullish/bearish via p.get('direction'), but every pattern detector emits the key 'signal' (confirmed in patterns/base.py:28-36 and all primary/candlestick/harmonic dicts, e.g. primary/patterns.py:45,92; candlestick/patterns.py:31). p.get('direction') is therefore always None, so bullish=bearish=0 and the function always returns (0.5,'NEUTRAL').
- **Impact:** The single highest-weighted component (30%) NEVER contributes to bullish_score/bearish_score (L99-102 branches never taken). The remaining max directional score is momentum .25 + sr .15 + volume .15 = 0.55; even with the +volatility_factor (max ~0.12) the confidence ceiling is ~0.67 < the 0.70 threshold, so the legacy engine can essentially NEVER emit a signal, silently disabling pattern-driven entries.
- **Fix:** Change L187-188 to read p.get('signal'). Add a contract test asserting producer keys (signal/confidence) match consumer reads, and assert a known bullish fixture yields pattern_signal=='BULLISH'.

### Analysis runs on the still-forming candle — signal repaint / look-ahead instability
- **Category:** realtime
- **Location:** `backend/analysis/market_direction_engine.py` : 179-180,207-208; decision_engine.py:88; timeframe_aggregator.py:80-86
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** All engines use iloc[-1], iloc[-5:] etc. on the latest bar, which for the current interval is incomplete. timeframe_aggregator.aggregate resamples with closed='left'/label='left' and does NOT drop the in-progress bucket, so the last 5m/15m bar mutates every minute. The direction engine recomputes every 1s and blends live_ltp into that forming bar (L179).
- **Impact:** EMA9/21/50/100, RSI, HH/HL structure, candle-body strength all flip as the bar fills; a UP at 09:31 can become NEUTRAL/DOWN by 09:34. Strategy entries fire on unstable values and chart markers jump — the classic 'looked right then changed' inaccuracy.
- **Fix:** Add closed-candle gating: compute indicators on df.iloc[:-1] for each timeframe and only treat a higher-tf bar as final once now_ist >= bar_start+interval. Use live LTP only as a separate 'price vs last closed level' overlay. Emit signals on bar-close transitions, not every second.

### Paper broker fetches F&O option LTP with wrong exchange prefix (NSE_ instead of NFO_)
- **Category:** correctness
- **Location:** `backend/services/paper_broker.py` : 54, 98, 56, 99
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** get_ltp (line 98) builds exchange_symbol = f"NSE_{trading_symbol}" and _calculate_unrealized_pnl (line 54) uses f"NSE_{pos['trading_symbol']}", then calls groww.get_ltp([symbol], segment='FNO'). Groww's get_ltp keys results by the exchange_symbol passed, and F&O contracts must use the FNO/NFO exchange prefix (the engine itself uses 'NFO_' at trading_engine.py:89). With 'NSE_' the API returns no data for the option, so get_ltp returns 0.
- **Impact:** Every paper entry/exit gets ltp<=0. place_order returns {'success':False,'error':'Could not get current price'} so NO paper trade ever fills, and unrealized P&L silently stays 0. This breaks the entire paper-trading path the user relies on for accuracy/results.
- **Fix:** Use the same FNO prefix the engine uses. Replace 'NSE_' with the correct Groww FNO exchange prefix (match trading_engine.py:89 'NFO_' or whatever the broker actually accepts) in get_ltp (98), _calculate_unrealized_pnl (54), and ensure get_positions (280) passes the right segment. Centralize prefix logic in one helper to avoid drift.

### Risk-limit field-name mismatch: daily loss/profit/order limits never enforced
- **Category:** risk
- **Location:** `backend\utils\risk_manager.py` : 24,28,32 (vs mongodb.py:168-169,206)
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** can_strategy_trade reads strategy.get('orders_today') and strategy.get('pnl_today'), but the DB document created/updated in mongodb.py uses keys 'today_orders' (line 168/202) and 'today_pnl' (line 169/206). The .get() falls back to default 0 for orders and 0 for pnl every time, so the order cap, profit limit, and loss limit comparisons can never become true.
- **Impact:** The single most important safety control is dead. A strategy can keep firing entries with unlimited daily orders and the daily loss limit will NEVER halt trading even after large realized losses are recorded in today_pnl. This directly endangers capital and contradicts the BEST RESULTS / accuracy goal.
- **Fix:** Standardize on one field name across DB, model, and risk_manager. Easiest: change risk_manager.py to read strategy.get('today_orders', 0), strategy.get('today_pnl', 0), and the Strategy model (models.py:124-125,150-154) to match. Add a unit test asserting can_strategy_trade returns False when today_pnl <= -max_loss_limit.

### increment_strategy_orders is never called — max_orders_per_day cannot trip even if field names were fixed
- **Category:** risk
- **Location:** `backend\database\mongodb.py` : 201-203 (call site missing in trading_engine.py:282-388)
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** execute_entry() records a trade (trading_engine.py:373) but never calls db.increment_strategy_orders(strategy_id). The counter today_orders stays at 0 forever, so even after fixing the field-name bug the max-orders-per-day limit would still never engage in the automated loop.
- **Impact:** Unlimited automated entries per day per strategy; runaway order generation on a noisy signal, exhausting margin and racking up brokerage/slippage. Real-time risk gating is non-functional.
- **Fix:** Call db.increment_strategy_orders(str(strategy['_id'])) inside execute_entry after a successful order, and re-check can_strategy_trade at the top of evaluate_strategies' per-strategy loop (trading_engine.py:151) so the cap is enforced before each entry, not only at start_strategy.

### overall_pnl_today is never incremented — account-level profit/loss kill never fires
- **Category:** risk
- **Location:** `backend\utils\risk_manager.py` : 53-61 (no writer anywhere)
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** can_overall_trade reads settings['overall_pnl_today'] but a codebase-wide search shows this key is only initialized (auth_routes.py:78) and reset to 0 (scheduler.py:304, settings_routes.py:256) — never incremented after a closed trade. execute_exit only updates per-strategy today_pnl (trading_engine.py:469).
- **Impact:** The account-wide daily profit and daily loss circuit breakers are inert. Multiple strategies can collectively blow well past DEFAULT_MAX_DAILY_LOSS with no global halt.
- **Fix:** In execute_exit, after computing pnl, also do db.settings.update_one({'user_id': user_id}, {'$inc': {'overall_pnl_today': pnl}}). Then call can_overall_trade(settings, active_trades) inside evaluate_strategies before every entry.

### is_auto_exit_time references undefined config.AUTO_EXIT_HOUR/AUTO_EXIT_MINUTE — auto square-off crashes
- **Category:** correctness
- **Location:** `backend\utils\time_utils.py` : 34 (config.py:47-51 lacks these attrs)
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** is_auto_exit_time() builds time(config.AUTO_EXIT_HOUR, config.AUTO_EXIT_MINUTE) but config.py only defines MARKET_OPEN/CLOSE hour/minute. Any call raises AttributeError.
- **Impact:** If any scheduler/engine path calls is_auto_exit_time(), it throws, and intraday MIS positions are never auto-exited before close — exposing positions to forced broker square-off at unfavorable prices or overnight risk on non-MIS. Directly harms results.
- **Fix:** Add AUTO_EXIT_HOUR=15 and AUTO_EXIT_MINUTE=15 to config.py (env-overridable), or derive from MARKET_CLOSE minus an offset. Add a smoke test that calls is_auto_exit_time().

### run_backtest.py is broken: imports/Config fields do not exist in the on-disk backtester
- **Category:** correctness
- **Location:** `backend/groww/run_backtest.py / backend/groww/nifty_scalper_bt.py` : run_backtest.py:10,61-77; nifty_scalper_bt.py:43-72,410
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** run_backtest.py does `from nifty_scalper_bt import Config, Backtester, get_trading_dates` and instantiates Config(interval=..., index_move_threshold=...) then Backtester(cfg).run(). The nifty_scalper_bt.py present on disk (v4.2, 476 lines) defines no Backtester class and no get_trading_dates, and its Config has neither `interval` nor `index_move_threshold`. The cached .pyc is from a different/older version and fails to unmarshal. So the supposed non-interactive backtest entry point crashes at import/instantiation.
- **Impact:** The documented tuning workflow does not run at all. Any tuning the user believes they performed via run_backtest.py either never executed or ran against a stale, divergent code version — results are untrustworthy and unreproducible.
- **Fix:** Reconcile to a single backtester module: either restore the Backtester/get_trading_dates API (with interval and index_move_threshold in Config) or rewrite run_backtest.py to call the v4.2 functions (generate_signals/execute_trades). Delete the stale __pycache__ .pyc. Add a smoke test that imports and runs one date end-to-end in CI.

### Hardcoded live broker credentials (access tokens + TOTP secret) committed in source
- **Category:** security
- **Location:** `backend/groww/run_backtest.py / backend/groww/GrowwAPI.py` : run_backtest.py:17; GrowwAPI.py:4-5
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** A full Groww JWT access token is embedded in run_backtest.py:17, and GrowwAPI.py hardcodes both an api_key JWT and the raw TOTP `secret` ('ogv(...'). The TOTP secret allows minting fresh tokens indefinitely (token exp 2559104692 ~year 2051). These grant order-placement/live-data roles.
- **Impact:** Full account compromise: anyone with repo access can generate valid sessions and place/cancel real orders. This is the single highest-risk item for real capital.
- **Fix:** Immediately rotate the Groww API key and TOTP secret. Remove all secrets from source; load from environment/secret manager. Purge from git history (filter-repo/BFG). Add secret scanning to CI.

### Backtest signal logic does NOT match the live decision engine
- **Category:** accuracy
- **Location:** `backend/groww/nifty_scalper_bt.py vs backend/analysis/decision_engine.py` : nifty_scalper_bt.py:231-258; decision_engine.py:54-141; trading_engine.py:145-169
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** The live engine (trading_engine.py:145) takes signals from decision_engine.analyze_market — a 67-indicator weighted-confidence model (patterns 30%, momentum 25%, volatility 15%, S/R 15%, volume 15%, threshold 0.70). The backtest uses a totally separate heuristic: 15m close-vs-EMA20 trend + 5m RSI band + 1m volume>SMA + 1m candle move > ATR*1.2. None of the live indicators, weights, or 0.70 confidence gate appear in the backtest.
- **Impact:** Backtest performance has no causal relationship to live performance. Tuning the backtest's parameters optimizes a strategy the system does not actually trade. This defeats the user's stated goal of better accuracy/best results.
- **Fix:** Make the backtester call the SAME signal code path as live (import analyze_market and feed it historical DataFrames bar-by-bar with point-in-time slices), or formally declare the backtest as a separate research strategy. At minimum, document that they are different engines and stop using one to tune the other.

### Scanner uses next-candle High/Low as guaranteed target/SL — look-ahead / fill fantasy
- **Category:** realtime
- **Location:** `backend/groww/New/opportunity_scanner.py` : 195-261, 295-302
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** find_opportunities computes potential_up = opt_next_high - opt_next_open and treats reaching opt_next_high as a WIN with full `profit` captured, and opt_next_low as the SL/risk. It assumes you can exit exactly at the bar's extreme. There is no ordering (did high or low come first?), no fill probability, and the 'result' WIN/LOSS is derived from the same future bar that defines the target. print_table then sums full profit on wins and full risk on losses (:295-299).
- **Impact:** Massively optimistic, look-ahead-biased 'win rate' and 'net P&L'. Real scalps cannot reliably exit at the candle extreme; this overstates edge and will not reproduce live.
- **Fix:** Replace with realistic fills: enter at next-bar open (already done), exit at a fixed target/SL and resolve ambiguous bars (both touched) as the WORSE outcome (SL first), model slippage and spread, and simulate exit using subsequent bars rather than the signal bar's own future extreme. Add a clear disclaimer that the scanner is a labeller, not a P&L estimator.

### No retry or backoff on any Groww API call — single failure silently drops candle update
- **Category:** realtime
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\groww_client.py` : 85-166
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** _make_request() catches Timeout, ConnectionError, and RequestException but immediately returns FAILURE with no retry. On a transient 500 or network blip the entire candle sync job for all three symbols is silently skipped. The heartbeat also fails silently. There is no exponential backoff, no retry counter, and no circuit-breaker.
- **Impact:** During volatile market sessions where connectivity is stressed, the system can run on stale 60-second-old candles for multiple minutes without any alert. Strategy signals and stop-loss checks operate on incorrect price data, creating real financial risk.
- **Fix:** Wrap _make_request() with a retry decorator (e.g., tenacity) configured for 3 attempts with exponential backoff starting at 0.5 s, retrying on Timeout, ConnectionError, and HTTP 500/502/503/429. Add a jitter to avoid thundering-herd on shared rate limits. Log every retry attempt at WARNING level.

### Zero rate-limit handling — HTTP 429 from Groww API causes silent data loss
- **Category:** realtime
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\groww_client.py` : 142-150
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** _make_request() treats any non-200/201 response as a generic FAILURE by reading the error body. HTTP 429 Too Many Requests is never detected specially, so the caller receives {status: FAILURE} and moves on. The heartbeat (every 5 s) and sync job (every 60 s) each make multiple GET calls, plus the direction scheduler reads cached data but the sync job alone makes at least 3 API calls per minute for 3 symbols.
- **Impact:** If Groww imposes per-minute quotas and the system hits them, every subsequent call in that window is silently dropped. The DB is not updated and the last known candle timestamp diverges from wall-clock time. No alert is sent.
- **Fix:** Detect 429 explicitly in _make_request() (line ~143) and raise a specific RateLimitError. In the scheduler, catch this error, sleep for the retry-after duration (parse from response headers), and resume. Add a Redis counter for API call budgeting.

### candle_service._get_smart_window() uses naive datetime.now() — wrong timestamps sent to Groww API
- **Category:** accuracy
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\candle_service.py` : 128-164
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** datetime.now() at line 133 returns the system local time without any timezone. If the server is running in UTC (typical for cloud/VPS deployments), the computed start_time and end_time strings will be 5 h 30 min behind IST. The Groww historical API interprets these as IST, so the requested window is shifted forward by 5.5 hours — causing the API to return incorrect or empty candle ranges during morning hours, and completely wrong data windows during afternoon trading.
- **Impact:** All candle data fetched by sync_candles() and sync_realtime() will be from the wrong time window when running on a UTC server. The 1-minute sync feeds all aggregated timeframes (5m, 15m, 60m) so the entire analytical dataset will be wrong. Strategy signals fired from stale/wrong candles create false entries and exits.
- **Fix:** Replace `now = datetime.now()` (line 133) with `now = datetime.now(pytz.timezone('Asia/Kolkata'))`. Then use `now.replace(tzinfo=None)` for the formatting step if the API expects naive IST strings, or pass ISO8601 with +05:30 offset if the API accepts it. Also add import pytz at the top of candle_service.py.

### sync_and_aggregate_job calls full sync_candles (delete+insert) every minute instead of incremental sync_realtime
- **Category:** realtime
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\scheduler.py` : 198-210
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** sync_candles() (candle_service.py:166) always calls _execute_sync with mode='full', which in turn calls _save_to_db() — delete_many then insert_many on the entire 7-day window of 1m candles, every single minute. The delete_many + insert_many on potentially thousands of records is non-atomic. During the window between delete and insert, any consumer reading from the 'candles' collection gets an empty result. sync_realtime() (which does an upsert) is defined but never called from the scheduler.
- **Impact:** Every 60 seconds there is a brief window where the candles collection is empty. The direction_scheduler reads DB every 1 second and will receive [] during this gap, causing direction analysis to either fail or fall back to 5m data. Strategy evaluation in the heartbeat will also read empty candles. This is a real data-integrity hole during live trading.
- **Fix:** Change line 200 to call candle_service.sync_realtime() for the scheduled 1-minute job (upsert only new/updated candles). Reserve sync_candles for startup or explicit full-reload triggers. Alternatively, switch _save_to_db to use db.upsert_candles (bulk_write) instead of delete+insert.

### Non-atomic delete+insert in _save_to_db creates a read gap in the candles collection
- **Category:** data-integrity
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\candle_service.py` : 212-220
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** delete_many (line 216) fires first, then insert_many (line 217). Any MongoDB read between these two statements will find zero candles for that symbol+interval. MongoDB has no transaction semantics applied here. The direction_scheduler reads candles every second, and the heartbeat triggers strategy evaluation also reading candles. There is a guaranteed race.
- **Impact:** Up to several hundred milliseconds per minute where candles appear empty. In a 5-second heartbeat cycle this creates false 'no data' conditions during which strategies may refuse to evaluate or produce NEUTRAL signals, missing real trading opportunities at candle-close moments.
- **Fix:** Replace delete+insert with db.upsert_candles() bulk_write (already defined in mongodb.py:76) which uses ordered=False UpdateOne/upsert operations. This is safe to run concurrently. If a full replace is truly needed, use a MongoDB aggregation pipeline-based replace or a rename approach (write to temp collection, rename).

### 401 token expiry causes complete system halt with no automatic refresh
- **Category:** realtime
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\groww_client.py` : 122-130
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** When the Groww token expires (logged at CRITICAL level, line 123), _make_request returns FAILURE. The scheduler jobs check for active_user but never check if the token is expired (get_token_expiry_time/is_token_expired from time_utils exist but are never called from any scheduler path). _get_headers() retries _load_token() only when access_token is None (line 71), not when it has an expired value. Groww tokens expire at 6 AM IST per get_token_expiry_time() but the scheduler starts at app boot and the token is loaded once and cached on the GrowwClient instance.
- **Impact:** From midnight until the user manually refreshes the token, every API call fails silently. All candle syncs, LTP heartbeats, and order reconciliations return FAILURE. The system continues running but produces no real data, trading on stale signals.
- **Fix:** In _get_headers(), call is_token_expired() against the stored expiry from DB before every request (or at minimum cache the expiry and check it). On expiry, emit a CRITICAL log and trigger a Telegram alert. Add a pre-scheduled job at 05:55 IST to warn the user. Consider auto-TOTP refresh if the secret is stored.

### Dead API methods called in market.store.ts: instrumentsApi.getCount and marketApi.getLtp do not exist
- **Category:** correctness
- **Location:** `frontend/src/store/market.store.ts` : 86, 95
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** fetchSyncInfo (line 86) calls instrumentsApi.getCount() which is not defined in market.api.ts — only syncInstruments and getInstruments exist. getLtp (line 95) calls marketApi.getLtp(symbol) which also does not exist in market.api.ts. Both throw TypeError at runtime, silently caught by console.error. syncInfo remains null and getLtp always returns 0.
- **Impact:** The instrument count status panel on Strategy.tsx always shows 'No instruments synced' even after a successful sync. Any component calling getLtp receives 0 as LTP, making live price displays on any card that uses this path show ₹0.00.
- **Fix:** Add getCount to instrumentsApi in market.api.ts (GET /instruments/count or reuse the syncInstruments total field). Add getLtp to marketApi (GET /market/ltp/:symbol). Alternatively if the endpoints do not exist on the backend, remove these dead store methods and replace getLtp usage with the trade.ltp field already present on Trade objects.

### fetchExpiries double-unwrap bug: sets response.expiries on an already-unwrapped string[]
- **Category:** data-integrity
- **Location:** `frontend/src/store/market.store.ts` : 62-69
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** instrumentsApi.getExpiries (market.api.ts line 72-76) already unwraps the response and returns a plain string[]. But market.store.ts line 65 then reads response.expiries on that string[], which is always undefined. The store sets expiries[underlying] = undefined. In Strategy.tsx the dropdown never populates.
- **Impact:** The expiry dropdown in the strategy form is always empty for every index. A user cannot create a strategy using the form — they are forced to type the expiry manually or the form fails validation. This is a complete functional break of strategy creation.
- **Fix:** Change line 65 in market.store.ts from `expiries: { ...state.expiries, [underlying]: response.expiries || [] }` to `expiries: { ...state.expiries, [underlying]: response || [] }` since getExpiries already returns the array directly.

### No token refresh: expired JWT causes silent 401 redirect loop during active trading sessions
- **Category:** security
- **Location:** `frontend/src/api/axios.ts` : 30-38
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** The 401 interceptor immediately removes the token and redirects to /login via window.location.href (line 37). authApi.refreshToken() exists in auth.api.ts (line 43) but is never called. A JWT with a short TTL (e.g. 1 hour) will expire mid-session. Every polling interval will then fire a 401, causing full page reloads that interrupt an active live trade.
- **Impact:** During a live intraday trading session, token expiry mid-session causes the UI to force-redirect to login while live positions are open. The trader loses all visibility into open positions until they re-authenticate. Any in-flight exit or modify request that gets a 401 will be silently lost.
- **Fix:** Implement a token refresh interceptor: on 401, queue the failed request, call authApi.refreshToken(), update localStorage with the new token, and replay the queued request. Use axios-auth-refresh library or implement a custom queue-flush pattern. Set a proactive refresh at 80% of token TTL using a setTimeout in the auth store initialize() function.

---

## HIGH

### Groww credentials saved as broker_connected=True before token is verified in login route
- **Category:** correctness
- **Location:** `backend/routes/auth_routes.py` : 134-140
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** In the login() handler (line 134-140), if groww_api_key and groww_api_secret are present in the request body, the code immediately sets broker_connected=True in the database without calling generate_access_token() or performing any validation against the Groww API. The update_groww_credentials endpoint does perform validation, but the login path skips it. A user could supply random strings and the system would mark their broker as 'connected'.
- **Impact:** Subsequent live-mode trade attempts (get_data_client, get_groww_client) will succeed at the client construction stage but fail at the Groww API level with 401, creating confusing error states. Risk controls that depend on broker_connected status will be bypassed.
- **Fix:** Remove the broker credential update from the login handler entirely. Credentials should only be saved via /update-groww-credentials, which already validates against the Groww API. If login-time credential update is desired, reuse the same validation flow.

### get_data_client() leaks any user's Groww access token to any paper user — cross-user token sharing
- **Category:** security
- **Location:** `backend/routes/market_routes.py` : 17-35
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** When a paper-mode user makes any market data request, get_data_client() falls back to db.users.find_one({'broker_connected': True}) (line 31) and creates a GrowwClient with that found user's credentials. This means all paper users share (and consume the API quota of) the first connected live-mode user found in the database. The found user's token is used without their knowledge or consent.
- **Impact:** API quota exhaustion for live users. If multiple paper users poll frequently, the live user's token hits Groww rate limits, causing live trade execution to fail. Also a conceptual privilege escalation: paper users are accessing live data via another user's credentials.
- **Fix:** Create a dedicated system-level service account for market data, or configure a read-only API key in config for data-fetching. Do not traverse other users' credentials. Alternatively, serve cached data from Redis/MongoDB without hitting the live API for paper users.

### Redis distributed lock comparison is broken with decode_responses=True
- **Category:** correctness
- **Location:** `backend/routes/trade_routes.py` : 22-45
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** The lock identifier is set as str(time.time()) (line 33). The Redis client is configured with decode_responses=True (redis_client.py line 29), so client.get(lock_key) returns a Python str. The lock release check at line 41 does 'if current_value and current_value == identifier' — this comparison works because both are strings. However, the lock is acquired with client.set(lock_key, identifier, nx=True, ex=timeout), which stores the string. The real problem is that time.time() has microsecond precision but two near-simultaneous requests within the same microsecond would produce the same identifier, meaning release of one lock releases both. Additionally, if the executing code takes longer than the 5-second ex= expiry, the lock auto-expires and a concurrent request acquires it before the finally block runs; the finally block then reads a new identifier from a new holder and does not delete it (correct), but the original request continues executing concurrently — this is a classic TOCTOU on the lock.
- **Impact:** Under high concurrency (e.g., scheduler plus manual user action), duplicate orders can be placed for live accounts, causing double positions and unintended risk exposure.
- **Fix:** Replace the identifier with uuid.uuid4() to guarantee uniqueness. Use a Lua script (or Redis SET+GET atomically) for the release to avoid the race between GET and DELETE. Consider using the Redlock algorithm for production-grade distributed locking.

### Fail-open Redis lock: when Redis is down, all trade concurrency protection is disabled
- **Category:** risk
- **Location:** `backend/routes/trade_routes.py` : 24-27
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** If redis_client.client is None (Redis unavailable), acquire_trade_lock yields True unconditionally (line 26). This means all concurrent trade operations — place_order, exit_trade, exit_all_trades, execute_strategy_trade, quick_trade — proceed without any serialisation. If the scheduler is also running trade logic at the same moment, duplicate orders are placed.
- **Impact:** Redis outage causes silent removal of the only concurrency guard. For a live trading system this is a critical risk: during a Redis failure (which often coincides with high market volatility), trades could be duplicated.
- **Fix:** Change fail-open to fail-closed for live mode: if Redis is down and execution_mode is LIVE, return an error rather than proceed. For paper mode, fail-open is acceptable. Gate on get_user_execution_mode() before deciding the fallback.

### update_groww_credentials saves token_generated_at but not groww_token_expiry — token expiry is never tracked
- **Category:** accuracy
- **Location:** `backend/routes/auth_routes.py` : 278-281
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** When a token is successfully generated (line 273-281), only 'token_generated_at' is written. The token_response may contain an 'expiry' field (generate_access_token() returns result.get('expiry') at groww_client.py line 225). The groww_token_expiry field in the user document (set by update_user_token in mongodb.py line 156-162) is never populated through this code path. The is_token_expired() utility in time_utils.py and auth_routes.py is never called to gate API calls. The GrowwClient._load_token() (groww_client.py line 50-61) loads the token without checking expiry.
- **Impact:** Expired Groww tokens are silently used in API calls until a 401 is returned by Groww. In a live trading context, SL/target exit orders fail silently during the expiry window (daily at ~6 AM IST per get_token_expiry_time). The scheduler may continue attempting to fetch data with an expired token.
- **Fix:** In update_groww_credentials, also write 'groww_token_expiry': token_response.get('expiry') to the user document. In _load_token(), check is_token_expired() before setting self.access_token. Add a pre-request hook in GrowwClient to detect 401 responses and trigger a token refresh.

### No input validation on password strength during registration
- **Category:** security
- **Location:** `backend/routes/auth_routes.py` : 45-51
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** The register() handler only checks that email and password are non-empty (lines 48-51). No minimum length, no complexity rules, no email format validation. A password of '1' is accepted. There is also no CSRF protection (no SameSite cookie policy, no CSRF token) and no rate limiting on the auth endpoints — the login endpoint is fully brute-forceable.
- **Impact:** Weak passwords allow brute-force attacks on the login endpoint. Since the JWT is 24 hours and has no revocation, a compromised account stays compromised for a full day even after password reset.
- **Fix:** Enforce minimum password length (12 chars) and validate email format with a regex or email-validator library. Add flask-limiter with limits of e.g. 5/minute on /api/auth/login and /api/auth/register. Consider adding TOTP second-factor for live-mode users.

### Flask debug mode is on by default and app.run is used — unsafe for any production-like deployment
- **Category:** security
- **Location:** `backend/config.py` : 15
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** DEBUG defaults to True (config.py line 15: os.getenv('DEBUG', 'true').lower() == 'true'). Flask's debug mode enables the interactive Werkzeug debugger, which allows arbitrary Python code execution via the browser if debug PIN is guessed or leaked. app.run() (app.py line 140) is the single-threaded Werkzeug dev server, which cannot handle concurrent requests — the direction scheduler's 1-second loop plus a live user's HTTP requests would queue behind each other.
- **Impact:** Remote code execution risk if the application is accessible from outside localhost with debug=True. Single-threaded dev server will cause request timeouts under any real load: the direction scheduler thread cannot help because Flask's dev server serialises request handling.
- **Fix:** Default DEBUG to false. Deploy with gunicorn (e.g. gunicorn -w 4 -k gevent app:app) or uvicorn. Add an explicit guard: if config.DEBUG and config.EXECUTION_MODE == 'LIVE': raise RuntimeError('Cannot run in DEBUG+LIVE mode').

### Unvalidated int() casts on query params crash with 400-equivalent unhandled ValueError
- **Category:** correctness
- **Location:** `backend/routes/trade_routes.py` : 218, 403, 441
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** At trade_routes.py line 218, 403 (statistics), and 441 (journal), the code does int(request.args.get('limit', 50)) and int(request.args.get('days', 30)) without try/except. A request like GET /trade/trades?limit=abc raises an unhandled ValueError that propagates to Flask's 500 handler. The same pattern exists in market_routes.py (get_symbol_direction atm_offset processing implied by the analysis), strategy_routes.py line 226 (limit), and instruments_routes.py line 20 (limit).
- **Impact:** A malicious or misbehaving frontend can trigger 500 errors by sending invalid query parameters. Log noise and potential DoS by keeping the app's error-logging busy.
- **Fix:** Wrap all request.args int() conversions: use a helper like 'safe_int(val, default, min_val, max_val)' that returns the default on parse failure and clamps to a safe range. Also cap limit to a maximum (e.g., 500) to prevent excessive MongoDB queries.

### Telegram bot token and chat ID stored in plaintext in MongoDB settings collection
- **Category:** security
- **Location:** `backend/routes/settings_routes.py` : 163-167
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** configure_telegram() saves bot_token and chat_id directly to db (upsert_settings) without encryption. The same applies to the update_settings route (line 67-70 where telegram_bot_token is an allowed_field). Unlike Groww API keys (which use encryption.encrypt()), Telegram credentials are cleartext in the database.
- **Impact:** A MongoDB database dump exposes all users' Telegram bot tokens. An attacker with token access can send arbitrary messages to all users' Telegram chats, impersonate the trading system, or use the bots for spam/phishing.
- **Fix:** Encrypt Telegram bot_token using the existing encryption utility before storing, and decrypt on read, exactly as is done for groww_api_key.

### candle_service._get_smart_window uses naive local time, not IST — wrong fetch windows outside IST timezone
- **Category:** realtime
- **Location:** `backend/services/candle_service.py` : 128-164
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** The _get_smart_window() function uses datetime.now() (line 133) — the local system clock with no timezone. If the server runs in UTC (common on Linux servers), the market-open/close hour checks (lines 143-145: 'elif target_end.hour < 9') compare UTC hours against IST thresholds (9:15 AM IST = 3:45 AM UTC). This causes the function to believe it is before market open when the market is actually open, and sets the end_dt to the previous day's 15:30, fetching stale data. The CandleService also uses 'datetime.fromtimestamp(c[0])' (candle_service.py line 107) which is local-time-dependent.
- **Impact:** On a UTC server, all candle sync operations during IST market hours fetch data up to the previous trading day instead of the current session. The direction engine and decision engine then operate on stale candles, producing wrong signals and potentially wrong trade entries/exits.
- **Fix:** Replace datetime.now() with get_ist_now() from utils.time_utils throughout candle_service.py. Replace datetime.fromtimestamp(c[0]) with datetime.fromtimestamp(c[0], tz=IST).isoformat() to store timezone-correct datetimes.

### Direction calculation silently falls back to using 5m candles as 1m candles, corrupting multi-timeframe analysis
- **Category:** accuracy
- **Location:** `backend/routes/market_routes.py` : 91-94, 168-171
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** In get_symbol_direction() (line 91-94): if len(candles_1m) < 50, df_1m = df_5m.copy(). In _calculate_directions_on_demand() (line 170-171): df_1m = df_5m.copy() unconditionally. Feeding 5-minute bars where 1-minute bars are expected corrupts every indicator that relies on 1m granularity (e.g. momentum oscillators, volume per-minute). The direction engine will compute internally consistent but factually wrong values, and since it sees the same data at two 'different' timeframes, divergence signals become meaningless.
- **Impact:** Market direction (BULLISH/BEARISH/NEUTRAL) returned to the frontend and used in strategy execution decisions is calculated from wrong input data. Strategies configured to use_direction_engine=True may enter trades in the wrong direction.
- **Fix:** Return an error or NEUTRAL/low-confidence signal when 1m data is genuinely unavailable rather than substituting 5m data silently. Log a warning with the actual candle count. Ensure the scheduler always syncs 1m candles for all index symbols before the direction engine runs.

### bulk_upsert_instruments uses delete_many + insert_many — instruments disappear between the two calls
- **Category:** data-integrity
- **Location:** `backend/database/mongodb.py` : 274-278
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** bulk_upsert_instruments() and instrument_sync.sync_instruments() (instrument_sync.py line 43-44) both call db.instruments.delete_many({}) followed by insert_many(). Between the delete and insert, any concurrent query for instruments (option chain lookup, ATM strike resolution for an active trade) returns empty results. MongoDB has no transactions by default in standalone mode; even in a replica set, the two operations are not wrapped in a session-level transaction.
- **Impact:** During an instrument sync (which can be triggered by any authenticated user via POST /api/instruments/sync or the scheduler), live strategies performing ATM strike resolution will fail to find their symbols, causing missed entries or failed exits.
- **Fix:** Use a two-collection swap pattern: write new instruments to a staging collection (instruments_staging), then use a rename or bulk upsert with updateOne + upsert=True on the live collection. This eliminates the gap. Alternatively, wrap in a MongoDB multi-document transaction (requires replica set).

### get_today_trades uses UTC midnight boundary but trade timestamps may be in IST — wrong daily P&L
- **Category:** accuracy
- **Location:** `backend/database/mongodb.py` : 255-259
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** get_today_trades() computes today_start as datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) — midnight UTC. Indian market trades happen 9:15 AM to 3:30 PM IST, which is 3:45 AM to 10:00 AM UTC. A trade placed at 9:15 AM IST on June 6 has a UTC timestamp of 3:45 AM June 6. The query filter $gte: UTC midnight June 6 is correct for that case. However, if the server's clock drifts or if some code stores entry_time as datetime.now() (local) instead of datetime.utcnow(), the timestamps will be inconsistent and some trades will be excluded from the daily calculation.
- **Impact:** Daily P&L totals, win rate, and daily-limit checks (risk_manager.can_strategy_trade) may exclude trades made near the boundary, causing the system to undercount losses and not trigger the loss limit stop.
- **Fix:** Enforce a single timestamp convention throughout: always use datetime.utcnow() for all stored timestamps. Audit every db.create_trade() call to confirm entry_time is set to datetime.utcnow(). In quick_trade (trade_routes.py line 615), entry_time is already datetime.utcnow() — confirm this is consistent everywhere in the trading engine.

### is_auto_exit_time() references config.AUTO_EXIT_HOUR and config.AUTO_EXIT_MINUTE which do not exist in config.py
- **Category:** correctness
- **Location:** `backend/utils/time_utils.py` : 32-38
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** is_auto_exit_time() (lines 32-38) accesses config.AUTO_EXIT_HOUR and config.AUTO_EXIT_MINUTE. These attributes are not defined anywhere in config.py (which only defines MARKET_OPEN_HOUR/MINUTE and MARKET_CLOSE_HOUR/MINUTE). Calling is_auto_exit_time() raises AttributeError at runtime.
- **Impact:** Any code path that calls is_auto_exit_time() — including the scheduler that triggers automatic trade exits before market close — will crash with an AttributeError, disabling the auto-exit safety feature entirely. Open positions will not be closed automatically.
- **Fix:** Add AUTO_EXIT_HOUR = 15 and AUTO_EXIT_MINUTE = 15 (or similar) to config.py, and load them from env vars with appropriate defaults. Alternatively, derive auto-exit time from MARKET_CLOSE_HOUR/MINUTE minus a configurable offset.

### Live trade limits endpoint returns hardcoded zeros with a 'not fully implemented' message
- **Category:** accuracy
- **Location:** `backend/routes/trade_routes.py` : 371-386
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** The /api/trade/limits endpoint for LIVE mode (lines 381-386) returns available_balance=0 and used_margin=0 with the message 'Live balance fetch not fully implemented in demo'. The GrowwClient.get_margins() method exists (groww_client.py line 657-677) and would return actual margin data. The route never calls it.
- **Impact:** Live users see zero available balance, which makes risk management decisions at the UI level impossible. If any automated component relies on this endpoint to check available capital before placing orders, it will incorrectly believe no capital is available (or conversely, if it treats zero as 'not checked', it may place orders without capital verification).
- **Fix:** Replace the stub with: result = groww.get_margins(segment='FNO'); return jsonify(result.get('data', {})) if result.get('success') else jsonify({'error': result.get('error')}), 400.

### candle_service.generate_mock_candles is called but not defined in candle_service.py
- **Category:** correctness
- **Location:** `backend/routes/strategy_routes.py` : 232
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** The get_candles route (strategy_routes.py line 232) calls candle_service.generate_mock_candles(symbol, int(interval), limit). This method does not exist in backend/services/candle_service.py as read — the CandleService class has no generate_mock_candles method. Calling this will raise AttributeError at runtime whenever real candle data is unavailable.
- **Impact:** Any request to /api/strategy/candles/{symbol} when the DB has fewer than 10 candles raises an unhandled AttributeError, returning a 500 to the frontend. Chart rendering fails completely during startup or after a fresh install before candles are synced.
- **Fix:** Implement generate_mock_candles(symbol, interval, limit) in CandleService that produces synthetic OHLCV data around a reasonable seed price. Alternatively, return an empty array with a warning message rather than attempting mock generation.

### Risk check in start_strategy does not check max_concurrent_trades or overall P&L limits
- **Category:** risk
- **Location:** `backend/routes/strategy_routes.py` : 155-158
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** start_strategy() calls risk_manager.can_strategy_trade(strategy, settings) (line 156). can_strategy_trade() in risk_manager.py (lines 12-35) only checks the kill switch, per-strategy daily order count, and per-strategy profit/loss limits. It does not check overall portfolio limits (max_concurrent_trades, overall_max_profit, overall_max_loss) — those are in can_overall_trade(). Starting multiple strategies simultaneously can exceed the user's max_concurrent_trades setting without triggering any block.
- **Impact:** A user with max_concurrent_trades=3 and overall_max_loss=5000 can activate 10 strategies simultaneously if each individual strategy has not hit its own limit. The overall portfolio risk control is bypassed.
- **Fix:** In start_strategy(), also call risk_manager.can_overall_trade(settings, active_trades_count) before activating the strategy. Count active trades with len(db.get_active_trades(user_id)).

### GrowwClient instantiated fresh on every heartbeat tick - DB hit every 5 seconds
- **Category:** performance
- **Location:** `backend/services/scheduler.py` : 133-138
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** market_heartbeat_job calls get_groww_client(user_id) which creates a new GrowwClient, which calls _load_token(), which calls db.get_user_by_id() (a MongoDB round-trip), which calls encryption.decrypt(). This happens 12 times per minute, 720 times per hour. Also, get_trading_engine(user_id) is called every tick. Each call creates (or retrieves) engine instances via new DB lookups.
- **Impact:** Unnecessary MongoDB and CPU load every 5 seconds. Token decryption on every tick adds latency to the hottest code path. Under load, MongoDB query latency directly adds to heartbeat execution time, risking job overlap.
- **Fix:** Cache the authenticated client instance as self._client on the SchedulerService, refreshed only when user changes or a 401 is received. Same for the trading engine. Add a single user-check at startup and on DB change events.

### _get_active_user() queries MongoDB on every heartbeat - 12 queries/minute with no cache
- **Category:** performance
- **Location:** `backend/services/scheduler.py` : 40-49
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** market_heartbeat_job (line 129) calls self._get_active_user() which runs db.users.find_one({'broker_connected': True}) every 5 seconds. With no index on broker_connected, this is a full collection scan. The result is thrown away each time.
- **Impact:** 12 collection scans per minute on the users collection. As user count grows this degrades linearly. More critically, it adds latency to the 5s heartbeat critical path.
- **Fix:** Cache active_user_id in self.active_user_id (already stored at start() line 107 but never used in market_heartbeat_job). Use self.active_user_id directly in the heartbeat instead of re-querying. Add a MongoDB index on broker_connected.

### Direction scheduler re-aggregates MongoDB candles every 1 second but candles only update every 60 seconds
- **Category:** realtime
- **Location:** `backend/services/direction_scheduler.py` : 64-73
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** _run_loop runs every 1 second, reading 200 1-minute candles from MongoDB and re-running the full aggregation + direction analysis pipeline. But MongoDB candles are only updated by sync_and_aggregate_job every 60 seconds. So 59 out of every 60 iterations are doing identical work on identical data, burning 3 MongoDB reads (one per symbol) + full DataFrame aggregation + ML/indicator computation per second.
- **Impact:** 59x redundant computation every minute. More critically, the direction analysis does NOT incorporate the live LTP (fetched every 5 seconds) into candle close values. A 50-point NIFTY move within a minute is invisible to the direction engine until the next 60s sync.
- **Fix:** In _update_direction, after loading DB candles, patch the current forming candle's close (and high/low) with the live LTP from Redis (already fetched at line 121). This makes the analysis respond to intra-minute price moves. Also reduce the loop to run every 5s (matching heartbeat) rather than every 1s, or add a 'data_changed' flag to skip recomputation when candles haven't been refreshed.

### redis_client has no reconnection logic - one connection failure permanently disables all caching
- **Category:** realtime
- **Location:** `backend/database/redis_client.py` : 21-38
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** _initialize sets self.connected = False on ConnectionError and never retries. All subsequent calls to cache_ltp, get_cached_ltp, set, get short-circuit with None/False. If Redis is temporarily unavailable at startup, or drops mid-session, the entire caching layer is dead for the rest of the process lifetime. There is also no health-check or reconnect method.
- **Impact:** Without Redis: LTP is not cached so trading engine has no price input (evaluate_strategies gets no price), direction results are not shared cross-process, and all 1s direction loop work is wasted. The system silently degrades to full blindness.
- **Fix:** Implement lazy reconnection: in get/set/cache_ltp, if not self.connected, attempt self._initialize() with a backoff (e.g., retry at most once per 30 seconds). Alternatively use redis-py's retry-on-error mechanism (Retry class). Log a Telegram alert when Redis goes down.

### LTP Redis TTL is 10s but heartbeat interval is 5s - race condition can serve expired data
- **Category:** realtime
- **Location:** `backend/database/redis_client.py` : 47-49
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** cache_ltp stores price with expiry=10 (seconds). The heartbeat fires every 5 seconds. If the heartbeat is delayed (MongoDB slow query, GIL contention, Python GC pause), the 10s TTL can expire before the next successful write. get_cached_ltp returns None, and the caller (direction_scheduler.py:122) passes live_ltp=None to analyze_direction, which then has no live price context.
- **Impact:** Any heartbeat delay > 10 seconds (possible under load) causes the direction engine to run with no live LTP. On a volatile day this is a multi-point blind spot. The problem is compounded because TTL=10 gives only a 5-second margin above the poll interval.
- **Fix:** Increase TTL to 30s to provide a safe margin. More importantly, track the last_ltp per symbol in a process-local dict in the scheduler, and pass it directly to evaluate_strategies without relying on Redis round-trip. Redis should be a fallback for cross-process sharing, not the primary store.

### CandleService uses its own raw requests.Session instead of GrowwClient - token management is duplicated and divergent
- **Category:** correctness
- **Location:** `backend/services/candle_service.py` : 83
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** fetch_candles_from_groww uses a bare requests.get call with a manually constructed Authorization header from the token passed as a parameter. It does not use GrowwClient._make_request or GrowwClient.session. Any improvements to GrowwClient (retry logic, header version, SSL pinning) do not apply to candle fetches. The token is also passed as a plaintext string from the caller (scheduler.py:190) after manual decryption.
- **Impact:** Two divergent HTTP client paths with inconsistent error handling, no shared session (no connection pooling), no centralized retry. Candle fetches have no retry on failure. Token handling is inconsistent.
- **Fix:** Remove the raw requests.get in candle_service.py. Instead, inject a GrowwClient instance into CandleService and call client.get_historical_candles(). This unifies HTTP management and leverages the session object for connection pooling.

### sync_and_aggregate_job calls sync_candles (full/delete mode) every minute instead of sync_realtime (upsert mode)
- **Category:** data-integrity
- **Location:** `backend/services/scheduler.py` : 199-204
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** scheduler.py:199 calls candle_service.sync_candles() which internally calls _execute_sync with mode='full' which calls _save_to_db which does delete_many + insert_many. This destructive replacement runs every 60 seconds on live 1-minute candles during market hours. Any read in the delete-insert window gets an empty dataset.
- **Impact:** See also the data-integrity issue above. Even if individual incidents last only milliseconds, with 3 symbols * 60 cycles/hour = 180 destructive replacements per hour during market hours, the probability of a race conflict is non-trivial on busy systems.
- **Fix:** Change line 199 to call candle_service.sync_realtime() instead of sync_candles() during market hours. The full sync is appropriate only at startup or for an explicit 'refresh historical' command.

### Daily 1D candle aggregation uses pd.resample('1D') with no timezone-aware session boundary - aggregates across midnight UTC
- **Category:** accuracy
- **Location:** `backend/services/scheduler.py` : 228-248
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** The daily aggregation at line 233 uses df_day.resample('1D') on a DataFrame whose datetime column may be naive local or IST-aware (created at line 216-219 with pd.to_datetime without explicit timezone). resample('1D') snaps to midnight UTC, not midnight IST (00:00 IST = 18:30 UTC previous day). So the daily candle open is the 18:30 UTC bar from the day before, not the 09:15 IST bar of the trading session.
- **Impact:** Daily OHLC values are wrong: open is not the true session open, and high/low can include pre-market/cross-midnight UTC data. Any daily-timeframe strategy signals or support/resistance levels computed from 1D candles are inaccurate.
- **Fix:** Use df_day.resample('1D', offset='9h15min') anchored to IST market open, or apply a custom resampling that groups by trading session date (IST date of the 09:15 bar). Alternatively convert datetime to IST-aware before resample and use origin='start_day' with the correct session offset.

### instrument_sync.py does delete_many + insert_many without atomic guarantee - window of empty instruments collection
- **Category:** data-integrity
- **Location:** `backend/services/instrument_sync.py` : 43-44
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** Line 43 deletes all instruments, then line 44 inserts new ones. Between these two operations the instruments collection is completely empty. Any simultaneous request for ATM strikes, instrument lookup for order placement, or strategy initialization will find no instruments and fail silently or place orders with wrong symbols.
- **Impact:** During the ~100ms to several seconds of the insert, any order-placement attempt that looks up trading_symbol will find nothing. In live trading mode this could cause order rejections or, worse, the engine could fallback to a stale symbol.
- **Fix:** Use a two-collection swap pattern: insert into instruments_staging, then db.command(rename) to atomically replace instruments with instruments_staging. Or mark records with a sync_batch_id and delete only records from the previous batch after the new insert completes.

### Direction scheduler stores direction result as str(result) in Redis - dict serialized as Python repr, not JSON
- **Category:** correctness
- **Location:** `backend/services/direction_scheduler.py` : 139
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** redis_client.set(f'direction:{symbol}', str(result), ex=10) converts the result dict to a Python string via str() (e.g., "{'direction': 'BULLISH', 'confidence': 0.85, ...}'"). Any consumer reading this key with redis_client.get() gets a Python-repr string, not JSON. Parsing it requires eval() (unsafe) or ast.literal_eval() (fragile). No consumer-safe deserialization exists.
- **Impact:** Any cross-process or cross-service consumer of the direction Redis key gets an unparseable string unless they use ast.literal_eval. If the result contains non-literal types (datetime, numpy float32), ast.literal_eval also fails.
- **Fix:** Serialize with json.dumps(result, default=str) and deserialize with json.loads(). Add a json.loads wrapper in get_cached_direction.

### No rate-limit handling for Groww live-data API - 5s heartbeat * 3 symbols risks quota exhaustion
- **Category:** realtime
- **Location:** `backend/services/scheduler.py` : 141-165
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** The heartbeat fetches LTP for 3 symbols every 5 seconds (720 calls/hour on the live-data/ltp endpoint). In addition, sync_and_aggregate_job makes 3 historical candle calls per minute (180/hour). The system has no rate-limit tracking, no quota counter, no back-pressure mechanism, and no handling of 429 responses from Groww.
- **Impact:** If Groww enforces rate limits (typical: 1 req/sec or 60 req/min per endpoint), the system will receive 429s frequently. Because there is no retry with backoff, these silently fail. The LTP feed goes dark and the trading engine operates blind.
- **Fix:** Implement a token-bucket rate limiter per endpoint family. Track 429 responses in _make_request and apply a minimum 60s cool-down. Log rate-limit events to Redis for monitoring. Consider batching all 3 symbols in a single get_ltp call (already done at line 141) and reducing call frequency to every 10s.

### Direction scheduler fallback mistakenly uses 5m DataFrame as df_1m parameter
- **Category:** accuracy
- **Location:** `backend/services/direction_scheduler.py` : 105
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** In the fallback path (lines 99-107), when 1m candles are insufficient, df_1m is set to pd.DataFrame(candles_5m). This 5m DataFrame is then passed as the df_1m argument to analyze_direction(df_1m=df_1m, df_5m=df_5m, df_15m=df_15m). The direction engine receives 5m data in the df_1m slot, meaning any indicator logic that assumes 1m granularity (e.g., 14-period RSI on 1m = 14 minutes vs 70 minutes on 5m) will compute values on the wrong timeframe.
- **Impact:** When 1m data is absent (first minutes of day, weekend restart), the direction engine silently processes wrong-timeframe data without any warning. Signal confidence values are wrong and strategy decisions are based on incorrect timeframe analysis.
- **Fix:** When 1m data is insufficient, do not pass 5m data as df_1m. Instead pass an empty DataFrame or None and have analyze_direction handle the missing-1m case explicitly. At minimum, log a warning that the fallback is active.

### Dashboard AI signal has no periodic poll — badge goes arbitrarily stale
- **Category:** realtime
- **Location:** `frontend/src/pages/Dashboard.tsx` : 259-261
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** fetchDecision is triggered only when analysisSymbol changes (useEffect dep array = [analysisSymbol, fetchDecision]). There is no setInterval for the AI decision on Dashboard. A user who loads the page and leaves the symbol at 'NIFTY' will see the same signal badge indefinitely until they click another symbol tab or hit manual Refresh. config.SIGNAL_POLL_INTERVAL = 10 s is defined but never used here.
- **Impact:** The AI signal shown as the primary decision on the Dashboard can be many minutes stale. For a scalping system where signal direction can flip every few candles, an outdated signal creates false confidence and can result in wrong manual trade decisions.
- **Fix:** Add a setInterval(()=> fetchDecision(analysisSymbol, 5), config.SIGNAL_POLL_INTERVAL) inside the same or a separate useEffect with [analysisSymbol] as dependency, clearing the timer on cleanup. Match the pattern used in Signals.tsx lines 30-38.

### Active trade P&L computed from stale ltp field — not real-time price
- **Category:** realtime
- **Location:** `frontend/src/pages/Dashboard.tsx` : 518-520
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** Dashboard.tsx line 519 and Trades.tsx line 390 compute live P&L as (trade.ltp || trade.entry_price) * quantity * side_multiplier. The ltp field on the Trade object comes from the backend's last-known LTP embedded in the trade record itself — it is only updated when the backend processes a tick. The frontend poll is 10 s on Trades, meaning the displayed P&L can lag the real market by up to 10 s. Worse, the Dashboard does not poll active trades at all; ltp is from the initial mount fetch.
- **Impact:** Displayed unrealized P&L is stale. For options that can move 5-10% in a single candle, this creates a materially incorrect risk picture. On the Dashboard the lag is unbounded.
- **Fix:** Either: (a) reduce the active-trades poll interval to config.TRADE_POLL_INTERVAL (3 s) and ensure Dashboard also polls on the same timer, or (b) open a WebSocket to receive real-time LTP ticks and update trade.ltp in-store on each tick. At minimum, Dashboard should run a 3 s interval for fetchActiveTrades like Trades.tsx does.

### EMA warm-up uses first close as seed instead of SMA — produces wrong values for early bars
- **Category:** accuracy
- **Location:** `frontend/src/utils/indicators.ts` : 22-23
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** calculateEMA initializes `ema = data[0].close` at line 22 and immediately applies the EMA multiplier starting at index 0 (loop starts at i=0, line 24). The standard EMA definition seeds the first EMA value as the simple average of the first `period` closes, then applies the multiplier from bar `period` onward. Using the first close as seed means the EMA for the first ~20 bars is significantly biased toward data[0].close and will diverge from any backend EMA or standard library.
- **Impact:** EMA-20 overlay on Charts page will display wrong values for the first 20 bars. If EMA crossovers are used visually to confirm signals, the chart will show false crossovers near the beginning of the loaded data window.
- **Fix:** Change calculateEMA to: (1) compute SMA of the first `period` closes as initial ema; (2) start the EMA loop at index `period` (not 0); (3) push the first output at index `period`. This matches the standard definition used by TradingView, Zerodha, and the Python ta library.

### RSI first-period loop starts at i=1, skips data[0] change — initial avg gain/loss wrong
- **Category:** accuracy
- **Location:** `frontend/src/utils/indicators.ts` : 39-42
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** calculateRSI lines 39-42 iterate i from 1 to period (inclusive), computing data[i].close - data[i-1].close. This processes exactly `period` differences (indices 0 to period-1 price pairs, i.e. changes at bars 1 through period). The Wilder RSI standard computes the first average over bars 1..period (differences data[1]-data[0] through data[period]-data[period-1]) which is correct, but then the smoothed loop at line 48 starts at i = period+1 and references data[i]-data[i-1], also skipping the bar at index `period`. The net effect is the RSI series is offset by one bar relative to its correct position.
- **Impact:** RSI values are shifted by one candle and the warm-up average is computed over index 1..period instead of 0..period-1, introducing a systematic error. Any RSI-based signal threshold crossings shown visually on Charts will be one bar early.
- **Fix:** Rewrite to: initialise loop from i=1 to i<=period (computing period differences), then smoothed EMA loop from i=period+1. Ensure the first pushed RSI corresponds to time getTime(data[period]), matching standard Wilder RSI alignment.

### Bollinger Bands use population std dev (divide by N) instead of sample (divide by N-1)
- **Category:** accuracy
- **Location:** `frontend/src/utils/indicators.ts` : 80-81
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** calculateBollingerBands line 80 computes Math.sqrt(sumSqDiff / period). Standard Bollinger Bands as defined by John Bollinger and implemented by every major charting platform use the population standard deviation (divide by N, not N-1). While technically this is correct for Bollinger Bands, it is worth noting that many backend implementations (e.g. pandas ta.bbands) also use population std dev. More critically, there is no guard for period <= 1 — if candles has fewer than `period` elements or period is 0, sqrt(NaN) or division by zero will silently produce NaN band values that get passed to lightweight-charts, causing chart rendering errors.
- **Impact:** With very short data windows the chart renders NaN lines. If backend uses a different std dev convention, bands displayed on the frontend will differ from the backend's calculated bands used for signal generation, causing visual inconsistency.
- **Fix:** Add a guard: if (data.length < period) return { upper:[], lower:[], basis:[] }. Also verify which convention the backend uses and match it. Add explicit handling for edge case where period=1 (stdDev=0, bands collapse to SMA line).

### Risk/Reward ratio in Signals.tsx divides by zero when entry == stop_loss
- **Category:** correctness
- **Location:** `frontend/src/pages/Signals.tsx` : 297
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** Line 297: ((Math.abs(pat.target - pat.entry)) / (Math.abs(pat.entry - pat.stop_loss))).toFixed(1). If pat.entry equals pat.stop_loss (zero SL distance, which can happen if the backend returns a pattern with stop_loss at entry or if data is missing), this produces Infinity or NaN, which toFixed(1) renders as 'Infinity' or 'NaN' in the UI.
- **Impact:** UI shows 'Infinity' or 'NaN' as the Risk/Reward ratio for some patterns. Misleads traders about the true risk profile of a detected pattern.
- **Fix:** Add guard: const slDist = Math.abs(pat.entry - pat.stop_loss); const rr = slDist > 0 ? (Math.abs(pat.target - pat.entry) / slDist).toFixed(1) : 'N/A';

### concurrent fetchDecision calls from Charts + Dashboard create race condition on shared decision state
- **Category:** realtime
- **Location:** `frontend/src/store/strategy.store.ts` : 73-91
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** fetchDecision in strategy.store.ts writes both `decision` (shared singleton) and `decisions[symbol]`. Charts.tsx polls every 5 s calling fetchDecision(symbol, Number(interval)) (Charts.tsx:101). If the user has both Dashboard and Charts open in the same tab (navigating between them without unmounting), or if a future refactor mounts both simultaneously, the shared `decision` field will be overwritten by whichever fetch resolves last regardless of which symbol is active. Signals.tsx uses `decisions[selectedSymbol] || decision` as fallback (line 41), so it will silently show stale data from a different symbol when the per-symbol key is missing.
- **Impact:** Dashboard AI signal badge can display a signal computed for BANKNIFTY while the user is watching NIFTY, or vice versa. In a scalping context this is a trade-direction error.
- **Fix:** Remove the shared `decision` field and always use `decisions[symbol]` keyed by symbol. Update all consumers to explicitly select the key for the symbol they care about. If a latest-decision singleton is needed, add `lastDecisionSymbol` to track which symbol it belongs to and always display that in the UI label.

### Trades page setTimeout(loadData, 500) after exit/modify creates a second poll race
- **Category:** realtime
- **Location:** `frontend/src/pages/Trades.tsx` : 139, 199
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** After exitTrade (line 139) and handleModify (line 199), a 500 ms setTimeout triggers loadData() (full data refresh) in addition to the exitTrade/modifyTrade store actions themselves which already call get().refresh() internally (trade.store.ts:152, 162). This means two simultaneous refresh chains fire: one immediate (from the store action) and one 500 ms later. Both update the same Zustand state. If the 500 ms refresh arrives with stale data (the exit hasn't propagated on the backend yet), it will overwrite the correct post-exit state.
- **Impact:** Race condition: UI briefly shows correct post-exit state then reverts to the pre-exit state if the 500 ms fetch is faster than the backend's own processing. This appears as a 'ghost trade' that flickers back after exit.
- **Fix:** Remove the setTimeout(loadData) calls. The store's refresh() inside exitTrade/modifyTrade is sufficient. If a forced post-exit refresh is genuinely needed, add a small delay (1-2 s) and cancel it if the component unmounts (use a ref or AbortController).

### Charts.tsx creates chart with isDark snapshot at mount — theme changes are never applied
- **Category:** correctness
- **Location:** `frontend/src/pages/Charts.tsx` : 119-132
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** The chart is initialized inside a useEffect with dependency [] (runs once on mount). The isDark value is read from document.documentElement.classList at that moment (line 119). If the user changes theme after the chart is mounted, the chart keeps its original dark/light colors because chart.applyOptions() is never called in response to theme changes. The chart initialization effect does not depend on the theme store.
- **Impact:** After a theme toggle, candlestick chart background, grid lines, and text remain in the previous theme color. The rest of the UI switches correctly. This is a visual correctness defect that is jarring on a live-trading screen.
- **Fix:** Add a separate useEffect that depends on the theme value from useUIStore. Inside that effect call chartRef.current?.applyOptions({ layout: { background: { color: newBg }, textColor: newText }, grid: { ... } }). This keeps the mount effect clean and reactively updates colors.

### No AbortController / cleanup for in-flight API calls — stale responses overwrite current state on rapid navigation
- **Category:** realtime
- **Location:** `frontend/src/pages/Charts.tsx` : 87-113
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** loadData in Charts.tsx (line 87-108) and all store fetch functions have no AbortController. If the user switches symbol (line 43, setSymbol triggers loadData via the useEffect dep change at line 110-114), the in-flight request for the previous symbol is not cancelled. When it resolves, setCandles(uniqueData) (line 98) overwrites the current symbol's candles with the previous symbol's data. The chart briefly shows the wrong symbol's candles. Same pattern exists for fetchDecision and fetchDirection inside loadData.
- **Impact:** After rapid symbol switching, the chart can render candles for BANKNIFTY while the toolbar shows NIFTY. Any AI overlay or S/R levels will also be wrong until the correct request resolves.
- **Fix:** Use a ref to hold an AbortController: const abortRef = useRef<AbortController>(); at the start of loadData: abortRef.current?.abort(); abortRef.current = new AbortController(). Pass signal to api calls, and catch AbortError specifically to avoid setting state.

### Triplicate trading engine: two byte-identical files plus a stale backup, none guarded — high risk of editing the wrong file
- **Category:** maintainability
- **Location:** `backend/services/trading_engine.py, trading_engine_fixed.py, trading_engine_backup.py` : trading_engine.py:1-511; trading_engine_fixed.py:1-510; trading_engine_backup.py:1-372
- **Subsystem:** Groww trading-engine wiring, signal/candle data consumption, and dead-code audit (backend/)
- **Detail:** trading_engine.py and trading_engine_fixed.py are byte-identical (same MD5 ae35e1db3660b23c5f25af8aa9be343f, 510 lines). trading_engine_backup.py is the older logic (MD5 c6a9c5c6..., 371 lines) that still contains the known-broken broker.get_ltp([symbol]) path documented in BUGFIX_DOCUMENTATION.md. None are imported anywhere in code (verified by grep: only __init__.py:2 and scheduler.py:134/270 import `.trading_engine`). They are pure dead code that ships in the repo.
- **Impact:** A developer who fixes a bug in trading_engine_fixed.py (the natural name to edit, since the live file's own docstring says 'FIXED VERSION') will see no effect in the running app. Divergence between the duplicate and the live file can silently reintroduce fixed bugs. The backup file's broken LTP logic is a landmine if ever re-wired.
- **Fix:** Delete trading_engine_fixed.py and trading_engine_backup.py (or move to a clearly-excluded /archive that is not on sys.path). Keep exactly one engine. If history is needed, rely on VCS rather than parallel files.

### Scheduler (and thus all automated trading + candle sync) only starts under __main__, not under WSGI
- **Category:** realtime
- **Location:** `backend/app.py` : 133-140
- **Subsystem:** Groww trading-engine wiring, signal/candle data consumption, and dead-code audit (backend/)
- **Detail:** scheduler_service.start() is called only inside `if __name__ == '__main__':` (L137-138). Production deployments typically import the module-level `app = create_app()` (L131) via gunicorn/uwsgi and never execute the __main__ block, so no heartbeat, no candle sync, no monitoring runs. There is no app-factory hook that starts the scheduler.
- **Impact:** Under any real WSGI server the auto-trading engine, trailing-SL monitoring, and candle aggregation silently do nothing; open positions are never monitored for SL/target by the engine. Only direct dev runs (python app.py) trade.
- **Fix:** Start the scheduler from create_app() guarded against the reloader (e.g. only when WERKZEUG_RUN_MAIN or a config flag is set) or via a separate worker process/entrypoint, and document the deployment topology.

### VWAP computed as cumulative sum over the ENTIRE multi-day dataframe with no daily/session reset
- **Category:** accuracy
- **Location:** `backend/analysis/market_direction_engine.py; backend/analysis/support_resistance/indicators.py` : market_direction_engine.py:503-509
- **Subsystem:** Real-time price/candle data pipeline (Groww API -> backend cache/Redis/Mongo -> decision & direction engines -> Flask routes -> React/Zustand stores -> chart UI)
- **Detail:** _analyze_vwap does typical_price.cumsum()/volume.cumsum() over the full df passed in (5m candles spanning ~7-30 days per _get_smart_window). VWAP is by definition an intraday metric anchored to the session open. Cumulating across many days yields a meaningless long-run average price.
- **Impact:** The 10%-weight VWAP component (and any S/R VWAP) is effectively a slow-moving multi-week mean, so 'ABOVE/BELOW VWAP' is almost always one-sided and never reflects today's institutional reference. Degrades direction accuracy and the +5 VWAP alignment bonus is mis-applied.
- **Fix:** Reset VWAP at each IST session start (09:15): filter the df to the current trading day (or groupby date) before cumsum. Anchor typical-price*volume cumulative sums per session. Same fix for any S/R VWAP.

### min_confidence unit mismatch: DB stores percent (70), engine compares against fraction (0.0-1.0)
- **Category:** correctness
- **Location:** `backend/services/trading_engine.py; backend/routes/strategy_routes.py; backend/analysis/decision_engine.py` : trading_engine.py:162-163; strategy_routes.py:46-48; decision_engine.py:127-130
- **Subsystem:** Real-time price/candle data pipeline (Groww API -> backend cache/Redis/Mongo -> decision & direction engines -> Flask routes -> React/Zustand stores -> chart UI)
- **Detail:** strategy creation validates and stores min_confidence in 50-95 (percent) (strategy_routes.py:47). DecisionEngine returns confidence as a fraction 0.0-1.0 (decision_engine.py:127-128, capped at 1.0). evaluate_strategies does `if confidence < min_confidence: continue` with min_confidence default 0.6 but the stored value is 70 (strategy_routes default 70). So a strategy with the configured 70 will compare 0.0-1.0 confidence < 70, which is ALWAYS true -> the strategy never trades; or with the 0.6 fallback it ignores the user's setting entirely.
- **Impact:** Confidence gating is broken: either no entries ever fire (70 vs fraction) or the user's confidence config is silently ignored (0.6 fallback). Directly undermines signal-quality control the user configured.
- **Fix:** Standardize on one scale. Either multiply engine confidence by 100 before comparison, or divide stored min_confidence by 100 at read time. Add an explicit normalization helper and unit-test the boundary (e.g. confidence 0.72 vs config 70).

### strategy_routes.get_candles calls non-existent candle_service.generate_mock_candles -> 500 when DB is sparse
- **Category:** correctness
- **Location:** `backend/routes/strategy_routes.py; backend/services/candle_service.py` : strategy_routes.py:230-232
- **Subsystem:** Real-time price/candle data pipeline (Groww API -> backend cache/Redis/Mongo -> decision & direction engines -> Flask routes -> React/Zustand stores -> chart UI)
- **Detail:** When fewer than 10 candles exist, the route calls candle_service.generate_mock_candles(...) which is not defined in candle_service.py (grep confirms the only reference is the call site). This raises AttributeError -> 500.
- **Impact:** The chart endpoint crashes precisely in the cold-start / low-data / pre-market scenario it was meant to handle, so the chart shows nothing instead of placeholder data. Also a latent risk that mock data could leak into a 'real-time' view if it were implemented.
- **Fix:** Either implement generate_mock_candles or remove the fallback and return an explicit empty 200 ({candles:[], count:0, stale:true}) so the frontend can show a 'no data' state. Never silently inject synthetic candles into a real-time accuracy view.

### In-process direction cache never expires; serves stale direction indefinitely after market close or sync failure
- **Category:** realtime
- **Location:** `backend/services/direction_scheduler.py; backend/routes/market_routes.py` : direction_scheduler.py:43,134-136,147; market_routes.py:51-52
- **Subsystem:** Real-time price/candle data pipeline (Groww API -> backend cache/Redis/Mongo -> decision & direction engines -> Flask routes -> React/Zustand stores -> chart UI)
- **Detail:** direction_scheduler.direction_cache is a plain dict updated only while is_market_open(); get_all_directions (market_routes.py:42) returns it with no staleness check. There is no timestamp-based invalidation, so after 15:30 (or if Groww/Mongo is down and _update_direction returns early) the API keeps returning the last computed direction with a fresh top-level response timestamp (datetime.now() at market_routes.py:59), making stale data look live.
- **Impact:** Users see a confident UP/DOWN signal that is minutes-to-hours old, with a current timestamp, with no 'stale' indicator. High risk of acting on dead data.
- **Fix:** Store last_update per symbol (already partly tracked at direction_scheduler.py:136) and have get_all_directions/get_direction mark results stale or drop them when now-last_update exceeds a threshold (e.g. >15s during market, or any time market closed). Surface a per-symbol as_of timestamp to the frontend and render staleness.

### DEBUG=true enabling Werkzeug interactive debugger, bound to 0.0.0.0
- **Category:** security
- **Location:** `backend/app.py` : 140
- **Subsystem:** Groww Trading Platform - Authentication, Secrets Management & Order Execution
- **Detail:** app.run(host='0.0.0.0', port=5000, debug=config.DEBUG) with DEBUG defaulting to true (.env:3, config.py:15). The Werkzeug debugger exposes an interactive console (PIN-protected but bypassable) allowing remote code execution on unhandled exceptions, and leaks stack traces/source. Binding to 0.0.0.0 exposes it on all interfaces.
- **Impact:** Remote code execution and information disclosure on a host that holds the ENCRYPTION_KEY and can place live orders. Server compromise = full account compromise.
- **Fix:** Force DEBUG=false in production; never run app.run with debug in prod. Serve via a WSGI server (gunicorn/uwsgi) behind a reverse proxy, bound to localhost or an internal interface, with TLS termination.

### CORS allows any origin with credentials and reflects arbitrary Origin
- **Category:** security
- **Location:** `backend/app.py` : 53-79
- **Subsystem:** Groww Trading Platform - Authentication, Secrets Management & Order Execution
- **Detail:** CORS is configured with origins '*' and supports_credentials=True (lines 53-57), and after_request reflects the request's Origin header back verbatim with Access-Control-Allow-Credentials: true (lines 74-78). Although the JWT is stored in localStorage (axios.ts:15) rather than a cookie, the wildcard+credentials+reflected-origin configuration is unsafe and would expose any cookie-based auth; it also broadly weakens browser-side protections.
- **Impact:** Any malicious website can make authenticated-style cross-origin requests; if auth ever moves to cookies this becomes full CSRF/credential theft. Even now it permits any origin to invoke the API and read responses.
- **Fix:** Replace '*' with an explicit allowlist of trusted frontend origins; do not reflect arbitrary Origin. Only enable supports_credentials for the specific allowed origins.

### JWT logout does not revoke tokens; no token blocklist
- **Category:** security
- **Location:** `backend/routes/auth_routes.py` : 316-320
- **Subsystem:** Groww Trading Platform - Authentication, Secrets Management & Order Execution
- **Detail:** logout() simply returns a success message and the frontend deletes the token from localStorage (axios.ts:32). With JWT_ACCESS_TOKEN_EXPIRES=86400 (24h, .env:7) and no revocation/blocklist (no revoked_token store wired to the revoked_token_loader in app.py:96-98), a leaked/stolen token remains valid for up to 24 hours after logout. refresh-token (auth_routes.py:301-313) issues a new long-lived token without rotating/invalidating the old one.
- **Impact:** Stolen tokens (e.g. via XSS, shared device, or the wildcard CORS) cannot be invalidated, leaving a 24h window to place live orders. No way to force-logout a compromised session.
- **Fix:** Implement JWT revocation using a Redis blocklist keyed on jti, populate it on logout, and check it in a token_in_blocklist_loader. Shorten access token lifetime and add refresh-token rotation. Consider storing the JWT in an httpOnly cookie to mitigate XSS theft.

### Switching to LIVE money mode requires no re-authentication or confirmation
- **Category:** correctness
- **Location:** `backend/routes/settings_routes.py` : 81-98
- **Subsystem:** Groww Trading Platform - Authentication, Secrets Management & Order Execution
- **Detail:** /api/settings/mode (and the merged path in update_settings, lines 72-77) flips a user between PAPER and LIVE with only a valid JWT and no password re-prompt, no broker-connection verification, and no audit trail. trade_routes.get_user_execution_mode (lines 50-77) then trusts this value and routes orders to the live Groww client.
- **Impact:** A single stolen/forged JWT (made trivial by the guessable JWT_SECRET_KEY) can silently switch an account to LIVE and place real-money orders. There is no guardrail differentiating simulated vs real trading authorization.
- **Fix:** Require step-up authentication (password/OTP) and an explicit confirmation to enable LIVE mode; verify broker_connected and a valid, non-expired access token before allowing LIVE. Log all mode changes with timestamp/IP and alert the user via Telegram on switch.

### Fail-open trade lock allows duplicate live orders during Redis outage
- **Category:** realtime
- **Location:** `backend/routes/trade_routes.py` : 22-26
- **Subsystem:** Groww Trading Platform - Authentication, Secrets Management & Order Execution
- **Detail:** acquire_trade_lock yields True (proceeds without locking) when the Redis client is unavailable. The lock is the only mechanism preventing concurrent/duplicate order submission per user. Given the committed Redis credentials and a single cloud instance, an outage or attacker-induced disconnect removes duplicate-order protection.
- **Impact:** Concurrent requests (double-clicks, retries, or a malicious flood) can place multiple real-money orders simultaneously, causing unintended financial exposure.
- **Fix:** For LIVE orders, fail closed: if the lock cannot be acquired (Redis down), reject the order with a clear error rather than proceeding. Add idempotency keys (order_reference_id) per logical order so the broker rejects duplicates.

### Order placement endpoints lack input validation on quantity, type, and numeric fields
- **Category:** data-integrity
- **Location:** `backend/routes/trade_routes.py` : 89-140, 523-595
- **Subsystem:** Groww Trading Platform - Authentication, Secrets Management & Order Execution
- **Detail:** place_order only checks presence of trading_symbol/quantity/transaction_type (lines 96-99) but does not validate that quantity is a positive integer, transaction_type is BUY/SELL, order_type is in an allowed set, or price/trigger_price are non-negative numbers. Values flow straight into GrowwClient.place_order (groww_client.py:469-487) and on to /v1/order/create. quick_trade (line 552) takes quantity_override from the client with no bounds. A negative, zero, huge, or non-numeric quantity, or an injected segment/product, is passed to the live broker.
- **Impact:** Malformed or maliciously oversized orders can be submitted to the live exchange (e.g. an enormous quantity), risking large unintended financial loss or rejected/erroring orders. Lack of server-side bounds also undermines risk-management limits.
- **Fix:** Add strict server-side validation: quantity is a positive int within configured max lot limits; transaction_type in {BUY,SELL}; order_type/product/segment against allowlists; price/trigger_price numeric and >=0. Enforce per-user/per-strategy max quantity and reject out-of-range values before reaching the broker.

### No .gitignore present; secret files are tracked
- **Category:** security
- **Location:** `backend/.env` : N/A (repo-wide)
- **Subsystem:** Groww Trading Platform - Authentication, Secrets Management & Order Execution
- **Detail:** A repo-wide Glob for **/.gitignore returned no results, and backend/.env, backend/groww/env, and hardcoded-secret scripts are present in the tree. Without ignore rules, secrets are routinely committed (as evidenced by the three secret-bearing files found).
- **Impact:** Ongoing leakage of any newly added secrets into version control history, from which they are very hard to fully remove and may already be in remote clones/forks.
- **Fix:** Add a .gitignore covering .env, *.env, backend/groww/env, *.key, and credentials files. Adopt a pre-commit secret scanner (e.g. gitleaks/trufflehog) and rotate every secret already committed; assume all are compromised.

### Bollinger regime override reads a key that is never produced (dead code -> volatility regime mostly NORMAL)
- **Category:** correctness
- **Location:** `backend/analysis/decision_engine.py` : 227-232
- **Subsystem:** Groww Decision / Market-Direction Signal Engine
- **Detail:** _analyze_volatility does bollinger.get('width_percentile', 50), but calculate_bollinger (volatility/indicators.py:72-81) returns keys value(bandwidth), upper, middle, lower, percent_b, signal, strength — there is NO width_percentile. So bb_width is always the default 50, and the bb_width>80 / <20 branches never trigger. Regime is decided solely by ATR's fixed 1%/2% thresholds.
- **Impact:** The Bollinger squeeze/expansion contribution to regime detection is silently inert; volatility regime and the downstream VOLATILE/TRENDING/RANGING classification (lines 135-141) are less accurate than the code implies.
- **Fix:** Either compute a true rolling bandwidth percentile in calculate_bollinger and expose width_percentile, or read the existing 'value'/percent_b. Add a unit test asserting the keys consumed by the engine exist in the producer output.

### Correlated indicators are double- and triple-counted, inflating apparent consensus
- **Category:** accuracy
- **Location:** `backend/analysis/decision_engine.py` : 99-124,201,239,266
- **Subsystem:** Groww Decision / Market-Direction Signal Engine
- **Detail:** Many of the 'independent' votes are the same underlying signal. Momentum uses RSI, Stochastic, Williams %R and CCI (momentum/indicators.py) which are near-collinear oscillators (all functions of close vs recent high/low range) — Stochastic even hardcodes d=k (line 57). S/R uses moving_averages, vwap and ichimoku, all trend/MA-derived and correlated with the momentum EMA crossover. VWAP appears in momentum (vwap_momentum), in S/R (calculate_vwap) AND in the direction engine. Volume confirmation uses OBV and AD-line which are both cumulative price*volume proxies. Treating these as independent votes overstates consensus and makes confidence rise on what is effectively one factor.
- **Impact:** Confidence is overstated when one regime (e.g. an oscillator overbought cluster) dominates, producing overconfident, correlated bets and poor calibration; true diversification of evidence is far lower than the indicator count suggests.
- **Fix:** Group indicators into orthogonal factor families (trend, mean-reversion oscillator, volume/flow, volatility, structure) and take ONE consensus per family, or whiten via a correlation-shrinkage / PCA weighting estimated on historical data. Down-weight RSI/Stoch/Williams/CCI to a single oscillator vote. Remove VWAP duplication across buckets.

### No regime-dependent weighting: trend and mean-reversion indicators vote together in all regimes
- **Category:** accuracy
- **Location:** `backend/analysis/decision_engine.py` : 54-60,99-124
- **Subsystem:** Groww Decision / Market-Direction Signal Engine
- **Detail:** WEIGHTS are static constants. The engine detects a regime (TRENDING/RANGING/VOLATILE, lines 135-141) but never feeds it back into the weighting. In a ranging market, RSI/Stoch overbought correctly signals a fade, but the trend buckets (MAs, ichimoku, EMA crossover) keep voting with the trend, so the two cancel and confidence collapses; in a trending market the oscillators flag false reversals. Mean-reverting oscillators (BEARISH when RSI>70) are blended with trend-following S/R (BULLISH when price>MA20>MA50) — these are designed for opposite regimes.
- **Impact:** Signal quality is mediocre in BOTH regimes because the wrong factor family is always partially active. This is one of the largest available win-rate improvements.
- **Fix:** Make WEIGHTS a function of detected regime: in TRENDING, up-weight trend/structure/ADX and invert/disable counter-trend oscillator votes; in RANGING, up-weight oscillator fades at S/R levels and down-weight breakout/trend votes. Detect regime with ADX/volatility-ratio BEFORE fusion, then select a weight profile.

### Repaint / look-ahead: signals computed on the still-forming last candle
- **Category:** realtime
- **Location:** `backend/analysis/timeframe_aggregator.py` : 80-95
- **Subsystem:** Groww Decision / Market-Direction Signal Engine
- **Detail:** aggregate() resamples with closed='left', label='left' and dropna(), so the final bucket is the in-progress bar that keeps mutating each second as 1m data arrives (direction engine runs at 1Hz). All indicators read .iloc[-1], so RSI, EMA, structure, VWAP and candlestick patterns (engulfing/doji on df.iloc[-1]) repaint until the bar closes. Backtests that include the last formed candle will look-ahead-bias because in live trading that bar's close is unknown at decision time.
- **Impact:** Intra-bar signal flicker (false UP/DOWN flips), and any backtest using closed-bar data will overstate accuracy versus live, inflating measured win-rate and producing whipsaw entries live.
- **Fix:** Decide on closed bars only: for indicator computation use df.iloc[:-1] (drop the forming bar) or explicitly maintain the forming bar separately and only use its live price for entry timing, never for indicator state. Ensure the backtester replicates this exact bar-closing rule to remove look-ahead.

### All thresholds are hardcoded and non-adaptive across instruments and timeframes
- **Category:** accuracy
- **Location:** `backend/analysis/volatility/indicators.py` : 27-32,131-136,296-303
- **Subsystem:** Groww Decision / Market-Direction Signal Engine
- **Detail:** ATR regime cuts at 1%/2% (atr_percent), historical-vol regime at 15/25, RSI bands at 70/30, stochastic 80/20, CCI +/-100, MACD/ROC/momentum fixed % cuts in momentum/indicators.py, and the direction engine's 60/40 master cutoff (market_direction_engine.py:560-565) are all fixed magic numbers. BANKNIFTY/SENSEX have very different per-bar ATR% and noise than NIFTY, and 1m vs 5m have different RSI distributions, so the same 70/30 means different percentiles per symbol/TF.
- **Impact:** Mis-calibrated triggers per instrument: e.g. NIFTY rarely shows ATR%>2 intraday so it almost never reaches HIGH regime, while a wide-ranging symbol is permanently HIGH. Reduces cross-symbol accuracy and makes the system fragile to volatility regime shifts.
- **Fix:** Replace absolute cutoffs with rolling percentile / z-score bands estimated per symbol and per timeframe (e.g. RSI band = symbol-specific quantiles, ATR regime = rolling 1-yr percentile of ATR%). Annualize volatility with the correct periods-per-year for the bar size (see separate issue) before applying regime cuts.

### Intraday volatility annualized with sqrt(252), producing nonsensical vol regimes and India-VIX proxy
- **Category:** correctness
- **Location:** `backend/analysis/volatility/indicators.py` : 129,153,213,265-266,318
- **Subsystem:** Groww Decision / Market-Direction Signal Engine
- **Detail:** historical_vol, parkinson_vol, garch, volatility_ratio and realized_vol compute returns on intraday (5m/1m) closes but annualize with sqrt(252), the daily-bar factor. For 5m bars there are ~75 bars/day, so the correct factor is sqrt(252*75). The result understates annualized vol by ~8.6x, so the 15/25 'NORMAL/HIGH' regime thresholds and the india_vix proxy (line 294) are essentially meaningless. The GARCH coefficients (0.06/0.94, line 207-211) are hardcoded RiskMetrics EWMA, not estimated, and seeded with full-sample variance (line 208) which is in-sample look-ahead.
- **Impact:** Volatility regime classification, India-VIX proxy, and implied_vol proxy are all on the wrong scale, so any logic keyed on them (regime, sizing) is wrong. GARCH provides no real conditional-vol value.
- **Fix:** Use bar-correct annualization (periods_per_year = 252 * bars_per_day) or stop annualizing and threshold on raw per-bar vol percentiles. Fit GARCH/EWMA lambda from data or drop the GARCH label; seed variance from a trailing window, not the full sample.

### Decision engine reads non-existent indicator keys (width_percentile, donchian, level_382/500/618) — volatility & fib summaries silently default
- **Category:** correctness
- **Location:** `backend/analysis/decision_engine.py + volatility/SR indicators` : decision_engine.py:227 (width_percentile), 288 (donchian), 308-310 (level_382/500/618); bollinger emits 'value'/'percent_b' (volatility/indicators.py:72-81); fibonacci emits 'levels' dict (support_resistance/indicators.py:41)
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** _analyze_volatility uses bollinger.get('width_percentile',50) but Bollinger never emits that key; there is no 'donchian' indicator at all; _summarize_sr reads fibonacci 'level_382'/'level_500'/'level_618' but fibonacci emits a 'levels' dict keyed '38.2'/'50'/'61.8'. All silently fall back to defaults/None.
- **Impact:** Volatility regime detection degrades to ATR-only; Bollinger bandwidth percentile is never used; Fibonacci levels are dropped from output. Reduced accuracy and misleading/empty UI fields.
- **Fix:** Align keys: have Bollinger emit a width percentile, drop or implement 'donchian', and read fibonacci via sr['fibonacci']['levels']['38.2'] etc. Add a contract test that every key the engine reads exists in indicator output.

### RSI uses simple rolling mean, not Wilder's smoothing (formula incorrect)
- **Category:** accuracy
- **Location:** `backend/analysis/momentum/indicators.py` : 17-23
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** avg_gain/avg_loss use pd.Series(...).rolling(period).mean() (a flat SMA of the last 14 deltas). Standard RSI uses Wilder's RMA (alpha=1/period) seeded by the first average. Values diverge materially and react differently to new bars; thresholds (70/30) are calibrated for Wilder RSI.
- **Impact:** RSI overbought/oversold crosses fire at the wrong times vs every charting platform the trader compares against; degrades accuracy of a 25%-weighted momentum block.
- **Fix:** Implement Wilder RMA: avg = prev_avg*(period-1)/period + current/period, seeded with the first SMA, and compute over full history then take iloc[-1].

### ADX is computed incorrectly — DI uses mean of DM/mean of TR instead of Wilder-smoothed sums, and ATR floored to 1
- **Category:** accuracy
- **Location:** `backend/analysis/momentum/indicators.py` : 77-87
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** Standard ADX: smooth +DM,-DM,TR with Wilder's method, +DI=100*smoothedDM/smoothedTR, DX=100*|+DI - -DI|/(+DI + -DI), ADX=Wilder-smoothed DX. Here TR/DM are simple rolling means (L77,81,82), ATR zeros are replaced with 1 (L79 — turns a flat market into DI≈DM*100, a huge spurious value), and DX is averaged with another simple rolling mean (L87). Also DI = 100*mean(DM)/mean(TR) double-divides by period incorrectly only by luck cancels, but the smoothing is still wrong.
- **Impact:** ADX magnitude and the 25 threshold are unreliable; trend/no-trend classification (used for market_regime and momentum scoring) is wrong, especially in low-volatility NIFTY ranges where ATR floor=1 fabricates directional strength.
- **Fix:** Replace with Wilder smoothing; for zero-TR bars keep TR=0 and guard the final division (return ADX=0 when smoothedTR==0) rather than substituting 1.

### Stochastic %D is a stub: d = k (no 3-period smoothing)
- **Category:** accuracy
- **Location:** `backend/analysis/momentum/indicators.py` : 56-57
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** d_period=3 is accepted but ignored: d = k (L57). %D should be the 3-period SMA of %K. The signal only uses %K, so there is no %K/%D crossover logic at all.
- **Impact:** Stochastic crossovers (the primary trade trigger of the indicator) are impossible; the indicator is effectively just a raw %K oscillator. Lost signal quality in a 25%-weighted block.
- **Fix:** Compute a rolling %K series and set %D = %K.rolling(d_period).mean(); generate signals on %K/%D cross plus overbought/oversold.

### VWAP is a cumulative average over 500 bars, not a session-anchored intraday VWAP
- **Category:** accuracy
- **Location:** `backend/analysis/support_resistance/indicators.py & momentum/indicators.py` : support_resistance/indicators.py:83-88; momentum/indicators.py:215-220
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** vwap = cumsum(tp*vol)/cumsum(vol) over the entire window. For 5-min NIFTY this blends multiple trading days and never resets at 09:15 IST. The VWAP a trader sees resets daily. Also the band uses std of typical price (L90), not volume-weighted standard deviation around VWAP.
- **Impact:** VWAP value and the BULLISH/BEARISH classification (close vs VWAP) are wrong relative to the real intraday VWAP, and the 2-sigma bands are statistically incorrect. This is a directly tradeable level that scalpers rely on, so accuracy loss is high.
- **Fix:** Anchor VWAP to the current session (reset cumsum at each new trading day using the candle timestamp). Compute the band as sqrt(cumsum(vol*(tp-vwap)^2)/cumsum(vol)) for a true VWAP standard deviation.

### Pivot points computed from the current/last candle, not the prior completed period (and recompute every bar)
- **Category:** accuracy
- **Location:** `backend/analysis/support_resistance/indicators.py` : 9-22
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** pivot uses df['high'/'low'/'close'].iloc[-1] — the latest 5-min bar. Standard floor pivots use the PRIOR completed period's (usually prior day) H/L/C and stay fixed for the whole next session. Here they change every 5-min bar and reflect a single tiny intrabar range.
- **Impact:** R1/R2/R3/S1/S2/S3 are meaningless as support/resistance and the close>r1 / close<s1 signal is near-degenerate (since pivot is derived from the same bar's close). Feeds a 15%-weighted S/R block with noise.
- **Fix:** Compute pivots from the prior completed daily (or chosen period) candle and hold them constant intraday. Take H/L/C from the previous session aggregate, not iloc[-1] of intraday bars.

### Harmonic detectors implement only bullish variants; bearish code paths are absent
- **Category:** correctness
- **Location:** `backend/analysis/patterns/harmonic/patterns.py` : detect_gartley L114-174, detect_butterfly L177-232, detect_crab L235-290
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** Only ABCD has both directions (L38-111). Gartley, Butterfly and Crab return only on bullish geometry; there is no bearish branch, so they can never produce a BEARISH harmonic signal.
- **Impact:** Systematic long-side bias in the harmonic family and missed bearish setups — bad for a two-sided F&O scalper and skews aggregate pattern direction.
- **Fix:** Add the mirror-image bearish detection (X high -> A low -> ...) for Gartley/Butterfly/Crab, mirroring the ABCD bullish/bearish structure.

### Harmonic patterns return the first match anywhere in 500 bars with no recency or completion check
- **Category:** correctness
- **Location:** `backend/analysis/patterns/harmonic/patterns.py` : detect_abcd L56-82; detect_gartley L129-173; etc.
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** The nested loops return on the first geometrically valid X/A/B/C/D found in the entire window, regardless of how old D is or whether price is currently near D (the PRZ). entry is hard-coded to close[-1] (L78) even if D occurred 300 bars ago. There is no check that D is the most recent swing or that the pattern just completed.
- **Impact:** Generates 'live' harmonic signals on patterns that completed long ago and are irrelevant to current price; entry/target/stop are computed off stale levels far from the market. Directly harms entry accuracy and stop placement.
- **Fix:** Require D to be among the most recent N swings and within a tolerance of current price (PRZ test); reject patterns whose D index is far from len(df)-1. Compute entry relative to the actual reversal candle, not close[-1].

### Nadaraya-Watson uses future bars and O(n^2) full-window recompute (repaint + latency)
- **Category:** realtime
- **Location:** `backend/analysis/volatility/indicators.py` : 163-195
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** For each i it weights ALL n points including i+1..n-1 (future), so y_hat[-1] is a non-causal estimate that changes as new bars arrive (repaint). It is also O(n^2) over 500 bars recomputed every 5s.
- **Impact:** Envelope signal repaints and adds avoidable CPU cost on every poll; the BULLISH/BEARISH from current-vs-envelope is unreliable in real time.
- **Fix:** Use a one-sided (causal) kernel that only weights past bars for the endpoint, and/or precompute. Acknowledge the known endpoint repaint of NW and only act on confirmed bars.

### Bare/silent exception handling masks all of the above bugs
- **Category:** maintainability
- **Location:** `all *_all_* aggregators` : momentum/indicators.py:281-284; volatility/indicators.py:373-378; support_resistance/indicators.py:313-317; candlestick L244-249, harmonic L304-311, primary L521-528 (except Exception: continue)
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** Every aggregator wraps each calculator in try/except that converts errors into NEUTRAL (indicators) or silently drops the pattern (patterns, with no error recorded). Combined with the key-mismatch bugs, large portions of the signal can be failing with zero visibility.
- **Impact:** The system can run for days appearing healthy while 30% (patterns) and chunks of volatility/SR are dead or erroring. Directly undermines accuracy and 'best results' with no alarm.
- **Fix:** Log exceptions at WARNING with indicator name and stack; emit a per-cycle health metric (count of failed/NEUTRAL-by-error indicators); fail loudly in tests.

### No staleness/timestamp guard on the candle window feeding analysis
- **Category:** realtime
- **Location:** `backend/services/trading_engine.py + candle_service.py` : trading_engine.py:134-148; candle_service.py:246-256
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** get_candles returns the latest 500 stored candles with no check that the most recent candle is recent (e.g., within one interval of now). If the feed stalls or the websocket drops, evaluate_strategies keeps generating signals and entering trades on stale data every 5s.
- **Impact:** Trading on stale prices during a feed outage is a direct risk-control failure for a live F&O scalper.
- **Fix:** Reject analysis if df.index[-1] is older than ~1.5x the candle interval; add a feed-heartbeat/kill-switch tie-in and surface staleness in the result.

### Volatility regime branch on Bollinger width is dead: width_percentile key never produced
- **Category:** correctness
- **Location:** `backend/analysis/decision_engine.py` : 227,229-232
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** _analyze_volatility reads bollinger.get('width_percentile', 50), but calculate_bollinger (volatility/indicators.py:72-81) returns value(bandwidth)/upper/middle/lower/percent_b/signal/strength — there is no width_percentile. bb_width is always the default 50, so the bb_width>80 and bb_width<20 branches never fire. Regime is decided solely by ATR's hardcoded 1%/2% thresholds.
- **Impact:** Squeeze/expansion detection is non-functional; HIGH-vol regime (which drives the volatility_factor boost and the 'VOLATILE' market_regime label at L136) is under-detected, degrading regime accuracy and the confidence contribution.
- **Fix:** Compute a true rolling bandwidth percentile in calculate_bollinger and expose width_percentile, OR read the existing 'value' (bandwidth) / 'percent_b'. Add a contract test for keys consumed by the engine.

### Confidence math adds volatility_factor unconditionally, fabricating directional confidence
- **Category:** accuracy
- **Location:** `backend/analysis/decision_engine.py` : 110-111,127-128
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** volatility_factor = volatility_score * 0.15 is added to confidence regardless of direction (L127). volatility_score is 0.4/0.6/0.8 (always positive, never direction-aware). So even a perfectly balanced/neutral market gets +0.06 to +0.12 confidence purely from volatility, and HIGH volatility (riskiest regime for scalping) INFLATES confidence the most.
- **Impact:** Confidence is not a calibrated probability of directional success. High-volatility periods (lowest directional edge, highest slippage) get the largest confidence boost, pushing marginal setups over the 0.70 gate — backwards for risk and win-rate.
- **Fix:** Treat volatility as a gate/penalty, not an additive booster: confidence = max(bull,bear) * volatility_dampener where HIGH vol < 1.0. Never let volatility alone create confidence. Re-calibrate the 0.70 threshold after the fix.

### Score weights are applied to incommensurable sub-scores; confidence is not a normalized probability
- **Category:** accuracy
- **Location:** `backend/analysis/decision_engine.py` : 95-128,192,216,253,270
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** Each component returns a sub-score on a different, non-comparable scale: patterns = bullish_fraction+0.3 capped at 1 (L192), momentum = count/6 (max ~0.83, L216), sr = count/5 (max 1.0, L253), volume = ratio/2 capped (L270). confidence = max(bullish_score, bearish_score) (L127) takes only the single dominant side, so the weights no longer form a convex combination and confidence is not in any meaningful [0,1] probability space. Momentum-only agreement maxes at 0.25*0.83=0.21.
- **Impact:** The headline 'confidence >= 70%' is mathematically arbitrary and rarely reachable, and the relative influence of each block does not match the documented 30/25/15/15/15 intent. Signal thresholds, min_confidence gating, and any confidence-keyed sizing are mis-scaled.
- **Fix:** Normalize every sub-score to a common signed [-1,1] directional score, then net = sum(weight*signed_score); confidence = abs(net) with weights summing to 1.0. Validate a fully-aligned bullish fixture yields ~1.0.

### _ema seeds from the oldest data point and recomputes O(n) every call, giving a wrong, length-dependent EMA
- **Category:** accuracy
- **Location:** `backend/analysis/market_direction_engine.py` : 577-586 (also 301,418)
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** _ema sets ema=data[0] (the OLDEST bar) and iterates the entire series with alpha=2/(period+1). With only ~50-200 bars the seed has not decayed enough, so the returned EMA depends on how many candles are in the buffer rather than converging to the true EMA. It is also recomputed from scratch every 1s tick, and _analyze_1m_momentum recomputes RSI 5 times in a list comprehension (L418) for the slope.
- **Impact:** EMA values (backbone of the 35%+25%+20% trend/structure/momentum components) drift with buffer length and differ from the pandas .ewm() EMAs used in momentum/indicators.py, causing cross-engine disagreement and inaccurate trend reads. Per-tick full recompute adds avoidable latency in a 1s loop over 3 symbols.
- **Fix:** Seed EMA with the SMA of the first `period` values (or use a warm-up window and discard it), or reuse pandas ewm(span=period, adjust=False). Cache/incrementally update EMA/RSI across ticks.

### Direction engine ignores live_volume entirely and double-counts the forming bar in the volume average
- **Category:** realtime
- **Location:** `backend/analysis/market_direction_engine.py` : 180,192,467-492; direction_scheduler.py:125-131
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** The scheduler calls analyze_direction with only live_ltp (direction_scheduler.py:130) — live_volume is never passed, so current_volume = df_1m['volume'].iloc[-1] (the forming, partial 1m bar). _analyze_volume then divides this partial volume by mean(volume[-20:]) which INCLUDES that same partial bar (L476). Early in a minute the ratio is tiny; the 'volume spike' (>1.2 confirmed, +5 bonus at L556) is structurally biased low.
- **Impact:** Volume confirmation (10% weight + a +5 strength bonus) is unreliable and time-of-minute dependent, weakening genuine breakout confirmation and randomly granting/withholding the bonus that can tip the 60/40 direction boundary.
- **Fix:** Pass a true live cumulative volume from the scheduler, compare current bar volume against the average of CLOSED bars (volume[-21:-1]), or project full-bar volume by scaling for elapsed fraction of the minute.

### _calculate_final_signal mixes a 0-100 weighted score with flat +5 bonuses and an asymmetric strength map
- **Category:** accuracy
- **Location:** `backend/analysis/market_direction_engine.py` : 536-575
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** weighted_score is a 0-100 weighted blend, but VWAP-alignment (+5, L551/553) and volume-confirmation (+5, L557) are added as absolute points that can push score past 100 before clamping, distorting the weight scheme. Direction is hard-cut at >=60 UP / <=40 DOWN (L560-563). For UP, strength=score; for DOWN, strength=100-score (L568-571); for NEUTRAL, strength=50-abs(50-weighted) (L573), which yields LOW strength for scores far from 50 — inverted semantics for a 'neutral confidence'.
- **Impact:** Strength is not a consistent confidence metric across directions; the +5 bonuses give VWAP/volume outsized influence near the boundary. The 60/40 dead-band with no hysteresis means the direction toggles on sub-point noise each second (chatter).
- **Fix:** Fold VWAP/volume into the weighted sum as proper weighted components (not flat bonuses), use signed scoring centered at 0, add hysteresis (require >=62 to flip to UP, <=38 to flip to DOWN, persist otherwise), and define strength consistently as distance from the neutral pivot.

### Aggregator assumes epoch is UTC; if upstream stored naive-local epochs, all higher-TF bars are mis-bucketed
- **Category:** data-integrity
- **Location:** `backend/analysis/timeframe_aggregator.py` : 64-93
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** aggregate() converts df['timestamp'] with pd.to_datetime(..., unit='s', utc=True).tz_convert('Asia/Kolkata') (L64), i.e. treats the epoch as UTC. If candles were written from a server-local naive datetime (an inconsistency seen elsewhere in the codebase), the same epoch is bucketed under two different time bases, shifting 5m/15m/60m buckets by the host UTC->IST offset and misaligning the 09:15 session boundary on UTC hosts. label='left'/closed='left' also never drops the open bucket.
- **Impact:** The 15m (35%) and 5m (25%) inputs to the direction engine and the 5m input to the decision engine are computed over mis-bucketed bars on any non-IST host, corrupting EMA/RSI/VWAP/structure and session VWAP resets.
- **Fix:** Pick one canonical time base end-to-end (store UTC-aware or raw epoch only) and build every index with the same pd.to_datetime(timestamp, unit='s', utc=True).tz_convert('Asia/Kolkata'). Add an assertion that the first bar of a session aligns to 09:15 IST.

### VWAP is computed over the entire passed DataFrame with no daily session reset
- **Category:** accuracy
- **Location:** `backend/analysis/market_direction_engine.py` : 503-509; support_resistance/indicators.py:77-103; momentum/indicators.py:209-229
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** _analyze_vwap uses cumsum over all rows in df_5m (L506-507). The scheduler feeds 200 1m candles aggregated to ~40+ 5m bars spanning potentially multiple sessions, so 'VWAP' is a multi-day cumulative average, not the intraday session VWAP institutions reference (the engine's stated purpose, L14).
- **Impact:** Price-vs-VWAP (10% weight + a +5 alignment bonus) is anchored to stale prior-session data, giving a wrong institutional reference and a wrong ABOVE/BELOW classification, especially after a gap open.
- **Fix:** Reset VWAP accumulation at the session open (09:15 IST); accumulate typical*volume only over bars from the current trading day; expose the session anchor used.

### No hysteresis / signal-stability control: 1s recompute produces signal chatter at the thresholds
- **Category:** realtime
- **Location:** `backend/analysis/market_direction_engine.py` : 559-565; direction_scheduler.py:64-73,139
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** _calculate_final_signal uses hard 60/40 cutoffs with no persistence, and the scheduler recomputes every 1 second writing a fresh Redis value (ex=10). Combined with forming-bar repaint and per-tick EMA recompute, the published direction can oscillate UP/NEUTRAL/DOWN second-to-second when weighted_score hovers near 60 or 40.
- **Impact:** Unstable signals cause whipsaw entries/exits for scalping (high slippage+brokerage cost), flickering UI, and unreliable confirmation logic — directly undermining the 'best results' and real-time correctness goals.
- **Fix:** Add hysteresis bands and a minimum-hold/confirmation count (require N consecutive ticks or a bar close before flipping). Smooth strength with an EMA. Publish a new direction only when it differs materially and persists.

### Daily P&L always reports 0 due to status casing mismatch ('closed' vs 'CLOSED')
- **Category:** data-integrity
- **Location:** `backend/services/paper_broker.py` : 316
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** get_daily_pnl filters with trade.get('status') == 'closed' (lowercase), but db.close_trade (mongodb.py:246) sets status='CLOSED' (uppercase) and get_active_trades uses 'OPEN'. No code path ever writes 'closed'.
- **Impact:** total_pnl, winning, and losing in get_daily_pnl are always 0/empty, so dashboards and any daily-loss guardrail that reads this value are wrong. Misleads the user on results and can defeat loss-limit logic.
- **Fix:** Compare case-insensitively or against 'CLOSED': if trade.get('status','').upper()=='CLOSED'. Standardize a STATUS enum/constant across mongodb.py, engine, and broker.

### Non-atomic read-modify-write of paper account creates race conditions and double-write on SELL
- **Category:** realtime
- **Location:** `backend/services/paper_broker.py` : 179-258
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** place_order reads account (179), mutates balance/positions in Python, then writes via upsert_paper_account. On SELL it writes twice: first {'realized_pnl':...} (250-252) then {'balance','positions'} (255-258). There is no lock and no atomic $inc. The scheduler heartbeat (monitor_active_trades) and the manual /exit route can run concurrently; the manual route holds acquire_trade_lock (trade_routes.py:240) but the heartbeat engine path does NOT acquire that lock, so they are not mutually exclusive.
- **Impact:** Concurrent entry+exit or two exits can clobber each other's positions array and balance (lost updates), produce a position that is sold twice or never removed, or persist realized_pnl without the matching balance/positions write if the process dies between the two upserts. Corrupts virtual capital and P&L.
- **Fix:** Wrap the full read-modify-write in the same trade lock used by the route, or perform atomic MongoDB updates ($inc on balance/realized_pnl, $pull/$push on positions with a filter that matches expected quantity). Collapse the two SELL upserts into one update document.

### Stop-loss/target only checked at 5s polling boundaries with no intrabar protection
- **Category:** realtime
- **Location:** `backend/services/trading_engine.py` : 174-219
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** monitor_active_trades runs every 5s and compares the latest LTP snapshot against SL/target. For a 5s scalping strategy on options, price can spike through the SL between polls; the engine only sees the price 5s later. Worse, execute_exit fills at the broker's current LTP (with slippage applied to that later price), not at the SL level, so the modeled exit understates the loss.
- **Impact:** Realized losses are systematically larger than the SL in live trading (slippage past SL) yet paper trading models exits at the recovered LTP, overstating paper results and giving false confidence. Directly harms the user's accuracy/best-results goals.
- **Fix:** For LIVE, place a real resting SL-M order with the broker (place_order order_type='SL_M', trigger_price=SL) at entry instead of polling. For PAPER, model the fill at the SL/target trigger price (plus slippage), not the post-move LTP, and consider checking the candle low/high to detect intrabar SL breaches.

### Trailing SL math is anchored to initial_sl, producing an incorrect (over-tight) trail
- **Category:** accuracy
- **Location:** `backend/utils/risk_manager.py` : 126-133
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** calculate_trailing_sl computes trail_steps=int(profit/trailing_value) then new_sl=initial_sl + trail_steps*trailing_value. The trail is anchored to the original SL, not to current_price minus trailing_value. Example: entry=100, initial_sl=80, trailing_value=5, price=130 -> profit=30, steps=6, new_sl=80+30=110. The SL (110) is ABOVE the current intended trail distance and far from a price-relative trail; the gap between price and SL is arbitrary and not equal to trailing_value.
- **Impact:** Trailing distance does not equal trailing_value and grows non-linearly; SL can jump above entry too aggressively or lag, causing premature exits or unprotected give-back. P&L outcomes are unpredictable.
- **Fix:** Anchor to price: new_sl = current_price - trailing_value (or use a percentage), then return max(current_sl, new_sl). If a step model is desired, base it on (entry + trail_steps*trailing_value) - fixed_offset, and document the intended behavior clearly.

### P&L ignores brokerage, STT, exchange fees, GST and lot/quantity semantics
- **Category:** accuracy
- **Location:** `backend/services/trading_engine.py` : 457-458
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** execute_exit computes pnl=(final_exit_price - entry_price)*trade['quantity'] with zero transaction costs. Paper place_order (paper_broker.py:235) is identical. Indian options carry significant round-trip costs (brokerage, STT on sell premium, exchange txn charges, SEBI, stamp, 18% GST). Also 'quantity' appears to be raw units; if a strategy stores lots vs units inconsistently the multiplier is wrong.
- **Impact:** Both paper and live realized P&L are overstated by the full fee stack (often a meaningful fraction of scalping edge). Strategy appears profitable in paper while being a net loser live. Undermines the user's best-results objective.
- **Fix:** Introduce a fees model (per-leg brokerage cap, STT 0.0625% on sell premium, txn charges, GST, stamp) and subtract from pnl in both engine.execute_exit and paper_broker.place_order. Validate that 'quantity' is consistently in units (lot_size * lots) everywhere and store lot_size on the trade.

### No guardrails enforced at entry: kill switch only, no concurrent-trade / daily-loss / max-orders checks
- **Category:** risk
- **Location:** `backend/services/trading_engine.py` : 114-172, 282-314
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** evaluate_strategies only checks settings.kill_switch and per-strategy OPEN trade. risk_manager.can_strategy_trade and can_overall_trade (richer guards: max_orders_per_day, daily profit/loss limits, max_concurrent_trades) are never called in the entry path. execute_entry also does not re-check limits or insufficient-margin for LIVE.
- **Impact:** Runaway entries possible: many strategies can each open trades simultaneously with no portfolio cap; a bad day can blow through daily-loss limits because nothing reads overall_pnl_today. Major risk-control hole given user is doing live-capable F&O.
- **Fix:** Call risk_manager.can_overall_trade(settings, active_trades) and can_strategy_trade(strategy, settings) before execute_entry, and re-check inside execute_entry just before place_order. Feed real today_pnl/active-trade counts. Halt new entries when limits hit.

### can_overall_trade is not invoked in the automated entry path or start_strategy
- **Category:** risk
- **Location:** `backend\services\trading_engine.py` : 114-169, 282
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** evaluate_strategies and execute_entry only check kill_switch and a hardcoded min_confidence (trading_engine.py:120,163). Neither can_strategy_trade nor can_overall_trade is called during automated entry. start_strategy (strategy_routes.py:156) calls only can_strategy_trade (which is broken per above) and never can_overall_trade, so concurrent-trade and global P&L limits are unenforced.
- **Impact:** Concurrent-trade cap (DEFAULT_MAX_CONCURRENT_TRADES) and global P&L limits are bypassed during live automated trading — the exact moment they matter most.
- **Fix:** Add a gate at the start of the per-strategy loop: compute active_trades = len(db.get_active_trades(user_id)); call can_overall_trade(self.settings, active_trades) and can_strategy_trade(strategy, self.settings); skip the strategy if either returns False, logging the reason.

### get_today_trades uses UTC midnight, not IST — daily P&L/limits miscount near boundary
- **Category:** accuracy
- **Location:** `backend\database\mongodb.py` : 255-259
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** today_start = datetime.utcnow().replace(hour=0,...) defines 'today' as UTC midnight (= 05:30 IST). Trades created between 00:00 and 05:30 IST are bucketed into the previous trading day for summaries, and any logic using this for daily totals is off by the 5.5h offset. created_at is stored as datetime.utcnow() (line 214) so the comparison is UTC-consistent internally but semantically wrong for an IST market.
- **Impact:** Daily summaries, win-rate, and any limit logic relying on get_today_trades undercount/miscount trades around the boundary and during the early-morning summary/reset window, degrading accuracy of reported and risk-relevant metrics.
- **Fix:** Compute today_start from get_ist_now().replace(hour=0,...) converted to UTC, e.g. ist_midnight = get_ist_now().replace(hour=0,minute=0,second=0,microsecond=0); today_start = ist_midnight.astimezone(pytz.utc). Align the reset job and daily_summary cutoffs to IST too.

### calculate_trailing_sl steps from initial_sl, not entry — trailing logic is mathematically wrong
- **Category:** correctness
- **Location:** `backend\utils\risk_manager.py` : 128-133
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** trail_steps = int(profit/trailing_value) and new_sl = initial_sl + trail_steps*trailing_value. This anchors the trail to the ORIGINAL stop (initial_sl), not to the current price minus a trailing distance. As profit grows, new_sl lags far behind price by (entry - initial_sl) plus rounding, and the step quantization means SL only moves in discrete jumps. It also never accounts for the gap between entry and initial_sl, so the SL can remain below entry while deep in profit.
- **Impact:** Profits are not protected as intended; the trailing stop stays loose, giving back gains on reversals. For scalping this materially reduces realized edge.
- **Fix:** Use a price-anchored trail: new_sl = current_price - trailing_value (locking a fixed distance), then return max(current_sl, new_sl). Optionally combine with break-even logic. Add tests covering rising-price scenarios.

### check_exit_condition evaluates target before SL and uses LTP, ignoring gap-through on both sides
- **Category:** correctness
- **Location:** `backend\utils\risk_manager.py` : 226-237
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** Target is checked before stop loss. On a gap candle where price jumps past both levels (e.g., a spike where the polled LTP is above target but had crossed SL intra-tick), TARGET wins regardless. More importantly, exit_price is set to the polled current_price, not to the SL/target level, so on a violent move the recorded fill assumption can be optimistic. Because monitoring is poll-based (every 5s, trading_engine.py:174), an option can blow through the SL between polls and exit far worse than stop_loss.
- **Impact:** Stop losses are advisory, not protective; realized losses can exceed the configured SL during fast moves — a real-time staleness defect that worsens results and risk.
- **Fix:** Check stop loss before target (protect downside first). For LIVE, prefer broker-side SL/GTT orders rather than poll-based exits. When triggered by SL, record exit at min(current_price, stop_loss) for realistic accounting and alerting; tighten the monitor interval or move to a streaming/websocket LTP feed.

### calculate_position_size ignores lot_size and option price; risk units are inconsistent
- **Category:** risk
- **Location:** `backend\utils\risk_manager.py` : 200-204
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** lots_based_on_risk = int(risk_amount / stop_loss_points) divides rupees by points, ignoring lot_size (a parameter that is accepted but unused) and the option's per-unit value. Risk per lot for an option SL of X points is X * lot_size, not X. The function also can return a huge integer when stop_loss_points is small and never caps against available margin or a max-lot ceiling.
- **Impact:** Position sizing can be wildly oversized (off by a factor of lot_size, e.g. 75x for NIFTY) leading to per-trade risk far above the intended risk_percent. Direct capital risk.
- **Fix:** Compute lots = int(risk_amount / (stop_loss_points * lot_size)) and clamp to >=1 and <= a configurable max_lots and to affordable margin. Guard stop_loss_points<=0. Add unit tests for NIFTY/BANKNIFTY lot sizes.

### Candle read path has no staleness/freshness guard
- **Category:** realtime
- **Location:** `backend\database\mongodb.py` : 126-135
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** get_candles returns the latest N candles by timestamp with no check that the newest candle is recent. If the scheduler/ingest stalls, the engine (trading_engine.py:134-145) silently analyzes stale candles and generates signals on outdated data.
- **Impact:** Trading decisions on stale market data — directly undermines real-time correctness and accuracy, the user's stated priorities. Can produce entries against the current market.
- **Fix:** Add an optional max_age check: compute now-IST minus newest candle timestamp; if it exceeds e.g. 2x the interval during market hours, return empty or raise so callers can skip trading. Surface a 'data_stale' status to the engine/UI.

### Models perform no validation; from_dict(cls(**data)) blindly trusts DB/request input
- **Category:** data-integrity
- **Location:** `backend\models\models.py` : 146-147,269-270,52-63
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** Strategy.from_dict and Trade.from_dict do cls(**data) with **kwargs swallowing unknown keys. There is no validation of quantity (could be negative/zero), stop_loss/target (could be negative), max_orders_per_day, min_confidence range, allowed_signals enum, exchange_segment, or option_type. Strategy fields like quantity:int and strike_price:str are inconsistently typed. update_strategy (strategy_routes.py:134) writes arbitrary JSON straight to Mongo via $set with no schema enforcement.
- **Impact:** Corrupt/abusive strategy configs (e.g., quantity=0, negative SL, min_confidence>100) propagate into live order placement; unvalidated PUT body can overwrite critical fields (e.g., user_id, is_active, today_pnl). Data-integrity and risk hole.
- **Fix:** Introduce explicit validation (pydantic or manual) in from_dict and at the route layer: positive int quantity within max lots, SL/target>0, min_confidence 0-100, allowed_signals in {BOTH,BULLISH,BEARISH}, enum-checked product/exchange. Whitelist updatable fields in update_strategy and reject user_id/_id/counter overrides.

### Trade model default status 'open' (lowercase) vs queries using 'OPEN'
- **Category:** correctness
- **Location:** `backend\models\models.py` : 227 (vs mongodb.py:234, trading_engine.py:156)
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** Trade.__init__ defaults status='open', but get_active_trades queries {'status':'OPEN'} (mongodb.py:234) and the engine queries status:'OPEN' (trading_engine.py:156) and close_trade sets 'CLOSED' (mongodb.py:246). The engine's execute_entry writes 'OPEN' directly (trading_engine.py:353) so the model default is inconsistent and any code path that constructs a Trade via the model would create an unmonitored position.
- **Impact:** If a trade is ever created through the model defaults (status='open'), it is invisible to get_active_trades/monitoring and will never get SL/target/exit handling — an orphaned, unmanaged live position.
- **Fix:** Standardize status casing to a single constant set (e.g., uppercase 'OPEN'/'CLOSED') everywhere, default Trade.status='OPEN', and add an index-backed status normalization or enum.

### bulk_upsert_instruments deletes all instruments before insert (non-atomic) — symbol resolution can fail mid-sync
- **Category:** data-integrity
- **Location:** `backend\database\mongodb.py` : 274-278
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** delete_many({}) wipes the entire instruments collection, then insert_many repopulates. There is no transaction. If insert_many fails or the process is killed between the two operations, the instruments collection is empty.
- **Impact:** During the sync window (or on failure) resolve_dynamic_symbol (trading_engine.py:269) and find_instrument_by_strike return nothing, so entries raise 'No instrument found' and the engine cannot trade — and worse, an empty collection persists until next sync. If sync runs at 8 AM while a strategy is somehow active, live entries break.
- **Fix:** Use an upsert-and-prune pattern: bulk upsert by trading_symbol/exchange_token, then delete only documents whose synced_at is older than this run. Or write to a temp collection and rename. Never leave the live collection empty.

### run_parameter_sweep() executes on import (outside __main__ guard)
- **Category:** correctness
- **Location:** `backend/groww/run_backtest.py` : 87-120
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** run_parameter_sweep() is defined after the `if __name__ == '__main__'` block and is then CALLED unconditionally at line 120 at module top level. Any import of run_backtest (or simply running it) triggers a 9-combo sweep, each hitting the live Groww API, regardless of intent. Combined with the broken Config/Backtester import this is dead, but once fixed it will fire unexpectedly.
- **Impact:** Unintended live API calls / rate-limit consumption on import; non-deterministic side effects; confusing behavior. Sweep also uses interval=1 and CE_ONLY hardcoded, diverging from the top-level config.
- **Fix:** Move the call inside the __main__ guard and gate it behind a flag (e.g. RUN_SWEEP=False). Never perform network I/O at module import time.

### Wrong NIFTY lot size (650) in run_backtest inflates P&L ~8.7x
- **Category:** accuracy
- **Location:** `backend/groww/run_backtest.py` : 46
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** LOT_SIZE is set to 650, but NIFTY F&O lot size is 75 (correctly defaulted in nifty_scalper_bt.py:69). pnl_rs = pnl_pts*lot_size - brokerage (nifty_scalper_bt.py:330) scales rupee P&L directly by lot size.
- **Impact:** Every rupee P&L, win/loss magnitude, and any capital/risk sizing derived from the backtest is overstated by ~8.7x, leading to dangerously oversized live positions if used for sizing.
- **Fix:** Set LOT_SIZE=75 (or fetch the current contract lot size from the instrument master at runtime, since it can change). Validate lot size against Groww instrument metadata.

### Optimistic / ambiguous intra-bar fills in execute_trades (TP and SL same bar, both assumed reachable)
- **Category:** realtime
- **Location:** `backend/groww/nifty_scalper_bt.py` : 300-320
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** Within a bar the code checks hit_tp = ob.h>=tp and hit_sl = ob.l<=t.sl using the same bar's high and low. When both are true it resolves to STOPLOSS (conservative, good), but in all cases it assumes you can be filled exactly at tp or at t.sl within that 1-min bar regardless of where the open/close were or whether price gapped through. Trailing (:300-301) also updates SL using the same bar's high before evaluating the SL in that bar, allowing the same-bar high to both trigger trailing and then be checked — order effects matter. Entry slippage is a flat 0.5 and exit slippage 0.5 with no spread/impact for fast-moving option bars.
- **Impact:** For low-priced weekly options (premiums ~20-45 here) a 1-min bar range of several points is common; assuming exact tp/sl fills overstates win rate and understates loss size. Trailing-before-check can lock unrealistic profits.
- **Fix:** Model fills against the bar OPEN when a gap occurs (if open>=tp, fill at open; if open<=sl, fill at open), apply a percentage/tick spread to slippage instead of a flat 0.5, evaluate SL before applying same-bar trailing, and stress-test with pessimistic fill assumptions to bound the edge.

### Single-day, single-symbol backtest — no walk-forward, OOS, or survivorship handling
- **Category:** accuracy
- **Location:** `backend/groww/run_backtest.py / backend/groww/nifty_scalper_bt.py` : run_backtest.py:31; nifty_scalper_bt.py:430-459
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** DATES=['2026-02-06'] (one day) and a single fixed CE/PE symbol are used. The fetched option symbol (NIFTY2621025850CE) is a specific strike/expiry chosen with hindsight; there is no logic to roll to the prevailing ATM strike per day, so backtesting other days reuses an inappropriate strike (deep ITM/OTM or expired). No in-sample/out-of-sample split, no walk-forward, no multi-day aggregation of stats.
- **Impact:** Results are a single-sample anecdote highly prone to overfit; the chosen strike introduces selection/survivorship bias (you know in advance which option was liquid and moved). Parameter sweeps on one day will overfit to that day's noise.
- **Fix:** Backtest over many days with per-day ATM strike selection derived from the index open (not chosen post hoc), split in-sample vs out-of-sample, add walk-forward parameter optimization, and report distribution of daily PnL with confidence intervals, not a single number.

### Timezone inconsistency: scanner uses naive local time, backtester uses IST — session filters break off-IST
- **Category:** correctness
- **Location:** `backend/groww/New/opportunity_scanner.py vs backend/groww/nifty_scalper_bt.py` : opportunity_scanner.py:44-50,78-80,173; nifty_scalper_bt.py:37,199-200,235
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** Scanner converts timestamps with datetime.fromtimestamp(ts) (no tz) and filters on time_str '09:20'..'15:20' and buckets higher timeframes by local minute. The backtester correctly uses tz=IST. On any server not in IST (e.g. UTC cloud host), the scanner's session window, the 09:20/15:20 skip, and the 5m/15m bucket alignment all shift, silently dropping or misaligning candles.
- **Impact:** On a UTC host the scanner would filter out the entire NSE session (09:15-15:30 IST = 03:45-10:00 UTC, all < '09:20'), producing zero or wrong opportunities; bucket alignment for 5m/15m would also be off. Non-reproducible across environments.
- **Fix:** Standardize on tz-aware IST (Asia/Kolkata) everywhere, mirroring nifty_scalper_bt.py:37. Convert with datetime.fromtimestamp(ts, tz=IST) in the scanner and align buckets in IST.

### market_heartbeat_job queries MongoDB on every 5-second tick for active user and GrowwClient instantiation
- **Category:** performance
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\scheduler.py` : 128-172
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** _get_active_user() (line 40) executes db.users.find_one({'broker_connected': True}) — a MongoDB round trip — on every heartbeat invocation (12 times per minute, 720 times per hour). Additionally get_groww_client() and get_trading_engine() are freshly constructed on every call (lines 137-138), meaning a new requests.Session is created and the token is decrypted from DB every 5 seconds.
- **Impact:** Unnecessary database load and CPU overhead. Each token reload involves a MongoDB query plus a decrypt operation. On a loaded system this adds latency to the heartbeat and can cause the 5-second interval to bleed into the next tick. The active_user_id set at start() (line 107) is never actually used in the job.
- **Fix:** Cache the active_user and GrowwClient at scheduler start and on explicit broker-connected events. Refresh the cache only when broker_connected changes or on a slow 60-second cycle. Use the already-set self.active_user_id (line 107) to avoid repeated find_one calls.

### direction_scheduler reads MongoDB 3 times per second (3 symbols x 1 s) without any candle-change detection
- **Category:** performance
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\direction_scheduler.py` : 83-142
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** _update_direction() calls candle_service.get_candles(db, symbol, '1', 200) unconditionally on every 1-second iteration, which executes a MongoDB find+sort+limit on the candles collection. Since the candle data only changes every 60 seconds (from sync_and_aggregate_job), 59 out of 60 reads are pure overhead. Three symbols means 3 DB reads per second, 10,800 per hour.
- **Impact:** Unnecessary MongoDB load competes with the write operations from sync_and_aggregate_job. If MongoDB is also handling trades, orders, and user queries, this creates query contention. The direction result computed from the same unchanged data 59 consecutive times is identical — the computation is fully wasted.
- **Fix:** Track the last candle timestamp per symbol in direction_scheduler. Only re-run analyze_direction() when the latest candle timestamp differs from the last known value. Between candle changes, serve the cached direction_cache result without recomputing. Alternatively, publish a Redis key when the candle sync completes and have the direction scheduler subscribe to that notification.

### direction_scheduler falls back to df_1m = candles_5m — mislabelled variable causes wrong aggregation
- **Category:** accuracy
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\direction_scheduler.py` : 99-115
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** When candles_1m has fewer than 50 records, the fallback at line 105 assigns df_1m = pd.DataFrame(candles_5m). Then at lines 113-114, timeframe_aggregator.aggregate(df_1m, '5') and aggregate(df_1m, '15') are called with this 5m data pretending to be 1m data. The aggregator resample logic uses label='left', closed='left' with the interval derived from the target_interval string. Resampling 5-minute candles with a 5-minute rule produces valid-looking but potentially wrong candles (boundary misalignment, duplicated aggregations).
- **Impact:** When 1m data is not yet available (first sync of the day, after system restart, or API failure), analyze_direction() receives a df_1m that is actually 5-minute data. Market direction signals during this window are computed from wrongly-labelled data. All trading decisions during the first hour of the day could be based on incorrect direction analysis.
- **Fix:** If 1m candles are unavailable, pass candles_5m as df_5m and df_15m directly to analyze_direction() and pass an empty df_1m (or a note that 1m is unavailable). Do not alias df_1m = candles_5m. The analyze_direction() function signature already accepts all three separately.

### Redis direction key serialised with str(result) — dict becomes a string that cannot be deserialised
- **Category:** correctness
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\direction_scheduler.py` : 139
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** redis_client.set('direction:{symbol}', str(result), ex=10) stores the Python dict repr (e.g., "{'direction': 'BULLISH', 'confidence': 0.8, ...}") as a plain string. Any consumer calling redis_client.get('direction:{symbol}') gets back a string that looks like a dict but cannot be safely parsed with json.loads() because str(dict) uses single quotes. ast.literal_eval() would be needed, which is a security risk.
- **Impact:** Any cross-process consumer of the direction key (e.g. a separate worker or API endpoint) will receive an unparseable string. The in-process direction_cache dict is used directly, so the issue is masked locally. But the feature of cross-process Redis-based direction sharing is broken.
- **Fix:** Replace str(result) with json.dumps(result) (line 139). Add a default= handler for any non-serialisable types (numpy floats, pandas Timestamps). Consumers should use json.loads().

### Redis client has no reconnection logic — after initial failure connected=False forever
- **Category:** realtime
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\database\redis_client.py` : 35-38
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** If Redis is unavailable at startup, self.connected = False (line 38). All subsequent calls to cache_ltp(), get_cached_ltp(), set(), get() short-circuit to return None/False. There is no background reconnect attempt; the client remains disconnected for the process lifetime even if Redis becomes available seconds later. Additionally, after initial success, if Redis drops during runtime, the redis.Redis.setex/get calls will raise redis.ConnectionError but the generic `if self.connected` guard will not catch it — get() and set() (lines 52, 56) have no try/except.
- **Impact:** A transient Redis restart causes LTP caching to silently fail for the entire session. The heartbeat stores no prices, direction_scheduler.get_cached_ltp() returns None for every symbol, and live_ltp passed to analyze_direction() is always None — degrading signal quality. The direction keys are also not published, breaking the cross-process contract.
- **Fix:** Add try/except around every redis operation post-init. Implement a lazy reconnect: on ConnectionError, attempt self._initialize() once, set connected appropriately. Or use redis-py's retry_on_error parameter. Add a health-check method that tests connectivity and expose it in the /api/health endpoint.

### LTP Redis TTL is 10 seconds but heartbeat fires every 5 seconds — staleness window is too wide for scalping
- **Category:** realtime
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\database\redis_client.py` : 47-49
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** cache_ltp() sets a 10-second TTL. The heartbeat interval is 5 seconds. This means in the best case a consumer reads a price that is 0–5 s old; in the worst case (heartbeat delayed by MongoDB queries or network), 5–10 s old. For F&O scalping where NIFTY can move 20–30 points in 5 seconds, a 10-second stale price used for stop-loss evaluation or entry decision is unacceptable.
- **Impact:** engine.monitor_active_trades() at line 165 of scheduler.py uses the price from ltp_result, not from Redis, so it's fine for that call. However direction_scheduler._update_direction() reads Redis LTP (line 121) — if the heartbeat is even slightly delayed, the direction engine uses a stale price for its live_ltp computation, degrading signal accuracy.
- **Fix:** Reduce LTP Redis TTL to 6 seconds (just above the heartbeat interval) so stale values expire between heartbeats instead of persisting through two cycles. Better yet, reduce the heartbeat interval to 2–3 seconds and the TTL to 4 seconds.

### sync_and_aggregate_job has no max_instances guard for the reconcile_orders_job
- **Category:** risk
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\scheduler.py` : 73-79
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** reconcile_orders_job is added with IntervalTrigger(minutes=1) but without max_instances=1 (unlike market_heartbeat at line 60 and sync_and_aggregate at line 70). If a reconciliation call takes longer than 60 seconds (slow Groww API, large order list, MongoDB latency), APScheduler will spawn a second concurrent instance of the job, potentially running two reconciliations simultaneously.
- **Impact:** Concurrent reconciliation can cause double-processing: engine.reconcile_positions() called twice with the same broker state could create duplicate internal position adjustments or double-close trades in paper mode.
- **Fix:** Add max_instances=1 to the reconcile_orders_job add_job call (line 73). Consider adding coalesce=True as well so missed fires are not queued.

### is_market_open() has no trading-holiday awareness — system polls Groww API on NSE holidays
- **Category:** accuracy
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\utils\time_utils.py` : 16-28
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** is_market_open() only checks weekday (Mon-Fri) and the 9:15–15:30 window. It does not check the NSE/BSE holiday calendar. On trading holidays (e.g., Republic Day, Diwali Muhurat, etc.), the market is closed but is_market_open() returns True. All scheduler jobs fire, the heartbeat polls Groww for LTP, candle syncs attempt to fetch data, and strategy evaluation runs on stale/null data.
- **Impact:** On market holidays, get_ltp() will return either zero prices or error responses. If prices are zero, cache_ltp stores 0 and the direction engine may compute extreme signals. If the API returns success with last-traded prices from the previous day, the system could generate false signals and — in LIVE mode — place real orders.
- **Fix:** Maintain a holiday list (static dict or DB collection, updated annually) and add a check in is_market_open(). The NSE publishes holiday calendars in advance. Alternatively, use a Groww API endpoint to check market status before each job run.

### sync_and_aggregate_job always fetches 7 days of 1m candles every minute — massive redundant data transfer
- **Category:** performance
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\candle_service.py` : 128-164
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** _get_smart_window(interval=1) always returns a 7-day lookback window (line 155-156). For a 1-minute interval over 7 trading days, that is approximately 7 x 375 = 2,625 candles per symbol, three symbols per sync cycle. Every 60 seconds the system downloads ~8,000 candles from Groww (which already exist in DB) just to overwrite them. The actual new data in each cycle is 1 candle.
- **Impact:** Heavy API bandwidth, slow response times (30 s timeout configured), increased risk of rate limiting, and extended window during which the DB is empty (delete_many has more rows to delete). On a slow connection this full-sync can take several seconds per symbol, meaning the 60-second sync cycle may not complete before the next one fires.
- **Fix:** For the per-minute sync, determine the last known candle timestamp from the DB (one lightweight DB query) and request only the missing window from Groww (e.g., last 5–10 minutes). Only perform the full 7-day backfill on explicit startup or daily reset. This reduces per-cycle data to 1–10 candles.

### AI decision on Dashboard has no polling interval — displays stale signal indefinitely
- **Category:** realtime
- **Location:** `frontend/src/pages/Dashboard.tsx` : 259-261
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** The useEffect at line 259-261 only fires fetchDecision(analysisSymbol, 5) when analysisSymbol changes. There is no setInterval. The AI Signal card (lines 411-426) shows the signal, confidence, bullish/bearish scores, and indicator count from the last fetch. If the user lands on Dashboard and does not switch symbols or click Refresh, the displayed signal can be 30+ minutes old while the Market Direction Engine cards (which do poll every 30s) show a contradicting live direction.
- **Impact:** The most prominent dashboard card shows stale AI signal that may indicate BULLISH while the direction engine cards show BEARISH. This directly leads to wrong manual strategy decisions and undermines the trader's trust in the system accuracy.
- **Fix:** Add a polling interval for fetchDecision in Dashboard.tsx parallel to the direction polling: `const decisionTimer = setInterval(() => fetchDecision(analysisSymbol, 5), 30000)`. Clean it up in the effect return. Alternatively colocate direction and decision in one 30s poll for efficiency.

### Duplicate conflicting formatCurrency implementations with different default precision and formatting logic
- **Category:** accuracy
- **Location:** `frontend/src/utils/formatter.ts` : 4-11
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** Two formatCurrency functions exist: utils/formatter.ts (line 4, defaults to 2 decimals, uses en-IN toLocaleString showing full price like ₹24,532.50) and utils/index.ts (line 2, defaults to 0 decimals, abbreviates to ₹24.5K or ₹2.4L). Dashboard.tsx imports from utils/formatter while pages like Signals.tsx format prices with raw .toLocaleString() calls. The P&L on the Trades page (line 8 import) uses formatCurrency from formatter.ts so shows 2 decimal places, but the strategy today_pnl on Dashboard uses the same import — inconsistency within the same page if any component imports from index.ts.
- **Impact:** Traders see inconsistent price representations: ₹24,532.50 on one card and ₹24.5K on another for the same value. On volatile NIFTY options where price moves in sub-rupee increments, abbreviation to 0 decimals loses critical precision (e.g., an option at ₹23.75 shows as ₹24). This is an accuracy risk for entry/exit price verification.
- **Fix:** Remove one of the two formatter files. Keep utils/index.ts as the canonical source. Export both formatCurrency (abbreviated, for large INR values like portfolio P&L) and formatCurrencyFull (full precision, for option prices and trade P&L). Update all imports across pages to use the appropriate variant explicitly. Never show option prices abbreviated — always use 2 decimal places minimum.

### Client-side P&L computed from stale trade.ltp — not a live streaming broker price
- **Category:** realtime
- **Location:** `frontend/src/pages/Dashboard.tsx` : 518-519
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** Active trades table in Dashboard (line 518-519) and Trades.tsx (line 390) compute unrealized P&L as: `(trade.ltp - trade.entry_price) * trade.quantity * direction`. The trade.ltp value comes from the last poll of tradeApi.getActiveTrades(), which has a 10s interval. This is a snapshot from the backend, which itself may have fetched the LTP from Groww broker APIs with an additional delay. The P&L shown is up to 10-20 seconds stale.
- **Impact:** For NIFTY options scalping with tight 20-point stop losses, a 10-20 second stale LTP can show a P&L of +₹500 when the actual unrealized P&L is -₹300 (if the option moved adversely in that window). This creates a false sense of security and can prevent timely manual intervention.
- **Fix:** Reduce fetchActiveTrades interval to 3s (matching the config.TRADE_POLL_INTERVAL that is defined but unused). Alternatively, implement a WebSocket subscription to the backend for live LTP pushes for open positions only. At minimum, display a staleness indicator showing 'Last updated Xs ago' next to each LTP cell.

### handlePlaceOrder: SL/Target applied via a separate modifyTrade call leaving a window with no risk controls
- **Category:** risk
- **Location:** `frontend/src/pages/Trades.tsx` : 218-248
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** In Trades.tsx handlePlaceOrder, a quickTrade order is placed (line 218-223), then — only if the response contains a valid tradeId and entryPrice (line 230) — a separate modifyTrade call applies the stop loss and target (lines 243-248). Between the quickTrade success and modifyTrade completion (network round trip), the position has zero risk controls on the broker side. If the market moves sharply in that window or if the modifyTrade call fails (line 258 catch), the trade remains open with no SL.
- **Impact:** On a NIFTY options scalp during high volatility (e.g., news event), a 200-300ms gap with no SL can result in a runaway loss that exceeds the entire configured max_loss_limit. This is especially dangerous because the UI shows the buttons for SELL CE/PE which are short-side trades with theoretically unlimited loss.
- **Fix:** Move the SL/Target application to the backend: modify the quickTrade API endpoint to accept stop_loss_points and target_points parameters and have the backend apply them atomically with the order. If that is not feasible, the frontend should at minimum show an error and attempt an immediate market exit if modifyTrade fails, rather than silently logging a warning.

### isAnalyzing flag in strategy.store is shared across all symbols — analyzing BANKNIFTY blocks NIFTY signal display
- **Category:** correctness
- **Location:** `frontend/src/store/strategy.store.ts` : 73-90
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** fetchDecision (line 74) sets isAnalyzing: true globally. The Signals.tsx loading guard at line 44-55 checks `!data && isAnalyzing` — but isAnalyzing is true for the entire duration of any symbol's analysis. If a user switches from NIFTY to BANKNIFTY, both the NIFTY data check and the BANKNIFTY loading state use the same isAnalyzing flag. Also, analyzeStrategy (line 98) overwrites the shared decision field regardless of which symbol it pertains to, destroying the previously selected signal.
- **Impact:** The Signals page can show the wrong symbol's signal if analyzeStrategy is called while the user is viewing Signals.tsx. The loading spinner blocks the entire UI for all symbols when any one is being analyzed.
- **Fix:** Add per-symbol isAnalyzing state: `isAnalyzingSymbols: Record<string, boolean>`. Set and clear per symbol in fetchDecision. Signals.tsx should check `isAnalyzingSymbols[selectedSymbol]` instead of the global flag. analyzeStrategy should store its result in decisions[strategySymbol] not the shared decision field.

### Race condition in handleDirectionClick: directionLoading set to false before fetchDirection may resolve if called twice
- **Category:** realtime
- **Location:** `frontend/src/pages/Dashboard.tsx` : 298-307
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** handleDirectionClick (lines 298-307): setDirectionLoading(true) is set, then await fetchDirection(symbol, true). If the user clicks a different direction card before the first fetchDirection resolves, a second handleDirectionClick fires, starts another fetchDirection, and both will set directionLoading(false) when they finish — but the selectedSymbol state will show the second symbol while the first fetch might write to directions[firstSymbol], causing the modal to briefly show old data. There is also no AbortController to cancel the first in-flight request.
- **Impact:** The direction analysis modal can display the data of the previously clicked symbol for up to the network round-trip duration. On a fast click sequence, the modal may show NIFTY data for a BANKNIFTY card for 500ms-2s, potentially misleading the trader about the market direction of the instrument they are reviewing.
- **Fix:** Use an AbortController ref to cancel the previous fetchDirection call when a new one starts. Set a request ID ref and only update state if the request ID matches the latest. Pattern: `const reqId = useRef(0); reqId.current++; const thisId = reqId.current;` then only update if `thisId === reqId.current`.

### No polling for market status, indices, strategies, or engine status on Dashboard — data only refreshes on manual click
- **Category:** realtime
- **Location:** `frontend/src/pages/Dashboard.tsx` : 219-282
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** Dashboard stores the initial data from mount but never polls fetchMarketStatus, fetchIndices, fetchStrategies, or fetchEngineStatus on any interval. The Market Overview cards (index prices) go stale immediately after initial load. If a strategy is started/stopped from the backend or from another browser tab, the dashboard strategy list does not reflect it until manual refresh.
- **Impact:** Index prices shown (NIFTY, BANKNIFTY, SENSEX) are from initial load time, potentially hours old if the user keeps the dashboard open. The Engine Status card will show a strategy as 'Running' when it has been auto-stopped by a risk limit trigger, giving the trader false assurance that the engine is actively managing their position.
- **Fix:** Add a 30s polling interval for fetchIndices and fetchEngineStatus. Add a 60s polling interval for fetchStrategies (strategy list changes are less frequent). Use the isBackground pattern already established in direction.store.ts to suppress loading spinners.

---

## MEDIUM

### get_quote endpoint splits symbol on first underscore only — fails for symbols like 'NSE_NIFTY_50_CE'
- **Category:** correctness
- **Location:** `backend/routes/market_routes.py` : 313-318
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** At lines 313-315, the code does: parts = exchange_sym.split('_'); exchange = parts[0]; trading_symbol = parts[1]. For a symbol like 'NSE_NIFTY_23JUN_19000CE', this produces exchange='NSE', trading_symbol='NIFTY', dropping the rest of the string. The get_quote call then queries for the wrong symbol.
- **Impact:** Option quote lookups fail silently — the Groww API returns data for 'NIFTY' (the index) instead of the requested option contract, or returns an error. The frontend receives wrong OHLC data.
- **Fix:** Use: parts = exchange_sym.split('_', 1); exchange = parts[0]; trading_symbol = parts[1] if len(parts) > 1 else exchange_sym. Alternatively, accept exchange and segment as separate query parameters rather than encoding them into the path.

### Instrument sync is open to any authenticated user — can be used to wipe the instruments collection
- **Category:** security
- **Location:** `backend/routes/instruments_routes.py` : 10-14
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** The POST /api/instruments/sync endpoint (and POST /api/market/instruments/sync in market_routes.py line 431-438) requires only a valid JWT, not admin privileges. Any registered user can trigger instrument_sync.sync_instruments(), which calls db.instruments.delete_many({}) followed by insert_many(). A malicious user (or a user whose token is stolen) can trigger repeated syncs, causing the delete-and-insert gap repeatedly, or abuse the endpoint to exhaust server resources by downloading and processing the large Groww instruments CSV.
- **Impact:** DoS via repeated sync requests. During each sync, active strategies using instruments lose their symbol resolution for seconds. If an attacker can prevent the insert (e.g., by flooding with concurrent sync requests), the instruments collection stays empty.
- **Fix:** Add an admin role check (e.g., user.get('is_admin') == True). Rate-limit the endpoint to once every N minutes using Redis (store last_sync timestamp and reject if too recent). Also fix the underlying delete+insert atomicity issue.

### Quick-trade creates a CLOSED trade record for SELL transactions with entry_price=0 potential
- **Category:** data-integrity
- **Location:** `backend/routes/trade_routes.py` : 597-621
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** In quick_trade(), the trade status is set as: 'status': 'OPEN' if transaction_type == 'BUY' else 'CLOSED' (line 610). For a SELL, the trade is immediately stored as CLOSED with pnl=0 (line 621) and entry_price from result.get('execution_price', result.get('average_price', 0)) (line 608). If execution_price and average_price are both absent from the broker response, entry_price is stored as 0. A SELL without a corresponding BUY position has no meaningful P&L at entry time; recording it as instantly CLOSED with pnl=0 is incorrect and corrupts daily P&L summaries.
- **Impact:** Daily P&L calculations count SELL orders as zero-PnL closed trades. Win rate calculations are distorted. The positions view shows no open SELL position even if one is in flight.
- **Fix:** For SELL transactions, link the trade to an existing OPEN trade rather than creating a new closed record. Model sells as exits of existing positions. If the intent is to record a short-sell entry, keep status=OPEN until the covering BUY happens.

### option chain fallback returns raw DB instrument records without normalising field names for the frontend
- **Category:** accuracy
- **Location:** `backend/routes/market_routes.py` : 378-394
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** When the live Groww API fails, get_option_chain() falls back to db.get_instruments_by_underlying(). The returned documents are raw instrument records with fields like instrument_type, strike_price, expiry_date — which differ from the live API path that returns CE/PE nested objects under a strike key. The enriched_data list at line 387 contains heterogeneous field layouts compared to the live path (lines 355-374). The frontend consuming the 'data' array would receive structurally different objects.
- **Impact:** Option chain display breaks or shows incorrect data when the API fallback triggers. For a scalping system that relies on accurate option chain data to select strikes, this can cause wrong strike selection.
- **Fix:** Normalise the DB fallback to produce the same schema as the live response: transform instrument records into the {strike_price, CE: {...}, PE: {...}} format before returning.

### settings_routes.update_user_field does not validate execution_mode against LIVE mode pre-conditions
- **Category:** risk
- **Location:** `backend/routes/settings_routes.py` : 81-98
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** update_execution_mode() allows switching to LIVE mode without checking whether a valid, unexpired Groww access token exists. A user with no API credentials or an expired token can switch to LIVE mode. Subsequently, place_order() calls get_groww_client(user_id) which constructs a GrowwClient with no access token and places requests to Groww without Authorization headers, which Groww will reject with 401.
- **Impact:** A user in LIVE mode without a valid token believes their orders are being placed but Groww rejects all of them. They have no open positions on Groww but the system may record phantom orders in MongoDB if any code path creates trade records before checking the broker response.
- **Fix:** Before switching to LIVE mode, verify: (1) the user has a groww_access_token, (2) it is not expired (is_token_expired()), (3) a test API call succeeds. Return 400 with an actionable error if any check fails.

### get_indices caches the indices response with source='LIVE' but the Redis cache key is not user-scoped
- **Category:** accuracy
- **Location:** `backend/routes/market_routes.py` : 215-252
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** The indices summary is cached at the key 'market:indices_summary' (line 215-217). This is a global key shared across all users. When the cache is populated, it is populated using the credentials of whichever user happened to make the first request. If that user's token is subsequently invalidated, cache hits will return stale data but the key lookup appears to succeed (cache HIT). The 2-second TTL mitigates staleness but does not eliminate it.
- **Impact:** Minor: all users see the same cached index prices regardless of which client fetched them. This is actually acceptable for public market data. However, if the fetching user's token is from the shared paper-user fallback (get_data_client bug above), the cache may be populated with potentially wrong exchange/segment mappings.
- **Fix:** Low priority given the 2 s TTL, but document that this is intentionally a shared cache. Fix the get_data_client credential-sharing issue first.

### update_settings allows overwriting execution_mode in the settings collection AND the users collection separately — dual source of truth
- **Category:** data-integrity
- **Location:** `backend/routes/settings_routes.py` : 53-78
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** update_settings() (line 53) accepts execution_mode in data, writes it to the settings collection via upsert_settings (line 70), AND separately writes to the users collection via update_user_field (line 76). The dedicated update_execution_mode endpoint (line 81) does both updates. get_settings() (line 39) reads execution_mode from the users collection and injects it into the settings response. get_user_execution_mode() in trade_routes.py (line 57) reads from settings first, then from users. If these two writes get out of sync (partial failure, concurrent update), the execution mode seen by the trade routing layer differs from what the settings API returns.
- **Impact:** A user who is in PAPER mode in the settings collection but LIVE in the users collection (or vice versa) would receive inconsistent responses. More critically, trade execution would use a different mode than what the user configured.
- **Fix:** Treat the users.execution_mode field as the single source of truth. Remove execution_mode from the settings collection entirely. The settings GET endpoint should always read from users. update_settings should only update users.execution_mode, not the settings collection.

### scheduler_service.start() is only called in __main__ block — the direction scheduler has no guaranteed start path in production
- **Category:** realtime
- **Location:** `backend/app.py` : 133-140
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** scheduler_service.start() (line 138) is only called inside 'if __name__ == "__main__":'. When Flask is deployed via gunicorn or another WSGI server (the correct production method), __main__ is never executed. The scheduler threads never start. The direction scheduler and candle sync scheduler are never launched. All real-time data that depends on these schedulers (cached LTP, direction signals, candle updates) will never be refreshed.
- **Impact:** In production deployment: direction engine returns stale cached values (or falls back to on-demand calculation from stale MongoDB candles). Candle data is never updated. The system effectively operates on static data.
- **Fix:** Move scheduler startup into create_app() using a Flask application context startup hook: with app.app_context(): scheduler_service.start(). Guard against double-start in multi-worker scenarios using a Redis lock or by running schedulers in a separate dedicated process.

### _parse_ohlc_string uses naive split(':') that breaks on price values with colons or OHLC-key ordering changes
- **Category:** accuracy
- **Location:** `backend/services/groww_client.py` : 168-189
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** Line 184 does `k, v = part.split(':')` with no maxsplit. If Groww's API ever returns a timestamp or non-standard value with a colon (e.g., an ISO time string), this raises ValueError and the whole OHLC parses to zeros. It also assumes fixed key names ('open','high','low','close') and no validation of parsed float values.
- **Impact:** Silent data corruption: any malformed OHLC string returns {open:0, high:0, low:0, close:0}. Downstream strategy logic using these zeros will generate garbage signals.
- **Fix:** Use `part.split(':', 1)` (maxsplit=1) to handle values with colons. Add a validation step: check all four keys are present and values are > 0. Fall back to querying get_quote individually on parse failure.

### is_market_open() uses '<=' for market_close check - includes the 15:30 minute bar
- **Category:** accuracy
- **Location:** `backend/utils/time_utils.py` : 28
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** return market_open <= current_time <= market_close returns True when current_time == 15:30:xx. NSE/BSE close at 15:30:00 and no new orders are accepted. The heartbeat job and sync job will attempt LTP polls and candle syncs during the closing auction period, and strategies will continue evaluating with stale 15:30 data.
- **Impact:** Strategies can fire signals at/after market close. For scalping this is particularly dangerous as liquidity is zero and spreads are wide during the closing auction.
- **Fix:** Change to `market_open <= current_time < market_close` (strict less-than at close). Add a separate is_auto_exit_window check for 15:25 to 15:30 to force-close positions.

### TimeframeAggregator in-process cache (self.cache) grows unbounded and is never cleared
- **Category:** performance
- **Location:** `backend/analysis/timeframe_aggregator.py` : 34
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** self.cache is a dict that stores full DataFrames per symbol per interval. aggregate_all updates it every time it is called (direction_scheduler calls it 3 * 60 = 180 times/minute). Although there are only 3 symbols, each DataFrame can hold thousands of rows. clear_cache is never called anywhere in the scheduler or direction scheduler code paths.
- **Impact:** Memory grows steadily with each aggregation call. Over a full trading day (6.25 hours), the cache holds 3 symbols * 5 intervals * up to 50,000 rows each. At ~200 bytes/row this is ~150 MB of redundant DataFrames that are never read from the cache (the cache getter is never called in direction_scheduler).
- **Fix:** Either stop using the instance cache in aggregate_all (return only, don't store), or call clear_cache(symbol) after each direction update cycle. Since the direction_scheduler never calls get_cached(), the cache is write-only and can be removed entirely.

### reconcile_orders_job has no market-open guard and runs every minute including off-hours
- **Category:** risk
- **Location:** `backend/services/scheduler.py` : 266-288
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** reconcile_orders_job has no is_market_open() guard. It iterates all LIVE-mode settings and calls get_positions() every minute, 24/7. Groww API calls outside market hours may return errors or stale data, and the reconcile_positions logic in the trading engine may misinterpret zero-position responses as closed trades.
- **Impact:** Off-hours reconciliation could incorrectly close OPEN trade records if Groww returns an empty position list after settlement. Unnecessary API calls 24 hours a day.
- **Fix:** Add `if not is_market_open(): return` at the top of reconcile_orders_job. For critical position tracking run it only during 09:15-15:30 IST on weekdays.

### Telegram _send_message is synchronous and called in critical trading paths - blocks event loop under failure
- **Category:** realtime
- **Location:** `backend/services/telegram_alert.py` : 39-55
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** requests.post with a 10s timeout is called synchronously inside send_entry_alert and send_exit_alert, which are invoked during trade execution flows. If Telegram's API is slow or unreachable, the trade execution thread blocks for up to 10 seconds. With multiple simultaneous trades this compounds.
- **Impact:** Trade entry/exit can be delayed by up to 10 seconds waiting for Telegram acknowledgment. In scalping, 10 seconds of delay on a stop-loss trigger can cause significant additional loss.
- **Fix:** Send all Telegram messages in a background thread: use threading.Thread(target=_send_message, daemon=True).start() or a simple queue with a dedicated sender thread. Never block trade-critical code paths on external notification APIs.

### test_connection in TelegramAlert mutates self.bot_token / self.chat_id non-atomically under concurrent access
- **Category:** correctness
- **Location:** `backend/services/telegram_alert.py` : 157-186
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** test_connection temporarily replaces self.bot_token, self.chat_id, and self.base_url with test values, calls _send_message, then restores originals. If another thread calls send_entry_alert or send_kill_switch_alert between the override and restore (lines 163-178), it uses the test credentials and sends the alert to the wrong chat.
- **Impact:** Critical trade alerts (entry, exit, kill-switch) can be silently sent to a test chat_id and lost, or the real trade's notification is dropped entirely.
- **Fix:** Create a temporary TelegramAlert instance for the test instead of mutating the singleton: `TelegramAlert(bot_token, chat_id).test_connection()`. Remove all instance-state mutation from test_connection.

### symbol_map in market_heartbeat_job hardcodes 'NIFTY 50' -> 'NIFTY' but Groww may return 'NIFTY50' or other variants
- **Category:** accuracy
- **Location:** `backend/services/scheduler.py` : 150-155
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** The symbol_map at line 150 only maps 'NIFTY 50' and 'NIFTY BANK'. If Groww returns 'NIFTY50', 'NIFTY_50', or any other variant, the symbol falls through unmapped. The price would be cached under 'NIFTY50' or 'NSE_NIFTY 50' etc., while direction_scheduler and trading engine look up 'NIFTY'. redis_client.get_cached_ltp('NIFTY') returns None.
- **Impact:** Heartbeat successfully fetches NIFTY price but caches it under a wrong key. The direction engine and trading engine see ltp=None for NIFTY and skip analysis. This is a silent failure with no log entry.
- **Fix:** Consolidate symbol normalization into a shared utility function used by both the heartbeat, candle_service.INDEX_MAPPING, and direction_scheduler. Log a warning for any unmapped symbol returned by the API.

### get_today_trades uses datetime.utcnow() for 'today' boundary - trades entered after 5:30 AM IST are missed
- **Category:** accuracy
- **Location:** `backend/database/mongodb.py` : 256-259
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** get_today_trades filters created_at >= today_start where today_start is datetime.utcnow() with hour=0, minute=0. This sets the boundary at 00:00 UTC which is 05:30 IST. Trades created between 00:00 IST and 05:30 IST (which should belong to yesterday) are incorrectly included, and trades created before 05:30 IST for the current day are missed. The daily summary (scheduler.py:320) uses this to calculate P&L.
- **Impact:** Daily P&L summary and win-rate reporting are incorrect. The daily reset at 06:05 IST (scheduler.py:299) runs after the 05:30 UTC cutoff is applied, creating a gap where a few records are in a limbo state.
- **Fix:** Use IST midnight as the day boundary: `today_start = datetime.now(IST).replace(hour=0,minute=0,second=0,microsecond=0)` and store created_at as IST-aware datetime, or apply a UTC offset correction: `today_start = datetime.utcnow().replace(hour=0,minute=0,second=0) - timedelta(hours=5, minutes=30)`.

### candle_service.py uses datetime.fromtimestamp (local system time) not IST for 'datetime' field
- **Category:** accuracy
- **Location:** `backend/services/candle_service.py` : 106
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** Line 106: 'datetime': datetime.fromtimestamp(c[0]).isoformat() uses the OS local timezone (likely UTC or Windows local time on the developer machine, Windows 11 as per env). If the server runs in UTC, the 'datetime' field stored in MongoDB for a 09:15 IST candle will read '03:45:00' (UTC). timeframe_aggregator.py:67 then tries to parse this as UTC and convert to IST, but the initial parsing path at scheduler.py:216 uses pd.to_datetime without utc=True, so the timezone conversion is absent.
- **Impact:** All stored candle datetime strings are ambiguous (no timezone info). The aggregation pipeline may produce candles with wrong bar boundaries (e.g., a 5-min bar starting at 03:45 UTC instead of 09:15 IST), corrupting all higher-timeframe signals.
- **Fix:** Store datetime as IST explicitly: `datetime.fromtimestamp(c[0], tz=pytz.timezone('Asia/Kolkata')).isoformat()`. Alternatively store only the epoch timestamp and always derive display datetime from timestamp at read time.

### No market holiday awareness in is_market_open() - system runs on exchange holidays
- **Category:** accuracy
- **Location:** `backend/utils/time_utils.py` : 16-28
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** is_market_open() only checks weekday and time range. NSE/BSE have ~15 trading holidays per year. On holidays the market is closed but is_market_open() returns True (e.g., Republic Day, Diwali Muhurat trading has special timings). All jobs run, API calls are made, and the returned empty candle data triggers the 'API down' error path.
- **Impact:** On exchange holidays, the system wastes all API quota, potentially causes erroneous 'API failure' alerts, and may attempt order reconciliation on a closed exchange. The empty-data guard in _execute_sync prevents data deletion, but the repeated failures pollute logs.
- **Fix:** Maintain a hardcoded or configurable exchange holiday list (update annually). Add a holiday check in is_market_open(). For Muhurat trading (special evening session), store it as a config override.

### get_historical_candles in groww_client.py maps 'NIFTY' to 'NIFTY 50' but candle_service.py's INDEX_MAPPING maps 'NIFTY' back to 'NIFTY' - inconsistent symbol transformation
- **Category:** accuracy
- **Location:** `backend/services/candle_service.py` : 12-21
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** groww_client.py:383-387 maps 'NIFTY' -> 'NIFTY 50' for the API call. candle_service.py:64 uses its own INDEX_MAPPING which maps 'NIFTY' -> 'NIFTY' (identity). Since CandleService makes its own independent HTTP call, it sends 'NIFTY' to the API. The actual correct Groww symbol is 'NIFTY 50' for the index. If Groww's API requires 'NIFTY 50', candle_service fetches will fail or return empty data silently (line 96: prints warning and returns []).
- **Impact:** Candle syncs for NIFTY may return empty, causing the system to fall back to stale data. All 1m NIFTY candles could be missing if Groww requires the 'NIFTY 50' spelling.
- **Fix:** Consolidate all symbol mapping into a single utility function shared by both GrowwClient and CandleService. INDEX_MAPPING in candle_service.py should output 'NIFTY 50' for 'NIFTY', not 'NIFTY'.

### No max_instances set on reconcile_orders_job - overlapping executions possible
- **Category:** risk
- **Location:** `backend/services/scheduler.py` : 73-79
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** reconcile_orders_job is added without max_instances=1 (line 74-79). If a previous reconciliation is still running (e.g., Groww API is slow), APScheduler will launch a second instance simultaneously. Two concurrent reconciliation runs can each call engine.reconcile_positions() with the same broker data, potentially double-closing or double-updating trade records.
- **Impact:** Race condition in position reconciliation: the same trade could be updated twice with conflicting exit data, or a trade could be incorrectly marked as closed by both concurrent instances.
- **Fix:** Add max_instances=1 to the reconcile_orders_job add_job call, consistent with how heartbeat and sync jobs are configured.

### market.store.ts fetchIndices does not polling — Dashboard indices are stale after initial manual fetch
- **Category:** realtime
- **Location:** `frontend/src/pages/Dashboard.tsx` : 264-280
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** fetchIndices is only called in handleRefresh (Dashboard.tsx:268), which requires manual user action. The market overview grid showing NIFTY/BANKNIFTY/SENSEX prices therefore displays snapshot data from the time the page loaded or was last manually refreshed. config.MARKET_POLL_INTERVAL = 5 s is defined but not used for indices polling.
- **Impact:** Index prices shown in the Market Overview panel are stale. On a scalping dashboard this is the primary reference price. An outdated index price can mislead the user about current ATM strike and directional conviction.
- **Fix:** Add a setInterval polling fetchIndices() at config.MARKET_POLL_INTERVAL (5 s) inside a Dashboard useEffect, analogous to the direction polling at line 248-256.

### formatDateTimeIST naive UTC normalization appends 'Z' to already-UTC strings — double-UTC if backend sends ISO with 'Z'
- **Category:** accuracy
- **Location:** `frontend/src/pages/Trades.tsx` : 15-29
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** formatDateTimeIST at line 19-21 appends 'Z' if the string does not already end in 'Z' or contain '+'. If the backend sends a naive datetime string like '2025-06-07T09:30:00' (no timezone, but actually UTC), appending 'Z' is correct. However if the backend occasionally sends 'IST' timestamps as '2025-06-07T09:30:00+05:30', the function's condition (!dateString.includes('+')) would append 'Z' making it '2025-06-07T09:30:00+05:30Z' which is an invalid ISO string causing new Date() to return Invalid Date.
- **Impact:** Trade timestamps would display as 'Invalid Date' for any IST-aware backend timestamps, destroying time audit trail in the trade history table.
- **Fix:** Use a proper timezone-aware parse: if the string contains '+' treat it as already timezone-aware, do not mutate. Only append 'Z' when there is neither a 'Z' suffix nor a '+HH:MM' offset. Also validate the resulting Date before calling Intl.DateTimeFormat.

### Trades.tsx hard-coded .toFixed(2) on trade.stop_loss and trade.target without null check — runtime TypeError on open trades missing SL/Target
- **Category:** correctness
- **Location:** `frontend/src/pages/Trades.tsx` : 407-408
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** Trades.tsx lines 407 and 408: trade.stop_loss.toFixed(2) and trade.target.toFixed(2) are called directly with no null/undefined guard. If an open trade has no SL or Target set (possible when placed manually without SL, or if the backend returns null for a partially filled order), this throws 'Cannot read properties of undefined (reading toFixed)' and crashes the active positions table entirely, rendering no rows.
- **Impact:** A single trade without SL/Target crashes the entire positions table. The user cannot see any active trades and has no UI to exit them, which is a severe risk-control failure during live trading.
- **Fix:** Use optional chaining: trade.stop_loss?.toFixed(2) ?? '-' and trade.target?.toFixed(2) ?? '-'. Alternatively normalize at the store level to ensure stop_loss and target are always numbers (defaulting to 0) so toFixed never throws.

### Dashboard active-trade P&L uses wrong multiplier for SELL side — always positive for short options
- **Category:** accuracy
- **Location:** `frontend/src/pages/Dashboard.tsx` : 519
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** Dashboard.tsx line 519: pnl = (currentPrice - trade.entry_price) * trade.quantity * (trade.side === 'BUY' ? 1 : -1). For a SELL trade (sold option), P&L should be: (entry_price - currentPrice) * quantity. The formula (currentPrice - entry) * qty * -1 = (entry - currentPrice) * qty, which is correct when currentPrice > entry (profitable short). However 'side' on the Trade type can also be 'SELL' coming from a backend field named 'transaction_type' (not 'side'). Trades.tsx line 456 acknowledges this: const side = trade.side || trade.transaction_type. Dashboard.tsx does not do this normalization, so if trade.side is undefined but trade.transaction_type is 'SELL', the formula treats it as a BUY and inverts the P&L sign.
- **Impact:** Short option trades (option selling strategies) would show opposite P&L sign. A profitable short trade shows as a loss and vice versa on the Dashboard.
- **Fix:** Apply the same normalization as Trades.tsx:456 — const side = trade.side || trade.transaction_type || 'BUY' — before the P&L calculation in Dashboard.tsx:519 and wherever the pattern appears.

### Strategy page fires real-money execute-now without checking kill switch or market hours
- **Category:** risk
- **Location:** `frontend/src/pages/Strategy.tsx` : 314-328
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** handleExecuteNow calls executeStrategy() without first verifying settings.kill_switch or isMarketOpen(). The kill switch is displayed on the Dashboard as a warning banner but the Strategy page does not read the UIStore settings at all (no useUIStore call for settings). A user with kill switch enabled can still click 'Buy CE' / 'Buy PE' buttons and fire a live order. Similarly, orders can be attempted outside market hours.
- **Impact:** Kill switch bypass: the primary trading halt mechanism is circumventable from the Strategy page. In live mode this would result in unintended real-money orders.
- **Fix:** Add: const { settings } = useUIStore(); and in handleExecuteNow, add: if (settings?.kill_switch) { addToast('error', 'Kill switch is active'); return; } and optionally if (!isMarketOpen()) { addToast('warning', 'Market is closed'); return; }. Apply same guard to handleToggle for strategy start.

### Duplicate formatCurrency implementations — different decimal behavior for same price data
- **Category:** accuracy
- **Location:** `frontend/src/utils/formatter.ts` : 4-11
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** Two formatCurrency functions exist: one in utils/formatter.ts (line 4, default 2 decimals) and one in utils/index.ts (line 2, default 0 decimals). Components import from different paths: Dashboard.tsx imports from utils/formatter, Charts.tsx imports from utils/indicators. When both render on screen simultaneously, prices like ₹24,500 appear as '₹24,500.00' in some places and '₹24,500' in others. Signals.tsx line 116 uses a raw template literal ₹{data.current_price?.toLocaleString()} with no decimal control at all.
- **Impact:** Price values for the same underlying are displayed with inconsistent decimal places across different pages and components. For NIFTY options where cents matter (e.g., ₹24.50 vs ₹24), rounding differences visually misrepresent precision.
- **Fix:** Delete one of the two formatCurrency implementations. Consolidate to utils/formatter.ts (the more complete version with ₹ prefix and signed negative). Update all imports. Replace raw toLocaleString() usages in Signals.tsx line 116 with the canonical formatCurrency.

### isLoading not set during fetchActiveTrades and fetchPositions — no loading indicator while polling
- **Category:** correctness
- **Location:** `frontend/src/store/trade.store.ts` : 59-75
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** fetchActiveTrades (line 59-68) and fetchPositions (line 70-77) do not touch isLoading. Only fetchTrades sets isLoading (line 48). The 10 s poll on Trades.tsx calls fetchActiveTrades + fetchPositions + fetchDailyPnl — all without loading state. This is actually correct design (background polling should not flash a spinner) but exitTrade (line 150) also skips isLoading, so the exit button has no local feedback during the API call other than the per-button exiting local state. The inconsistency means the global error state for exitTrade is silently swallowed if it conflicts with the next poll.
- **Impact:** Minor UX issue, but more critically: exitTrade errors are set on store.error but the Trades page does not render store.error anywhere — errors are silently lost unless the notifyAction toast fires.
- **Fix:** Ensure exitTrade errors are surfaced via addToast in the Trades.tsx catch block (currently uses notifyAction which does toast + Telegram, which is fine). Alternatively, read useTradeStore().error in Trades.tsx and display it as a banner.

### Charts useEffect for rendering depends on [candles, decision, customLines, ...] — full re-render including indicator recalculation on every 5 s poll
- **Category:** performance
- **Location:** `frontend/src/pages/Charts.tsx` : 174-256
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** The giant render useEffect at Charts.tsx:174 has dependency array [candles, activeIndicator, showLevels, showAIOverlay, decision, customLines]. Every 5 s, new candles arrive → setCandles → triggers full re-render. This re-render includes: (A) setting all candle data via setData (full O(n) series replacement); (B) removing and re-adding all indicator series (EMA/SMA/Bollinger full recalculation O(n)); (C) removing and re-adding all price lines. For 300 candles and EMA-20, this is ~300 × 2 indicator iterations every 5 s. Also, every call to setData replaces the entire candle series — lightweight-charts supports update() for incremental updates.
- **Impact:** Performance degradation over long sessions. 300 candles × 5 s refresh = 60 full O(n) indicator recalculations per minute. On mobile or low-end hardware this can cause visible frame drops. The chart also flickers momentarily when the series is cleared and re-added.
- **Fix:** Use candleSeriesRef.current.update(latestCandle) for incremental updates instead of setData for the full series. Separate indicator recalculation into a debounced useMemo outside the chart render effect. Only recalculate when candles.length changes or activeIndicator changes, not on every single candle update.

### analyzeStrategy overwrites shared `decision` field without updating `decisions` map
- **Category:** correctness
- **Location:** `frontend/src/store/strategy.store.ts` : 93-102
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** analyzeStrategy (line 93) sets `decision` globally but does NOT update `decisions[symbol]`. If Signals.tsx is mounted and reads `decisions[selectedSymbol] || decision` (line 41), and analyzeStrategy is called for strategy S with symbol X, the global `decision` changes to X's data while `decisions[selectedSymbol]` may still hold stale data for a different symbol. The Signals page fallback to `decision` will display X's analysis regardless of what symbol is selected.
- **Impact:** Signals page can show analysis for the wrong symbol without any indication. A user watching BANKNIFTY signals could see a NIFTY analysis result after someone clicks 'Analyze' on a NIFTY strategy.
- **Fix:** In analyzeStrategy, also update the decisions map: set(state => ({ decision, decisions: { ...state.decisions, [strategy.index]: decision }, isAnalyzing: false })). Requires knowing the strategy's symbol, which should be passed to or fetched inside analyzeStrategy.

### config SIGNAL_THRESHOLDS weakBullish and weakBearish share the same value 0.45 — bearish threshold not lower than neutral
- **Category:** accuracy
- **Location:** `frontend/src/config/index.ts` : 74-81
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** SIGNAL_THRESHOLDS: { strongBullish: 0.7, weakBullish: 0.55, neutral: 0.45, weakBearish: 0.45, strongBearish: 0.3 }. weakBearish is set to 0.45, identical to neutral. This means any confidence value in [0.45, 0.55) is simultaneously 'neutral' and 'weakBearish' with no disambiguating logic. Any frontend code that iterates these thresholds to classify a confidence value will have ambiguous results in this range.
- **Impact:** If any component uses these thresholds directly for signal classification, confidence values around 45-55% will be misclassified. Although no page currently does a direct threshold comparison (they use the backend-provided signal string), the thresholds are misleading and incorrect for future use.
- **Fix:** Fix the threshold values to form a proper monotonic scale: e.g. { strongBullish: 0.70, weakBullish: 0.55, neutral: 0.50, weakBearish: 0.45, strongBearish: 0.30 }. Ensure weakBearish < neutral.

### Auth token stored as plaintext in localStorage — XSS exposure of trading credentials
- **Category:** security
- **Location:** `frontend/src/api/axios.ts` : 15
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** The JWT access token is stored in localStorage (axios.ts:15, auth.store.ts:45). localStorage is synchronously accessible to any JavaScript running in the page origin, including injected scripts from XSS vulnerabilities in npm dependencies. For a live-trading application where the token authorizes real-money order placement, this is a meaningful attack vector.
- **Impact:** If any XSS vulnerability exists (in any npm dependency, or injected ads/analytics), an attacker can steal the token and place or exit trades programmatically.
- **Fix:** Store tokens in httpOnly cookies set by the backend. If cookies are not feasible, store the token in memory only (module-level variable) and re-obtain it on page refresh via a silent httpOnly cookie-based session check. At minimum, ensure Content-Security-Policy headers are set on the backend to restrict XSS vectors.

### Data-length contract mismatch: engine accepts >=20 candles but decision_engine requires >=50 and returns empty signal
- **Category:** correctness
- **Location:** `backend/services/trading_engine.py + backend/analysis/decision_engine.py` : trading_engine.py:135; decision_engine.py:70
- **Subsystem:** Groww trading-engine wiring, signal/candle data consumption, and dead-code audit (backend/)
- **Detail:** evaluate_strategies proceeds when `len(candles) >= 20` (L135) and then calls get_signal(df). decision_engine.analyze() returns _empty_result('Insufficient data') with signal=None whenever `len(df) < 50` (L70). For 20-49 candles the engine does work building the dataframe and calling analysis, but always gets signal=None (no trade). Wasted work and a hidden no-signal window after market open / sparse-data symbols.
- **Impact:** Misleading: strategies appear active and evaluated but can never fire while candle count is 20-49. Confusing to debug; the 'reason' (insufficient data) is swallowed because evaluate_strategies ignores the error field.
- **Fix:** Align the threshold (use >=50 in evaluate_strategies) and log when signal is None due to insufficient data.

### quick-trade resolves symbol via engine but bypasses engine for order placement and SL/target computation
- **Category:** correctness
- **Location:** `backend/routes/trade_routes.py` : 556-635
- **Subsystem:** Groww trading-engine wiring, signal/candle data consumption, and dead-code audit (backend/)
- **Detail:** quick_trade uses engine.resolve_dynamic_symbol (L563) but then constructs the broker and places the order directly (L579-595) and writes trade_data manually (L599-621) with `stop_loss`/`target` taken raw from the strategy as absolute values (L616-618), whereas execute_entry computes SL/target via risk_manager.calculate_sl_target from the fill price and option_type (trading_engine.py:360-371). The two paths produce inconsistent SL/target semantics (points-from-entry vs absolute) and quick-trade does not send a telegram entry alert or set trailing_sl_value.
- **Impact:** Trades opened via quick-trade have different (likely wrong) SL/target values than engine-opened trades, and monitor_active_trades (which expects current_sl/target as absolute prices) may then exit them incorrectly or never.
- **Fix:** Route quick-trade through engine.execute_entry (passing a manual signal) so SL/target, mode handling, trade recording, and alerts are computed in one place.

### reconcile_positions is a no-op stub but scheduler calls it every minute as a 'safety net'
- **Category:** data-integrity
- **Location:** `backend/services/trading_engine.py + backend/services/scheduler.py` : trading_engine.py:482-485; scheduler.py:266-285
- **Subsystem:** Groww trading-engine wiring, signal/candle data consumption, and dead-code audit (backend/)
- **Detail:** reconcile_orders_job (every 1 min) fetches live broker positions and calls engine.reconcile_positions(broker_pos['data']) (scheduler.py:284-285), but reconcile_positions is `pass` with a TODO (trading_engine.py:484). The job's docstring claims it 'syncs Broker <-> DB'.
- **Impact:** DB and broker can drift with no reconciliation: orders filled/rejected/closed at the broker outside the app, partial fills, or manual broker actions are never reflected. The safety net advertised in code/comments does not exist.
- **Fix:** Implement reconciliation (match broker open positions against db OPEN trades, close orphaned DB trades, flag unknown broker positions) or remove the misleading job + docstring until implemented.

### Redis cross-process direction stored as Python repr str(result), not JSON — unreadable, dead cache
- **Category:** correctness
- **Location:** `backend/services/direction_scheduler.py; backend/database/redis_client.py` : direction_scheduler.py:139; redis_client.py:54-57
- **Subsystem:** Real-time price/candle data pipeline (Groww API -> backend cache/Redis/Mongo -> decision & direction engines -> Flask routes -> React/Zustand stores -> chart UI)
- **Detail:** direction:{symbol} is written as str(result) (Python dict repr) with ex=10. Nothing ever reads it, and if it were read it cannot be json.loads()'d (single quotes, True/False). The comment claims 'cross-process access' but the route reads the in-process dict instead, so under a multi-worker/gunicorn deployment the web workers would have an EMPTY in-process cache and the Redis copy is unusable.
- **Impact:** With more than one Flask worker process (the documented production pattern), the direction scheduler runs in one process while API requests hit other workers whose direction_cache is empty, triggering the slow on-demand fallback (which uses 5m-as-1m, see below) or returning neutral. Real-time direction effectively breaks in production.
- **Fix:** Serialize with json.dumps(result) and read with json.loads in market_routes; make the route prefer Redis over the in-process dict so any worker can serve it. Better: run the scheduler as a single dedicated process and have all workers read Redis only.

### On-demand direction fallback substitutes 5m candles for 1m, silently degrading the model
- **Category:** accuracy
- **Location:** `backend/routes/market_routes.py; backend/services/direction_scheduler.py` : market_routes.py:94,170; direction_scheduler.py:105-107
- **Subsystem:** Real-time price/candle data pipeline (Groww API -> backend cache/Redis/Mongo -> decision & direction engines -> Flask routes -> React/Zustand stores -> chart UI)
- **Detail:** When 1m data is insufficient, both the route fallback and the scheduler fallback set df_1m = df_5m (or copy) and even df_15m = df_5m. The MarketDirectionEngine then computes '1m momentum' (EMA9/21, RSI slope, candle strength) on 5m bars and '15m trend' possibly on 5m bars, while still labeling them as 1m/15m components with full weight.
- **Impact:** Momentum and trend components are computed on the wrong timeframe but weighted as if correct (20%+35%), producing a plausible-looking but wrong strength/direction. No flag tells the user the model is degraded.
- **Fix:** If 1m data is unavailable, either return an explicit reduced-confidence/degraded flag or skip the affected components and renormalize weights, rather than silently feeding 5m bars into 1m/15m slots.

### Strategy trade monitoring matches index by substring — NIFTY heartbeat manages BANKNIFTY trades
- **Category:** correctness
- **Location:** `backend/services/trading_engine.py` : trading_engine.py:183
- **Subsystem:** Real-time price/candle data pipeline (Groww API -> backend cache/Redis/Mongo -> decision & direction engines -> Flask routes -> React/Zustand stores -> chart UI)
- **Detail:** monitor_active_trades skips trades unless `index_symbol not in trade.get('symbol','')`. Since the heartbeat loops indices including 'NIFTY' and 'BANKNIFTY', the string 'NIFTY' is a substring of 'BANKNIFTY' option symbols, so the NIFTY iteration also evaluates BANKNIFTY positions (and FINNIFTY). evaluate_strategies has a similar coupling via the index field.
- **Impact:** Trades can be monitored/exited under the wrong index's price-tick iteration timing, and option LTP fetch + SL/target logic may run on mismatched cadence. Subtle double-processing and mis-timed exits.
- **Fix:** Match on the resolved underlying explicitly (store underlying on the trade and compare equality) rather than substring containment; guard 'NIFTY' vs 'BANKNIFTY'/'FINNIFTY'.

### All-REST polling with layered TTLs yields 10-15s worst-case LTP staleness and price-source disagreement
- **Category:** realtime
- **Location:** `backend/services/scheduler.py; backend/routes/market_routes.py; frontend/src/config/index.ts` : scheduler.py:55-61,163; market_routes.py:215-252,261-294; config/index.ts:8
- **Subsystem:** Real-time price/candle data pipeline (Groww API -> backend cache/Redis/Mongo -> decision & direction engines -> Flask routes -> React/Zustand stores -> chart UI)
- **Detail:** LTP path: 5s heartbeat -> Redis ltp ex=10 -> frontend 5s poll. Indices path: get_quote cached 2s in Redis under a different key (market:indices_summary) -> frontend 5s poll. The direction engine reads ltp:{symbol} while the chart price comes from candles and the header price from indices_summary, so three surfaces can show three different prices for the same instrument at the same instant. No websocket streaming despite the 'LIVE' badges (DirectionPanel.tsx:58).
- **Impact:** Worst-case index price on screen is ~10-15s old; different panels disagree; the 1s direction recompute is false precision over 5-60s-stale inputs. For an intraday options system this is a material real-time-accuracy gap.
- **Fix:** Adopt Groww's live websocket/streaming feed for LTP (and per-symbol last-tick) instead of 5s REST; push ticks to the frontend via SSE/WebSocket. If staying REST: shorten ltp TTL to ~heartbeat interval, unify all surfaces to read the same Redis LTP key, and stamp every payload with a server as_of time so the UI can show age.

### Encryption.decrypt silently returns empty string on failure (masks tampering/key mismatch)
- **Category:** correctness
- **Location:** `backend/utils/encryption.py` : 27-35
- **Subsystem:** Groww Trading Platform - Authentication, Secrets Management & Order Execution
- **Detail:** decrypt() catches all exceptions and returns '' on any failure (invalid token, wrong key, tampering). _load_token in groww_client.py:56 then sets access_token to '' which is falsy, leading to requests with no Authorization header and a 401, rather than surfacing a key-rotation or data-corruption problem.
- **Impact:** Silent failures hide ENCRYPTION_KEY rotation/migration errors and potential ciphertext tampering, complicating incident detection and producing confusing 'token expired' errors instead of actionable alerts.
- **Fix:** Log a warning/error with context (without leaking ciphertext) on decryption failure and distinguish 'no credential stored' from 'decryption failed'. Surface a specific error to the caller so credential re-entry or key issues are detected.

### Sensitive token-generation flow logs to stdout and reflects broker error strings
- **Category:** security
- **Location:** `backend/routes/auth_routes.py` : 269, 282, 288, 296
- **Subsystem:** Groww Trading Platform - Authentication, Secrets Management & Order Execution
- **Detail:** update_groww_credentials prints diagnostic messages including user_id and token-generation outcomes to stdout (lines 269, 282, 296) and returns the raw broker error message to the client (lines 290-291, 298). While the token itself is not printed, verbose broker errors and user identifiers in logs aid reconnaissance, and unstructured print logging of an auth flow is poor practice for a money-handling system.
- **Impact:** Information disclosure to clients and to anyone with log access; aids credential-guessing and account enumeration. Lack of structured audit logging hinders forensic response after a credential compromise.
- **Fix:** Replace print() with structured logging at appropriate levels; do not echo raw broker error strings to clients (return a generic message). Add an audit log of credential updates (user, time, IP, success/failure) without sensitive values.

### Redis configured without TLS (REDIS_SSL=false) for a public cloud endpoint
- **Category:** security
- **Location:** `backend/.env` : 14-17
- **Subsystem:** Groww Trading Platform - Authentication, Secrets Management & Order Execution
- **Detail:** REDIS_HOST points to a public Redis Cloud endpoint but REDIS_SSL=false (.env:17), so the password (line 16) and all cached data (LTPs, trade locks) traverse the network in cleartext. redis_client.py:28 honors this flag.
- **Impact:** On-path attackers can sniff the Redis password and cached trading data, then connect directly to manipulate locks/cache (compounding the fail-open lock issue) and read trading activity.
- **Fix:** Enable TLS (set REDIS_SSL=true and use the rediss endpoint) for any non-localhost Redis. Combine with IP allowlisting and password rotation.

### Volume 'confirmation' direction is assigned to whichever side is already winning, not to actual flow
- **Category:** correctness
- **Location:** `backend/analysis/decision_engine.py` : 119-124,266-269
- **Subsystem:** Groww Decision / Market-Direction Signal Engine
- **Detail:** _analyze_volume returns confirmed=True if recent volume > average AND (OBV or AD-line non-neutral). But in analyze(), the volume weight is then added to whichever of bullish/bearish is already larger (lines 121-124), regardless of whether OBV/AD actually point that way. So volume always reinforces the current leader — it can never contradict price. A high-volume distribution bar that should warn against a long instead boosts the long's confidence.
- **Impact:** Volume becomes a pure confidence amplifier rather than an independent confirmation/contradiction filter, biasing confidence upward and removing volume's protective value.
- **Fix:** Use the actual OBV/AD-line/MFI/force-index direction: only add to bullish_score if flow is bullish, subtract (or veto) if flow contradicts price. Treat divergence (price up, OBV down) as a confidence reducer.

### _analyze_momentum requires only a bare majority of 6 oscillators and normalizes by 6, capping at ~0.67
- **Category:** accuracy
- **Location:** `backend/analysis/decision_engine.py` : 197-219
- **Subsystem:** Groww Decision / Market-Direction Signal Engine
- **Detail:** Score = winning_count / len(key_indicators=6). With 4 of 6 bullish the score is 0.67; even 6/6 gives 1.0 only when every oscillator agrees. There is no use of each indicator's own 'strength' field (the indicators compute calibrated strength 0-1 but it is discarded here). Ties (3-3, or all neutral) collapse to 0.5/NEUTRAL. Because 4 of the 6 (RSI, Stoch, Williams, CCI) are collinear, a single oscillator regime drives the 'majority'.
- **Impact:** Momentum contribution is coarse, ignores signal strength, and is dominated by correlated oscillators, weakening discrimination between strong and marginal setups.
- **Fix:** Aggregate using each indicator's strength weighted by an estimated information coefficient, after de-correlating the oscillator family to one effective vote. Normalize by the number of NON-neutral, de-correlated votes rather than the raw count of 6.

### Direction engine recomputes EMA/RSI from scratch O(n) per second and recomputes RSI in an inner loop
- **Category:** performance
- **Location:** `backend/analysis/market_direction_engine.py` : 418,577-612
- **Subsystem:** Groww Decision / Market-Direction Signal Engine
- **Detail:** _ema and _rsi iterate the full price array in pure Python on every call, _analyze_1m_momentum recomputes RSI from scratch ~5 times in a list comprehension (line 418), and _analyze_15m_trend recomputes a second 50-EMA over close[:-5] for slope (line 301). At 1Hz across 3 indices this is wasteful and, more importantly, the EMA is reseeded from data[0] each call (line 583) so it is a transient-biased EMA, not a stable recursive one — its value depends on how many bars happen to be in the window.
- **Impact:** CPU overhead at 1Hz and, critically, non-stationary EMA values: the same true market state yields different EMA depending on lookback length, undermining reproducibility and the 60/40 thresholds. Conflicts with the stated <1ms HFT-style latency goal.
- **Fix:** Vectorize EMA/RSI (pandas.ewm with adjust=False / Wilder) computed once per new closed bar and cache; only update the live price delta intra-bar. Seed EMA with an SMA of the first `period` bars for stability.

### Symmetrical-triangle / rectangle / doji direction inferred from prior trend creates pro-cyclical bias and trend/structure correlation
- **Category:** accuracy
- **Location:** `backend/analysis/patterns/primary/patterns.py` : 352-366,481-497
- **Subsystem:** Groww Decision / Market-Direction Signal Engine
- **Detail:** Neutral patterns (symmetrical triangle, rectangle) and doji (candlestick/patterns.py:25-27) assign BULLISH/BEARISH purely from the sign of the recent price change. This is just a slow trend proxy, so these 'patterns' are correlated with the MA/EMA trend buckets and with each other, again inflating consensus. They fire a directional vote without an actual breakout confirmation.
- **Impact:** Adds correlated, low-information directional votes that move in lockstep with the trend bucket, further overstating confidence and degrading calibration.
- **Fix:** Keep neutral patterns neutral until an actual breakout (close beyond the boundary on volume) is confirmed; do not assign direction from prior trend. Mark these as continuation-only and exclude from the directional consensus until triggered.

### Pattern score adds a flat +0.3 floor, so a single weak pattern reads as high-conviction
- **Category:** accuracy
- **Location:** `backend/analysis/decision_engine.py` : 191-194
- **Subsystem:** Groww Decision / Market-Direction Signal Engine
- **Detail:** _analyze_patterns returns min(winning_fraction + 0.3, 1.0). With one detected bullish pattern (fraction 1.0) the score is capped at 1.0; with two bullish vs zero bearish it is also high. The +0.3 floor means even a marginal pattern majority is scored >=0.3 above its raw fraction, and the individual pattern 'confidence' fields (0.55-0.85) are ignored — a 0.55-confidence doji counts the same as a 0.85 cup-and-handle.
- **Impact:** Pattern bucket (the highest weight, 0.30) is biased high and ignores per-pattern reliability, so low-quality patterns disproportionately push past the gate.
- **Fix:** Weight by each pattern's own confidence and by historical hit-rate per pattern type; drop the arbitrary +0.3 floor. Penalize conflicting simultaneous patterns rather than netting counts.

### Pivot points and Fibonacci computed from the last single bar / fixed lookback, not the prior session
- **Category:** accuracy
- **Location:** `backend/analysis/support_resistance/indicators.py` : 9-22,25-41
- **Subsystem:** Groww Decision / Market-Direction Signal Engine
- **Detail:** calculate_pivot_points uses high/low/close of only the LAST bar (df['high'].iloc[-1] etc.) rather than the previous trading session's HLC, which is the textbook definition. On intraday 5m data this makes 'pivots' a function of one 5m candle, essentially noise. Fibonacci uses a fixed 50-bar window high/low regardless of swing structure.
- **Impact:** Pivot-point S/R signal is meaningless on intraday data; it contributes a noisy directional vote into the S/R bucket and pollutes the consensus.
- **Fix:** Compute classic pivots from the prior session's (or prior day's) aggregated HLC. Anchor Fibonacci to detected swing highs/lows (you already compute swing points elsewhere) rather than a fixed lookback.

### Direction-engine 60/40 cutoffs plus additive bonuses double-count VWAP and volume
- **Category:** accuracy
- **Location:** `backend/analysis/market_direction_engine.py` : 536-557
- **Subsystem:** Groww Decision / Market-Direction Signal Engine
- **Detail:** weighted_score already includes vwap_score (10%) and volume_score (10%); then lines 550-557 add another +5 for VWAP alignment and +5 for volume confirmation. VWAP and volume thus contribute twice. The 60/40 master cutoffs are fixed and symmetric, ignoring that intraday drift makes UP and DOWN base rates asymmetric.
- **Impact:** VWAP/volume over-weighted relative to design intent; fixed symmetric cutoffs are not calibrated to the instrument's intraday up/down base rate, biasing NEUTRAL vs directional classification.
- **Fix:** Remove the additive bonuses (they are already in the weighted sum) or formally re-derive the weights to include them. Calibrate the UP/DOWN cutoffs from historical strength->forward-return distributions per symbol rather than fixed 60/40.

### No transaction-cost / slippage / R-multiple in the signal layer; confidence not tied to expectancy
- **Category:** risk
- **Location:** `backend/analysis/decision_engine.py` : 126-173
- **Subsystem:** Groww Decision / Market-Direction Signal Engine
- **Detail:** The engine emits a direction and confidence but no expected R-multiple, and confidence is never validated against realized forward returns net of options spread/slippage. trading_engine fires CE/PE whenever confidence>=min_confidence with no edge-after-cost check. Option buying has heavy theta and bid-ask cost, so a 'BULLISH' direction with low expected move is negative-expectancy even when correct on direction.
- **Impact:** High directional accuracy can still lose money after costs; win-rate alone is the wrong objective. Cannot rank setups by expectancy.
- **Fix:** Attach an expected-move / target-vs-cost estimate (use ATR and option spread) and gate on positive net expectancy, not just direction confidence. Calibrate confidence against forward P&L net of modeled costs in the backtester.

### ATR uses SMA of True Range, not Wilder's ATR
- **Category:** accuracy
- **Location:** `backend/analysis/volatility/indicators.py` : 23
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** atr = pd.Series(tr).rolling(period).mean().iloc[-1] is a simple moving average of TR. Standard ATR uses Wilder smoothing. SMA-ATR jumps when a large TR drops out of the window 14 bars later, causing artificial volatility-regime flips.
- **Impact:** ATR%, the LOW/NORMAL/HIGH regime (used in decision_engine volatility scoring and market_regime=VOLATILE) and ATR-derived India-VIX/implied-vol proxies all step-change spuriously. Affects position sizing/regime gating if downstream uses it.
- **Fix:** Use Wilder RMA for ATR. Keep the raw TR available; expose both SMA and Wilder if needed for comparison.

### Hammer/Hanging-Man use identical shape with contradictory and likely-wrong trend tests
- **Category:** accuracy
- **Location:** `backend/analysis/patterns/candlestick/patterns.py` : detect_hammer L110-113; detect_hanging_man L141-143
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** Hammer requires prior_trend>0 where prior_trend = mean(close[-10:-1]) - close[-1] (>0 means prior bars were ABOVE the close, i.e. recent decline — OK-ish). Hanging man requires close[-1] - mean(close[-10:-1]) > 0 (recent rise — OK-ish), but BOTH will frequently both trigger boundary cases, and neither verifies the candle is at the END of the move with a real swing low/high. The mean-vs-last test is a crude trend proxy and both can fire on the same ambiguous bar producing opposing BULLISH/BEARISH signals.
- **Impact:** Conflicting candlestick signals and false reversals; in a 5-min scalper these fire constantly on noise.
- **Fix:** Use a proper trend filter (e.g., slope of an EMA or position vs a moving average over a longer window) and require the candle to mark a local extreme; ensure mutually exclusive conditions.

### Engulfing patterns ignore wick size and body magnitude; bodies can be tiny
- **Category:** accuracy
- **Location:** `backend/analysis/patterns/candlestick/patterns.py` : detect_bullish_engulfing L54; detect_bearish_engulfing L79
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** engulfs only checks body open/close overlap, with no minimum body size relative to range/ATR. A near-doji current candle that marginally engulfs a near-doji previous candle qualifies with confidence 0.72. No requirement that the prior trend exists.
- **Impact:** Many low-quality 'engulfing' signals at 0.72 confidence inflate pattern counts and (once the 'direction' bug is fixed) would push the 30% pattern weight on noise.
- **Fix:** Require current body >= k*ATR and current body meaningfully larger than previous body; add a preceding-trend filter.

### GARCH and implied-vol/India-VIX are fabricated proxies presented as real metrics
- **Category:** accuracy
- **Location:** `backend/analysis/volatility/indicators.py` : calculate_garch L198-220 (mislabeled EWMA, fixed 0.06/0.94); calculate_implied_vol L223-245 (atr_percent*15); calculate_india_vix L287-311 (atr*10+hv)/2
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** GARCH(1,1) is actually a fixed-parameter EWMA, not an estimated GARCH (no omega term, params not fit). implied_vol multiplies ATR% by an arbitrary 15. india_vix is an arbitrary blend, not the real India VIX (the comment even says 'In production, fetch actual India VIX').
- **Impact:** These feed regime/strength outputs and the UI as if they were IV/VIX. For an options scalper, fake IV is dangerous: option pricing/edge depends on real IV term structure, not ATR*15.
- **Fix:** Fetch real India VIX and option-chain IV from the broker feed; label proxies clearly and exclude them from any pricing/edge decision. If keeping GARCH, fit omega/alpha/beta via MLE or rename to EWMA.

### Fibonacci retracement ignores swing direction (always high-to-low from window extremes)
- **Category:** accuracy
- **Location:** `backend/analysis/support_resistance/indicators.py` : 25-41
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** It takes max(high) and min(low) over the lookback irrespective of which came first (uptrend vs downtrend). Retracement levels are direction-dependent; without knowing whether the swing was up or down, the 38.2/61.8 mapping and the BULLISH/BEARISH thresholds at L37-40 are arbitrary.
- **Impact:** Fibonacci signal (part of 15% S/R block, read by decision_engine) is often inverted/meaningless. Also the engine fails to read these levels at all due to the key bug above.
- **Fix:** Determine swing direction from the order of the extreme high vs extreme low indices; compute retracements from the actual swing, and only then map proximity-to-level into a signal.

### Market profile value-area (VAH/VAL) math is wrong
- **Category:** accuracy
- **Location:** `backend/analysis/support_resistance/indicators.py` : 274-299
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** VAL/VAH are taken as searchsorted on a simple cumulative sum of bin TPO at 30%/70% of total (L288-289). The standard 70% value area is built symmetrically OUTWARD from the POC, not as the 30th/70th percentile of an unsorted price-ordered cumulative count. This yields incorrect VAH/VAL.
- **Impact:** VAH/VAL levels and the BULLISH(>VAH)/BEARISH(<VAL) signal are wrong, polluting the S/R block.
- **Fix:** Implement the standard value-area algorithm: start at POC, iteratively add the larger-TPO adjacent bin above/below until 70% of total volume/TPO is enclosed; VAH/VAL are the top/bottom of that range.

### Ichimoku has no forward displacement, no Chikou span, and degrades to tenkan when <26 bars
- **Category:** accuracy
- **Location:** `backend/analysis/support_resistance/indicators.py` : 237-252
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** Senkou A/B are computed at the current bar and compared directly to current price, but real Ichimoku plots the cloud 26 periods AHEAD; price-vs-cloud must compare price to the cloud value projected 26 bars earlier. Chikou span is omitted. Fallbacks (kijun=tenkan when <26 bars, senkou_b=senkou_a when <52) silently produce degenerate clouds.
- **Impact:** The Ichimoku BULLISH/BEARISH (strength 0.75, the highest among S/R) is computed against a non-displaced cloud, so cloud breakouts are mistimed.
- **Fix:** Compute senkou A/B over history and shift forward 26 for the price comparison (compare close to cloud[-26]); add chikou confirmation; require >=52 bars before trusting it.

### Swing levels and order blocks contain look-ahead and recompute every bar
- **Category:** realtime
- **Location:** `backend/analysis/support_resistance/indicators.py` : swing_levels L133-137; order_blocks L218-227 (close[i+1], close[i+2])
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** swing_levels uses centered window (look-ahead). order_blocks references close[i+1] and close[i+2] (future relative to candle i) to classify a block — non-causal — and loops from len-3 so the most recent blocks are unconfirmed.
- **Impact:** Resistance/support and institutional-zone signals shift as future bars arrive; entries/exits anchored to them are unstable.
- **Fix:** Use causal confirmation (only past bars) and lag the most recent zone until confirmed.

### Division-by-zero / NaN gaps remain in several indicators despite 'safe division' claims
- **Category:** correctness
- **Location:** `multiple` : momentum: roc L159 close[-period] index can be out of range if len<period; cci 0.015*mad guarded but mad NaN if <period; volatility: parkinson log(high/low) if low==0 -> -inf (L152); historical_vol log(close) if any close<=0 (L127); evt peak==0 division (L336); SR camarilla diff could be 0 fine; pitchfork denom guarded
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** Several functions assume len(df)>=period (e.g. roc close[-period], momentum close[-2*period]) and will IndexError on short windows; np.log of non-positive prices (possible on bad ticks/zero-volume synthetic bars) yields -inf/NaN that then propagate. These are swallowed by the bare try/except in calculate_all_* and turned into NEUTRAL, silently dropping the indicator.
- **Impact:** On thin/early-session data or a single bad tick, multiple indicators silently vanish (count toward NEUTRAL), skewing the aggregate without any alert. Data-integrity hole.
- **Fix:** Add explicit length guards returning a typed 'insufficient data' result; sanitize OHLC (drop/forward-fill non-positive or zero-range bars) before log/division; log when an indicator errors instead of silently NEUTRAL.

### Full O(n)/O(n^2) recompute of 67 indicators + 24 patterns every 5s contradicts the latency target
- **Category:** performance
- **Location:** `all indicator/pattern files` : e.g. support_resistance volume_profile L112-116 and market_profile L279-283 (nested Python loops), nadaraya_watson volatility L170-172, ADX/OBV/MFI Python loops momentum L70-75,103-105,200-203
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** Pure-Python double loops over 500 bars run on every 5s poll for every index, recomputing everything from scratch with no incremental update or memoization keyed on the last completed bar.
- **Impact:** Unnecessary CPU/latency; scaling to multiple indices or finer intervals will hit the 5s budget. Far from the stated sub-1ms HFT aspiration (though this stack is clearly not true HFT).
- **Fix:** Cache results per (symbol, interval, last_completed_bar_timestamp); only recompute when a bar closes. Vectorize volume/market profile with np.histogram and the Python loops in ADX/OBV/MFI with pandas/numpy.

### Pattern confidence values are hard-coded and never propagated into the weighted decision
- **Category:** accuracy
- **Location:** `decision_engine + all pattern files` : e.g. candlestick confidence 0.55-0.75; harmonic 0.70-0.80; primary 0.62-0.75; decision_engine _analyze_patterns L182-195 uses only counts
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** Each pattern emits a fixed confidence, but the aggregator (even once the direction/signal bug is fixed) uses a raw bullish/bearish COUNT, not confidence or strength, and caps with a flat +0.3. So a high-confidence crab (0.80) counts the same as a marginal doji (0.55).
- **Impact:** Signal quality information is discarded; weak and strong patterns are treated identically, reducing edge.
- **Fix:** Aggregate patterns by summing/averaging confidence per direction (optionally time-decayed and de-duplicated), and feed that into the 30% weight.

### EVT/HV/RV annualize 5-minute returns with sqrt(252), the wrong scaling factor
- **Category:** accuracy
- **Location:** `backend/analysis/volatility/indicators.py` : historical_vol L129; garch L213; realized_vol L318; parkinson L153; volatility_ratio L265-266
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** sqrt(252) annualizes DAILY returns. The data is 5-minute bars (≈75 bars/day for NIFTY, ≈18,750 bars/year). Annualizing 5-min log returns requires sqrt(bars_per_year)≈sqrt(18750), not sqrt(252). Reported HV/RV/GARCH 'annualized %' are therefore understated by ~sqrt(75)≈8.6x.
- **Impact:** All annualized volatility numbers and their LOW/NORMAL/HIGH regimes (e.g. HV<15/<25) are calibrated against wrong magnitudes; the India-VIX proxy that blends these is doubly wrong. Misleads regime gating and any vol-based sizing.
- **Fix:** Use the correct annualization factor for the bar interval (sqrt(periods_per_year)) or compute vol per-bar and document units; recalibrate the LOW/NORMAL/HIGH thresholds accordingly.

### Momentum uses only 6 of 17 indicators; the other 11 computed indicators are discarded
- **Category:** accuracy
- **Location:** `backend/analysis/decision_engine.py` : 201,216,218
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** _analyze_momentum scans only ['rsi','macd','stochastic','adx','williams_r','cci'] (L201) and divides by len(key_indicators)=6, while calculate_all_momentum computes 17 (incl. mfi, roc, ema_crossover, obv, ad_line, vwap_momentum, trend_slope, velocity, acceleration). Similarly SR uses 5 of 13 (L239). The '67 indicators' claim is not what drives the decision.
- **Impact:** Most of the expensive indicator computation is wasted, and the directional vote rests on a small, partly redundant subset (RSI/Stoch/Williams/CCI are all overbought-oversold oscillators that frequently agree, over-weighting mean-reversion vs trend).
- **Fix:** Either expand the voting set with explicit per-indicator weights, or drop unused computations to cut latency. De-correlate the oscillator cluster so 4 redundant oscillators do not dominate a 6-vote tally.

### _rsi uses alpha=1/period and seeds avg_gain/avg_loss from a single bar — not standard Wilder RSI
- **Category:** accuracy
- **Location:** `backend/analysis/market_direction_engine.py` : 588-612
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** Wilder's RSI seeds avg_gain/avg_loss with the SMA of the first `period` gains/losses then smooths. Here avg_gain=gains[0]/avg_loss=losses[0] (a single delta) and alpha=1/period (L598-604). The single-bar seed plus full-history smoothing makes RSI length-dependent and noisy on short buffers, and disagrees with the pandas-rolling RSI in momentum/indicators.py:12-28.
- **Impact:** RSI zones (L291-298) and RSI-slope (L420,452-455) feed the 35% trend and 20% momentum scores; biased RSI shifts direction near the 60/40 RSI thresholds and corrupts strength.
- **Fix:** Use proper Wilder seeding (mean of first `period` gains/losses) and a single consistent RSI implementation shared across both engines.

### 5m swing/structure detection has look-ahead and fragile negative-index ordering
- **Category:** correctness
- **Location:** `backend/analysis/market_direction_engine.py` : 328-358
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** Swing detection iterates idx=-i and checks high[idx+1] (L334); for i==2 that reads high[-1], the CURRENT (forming) bar, so a 'confirmed swing' uses an unclosed bar (look-ahead/repaint). The loop range range(2, min(20, len(df)-2)) and sort by x[0] (negative ints) order from most-negative to -2, so recent_highs[-1] is the NEWEST; the HH/HL comparison is fragile and only triggers when both >=2 swings exist, otherwise structure silently stays RANGING.
- **Impact:** Structure (HH_HL/LH_LL) drives a +/-25 swing on the 25%-weight 5m score and the structure_type shown in the UI. Look-ahead makes it repaint; the frequent RANGING fallback under-weights real structure.
- **Fix:** Confirm swings only on closed bars (start the loop so the most recent candle examined is iloc[-2] or earlier). Use explicit chronological ordering and add a fractal confirmation lag.

### Engines silently swallow exceptions and return neutral defaults indistinguishable from real analysis
- **Category:** risk
- **Location:** `backend/analysis/decision_engine.py` : 178-180,313-320; market_direction_engine.py:247-249,614-646
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** analyze() wraps everything in try/except and returns _empty_result (confidence 0). The direction engine returns _empty_result with strength=50.0 and all component scores=50.0 and direction NEUTRAL (L616-646) — indistinguishable from a genuine neutral read. Per-indicator failures in calculate_all_* are also caught and replaced with NEUTRAL stubs (momentum/indicators.py:283-284), so a broken indicator silently degrades the vote denominator without surfacing.
- **Impact:** A crashed pipeline or NaN-producing indicator masquerades as a calm/neutral market. Downstream consumers cannot distinguish 'analysis failed' from 'market is neutral', so no alerting/circuit-breaking occurs and decisions proceed on partial data.
- **Fix:** Add an explicit status/error field and a quality score (fraction of indicators that succeeded) to results. Have consumers refuse to trade when status!='OK' or quality<threshold. Log and count per-indicator failures.

### to_python_type maps NaN/Inf to None, which downstream float() casts re-break or treat as 0
- **Category:** data-integrity
- **Location:** `backend/analysis/decision_engine.py` : 27-30,146-171
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** to_python_type converts NaN/Inf floats to None (L28-29). Some result fields are wrapped in explicit float(...) before scrubbing (e.g. confidence at L146) but nested sub-values go through to_python_type; a NaN reaching a numerically-consumed field becomes None. trading_engine reads confidence then compares confidence < min_confidence (trading_engine.py:163) — a None confidence raises; the scrub only protects nested 'details', not the numeric guarantee.
- **Impact:** Inconsistent NaN handling: some paths yield None (TypeErrors on comparison/sizing), others silently coerce. NaN indicators (rolling means on <period bars) can propagate as None into the UI and risk calcs.
- **Fix:** Sanitize NaN->0.0 (or a sentinel) for fields that must stay numeric for gating/sizing, and validate inputs (drop/forward-fill NaN OHLCV) before indicator computation. Add explicit non-null contracts for signal/confidence/strength.

### Insufficient-data fallbacks return EMA=0, biasing direction UP exactly when data is least reliable
- **Category:** correctness
- **Location:** `backend/analysis/market_direction_engine.py` : 256-257,317-318,405-406; decision_engine.py:70-71
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** When len(df)<100 (15m), <50 (5m), or <25 (1m), helpers return ema values of 0 (e.g. L257 returns ...,0,0,50). Those zeros flow into DirectionResult, and to_dict (L107-110) renders 0 as None (falsy). More importantly current_price > ema_50(=0) is always True, so a data-starved 15m frame can spuriously read UP. The decision engine requires only 50 bars (L70) but moving_averages needs >=200 and silently substitutes shorter MAs.
- **Impact:** Early in the session or for thinly-populated symbols, direction is biased UP purely because EMA defaults are 0, and SR/structure quietly use degraded windows — false confidence when data is least reliable.
- **Fix:** On insufficient data, return a hard NEUTRAL with a 'low_data' flag and do NOT emit tradeable signals. Never default EMAs to 0; use the available mean or mark unavailable. Enforce per-indicator minimum-bar requirements explicitly.

### LiveCandle resets volume on rollover and buckets by wall-clock, risking massive volume inflation
- **Category:** data-integrity
- **Location:** `backend/analysis/timeframe_aggregator.py` : 145-186
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** On a new candle LiveCandle starts volume=volume of the triggering tick (L173) and returns the prior candle, but the completed candle never receives the FINAL tick of its interval; volume is per-tick incremental which assumes ticks carry per-tick traded volume (many broker feeds send CUMULATIVE day volume, which would massively over-sum). Bucketing uses datetime.now(IST) (L153) not the tick's own timestamp, so late/out-of-order ticks land in the wrong candle.
- **Impact:** If fed a cumulative-volume stream, OHLCV volume is wildly inflated, corrupting every volume-based indicator/score. Wall-clock bucketing drops/mislabels ticks during latency spikes.
- **Fix:** Bucket by the tick's exchange timestamp, not now(). Detect cumulative vs incremental volume and delta it. Carry the last tick into the closing candle before rollover.

### Multi-timeframe inputs are recomputed from one 1m source with no freshness/consistency check
- **Category:** realtime
- **Location:** `backend/analysis/market_direction_engine.py` : 158-208; direction_scheduler.py:94-118
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** df_5m and df_15m are derived by aggregating the same 200 1m candles every second (direction_scheduler.py:113-114). There is no check that the 1m data is itself fresh before deriving higher TFs, and the fallback path (L97-107) substitutes 5m data for 1m and even 5m for 15m, so the engine can run with df_1m==df_5m==df_15m, collapsing the multi-timeframe design into a single timeframe while still applying the 35/25/20 weights to identical bars.
- **Impact:** During data gaps the 'multi-timeframe' consensus is illusory (all three components see identical data), inflating apparent agreement and resulting strength. Stale 1m data silently produces confident-looking but stale directions.
- **Fix:** Validate 1m recency (timestamp age) before computing; if higher-TF data must be substituted, down-weight or flag it. Never reuse the same DataFrame for all three timeframes without marking the result degraded.

### Unrealized P&L uses raw LTP, but realized P&L uses slippage-adjusted price — inconsistent and double-counts capital on SELL
- **Category:** accuracy
- **Location:** `backend/services/paper_broker.py` : 62-65, 243-246
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** _calculate_unrealized_pnl uses (ltp - entry)*qty with a comment that slippage is applied only on exit, while SELL computes pnl with the slippage-adjusted exec_price. Separately, the SELL balance update credits original_capital (entry*qty) + pnl back to balance (245-246) while BUY deducted only premium (213). This double-accounts: on BUY balance -= entry*qty; on SELL balance += entry*qty + pnl, which is correct only if entry*qty was the locked amount — but unrealized equity in get_account adds unrealized on top of a balance that already had premium deducted, which is consistent, yet realized_pnl is also tracked separately and added in get_account.total_pnl. The mixed accounting is fragile.
- **Impact:** Equity/total_pnl can be inconsistent between open and closed states; the transition from unrealized to realized can show a discontinuity equal to slippage, confusing reported results.
- **Fix:** Define one accounting model: lock premium on BUY, on SELL credit exec_proceeds = exec_price*qty (already net of slippage) and set realized_pnl += exec_proceeds - entry*qty. Compute unrealized as (ltp - entry)*qty consistently and never add realized twice.

### Entry signals derived from 5-minute candles are too stale for 5-second scalping
- **Category:** realtime
- **Location:** `backend/services/trading_engine.py` : 134-145
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** evaluate_strategies pulls 5m candles (candle_service.get_candles ... '5') and runs analyze_market on them. These candles are produced by a separate aggregation job; the most recent 5m candle can be up to ~5 minutes old and only updates on the aggregation cadence. The 5s heartbeat re-evaluates the same near-static signal repeatedly.
- **Impact:** Entries lag the market by up to a full 5m bar — fatal for scalping accuracy. Also wasteful: the same signal is recomputed every 5s with full DataFrame construction.
- **Fix:** Blend the live current_ltp passed into evaluate_strategies into an in-progress candle, or use 1m candles (already synced as base) for signal generation. Cache the computed signal per bar and only recompute when a new candle closes.

### Entry fill price falls back to current LTP, fabricating an inaccurate fill
- **Category:** accuracy
- **Location:** `backend/services/trading_engine.py` : 332-334, 442-454
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** If execution_price resolves to 0 (LIVE order whose fill price could not be read after 3 short retries), execute_entry sets execution_price = self._get_option_ltp(trading_symbol) — the LTP at that later instant, not the actual fill. execute_exit has the analogous fallback to the trigger exit_price. _get_order_fill_price only retries 3x at 0.5s and may return 0 for not-yet-filled orders.
- **Impact:** Recorded entry/exit prices and all downstream SL/target/P&L are based on a fabricated price that can differ materially from the real broker fill, corrupting accuracy and risk levels for the whole trade.
- **Fix:** For LIVE, poll order status until terminal (FILLED) with backoff before recording, and use get_trades_for_order (already in groww_client) to read true average fill. If still unknown, mark the trade as needs-reconciliation rather than silently substituting LTP.

### resolve_dynamic_symbol uses spot price from a 10s-expiry redis cache and loose regex; can pick wrong strike/expiry
- **Category:** accuracy
- **Location:** `backend/services/trading_engine.py` : 248-276
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** Spot is read from redis_client.get_cached_ltp (cached 10s by heartbeat) and ATM rounding uses it; in fast markets the strike can be one step off. The instrument lookup regex '^{index}.*{strike}{type}$' is greedy: e.g. NIFTY...24500CE could also match a symbol where 24500 appears inside a larger number or different segment, and BANKNIFTY strike step is 100 but BANKNIFTY is mapped while FINNIFTY/MIDCPNIFTY are not handled in the step map (default 50).
- **Impact:** Wrong strike or wrong contract selected, especially around strike boundaries and for non-listed indices; trades the wrong instrument with mismatched liquidity/greeks.
- **Fix:** Anchor strike selection to a freshly fetched spot (or accept current_ltp param), match instruments on structured fields (underlying, strike, option_type, expiry) rather than regex on trading_symbol, and maintain a complete index->step map. Verify the selected expiry is the intended weekly.

### is_market_open check is bypassed for PAPER mode, allowing fills on stale/closed-market prices
- **Category:** realtime
- **Location:** `backend/services/trading_engine.py` : 284
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** execute_entry returns 'Market is closed' only when (not is_market_open() and execution_mode=='LIVE'). In PAPER mode entries proceed regardless. Although the scheduler heartbeat itself checks is_market_open, manual entry routes (trade_routes.py execute path) and any PAPER-mode call can place trades against the last LTP returned by the API, which during closed markets is a stale snapshot.
- **Impact:** PAPER trades can be opened/closed at stale prices outside market hours, producing unrealistic paper results that the user is using to judge the strategy.
- **Fix:** Also gate PAPER entries on is_market_open (or on LTP freshness / a quote timestamp). Reject fills when the quote is stale beyond a threshold.

### Slippage model is random and price-only; ignores spread, depth, and order size
- **Category:** accuracy
- **Location:** `backend/services/paper_broker.py` : 118-140
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** _calculate_slippage applies a flat 0.05% base spread times a uniform(0.8,1.5) random factor, symmetric for buy/sell. Real option slippage depends on bid/ask spread (wide for OTM/illiquid strikes), order size vs available depth, and is far larger than 0.05% for cheap options. Quote depth is available via groww_client.get_quote but unused.
- **Impact:** Paper fills are unrealistically tight, overstating profitability of a scalping strategy whose entire edge is small per-trade. Live results will be worse, defeating accuracy/best-results goals.
- **Fix:** Use the actual bid/ask from get_quote (buy at ask, sell at bid) plus a size-based impact term; fall back to a wider, strike-price-aware spread model. Calibrate against observed live fills.

### No idempotency/lock around heartbeat exit — duplicate SELL orders possible within or across cycles
- **Category:** risk
- **Location:** `backend/services/trading_engine.py` : 212-219, 460-465
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** When an exit triggers, execute_exit places the SELL and only afterwards calls db.close_trade. If two heartbeats overlap (slow LTP fetches push a cycle past 5s) or the heartbeat and the manual /exit route run together, the same OPEN trade can be selected twice and sold twice before status flips to CLOSED. The heartbeat path does not take acquire_trade_lock.
- **Impact:** Double exits: in LIVE this opens an unintended short position; in PAPER it can fail at 'No matching position' or corrupt balances. Real capital risk.
- **Fix:** Acquire the per-user/per-trade lock in monitor_active_trades before execute_exit, and make close_trade atomic with a status guard (update_one filter {'_id':id,'status':'OPEN'}) so a second exit is a no-op.

### Two identical 'fixed' engine files plus an obsolete backup create import-confusion risk
- **Category:** maintainability
- **Location:** `backend/services/trading_engine_fixed.py` : 1-511
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** trading_engine_fixed.py is byte-identical to the active trading_engine.py (confirmed by diff), and trading_engine_backup.py is an older, buggy version (uses config.EXECUTION_MODE globally, broker.get_ltp list-quote parsing, product_type branch, hardcoded confidence<0.6). Only trading_engine.py is imported. The duplicates are dead code.
- **Impact:** High risk that a future edit lands in the wrong file or that an import is accidentally repointed to the stale backup, silently reverting fixes (e.g., reintroducing the global execution_mode bug). Maintenance and review overhead.
- **Fix:** Delete trading_engine_fixed.py and trading_engine_backup.py (rely on version control for history). Keep a single trading_engine.py as the source of truth.

### reconcile_positions is an unimplemented stub, so LIVE DB/broker drift is never corrected
- **Category:** data-integrity
- **Location:** `backend/services/trading_engine.py` : 482-485
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** reconcile_positions just 'pass'es (TODO). The scheduler's reconcile_orders_job (scheduler.py:266-288) fetches broker positions and calls it, but nothing happens. Manual broker fills, partial fills, or trades closed outside the app are never reconciled into the DB.
- **Impact:** DB can show OPEN trades that no longer exist at the broker (or miss positions opened/closed externally), so monitoring acts on phantom positions and P&L/risk state diverges from reality in LIVE.
- **Fix:** Implement reconciliation: match broker positions to OPEN trades by symbol, close trades with no matching broker position (capturing realized P&L from broker), and flag/auto-create unknown broker positions for review.

### Encryption key derivation uses unsalted single-pass SHA-256; decrypt swallows all errors
- **Category:** security
- **Location:** `backend\utils\encryption.py` : 15-18,27-35
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** The Fernet key is SHA-256(config.ENCRYPTION_KEY) with no salt and no KDF iteration; config.ENCRYPTION_KEY defaults to a hardcoded dev string (config.py:33). decrypt() catches every exception and returns '' silently (line 34-35), so a wrong key, tampered ciphertext, or rotated key is indistinguishable from an empty credential.
- **Impact:** Weak key derivation makes brute force easier if the env key is weak/default; silent decrypt failure means the system treats corrupted/undecryptable broker secrets as 'no credentials', potentially logging the user in but failing broker calls with confusing empty-key errors, or masking key-rotation/tampering incidents.
- **Fix:** Require a strong ENCRYPTION_KEY at startup (fail fast if default in non-dev). Use a proper KDF (PBKDF2/scrypt) with a stored salt, or use Fernet.generate_key() stored in a secret manager. Make decrypt distinguish 'empty input' from 'decryption failure' (raise/log on InvalidToken) so callers can alert.

### Checksum/auth has no timestamp skew or replay protection and is not constant-time
- **Category:** security
- **Location:** `backend\utils\checksum.py` : 8-27
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** generate_checksum hashes secret+timestamp with plain SHA-256. There is no validation that a server-provided timestamp is within an acceptable skew window, and comparison elsewhere (not in this file) likely uses ==. While generation is client-side, the lack of any freshness/skew handling around the timestamp means a clock-skewed client can produce rejected checksums with no diagnostic, and reuse of an old timestamp+checksum is possible within the broker's window.
- **Impact:** Auth failures from clock skew are silent/hard to diagnose; potential replay within the validity window. Could intermittently break broker connectivity, halting real-time trading.
- **Fix:** Centralize timestamp generation, log the timestamp used, and if the broker returns auth errors, retry with a freshly fetched server time. Where any checksum is compared server-side, use hmac.compare_digest. Document the broker's accepted skew window.

### Strategy.validate_signal uses naive datetime.now() for time filter — wrong timezone on UTC servers
- **Category:** accuracy
- **Location:** `backend\models\models.py` : 192-196
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** The time filter compares datetime.now().strftime('%H:%M') against time_filter_start/end. datetime.now() is server-local; on a UTC-deployed server this is 5.5h behind IST, so the trading-hours window is evaluated against the wrong clock. Lexicographic '%H:%M' string comparison also misbehaves if a 24h boundary or single-digit hour ever appears.
- **Impact:** Time-window filters admit or reject signals at the wrong real-world times, causing trades outside intended hours or missing the intended window — degrades accuracy and can trade in illiquid periods.
- **Fix:** Use get_ist_now() from time_utils for the time filter, and compare time objects rather than strings. Centralize all 'now' calls through the IST helper.

### Missing indexes on frequently-queried fields (status+index on strategies, trades.trading_symbol, settings.user_id, paper_account.user_id, daily_summary, signals timestamp)
- **Category:** performance
- **Location:** `backend\database\mongodb.py` : 42-72
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** evaluate_strategies queries strategies by {user_id,is_active,index} (trading_engine.py:124) but indexes exist only on user_id and is_active separately (lines 49-50) — no compound index including 'index'. resolve_dynamic_symbol uses a regex on trading_symbol sorted by 'expiry' (trading_engine.py:269-271) but the index is on 'expiry_date' (line 64) and the regex is non-anchored-prefix-unfriendly. settings/paper_account/trade_journal/daily_summary collections have no indexes on user_id despite frequent lookups (mongodb.py:263,327,336,351). trades has no index on trading_symbol though monitoring filters by it.
- **Impact:** Collection scans on the hot 5-second evaluate/monitor loop increase latency and DB load, harming real-time responsiveness as data grows. The expiry-sort uses a wrong/missing index field, so 'nearest expiry' resolution may be unsorted or slow.
- **Fix:** Add compound index strategies[(user_id,is_active,index)]; add settings[user_id] unique, paper_account[user_id] unique, daily_summary[(user_id,date)] unique, trade_journal[user_id]; reconcile the expiry field name (expiry vs expiry_date) and index it; index trades[trading_symbol]. Anchor the symbol regex or store parsed strike/type for indexed equality lookups.

### is_market_open has no holiday calendar and includes the exact close minute boundary
- **Category:** accuracy
- **Location:** `backend\utils\time_utils.py` : 16-28
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** is_market_open only checks weekends and a fixed 09:15-15:30 window. NSE trading holidays are not handled, and the comparison market_open <= t <= market_close treats 15:30:00 as open. There is also no pre-open/post-close session distinction.
- **Impact:** On exchange holidays the system believes the market is open and may attempt to fetch LTP / place orders that fail, and edge-minute logic at exactly 15:30 can attempt entries at the close. Reduces real-time correctness.
- **Fix:** Add an NSE holiday list (config or data file) and exclude those dates; make the close boundary exclusive or stop new entries a configurable buffer (e.g., AUTO_EXIT) before close. Consider a separate is_trading_session helper.

### get_current_expiry_dates hardcodes Thursday expiry; NSE moved NIFTY weekly expiry off Thursday
- **Category:** accuracy
- **Location:** `backend\utils\time_utils.py` : 141-165
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** Weekly expiry is computed as the next Thursday and monthly as the last Thursday. NSE has changed index weekly/monthly expiry weekdays (NIFTY weekly expiry has shifted), so hardcoded Thursday logic can produce incorrect expiry dates. The 15:00 cutoff for same-day Thursday is also arbitrary vs the 15:30 expiry time.
- **Impact:** Wrong expiry dates feed instrument selection; resolve_dynamic_symbol may pick a non-existent or wrong-expiry contract, causing failed entries or trading the wrong series — accuracy and execution risk.
- **Fix:** Drive expiry weekday from config or, preferably, derive available expiries from the instruments collection (db.get_available_expiries) and pick the nearest valid one rather than computing weekdays. Keep a configurable expiry-weekday and holiday-shift rule.

### 5m/15m timeframe aggregation has gap/boundary bug (no time-continuity check)
- **Category:** data-integrity
- **Location:** `backend/groww/New/opportunity_scanner.py` : 73-94
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** convert_to_higher_timeframe groups by computed bucket_ts but only closes a bucket when bucket_ts changes (`bucket[0][0] != bucket_ts`). If the data has a gap (missing minutes) that still maps to the same minute//N bucket on a later day, or if candles are unsorted, candles from different real periods can be merged. There is no check that minutes are contiguous or that the day matches, and no sorting of input (unlike the backtester which sorts at :203).
- **Impact:** Across multi-day data or with missing candles, 5m/15m bars can aggregate the wrong minutes, corrupting the higher-timeframe context that feeds opportunity detection and any indicator built on it.
- **Fix:** Sort candles by ts first; key buckets by the full aligned epoch (date+time) and verify expected member count; emit None/flag for incomplete buckets; skip aggregation across session boundaries.

### Indicator look-back leakage: indicators computed over multi-day context but signals not date-gated
- **Category:** accuracy
- **Location:** `backend/groww/nifty_scalper_bt.py` : 178-220,231-258
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** fetch_smart pulls 5-7 days of 5m/15m context (good for warm-up) but 1m index bars are fetched with days_back=0 in run() (:433) while 5m/15m use days_back=7. generate_signals never filters bars to the target date, so if any path supplies multi-day 1m bars, signals would be generated for prior days too, and get_last_completed_bar walks all 15m/5m bars without a same-session constraint. The EMA/RSI/ATR seeds also include the previous days' values, which is fine for warm-up but means the first bars of the test day inherit cross-day state without explicit handling of overnight gaps in TR (atr at :150-154 uses prev close across the overnight gap, inflating ATR on the first bar).
- **Impact:** Overnight gap inflates day-open ATR -> dynamic_threshold too high at open (missed early signals) or, on a gap-down option, distorted TR. Potential cross-day signal leakage if 1m days_back changes.
- **Fix:** Explicitly filter trading/signal logic to the target date; reset or mask the first-bar TR across session boundaries; document the warm-up window and exclude warm-up bars from signals.

### No cooldown/one-trade-at-a-time enforcement matches live, and re-entry index uses option-bar holding count
- **Category:** correctness
- **Location:** `backend/groww/nifty_scalper_bt.py` : 272,318-319,327-328
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** execute_trades prevents overlapping trades via last_exit_idx, but it sets last_exit_idx = idx_1m + t.holding_candles where holding_candles is counted in OPTION bars (opt_idx_start based, :318) while idx_1m indexes the 1m INDEX bar list. Index and option bar arrays are not guaranteed to be index-aligned (missing option candles cause opt_map misses at :277), so adding an option-bar count to an index-bar index can under- or over-block subsequent signals.
- **Impact:** Either spurious blocking of valid signals or allowing overlapping trades that the live system (which blocks if an OPEN trade exists per strategy, trading_engine.py:154-159) would not take — backtest trade count diverges from live.
- **Fix:** Track cooldown in a common time domain (timestamp), not mixed array indices. Map exit timestamp back to the 1m index by ts and block signals with ts <= exit_ts. Align option/index bars by timestamp explicitly.

### Scanner profit/loss accounting only counts target/SL, ignores actual exit and time-stops
- **Category:** accuracy
- **Location:** `backend/groww/New/opportunity_scanner.py` : 212-260,295-299
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** Every opportunity is scored as a binary WIN (full potential profit) or LOSS (full risk = the next-bar opposite extreme), with R:R computed from the same bar (rr uses potential_up/potential_down, :214). There is no concept of holding period, time exit, or the fact that target and SL are derived from the same single future bar. print_table's Net P&L therefore equals sum of bar high-moves minus bar low-moves on winners/losers.
- **Impact:** The headline win-rate and net-points figures are meaningless as an edge estimate; they cannot be compared to the backtester (which at least simulates multi-bar exits) and overstate profitability.
- **Fix:** Either remove the P&L/win-rate summary from the scanner (label it purely as candidate detection) or reimplement it with the same execute_trades simulation used by the backtester so the two agree.

### Volume filter and indicators silently degrade to 0 / pass-through on insufficient data
- **Category:** data-integrity
- **Location:** `backend/groww/nifty_scalper_bt.py` : 120,130,148,163,238,243,248,250
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** ema/rsi/atr/sma return all-zeros when len < period (e.g. :120,:130). generate_signals skips when last_15m.ema==0 or last_5m.rsi==0 (:238,:243) — but ATR==0 is only skipped via dynamic_threshold==0 (:248), and vol_sma can legitimately be 0 for early bars making is_high_volume = v>0 always true (:250). Option bars set v=0 if len<=5 (:201). A genuine RSI of exactly 0.0 (impossible) vs uninitialized 0.0 are conflated.
- **Impact:** Early-session or low-history days produce signals with a no-op volume filter (is_high_volume always true) and ATR thresholds that may be artificially tiny, generating low-quality entries; conflating 'no data' with value 0 hides data-quality failures.
- **Fix:** Use NaN/None sentinels for uninitialized indicators and explicitly require sufficient warm-up before allowing signals; guard is_high_volume with vol_sma>0; assert option bars carry real volume.

### No transaction-cost realism beyond flat slippage + flat brokerage; ignores STT, exchange fees, GST, spread
- **Category:** accuracy
- **Location:** `backend/groww/nifty_scalper_bt.py / run_backtest.py` : nifty_scalper_bt.py:67-70,330; run_backtest.py:47-49
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** Costs are modeled as entry_slippage+exit_slippage (flat points) and brokerage_per_order=20 once per trade (pnl_rs subtracts only one 20, not 20 entry + 20 exit). Real Indian options round-trip costs include STT on sell, exchange transaction charges, SEBI fees, stamp duty, and 18% GST on (brokerage+txn charges), plus bid-ask spread which on cheap weeklies can exceed the 0.5 slippage assumed.
- **Impact:** Net P&L is overstated; for a high-frequency scalper where edge per trade is a few points, omitting half the brokerage and all statutory charges can flip a 'profitable' system to negative.
- **Fix:** Apply brokerage for BOTH legs (entry+exit), add a cost model for STT/exchange/GST/stamp, and model slippage as max(ticks, spread%) per leg. Recompute all reported metrics after full costs.

### GrowwAPI.py executes network/token side effects and prints the token at import time
- **Category:** security
- **Location:** `backend/groww/GrowwAPI.py` : 7-10
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** At module import the file calls GrowwAPI.get_access_token(...) with hardcoded credentials and print()s the resulting access token, then constructs a global `groww` client. Any import triggers a live auth call and leaks the token to stdout/logs.
- **Impact:** Token leakage into logs/CI output, unexpected live authentication on import, and tight coupling that makes safe testing impossible.
- **Fix:** Wrap in a function, load credentials from env, never print tokens, and avoid side effects at import. Treat the leaked secret as compromised and rotate.

### _parse_ohlc_string() splits on comma without handling values containing commas or missing keys
- **Category:** correctness
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\groww_client.py` : 168-189
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** The parser at line 180 does clean_str.split(',') and then part.split(':') expecting exactly two parts. If any numeric value is formatted as '1,234.56' (Indian number formatting with comma) or if a key-value pair has extra colons, the split produces wrong results or raises ValueError. The except block at line 187 returns all zeros, silently masking bad parses.
- **Impact:** OHLC data returned from get_quote() and get_ohlc() could be silently zeroed out for instruments whose prices are in the lakhs range (e.g., BANKNIFTY index at 45,000+ could have commas in some locales). Zero OHLC leads to wildly incorrect indicators and signals.
- **Fix:** Use a regex-based parser: re.findall(r'(\w+):\s*([\d.]+)', ohlc_str) which handles whitespace and avoids comma-splitting entirely. Log a WARNING with the raw string whenever parsing falls back to zeros.

### candle_service.fetch_candles_from_groww does not use shared GrowwClient session — creates new requests.get per call
- **Category:** performance
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\candle_service.py` : 33-126
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** CandleService uses bare requests.get() (line 83) instead of the shared requests.Session from GrowwClient. This means no HTTP connection reuse (no keep-alive), no shared headers, and no centralized timeout/retry policy. It also duplicates the header construction (lines 68-73) outside of GrowwClient, creating a second code path with different header keys (no checksum, no Content-Type).
- **Impact:** Each candle fetch opens and closes a fresh TCP connection to api.groww.in. For 3 symbols x 1 minute, this is 3 new TLS handshakes per minute, adding 100–300 ms latency each time. Over a 6-hour session that is 18,000 unnecessary TLS handshakes.
- **Fix:** Refactor candle_service to accept a GrowwClient instance (or call client.get_historical_candles()) rather than making raw requests.get calls. GrowwClient already has get_historical_candles() (line 367) which uses the shared session and centralised error handling.

### instrument_sync uses delete_many+insert_many non-atomically — instruments collection empty during sync
- **Category:** data-integrity
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\instrument_sync.py` : 43-45
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** db.instruments.delete_many({}) (line 43) deletes all instruments before insert_many (line 45). Any concurrent query (ATM strike lookup, strategy evaluation, instrument search) between delete and insert returns empty results. The sync happens at 08:00 IST, just before market open — a high-activity window.
- **Impact:** Strategy startup at 09:00 that loads instruments to find ATM strikes will get empty results if instrument sync is still in progress or if insert fails mid-way. In LIVE mode this means orders cannot be constructed for the first few minutes.
- **Fix:** Use a shadow-copy pattern: insert into a temp collection instruments_new, then use db.instruments_new.rename('instruments', dropTarget=True) which is atomic in MongoDB. Or use bulk_write with upsert=True keyed on trading_symbol.

### Daily 1D candle resampled with resample('1D') ignores IST session boundary — aggregates midnight-to-midnight UTC
- **Category:** accuracy
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\scheduler.py` : 228-248
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** df_day.resample('1D') at line 233 is called on df_1m which has its datetime index set from the IST-converted values (line 230). However resample('1D') without an explicit offset anchors to UTC midnight (00:00 UTC = 05:30 IST). This means the daily bar open is set at 05:30 IST, not 09:15 IST. Candles from the previous session's late data and the next session's pre-market would be grouped incorrectly.
- **Impact:** Daily OHLC values are wrong. The open price of the 1D bar is the 05:30 IST value (which is not a trading candle — market opens at 09:15) and the close is wrong too. Any strategy using daily levels, support/resistance from 1D candles, or daily ATR will operate on garbage data.
- **Fix:** Use resample('1D', offset='9h15min') or resample('B') with custom market hours. Better: group by date using df_day.groupby(df_day.index.date).agg({...}) after filtering to market hours only (09:15–15:30 IST).

### get_today_trades() uses datetime.utcnow() midnight — misses IST trades from 00:00–05:30 UTC
- **Category:** accuracy
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\database\mongodb.py` : 255-259
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** today_start = datetime.utcnow().replace(hour=0, ...) is midnight UTC. IST is UTC+5:30, so IST midnight is 18:30 UTC the previous day. Trades created between 18:30 UTC (00:00 IST) and 00:00 UTC are on a different UTC date and will be excluded from today_start queries. For the daily_summary_job (scheduler.py:320) this means the P&L summary at 15:35 IST will always be based on a complete day's trades. However if the system is ever used for overnight positions or the summary is generated near midnight UTC, trade counts will be wrong.
- **Impact:** Daily P&L summary and win-rate calculations in the Telegram summary may undercount or overcount trades for the IST trading day, leading to incorrect performance metrics.
- **Fix:** Compute today_start as IST midnight: use `from utils.time_utils import get_ist_now; ist_now = get_ist_now(); today_start = ist_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.utc)` and store as a UTC-aware datetime for the MongoDB query.

### telegram_alert.send_daily_summary() references 'losing' key not populated in summary dict
- **Category:** correctness
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\telegram_alert.py` : 135
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** The message template at line 135 accesses summary.get('losing', 0). In scheduler.py:daily_summary_job() (lines 321-329) the summary dict is constructed with keys total_pnl, total_trades, winning, win_rate, execution_mode — there is no 'losing' key. summary.get('losing', 0) silently returns 0 for all daily summaries.
- **Impact:** The Telegram daily summary always shows '0 Losing trades' regardless of actual performance. The user receives misleading performance information.
- **Fix:** Add `'losing': total_trades - winning` to the summary dict in scheduler.py:daily_summary_job() at line 325.

### telegram_alert._send_message() is synchronous and blocking — can delay heartbeat and scheduler threads
- **Category:** realtime
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\telegram_alert.py` : 33-55
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** requests.post() to Telegram API with a 10-second timeout (line 46) is called synchronously in the APScheduler job threads (e.g., daily_summary_job calls it directly). If the Telegram API is slow or unreachable, the scheduler thread blocks for up to 10 seconds. daily_summary_job runs in the same thread pool as sync_and_aggregate_job and heartbeat jobs.
- **Impact:** A Telegram API outage at 15:35 IST (daily summary time) can delay the daily_summary_job by 10 seconds, consuming a scheduler thread slot. In edge cases this could interfere with reconcile_orders_job which also runs at 1-minute intervals.
- **Fix:** Send Telegram messages asynchronously using a background thread (threading.Thread) or a dedicated queue (queue.Queue consumed by a daemon thread). This decouples notification delivery from trading-critical scheduler threads.

### test_connection() in TelegramAlert mutates instance state (bot_token, chat_id) without a thread lock
- **Category:** correctness
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\telegram_alert.py` : 157-186
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** test_connection() temporarily overwrites self.bot_token, self.chat_id, and self.base_url (lines 163-168) to use test credentials, then restores them (lines 180-184). If _send_message() is called from another thread between the overwrite and restore (e.g., a trade exit alert fires concurrently), it will use the test credentials and send the alert to the wrong chat.
- **Impact:** Real trading alerts (entries, exits, kill-switch) could be silently routed to a test chat during the test_connection call window. In live trading, this means the operator does not receive critical order notifications.
- **Fix:** Create a temporary TelegramAlert(bot_token, chat_id) instance for testing rather than mutating the singleton. The get_telegram_alert() factory already supports this pattern.

### SUPPORTED_UNDERLYINGS missing from config.py — AttributeError at runtime if not in .env
- **Category:** correctness
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\groww_client.py` : 710
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** filter_fno_instruments() calls config.SUPPORTED_UNDERLYINGS (line 710) but this attribute is not defined in config.py. instrument_sync.py (line 15) guards with hasattr() and falls back to a hardcoded list. groww_client.py has no such guard — calling filter_fno_instruments(df) with no underlyings argument will raise AttributeError at runtime.
- **Impact:** Any code path calling filter_fno_instruments without explicit underlyings will crash. If this is called during the instrument_sync job it will silently return an empty frame after exception, leaving instruments collection empty.
- **Fix:** Add SUPPORTED_UNDERLYINGS = ['NIFTY', 'BANKNIFTY', 'SENSEX', 'FINNIFTY', 'MIDCPNIFTY'] to config.py. Apply consistent hasattr() guard in groww_client.py line 710.

### sync_candles and sync_realtime are identical in implementation — sync_realtime provides no incremental benefit
- **Category:** correctness
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\candle_service.py` : 175-182
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** sync_realtime() (line 175) calls _get_smart_window(int_interval) with the same lookback window as sync_candles() (7 days for 1m), then calls _execute_sync with mode='realtime'. The only difference is the DB write path (upsert vs delete+insert). But the Groww API request fetches the same 7-day window. There is no short-window / incremental fetch — both methods hit the same API endpoint with the same parameters.
- **Impact:** sync_realtime() is named to suggest it fetches only recent data but actually requests 7 days of candles every time it's called, providing no performance or bandwidth advantage over sync_candles. The API latency is identical, as is the data transfer volume.
- **Fix:** Add a separate _get_incremental_window(interval, minutes_back=10) method that computes a start_dt = now - 10 minutes for realtime syncs, dramatically reducing the API request size and latency.

### APScheduler BackgroundScheduler has no misfire_grace_time — long-running jobs silently dropped
- **Category:** realtime
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\scheduler.py` : 36
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** BackgroundScheduler is initialised with timezone only. APScheduler's default misfire_grace_time is 1 second. If sync_and_aggregate_job (which fetches 7 days of 1m data for 3 symbols) takes longer than 60 seconds, the next scheduled CronTrigger fire at the next minute boundary will be considered misfired and dropped (because it is more than 1 second past its scheduled time). This can cause entire sync cycles to be silently skipped.
- **Impact:** On a slow API day, the 1-minute candle sync could stretch to 90+ seconds per symbol (3 API calls x 30 s timeout each). Subsequent minute syncs are misfired and dropped, creating multi-minute gaps in candle data during the exact sessions that are most volatile.
- **Fix:** Set misfire_grace_time=60 on the scheduler: BackgroundScheduler(timezone='Asia/Kolkata', misfire_grace_time=60). Also add coalesce=True to the sync_and_aggregate job so misfired executions collapse into a single catch-up run.

### EMA calculation uses cold-start seed of data[0].close rather than a proper warm-up period
- **Category:** accuracy
- **Location:** `frontend/src/utils/indicators.ts` : 19-31
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** calculateEMA initializes `ema = data[0].close` (line 23) and immediately starts applying the EMA multiplier from i=0. This is the naive initialization. The standard approach (used by most charting systems including TradingView) is to seed the EMA using the SMA of the first `period` candles, then apply EMA from index `period` onward. With 300 candles and a period of 20, the first ~40 EMA values will be materially wrong.
- **Impact:** The EMA line on the chart will diverge from backend-computed EMA (which the AI decision uses for signals). If a trader uses the charted EMA to validate the AI BULLISH/BEARISH signal visually, the chart EMA and the AI EMA will show different crossover points, causing confusion and incorrect manual decision-making.
- **Fix:** Replace the seed: compute SMA of first `period` candles as the initial EMA value. Then run the EMA formula from index `period` forward. This matches TradingView and the standard definition: `let ema = data.slice(0, period).reduce((s, c) => s + c.close, 0) / period; for (let i = period; i < data.length; i++) { ema = data[i].close * k + ema * (1 - k); result.push(...) }`.

### Bollinger Bands uses population standard deviation (divides by N) instead of sample standard deviation (N-1)
- **Category:** accuracy
- **Location:** `frontend/src/utils/indicators.ts` : 77-80
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** calculateBollingerBands (line 80): `const stdDev = Math.sqrt(sumSqDiff / period)`. The industry-standard Bollinger Bands formula (as defined by John Bollinger and implemented in TradingView, Bloomberg, etc.) uses population standard deviation which is `Math.sqrt(sumSqDiff / period)`. However, many data providers use sample stddev (N-1). The discrepancy is small but consistent: the bands will be slightly narrower than expected, causing the price to appear to touch or breach the bands more frequently.
- **Impact:** Band breach signals (used as overbought/oversold indicators) will fire slightly more often than on TradingView, leading the trader to see more false breakout signals than the platform they may be cross-referencing with.
- **Fix:** This is actually the correct formula for Bollinger Bands as originally defined. Document this explicitly in a comment. More importantly, ensure the backend indicator computation also uses population stddev for consistency. The primary fix needed is ensuring backend and frontend use identical formulas.

### Signals.tsx fetchDecision effect has no AbortController — stale closure race when switching symbols rapidly
- **Category:** realtime
- **Location:** `frontend/src/pages/Signals.tsx` : 30-38
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** The useEffect at lines 30-38 creates a load function that calls fetchDecision(selectedSymbol, 5) and sets an interval. When selectedSymbol changes, React clears the old interval via cleanup, but any in-flight fetchDecision HTTP request from the previous symbol is not cancelled (no AbortController). If a BANKNIFTY request started 50ms before the symbol switch to NIFTY, and the BANKNIFTY response arrives after the NIFTY request has already set the store, the BANKNIFTY result could overwrite decisions['NIFTY'] due to the store's spread logic at line 80.
- **Impact:** The Signals page could briefly display BANKNIFTY signal data labeled as NIFTY, or vice versa. Given that BANKNIFTY signals are typically inverse to NIFTY (more volatile), this could cause a trader to place a CE trade when the actual NIFTY signal is BEARISH.
- **Fix:** Pass an AbortSignal into the API call and check it in the store. At minimum, check `if (symbol === selectedSymbol)` before calling set() in fetchDecision in the store. This requires threading the symbol through the async call.

### config.TRADE_POLL_INTERVAL (3s) defined but never used — active trades polled at 10s instead
- **Category:** realtime
- **Location:** `frontend/src/config/index.ts` : 10
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** config.TRADE_POLL_INTERVAL is set to 3000ms (line 10) but Trades.tsx hardcodes 10000ms (line 118). config.MARKET_POLL_INTERVAL and SIGNAL_POLL_INTERVAL are also ignored in favor of hardcoded values in the pages that use them (Signals.tsx line 36: 10000ms, Charts.tsx line 112 does use MARKET_POLL_INTERVAL). The config is the intended single source of truth but is bypassed.
- **Impact:** Changing the poll interval in config has no effect on Signals and Trades pages. The trades page refreshes LTP and P&L 3x slower than intended (10s vs 3s). For scalping where positions can be in and out in under a minute, a 10s stale P&L is operationally unacceptable.
- **Fix:** Replace all hardcoded interval values in useEffect calls with the corresponding config constants. Use config.TRADE_POLL_INTERVAL in Trades.tsx line 118, config.SIGNAL_POLL_INTERVAL in Signals.tsx line 36.

### Charts.tsx: interval '1D' (daily) coerces to NaN when passed to Number(interval) for fetchDecision
- **Category:** correctness
- **Location:** `frontend/src/pages/Charts.tsx` : 101
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** Charts.tsx line 101: `fetchDecision(symbol, Number(interval))`. The interval state can be '1', '5', '15', '60', or '1D' (config.CHART_INTERVALS line 54). When interval is '1D', Number('1D') === NaN. This NaN is passed as the interval parameter to the backend GET /strategy/decision endpoint, which likely defaults or errors. However the interval selector in Charts.tsx (line 295-298) only offers '1', '5', '15', '60' (no '1D'), while config.CHART_INTERVALS includes '1D'. This inconsistency suggests '1D' could be added to the UI later and would immediately break.
- **Impact:** If '1D' interval is selected (or added to the UI), the AI decision fetch sends NaN interval to the backend. The backend either ignores it and returns a default 5m decision (mismatched to the chart timeframe) or returns an error, leaving the Charts page without AI signal overlay.
- **Fix:** Guard the fetchDecision call: `const numericInterval = parseInt(interval, 10); if (!isNaN(numericInterval)) fetchDecision(symbol, numericInterval)`. Separately, remove '1D' from config.CHART_INTERVALS if it is not supported by the backend decision endpoint, or map it to a supported interval value.

### Chart re-initialized ignoring theme changes — chart always uses the theme at mount time
- **Category:** correctness
- **Location:** `frontend/src/pages/Charts.tsx` : 117-167
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** The chart initialization useEffect (lines 117-167) has an empty dependency array `[]`. It reads `document.documentElement.classList.contains('dark')` at mount time (line 120) to determine colors. When the user toggles theme via useUIStore.setTheme, the chart colors (bgColor, textColor, gridColor) are not updated. The chart will remain dark-themed in a light-mode UI or vice versa.
- **Impact:** After a theme toggle, the chart shows wrong background/grid colors: white text on white background (light mode with dark chart) makes the chart entirely unreadable. This is a UX correctness failure that prevents chart analysis.
- **Fix:** Add `theme` from useUIStore to the chart init effect dependencies, or use chart.applyOptions() in a separate useEffect that watches the theme: `useEffect(() => { if (chartRef.current) { chartRef.current.applyOptions({ layout: { background: { color: isDark ? '#0a0f1a' : '#ffffff' }, textColor: ... } }) } }, [theme])`.

### loadData in Charts.tsx calls fetchDecision and fetchDirection on every 5s poll — redundant computation
- **Category:** performance
- **Location:** `frontend/src/pages/Charts.tsx` : 87-108
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** loadData (lines 87-108) is called every 5 seconds (line 112-113). Each call to loadData calls fetchDecision and fetchDirection, triggering backend computations that the comment in strategy.api.ts says involve '67 indicators'. The backend must run the full indicator computation stack on every 5s chart poll. The decision data changes at most on candle close (every 1-15 minutes depending on interval), so 99% of these fetches return unchanged data. The Signals page also polls fetchDecision every 10s independently, meaning if both pages are open the backend runs full indicator computation every 5s from Charts plus every 10s from Signals.
- **Impact:** Unnecessary backend CPU load during market hours. More critically, each fetchDecision call sets isAnalyzing: true globally, which means the loading spinner on Signals.tsx fires every 5 seconds if both pages are mounted (e.g., in split-screen), making the signals display flash.
- **Fix:** Separate candle data polling (5s) from AI decision polling (30s or only on candle close). In loadData, only call fetchDecision in a separate lower-frequency effect. Add a dedicated effect: `useEffect(() => { fetchDecision(symbol, Number(interval)); const t = setInterval(() => fetchDecision(symbol, Number(interval)), 30000); return () => clearInterval(t) }, [symbol, interval])`.

### trade.store.ts refresh() does not include fetchTrades — trade history goes stale after exit/modify actions
- **Category:** data-integrity
- **Location:** `frontend/src/store/trade.store.ts` : 192-199
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** The refresh() method (lines 192-199) calls fetchActiveTrades, fetchPositions, fetchDailyPnl, and fetchLimits but not fetchTrades. After exitTrade or modifyTrade, refresh() is called but the trade history (trades[] array) is not updated. A just-closed trade will still appear in activeTrades momentarily, and the historical P&L record for that trade is not refreshed.
- **Impact:** After manually exiting a trade on the Trades page, the user sees the exit action succeed but the trade history table does not update to reflect the closed trade. They must click 'Refresh' again to see the closed trade. In a scalping environment with multiple trades per day, this creates operational confusion about which trades have been closed.
- **Fix:** Add `get().fetchTrades()` to the refresh() call in trade.store.ts. To avoid excessive history fetches on every active-trade poll, add a separate lightweight refresh for history that only runs after explicit exit/modify actions, not on the polling interval.

### SIGNAL_THRESHOLDS has identical value for weakBullish and weakBearish (both 0.45) — neutral zone is undefined
- **Category:** accuracy
- **Location:** `frontend/src/config/index.ts` : 74-80
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** config.SIGNAL_THRESHOLDS (lines 74-80): weakBullish: 0.55, neutral: 0.45, weakBearish: 0.45. The weakBearish threshold is identical to the neutral threshold. A confidence score of 0.45 would be simultaneously classified as both NEUTRAL and weakBearish. The thresholds imply a 5-way classification but the neutral zone has no range — it is a single point. However these constants are not actually used anywhere in the frontend code; they exist in config but no component reads them to classify signals. The backend makes the BULLISH/BEARISH/NEUTRAL determination. Still, if they are intended for future frontend filtering, the logic is broken.
- **Impact:** If these thresholds are used for frontend filtering of AI signals (e.g., hiding low-confidence signals), the neutral band is undefined and any confidence score in [0, 0.45] triggers both neutral and bearish classifications. Currently low impact since they are unused, but creates a latent bug if implemented.
- **Fix:** Fix the threshold values: weakBullish: 0.55, neutral_upper: 0.55, neutral_lower: 0.45, weakBearish: 0.30. Define a proper range-based classification function. If these are truly unused, remove them from config or add a TODO comment.

### Signals.tsx risk/reward calculation divides by zero when entry price equals stop loss
- **Category:** correctness
- **Location:** `frontend/src/pages/Signals.tsx` : 297
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** Line 297 computes risk/reward: `((Math.abs(pat.target - pat.entry)) / (Math.abs(pat.entry - pat.stop_loss))).toFixed(1)`. If pat.entry === pat.stop_loss (which can happen if the backend returns a pattern with a stop loss at the current price), the denominator is 0, producing Infinity or NaN, displayed as 'Infinity' or 'NaN' in the UI.
- **Impact:** Displays 'Infinity' as the risk/reward ratio in a trading UI. This is misleading — a trader might interpret an 'Infinity R:R' as a perfect trade and act on a pattern that actually has a defective stop loss value.
- **Fix:** Guard the calculation: `const risk = Math.abs(pat.entry - pat.stop_loss); const reward = Math.abs(pat.target - pat.entry); const rr = risk > 0 ? (reward / risk).toFixed(1) : 'N/A';`

### auth.store initialize() trusts localStorage JSON blindly — malformed user data is silently cleared without session preservation
- **Category:** security
- **Location:** `frontend/src/store/auth.store.ts` : 27-39
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** initialize() reads the user from localStorage (line 29-30) and sets isAuthenticated:true without any server-side token validation. An attacker with access to localStorage (XSS) can inject a crafted user JSON and gain authenticated UI access. The token is a JWT but its signature is never verified on the frontend (which is acceptable) — however the lack of any server ping means an invalidated/revoked token still grants UI access until the first API call triggers a 401.
- **Impact:** If a user's session is revoked server-side (e.g., logout from another device, API key rotation), the frontend still shows the dashboard and allows navigation to all protected routes. The first polling call will trigger a redirect, but the trader has a window where they believe they are monitoring live positions when the backend has terminated their session.
- **Fix:** On initialize(), after setting state from localStorage, fire a background fetchUser() call to validate the token server-side. If fetchUser fails (401), clear state and redirect. This adds one API call on app load but ensures session integrity. Pattern: `set({ user, isAuthenticated: true }); get().fetchUser().catch(() => { localStorage.removeItem('access_token'); set({ user: null, isAuthenticated: false }) })`.

### Strategy.tsx loadExpiries includes form.expiry in dependency array — can trigger infinite re-fetch loop
- **Category:** correctness
- **Location:** `frontend/src/pages/Strategy.tsx` : 150-163
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** loadExpiries useCallback (lines 150-163) includes `form.expiry` in its dependency array (line 163). The useEffect at line 202-207 depends on loadExpiries. When loadExpiries sets a new expiry via `setForm(f => ({ ...f, expiry: list[0] }))` (line 156), this triggers a form state change, which changes the loadExpiries reference (because form.expiry changed), which triggers the useEffect again, which calls loadExpiries again. This is a circular dependency.
- **Impact:** On opening the strategy form, loadExpiries may be called in a rapid loop until form.expiry stabilizes at list[0]. This fires multiple unnecessary API calls to /instruments/expiries/:index and creates a burst of backend load. The loop terminates because the second call also gets the same expiry list and sets the same value, so it is bounded — but it is still wasteful and shows multiple loading spinners.
- **Fix:** Remove form.expiry from the loadExpiries useCallback dependency array. The expiry auto-selection inside loadExpiries should use a ref or a separate effect that only fires when expiries[] changes, not as part of the callback itself.

### Multiple concurrent polling loops with no coordination — open tabs create exponential backend load
- **Category:** performance
- **Location:** `frontend/src/pages/Charts.tsx` : 110-114
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** There is no global polling manager. Each page that is mounted sets its own independent setInterval timers. If a user has Dashboard + Signals + Charts open simultaneously (multiple tabs or a split-view scenario), the backend receives: Direction polls every 30s (Dashboard), Decision polls every 5s (Charts) + 10s (Signals) simultaneously, Candle polls every 5s (Charts), Active trade polls every 10s (Trades). The page-visibility API is not used to pause polling when a tab is hidden.
- **Impact:** With three pages open, the backend receives ~24 API calls per minute during market hours. Each decision fetch triggers 67-indicator computation on the backend. This creates unnecessary load that can delay actual broker API calls for order execution.
- **Fix:** Implement a polling manager singleton (or React context) that coordinates intervals and uses the Page Visibility API: `document.addEventListener('visibilitychange', () => { if (document.hidden) pausePolling() else resumePolling() })`. Consider using React Query or SWR which have built-in refetchOnWindowFocus, staleTime, and background refetch management.

---

## LOW

### OHLC string parser splits on first colon only — fails for values with colons (e.g., datetime strings)
- **Category:** correctness
- **Location:** `backend/services/groww_client.py` : 168-189
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** _parse_ohlc_string() at line 185 does k, v = part.split(':'), which raises ValueError if 'v' contains a colon (e.g., if Groww ever returns a timestamp like '2024-06-06T09:15:00'). The format is currently documented as numeric values, so this is low risk, but the split is not guarded.
- **Impact:** If Groww changes its OHLC format to include time components, the parser will crash and all quote lookups will return zeros silently.
- **Fix:** Use k, v = part.split(':', 1) to split on only the first colon, making the parser robust to value changes.

### MongoDB singleton is not thread-safe for index creation — may produce warnings/errors in multi-threaded Flask
- **Category:** correctness
- **Location:** `backend/database/mongodb.py` : 42-72
- **Subsystem:** API & Entry Layer — Flask app wiring, blueprints, JWT auth, request validation, error handling, market/strategy/trade/settings/instruments routes
- **Detail:** _create_indexes() at line 42 is called during __new__ singleton initialization. If two threads happen to trigger the singleton's first initialization simultaneously (unlikely with Python's GIL but possible at process start with gunicorn pre-fork), both may attempt to create the same indexes. The try/except at line 71 catches and ignores this. The unique compound index on candles (line 70) is critical for correctness; silent swallowing of its creation error could leave the collection without the duplicate-prevention guarantee.
- **Impact:** Low probability, but if the unique index silently fails to create, duplicate candle entries can accumulate in MongoDB, causing incorrect candle counts and inflated indicator calculations.
- **Fix:** Log index creation failures at WARNING level rather than silently passing. Separate index creation from object initialization and call it explicitly at app startup with explicit error reporting.

### CandleService.get_candles uses an in-memory reverse of a DESC-sorted result instead of ASC sort
- **Category:** performance
- **Location:** `backend/services/candle_service.py` : 249-253
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** Line 250 queries with .sort('timestamp', -1).limit(limit) then line 253 does candles[::-1]. MongoDB returns in DESC order, Python reverses in memory. The compound index on (symbol, interval, timestamp DESC) at mongodb.py:70 supports DESC efficiently, but the data is then fully copied in memory for every call.
- **Impact:** Minor: every candle read creates a full list copy. For limit=50000 (used in scheduler.py:206), this copies 50,000 dicts in memory. More critically, the compound unique index has timestamp DESCENDING but MongoDB sort on 'timestamp' with -1 will use the index; this is fine, but ASC sort may require a different index.
- **Fix:** Change to .sort('timestamp', 1) (ASC) to get chronological order directly, and remove the [::-1] reversal. Add (symbol, interval, timestamp ASC) as the retrieval index alongside the unique constraint.

### SUPPORTED_UNDERLYINGS missing from config.py - InstrumentSync falls back to hardcoded list with MIDCPNIFTY/FINNIFTY which may not be available
- **Category:** correctness
- **Location:** `backend/services/instrument_sync.py` : 15
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** InstrumentSync.__init__ uses `config.SUPPORTED_UNDERLYINGS if hasattr(config, 'SUPPORTED_UNDERLYINGS') else ['NIFTY', 'BANKNIFTY', 'SENSEX', 'FINNIFTY', 'MIDCPNIFTY']`. The config.py file does not define SUPPORTED_UNDERLYINGS at all, so the hardcoded fallback is always used. FINNIFTY and MIDCPNIFTY are included but GrowwClient.filter_fno_instruments and groww_client.get_historical_candles do not have symbol mappings for them.
- **Impact:** If Groww's CSV uses different underlying_symbol values for FINNIFTY or MIDCPNIFTY, those instruments are silently excluded from the DB. If they are included but have no symbol map entry, candle fetches use the raw name which may fail.
- **Fix:** Add SUPPORTED_UNDERLYINGS to config.py. Verify Groww CSV column values for all underlyings and align the symbol_map in get_historical_candles to cover them.

### Dashboard direction poll fires fetchAllDirections() synchronously on button click without isBackground flag — causes spinner flash during manual refresh
- **Category:** correctness
- **Location:** `frontend/src/pages/Dashboard.tsx` : 274, 366
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** Two call sites call fetchAllDirections() without the isBackground=true argument: handleRefresh line 274 and the inline refresh button at line 366. These trigger set({ isLoading: true }) in direction.store.ts:48, which causes the DirectionStore loading state to flash. Since the direction cards on Dashboard do not visually react to the direction store's isLoading, this is a minor inconsistency — but if any child component reads isLoading it will flicker unnecessarily.
- **Impact:** Low visual impact but may cause brief UI instability if other components conditionally render on direction store's isLoading state.
- **Fix:** Pass isBackground=true in both call sites on Dashboard since they are user-triggered refreshes that should not disrupt the live direction panel. Only the initial mount fetch should pass false.

### loadExpiries in Strategy.tsx has stale closure on form.expiry — may skip auto-setting first expiry on re-renders
- **Category:** correctness
- **Location:** `frontend/src/pages/Strategy.tsx` : 151-163
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** loadExpiries is a useCallback with dependency [editingStrategy, form.expiry]. The closure captures form.expiry at creation time. If form.expiry is already set (from the defaultForm or from an editingStrategy), the condition !form.expiry on line 155 evaluates against the stale captured value. When the user changes the index, loadExpiries is re-created (form.expiry dep changes), but there is a render cycle gap during which an old loadExpiries runs with the previous form.expiry and may skip auto-setting.
- **Impact:** When editing a strategy and changing the index, the expiry dropdown may not auto-select the first available expiry for the new index, leaving the form in an inconsistent state requiring manual selection.
- **Fix:** Remove form.expiry from the useCallback dependency and instead pass it as a parameter to loadExpiries. This avoids the stale closure entirely: loadExpiries = useCallback(async (index, currentExpiry) => { ... if (!currentExpiry) setForm(...) }, [editingStrategy]).

### App.tsx useEffect for initialize() has empty dependency array but missing `initialize` in deps — ESLint exhaustive-deps violation
- **Category:** maintainability
- **Location:** `frontend/src/App.tsx` : 31-33
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** useEffect(() => { initialize() }, []) should include `initialize` in its dependency array per React's exhaustive-deps rule. While initialize() is a stable Zustand action and will not change between renders, the omission suppresses the lint warning and is a pattern that can mask real bugs when copy-pasted. The same pattern appears in Strategy.tsx:93-96 (fetchStrategies, fetchSyncInfo missing from deps) and multiple other pages.
- **Impact:** No runtime impact with current stable Zustand actions, but creates a code review smell and could cause issues if the action functions were ever changed to be instance-unstable.
- **Fix:** Add `initialize` to the dep array or suppress with an explicit // eslint-disable-next-line comment and a justification. Audit all pages for the same pattern and apply consistently.

### Signals.tsx lastUpdated state is set client-side at fetch-initiation time, not at data-receipt time
- **Category:** accuracy
- **Location:** `frontend/src/pages/Signals.tsx` : 27, 33-34
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** setLastUpdated(new Date()) is called at line 34 immediately after await fetchDecision completes. This is the client-side time of fetch completion, not the timestamp of when the backend computed the decision. If the backend decision was computed 30 s ago and cached, the displayed 'Updated:' time will be misleadingly current. The Decision type has no top-level timestamp field (though individual component data may have timestamps).
- **Impact:** The 'Updated' timestamp shown to the user reflects when the HTTP response arrived, not when the signal was generated. A cached backend response could make a 30 s old signal appear fresh.
- **Fix:** Use a timestamp from the decision data itself if available (e.g. decision.timestamp or decision.generated_at). Fall back to current time only if the decision has no timestamp. Display the source of the timestamp clearly (e.g. 'Computed at' vs 'Fetched at').

### market.store.ts fetchMarketStatus errors are silently swallowed — stale marketStatus shown without any indication
- **Category:** correctness
- **Location:** `frontend/src/store/market.store.ts` : 32-39
- **Subsystem:** Frontend — Real-Time UI & State (Groww NIFTY F&O Scalping)
- **Detail:** fetchMarketStatus catch block only logs to console.error. marketStatus is never cleared on error, so the Dashboard shows the last known market status (open/closed) indefinitely even if the backend becomes unreachable. During a backend outage, the Dashboard will show 'Market Open' with animated green dot when the market data source is down.
- **Impact:** False sense of market connectivity. The user cannot distinguish between a live market feed and a stale/disconnected state from the UI.
- **Fix:** Track a lastMarketStatusFetch timestamp and/or a marketDataError boolean in the store. Display a 'Data unavailable' indicator on the Dashboard when the last successful fetch is more than N seconds ago or when consecutive errors occur.

### signal can be None (neutral/below-threshold) and is silently dropped; no NEUTRAL handling in engine
- **Category:** correctness
- **Location:** `backend/services/trading_engine.py + backend/analysis/decision_engine.py` : trading_engine.py:145-169; decision_engine.py:131-133,316
- **Subsystem:** Groww trading-engine wiring, signal/candle data consumption, and dead-code audit (backend/)
- **Detail:** decision_engine sets signal=None when confidence < 0.70 (L133) and in _empty_result (L316). evaluate_strategies reads signal and only acts on exact 'BULLISH'/'BEARISH' (L166-169), so None is correctly ignored — but note this means decision_engine has its OWN hard 0.70 gate independent of the per-strategy min_confidence, so a strategy with min_confidence below 70 can never receive a sub-70 signal regardless of its setting.
- **Impact:** Per-strategy confidence tuning below 70% is impossible; the engine-internal 0.70 threshold overrides it. Combined with the scale bug above, effective behavior is opaque.
- **Fix:** Expose the raw confidence/signal independent of the 0.70 cutoff (e.g. return signal even when below threshold and let the strategy gate decide), or document that 70% is a hard floor.

### Per-trade synchronous LTP REST calls inside the 5s heartbeat can overrun the tick
- **Category:** performance
- **Location:** `backend/services/trading_engine.py + backend/services/scheduler.py` : trading_engine.py:77-108,192; scheduler.py:55-61,165
- **Subsystem:** Groww trading-engine wiring, signal/candle data consumption, and dead-code audit (backend/)
- **Detail:** monitor_active_trades calls _get_option_ltp per open trade (L192), which in LIVE mode does a synchronous Groww REST get_ltp with no batching (L90) and _get_order_fill_price retries with time.sleep(0.5) (L411). The heartbeat IntervalTrigger is 5s with max_instances=1; with several open trades the tick can exceed 5s and APScheduler will skip subsequent fires.
- **Impact:** Under load, SL/target monitoring frequency degrades unpredictably; missed ticks delay protective exits.
- **Fix:** Batch option LTP fetches into a single get_ltp call per heartbeat, cache option LTPs in Redis like index LTPs, and avoid blocking sleeps in the hot path.

### Misleading comment references nonexistent 'candles_1min' collection
- **Category:** maintainability
- **Location:** `backend/services/scheduler.py` : 199-206
- **Subsystem:** Groww trading-engine wiring, signal/candle data consumption, and dead-code audit (backend/)
- **Detail:** Comment says sync 'saves to candles_1min collection' (L199) but candle_service writes to the single db.candles collection keyed by interval string (candle_service.py:216-217, mongodb.py:35). Storage IS consistent — only the comment is wrong.
- **Impact:** Misleads maintainers into looking for a separate collection; low functional risk.
- **Fix:** Fix the comment to reference db.candles keyed by interval.

### Pollers run unconditionally regardless of market-open state or tab visibility; hardcoded NIFTY decision
- **Category:** performance
- **Location:** `frontend/src/components/layout/Layout.tsx; frontend/src/pages/Charts.tsx` : Layout.tsx:34-54,27,40; Charts.tsx:112
- **Subsystem:** Real-time price/candle data pipeline (Groww API -> backend cache/Redis/Mongo -> decision & direction engines -> Flask routes -> React/Zustand stores -> chart UI)
- **Detail:** Layout sets unconditional setInterval timers (3-10s) and fetchDecision('NIFTY',5) is hardcoded, ignoring the user's selected symbol. Timers keep firing when the market is closed and when the browser tab is hidden (no visibilitychange gating). The backend short-circuits closed-market work, so these become wasted requests that also keep refreshing the never-expiring direction cache view.
- **Impact:** Wasted requests/CPU off-hours; decision shown in global UI is always NIFTY even when viewing BANKNIFTY; no backpressure if a request is slow (overlapping intervals).
- **Fix:** Gate polling on marketStatus.is_open and document.visibilityState; drive fetchDecision off the selected symbol; use a self-rescheduling timeout (await then setTimeout) instead of fixed setInterval to avoid overlap.

### Candle save/upsert race and full-delete path can transiently drop or duplicate the latest candle
- **Category:** data-integrity
- **Location:** `backend/services/candle_service.py; backend/database/mongodb.py` : candle_service.py:212-217; mongodb.py:76-117
- **Subsystem:** Real-time price/candle data pipeline (Groww API -> backend cache/Redis/Mongo -> decision & direction engines -> Flask routes -> React/Zustand stores -> chart UI)
- **Detail:** _save_to_db (full sync) does delete_many then insert_many non-atomically; a concurrent get_candles between the two can read an empty set. The 1m sync (full mode in sync_and_aggregate) re-deletes and re-inserts the whole window each minute. Aggregation upserts derive the last (forming) bucket, so the most recent higher-tf candle is rewritten each minute (expected) but combined with the timezone bug can create duplicate timestamps under the unique index (E11000 swallowed at mongodb.py:116).
- **Impact:** Brief windows where the chart/decision sees zero or partial candles right after a sync; swallowed E11000 can hide real bucketing bugs.
- **Fix:** Use upsert for 1m as well (avoid delete_many in the live path), or wrap replace in a single bulk operation. Don't blanket-swallow E11000 without counting; alert if duplicate rate is high (it signals timestamp bugs).

### No market-holiday calendar or pre/post-auction handling in is_market_open
- **Category:** accuracy
- **Location:** `backend/utils/time_utils.py` : time_utils.py:16-28
- **Subsystem:** Real-time price/candle data pipeline (Groww API -> backend cache/Redis/Mongo -> decision & direction engines -> Flask routes -> React/Zustand stores -> chart UI)
- **Detail:** is_market_open only checks weekday and 09:15-15:30 IST. It ignores NSE/BSE trading holidays and special sessions. On holidays the schedulers will attempt fetches (Groww returns empty, mostly harmless) but the direction cache stays stale-from-Friday and any candle window math in _get_smart_window can pick a holiday as 'last trading day'.
- **Impact:** Stale signals presented as live on holidays; smart-window can choose an empty/holiday day yielding 'No data' errors.
- **Fix:** Add an exchange holiday calendar (config or library) to is_market_open and to _get_smart_window's last-trading-day selection.

### Redis direction cache serialized with str(dict) and exception path swallows engine errors as NEUTRAL
- **Category:** data-integrity
- **Location:** `backend/services/direction_scheduler.py` : 139
- **Subsystem:** Groww Decision / Market-Direction Signal Engine
- **Detail:** redis_client.set(f'direction:{symbol}', str(result), ex=10) stores Python repr of a dict, which is not round-trippable JSON (single quotes, None/True) — any cross-process consumer must ast.literal_eval, and NaN/inf would break it. Separately, market_direction_engine.analyze catches all exceptions and returns a NEUTRAL result (lines 247-249), so a bug in any sub-analyzer silently degrades to NEUTRAL with no alerting.
- **Impact:** Brittle cross-process data and silent signal degradation; a partial failure looks identical to a genuinely neutral market, masking accuracy problems.
- **Fix:** Serialize with json.dumps using the existing to_python_type sanitizer; log/metric on the exception path and surface a 'degraded' flag instead of an indistinguishable NEUTRAL.

### safe_div helper is broken for scalar inputs and is effectively unused
- **Category:** correctness
- **Location:** `backend/analysis/momentum/indicators.py` : 8-10
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** np.full_like(a, default, dtype=float) requires a to be array-like; called with Python scalars it will misbehave, and the function is not actually used by any indicator (each re-implements its own guard). Dead, misleading code.
- **Impact:** Maintenance hazard; if someone uses it with scalars it raises or returns wrong shape. Low direct trading impact.
- **Fix:** Remove it or fix to handle scalars (np.asarray(a, float)); centralize division guards so all indicators use one tested helper.

### Bollinger/HV/CV use sample std (ddof=1) / inconsistent normalization across the codebase
- **Category:** accuracy
- **Location:** `backend/analysis/volatility/indicators.py` : bollinger pd.std L49 (ddof=1); historical_vol np.std L129 (ddof=0); realized_vol L318
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** pandas .std() defaults to ddof=1 (sample) while np.std defaults to ddof=0 (population). Bollinger bands here are slightly wider than the conventional population-std bands most platforms use, and HV vs RV use different denominators. Minor but causes mismatch with reference charts.
- **Impact:** Small but systematic deviation of band width and vol numbers from standard tools; thresholds (percent_b, regimes) drift slightly.
- **Fix:** Standardize ddof. Bollinger conventionally uses population std (ddof=0); set explicitly and document.

### Flag detector compares percentage flagpole move to a normalized-range consolidation incorrectly
- **Category:** accuracy
- **Location:** `backend/analysis/patterns/primary/patterns.py` : 199-203
- **Subsystem:** Indicators & Patterns (backend/analysis: momentum, volatility, support_resistance, patterns)
- **Detail:** prior_move is a return ((prior[-1]-prior[0])/prior[0]) while recent_range is (max-min)/mean of the last 10 — different bases. The 0.03 vs 0.02 thresholds are not on comparable scales and 'lookback=15' (L195) is unused dead code. Also no slope/down-channel check for the flag itself.
- **Impact:** Flags fire on arbitrary low-range periods after any 3% move; quality is low.
- **Fix:** Define consolidation relative to flagpole size (e.g., retrace < 50% of pole) and verify a counter-trend channel; remove dead variable.

### market_regime classification is shallow and TRENDING is currently unreachable
- **Category:** accuracy
- **Location:** `backend/analysis/decision_engine.py` : 136-141
- **Subsystem:** Decision & Direction Engine (backend/analysis)
- **Detail:** Regime is HIGH-vol->VOLATILE else (pattern_signal==momentum_signal and !=NEUTRAL)->TRENDING else RANGING. Because _analyze_patterns is broken (always NEUTRAL, see critical issue), pattern_signal can never equal a non-NEUTRAL momentum_signal, so 'TRENDING' is unreachable until the pattern key bug is fixed; nearly everything is VOLATILE or RANGING. There is no ADX/structure-based trend confirmation despite ADX being computed.
- **Impact:** The regime label fed to UI/strategies is misleading; any regime-conditional logic gets the wrong context.
- **Fix:** After fixing the pattern key, base regime on ADX/EMA-slope + Bollinger bandwidth rather than pattern==momentum coincidence, and unit-test that each regime is reachable.

### monitor_active_trades index filter via substring match is fragile and can monitor/skip wrong trades
- **Category:** correctness
- **Location:** `backend/services/trading_engine.py` : 183
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** The filter `if index_symbol not in trade.get('symbol','')` uses substring containment. 'NIFTY' is a substring of 'BANKNIFTY' and 'FINNIFTY', so a NIFTY heartbeat will also process BANKNIFTY/FINNIFTY trades (and vice-versa depending on ordering), potentially monitoring a trade twice or with the wrong index context.
- **Impact:** Trades may be evaluated multiple times per cycle or attributed to the wrong index tick, causing redundant LTP fetches and possible duplicate exit attempts.
- **Fix:** Store the underlying index on the trade record and match exactly (trade['index']==index_symbol), rather than substring matching on the option symbol.

### trailing SL update is the only post-entry SL adjustment; break-even and partial-exit logic exist but are never wired in
- **Category:** maintainability
- **Location:** `backend/utils/risk_manager.py` : 137-179
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** calculate_break_even_sl and calculate_partial_exit are implemented but never called by the engine. check_sl_target in paper_broker accepts partial_target_1 but execute_exit always sells full trade['quantity'] and never handles PARTIAL_TARGET_1 specially (it would close the whole trade and mislabel it).
- **Impact:** Documented risk features (break-even, scaling out) are dead code; if a partial_target_1 is set, a PARTIAL_TARGET_1 trigger fully exits the position, contradicting intent.
- **Fix:** Either remove the unused functions or wire them: call calculate_break_even_sl in monitor loop, and on PARTIAL_TARGET_1 sell calculate_partial_exit(qty) and keep the remainder open with updated SL.

### _get_user_execution_mode re-queried on every _get_broker call adds DB round-trips into the hot path
- **Category:** performance
- **Location:** `backend/services/trading_engine.py` : 68-75, 42-61
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** _get_broker calls _get_user_execution_mode every time, which does db.get_user_by_id when settings lacks execution_mode. _get_broker is invoked in execute_entry and execute_exit, inside the per-tick loop, adding synchronous DB calls during time-sensitive order placement.
- **Impact:** Extra latency on the critical order path and repeated DB load every 5s per trade; can contribute to heartbeat overrun.
- **Fix:** Resolve execution_mode once per heartbeat (or cache with short TTL) and pass it down; avoid per-order DB lookups.

### Bare/broad exception swallowing hides LTP and account failures
- **Category:** correctness
- **Location:** `backend/services/paper_broker.py` : 68-69, 113-114
- **Subsystem:** Trading Engine & Paper Broker (NIFTY F&O scalping, Groww broker)
- **Detail:** _calculate_unrealized_pnl uses a bare `except: pass` (68-69) and get_ltp catches all exceptions returning 0 with only a print. Failures (auth expiry, malformed payload) are silently treated as 'no price', which downstream code interprets as a benign skip.
- **Impact:** Real-time failures (e.g., token expiry mid-session) masquerade as missing prices: monitoring silently skips exits and unrealized P&L silently drops contributions, so the user gets no signal that risk management has stopped functioning.
- **Fix:** Catch specific exceptions, log with context, and surface a health flag (e.g., increment an error counter / raise an alert) when LTP fetch fails repeatedly so monitoring degradation is visible.

### get_user_by_id and get_strategy_by_id use bare except, hiding real DB errors
- **Category:** maintainability
- **Location:** `backend\database\mongodb.py` : 148-149,183,224
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** These methods wrap find_one in try/except returning None on ANY exception, including connection errors and BSON errors, conflating 'not found' with 'database down' or 'malformed id'.
- **Impact:** Transient DB outages surface as 'not found', which can be misinterpreted upstream (e.g., treating a missing user as unauthenticated) and masks operational issues that affect real-time trading reliability.
- **Fix:** Catch only bson.errors.InvalidId for the ObjectId conversion; let genuine pymongo errors propagate or be logged distinctly so outages are visible and not silently treated as missing data.

### upsert_candles bulk_write swallows non-duplicate errors with only a print
- **Category:** data-integrity
- **Location:** `backend\database\mongodb.py` : 110-117
- **Subsystem:** Data, Models & Risk Utils (MongoDB, models, risk_manager, time_utils, encryption, checksum)
- **Detail:** On bulk_write failure, only E11000 is filtered; any other error is printed and ignored, with no return signal to the caller and no metric. Partial writes under ordered=False leave gaps silently.
- **Impact:** Silent partial candle ingestion produces gaps in the time series that the analysis layer (which requires len>=20) may not detect, leading to subtly wrong indicators and signals.
- **Fix:** Return write counts/errors to the caller, log structured errors, and surface a data-gap alert if expected-vs-written counts diverge. Consider verifying contiguity of timestamps after ingestion.

### Visualizer maps trades to candles by time_str only — collides across days and on duplicate times
- **Category:** correctness
- **Location:** `backend/groww/nifty_scalper_bt.py` : 366-393
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** generate_html locates entry/exit datetimes via df.loc[df['time_str']==t.entry_time,'dt'].values[0]. time_str is HH:MM, so for multi-day data the first matching day is always picked, mislocating markers; for two trades at the same minute it also collides. IndexError is swallowed (:393), silently dropping markers.
- **Impact:** Misleading visual validation — markers can appear on the wrong day/bar, undermining the manual sanity-check the visualizer exists for.
- **Fix:** Carry the full timestamp on each Trade (entry_ts/exit_ts) and match on ts, not on HH:MM string. Surface dropped markers as warnings instead of silently continuing.

### No NIFTY trading-holiday / market-closed handling; get_trading_dates referenced but absent
- **Category:** data-integrity
- **Location:** `backend/groww/run_backtest.py / backend/groww/nifty_scalper_bt.py` : run_backtest.py:10,34; nifty_scalper_bt.py (absent)
- **Subsystem:** Scanner & Backtest (NIFTY F&O scalping) — backend/groww/New/opportunity_scanner.py, backend/groww/New/run_scanner.py, backend/groww/nifty_scalper_bt.py, backend/groww/run_backtest.py, backend/groww/GrowwAPI.py
- **Detail:** run_backtest.py references get_trading_dates(5, end_date=...) to build a trailing trading-day window, but the function does not exist in the module. There is also no holiday calendar; fetch_smart's days_back uses calendar days, so weekends/holidays silently shorten the indicator warm-up window inconsistently.
- **Impact:** Warm-up windows vary unpredictably (a Monday test date with 7 calendar days back may include only ~4-5 sessions), changing EMA/RSI/ATR seeds and thus signals; and the trailing-N-days helper is unusable.
- **Fix:** Implement get_trading_dates with an NSE holiday calendar; specify warm-up in sessions not calendar days; assert the required number of warm-up bars exist before generating signals.

### direction_scheduler last_update uses datetime.now() (naive/local) — inconsistent with IST-aware get_ist_now()
- **Category:** correctness
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\direction_scheduler.py` : 136
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** self.last_update[symbol] = datetime.now() uses naive local datetime. The get_status() method at line 154 serialises these as .isoformat() with no timezone — the returned JSON will show local-timezone times that may be incorrect for UTC servers, mixing naive timestamps with the IST-aware timestamps used elsewhere.
- **Impact:** Monitoring dashboards or logs using direction scheduler status will display incorrect last-update times on UTC servers, making it hard to diagnose staleness or verify the scheduler is running during market hours.
- **Fix:** Replace datetime.now() with get_ist_now() (already imported at line 17) so last_update timestamps are timezone-aware IST values.

### RedisClient singleton _initialize comment '# ... (Rest of the methods...)' — code appears truncated
- **Category:** maintainability
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\database\redis_client.py` : 40
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** Line 40 contains a comment '# ... (Rest of the methods: get, set, cache_ltp remain exactly the same) ...' which is copy-paste documentation left in production code. The methods are present but the comment implies this is a partial/stub file, which is confusing for maintenance and may indicate other methods were intended but not implemented (e.g., delete, expire, hset for more structured data).
- **Impact:** Low direct impact, but signals incomplete implementation. If future developers look for additional Redis helpers (e.g., for candle caching, session management) they may not add them here, leading to scattered Redis usage.
- **Fix:** Remove the comment. Add commonly needed methods: delete(key), exists(key), hset/hget for structured data, and a health_check() method.

### GrowwClient.download_instruments() has no authentication — fails silently if URL returns 403/non-CSV
- **Category:** correctness
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\groww_client.py` : 684-695
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** download_instruments() uses requests.get() with only raise_for_status() error handling. If the Groww CDN URL returns a non-CSV (e.g., an HTML error page), pd.read_csv() will parse the HTML as CSV, returning a DataFrame with garbage column names but no exception. The instrument_sync job will then call _prepare_instruments() on a corrupted DataFrame, potentially inserting invalid records.
- **Impact:** If the instruments URL ever changes or returns an error page, the DB could be populated with malformed instrument records. This would cause all ATM strike lookups and FNO order placement to fail silently.
- **Fix:** After response.raise_for_status(), validate the content-type header is 'text/csv' or 'application/octet-stream', and validate that expected column names (trading_symbol, exchange, segment) exist in df.columns before proceeding.

### scheduler.active_user_id set at start() but never used — _get_active_user() queries DB on every job run
- **Category:** performance
- **Location:** `c:\Users\Akshay Thakare\Desktop\Project\ai_trading\Groww\backend\services\scheduler.py` : 104-113
- **Subsystem:** Real-time Data & Scheduling
- **Detail:** self.active_user_id is set in start() (line 107) but is never referenced again. Every job (heartbeat, sync, reconcile) calls self._get_active_user() which performs a fresh DB lookup instead of using the cached self.active_user_id. The start-time assignment is dead code.
- **Impact:** Minor: one extra DB query per heartbeat tick (12/min). The cached ID is not used for anything, so it provides no benefit. If the user's broker_connected state changes, the cached ID would be stale anyway — but since it is never used, there is no actual bug.
- **Fix:** Either remove self.active_user_id entirely and document that _get_active_user() is always called live, or actually use it with a proper refresh mechanism.

### ui.store setTheme fires background API call without error propagation — theme can diverge between frontend and backend
- **Category:** data-integrity
- **Location:** `frontend/src/store/ui.store.ts` : 89-93
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** setTheme (lines 89-93) calls `settingsApi.updateTheme(theme).catch(console.error)` as a fire-and-forget. If the API call fails, localStorage and the React state show the new theme, but the backend settings still hold the old theme. On next login or page refresh, fetchSettings will restore the backend theme, overriding the user's local preference.
- **Impact:** Low severity: a theme preference mismatch is not a safety issue. However if the backend theme is used to control anything beyond visual styling (e.g., if it feeds into a settings export), the divergence creates data integrity problems.
- **Fix:** Either make setTheme async and propagate the error (showing a toast if backend update fails while keeping localStorage), or designate localStorage as the sole source of truth for theme and remove the backend sync. Currently App.tsx line 47-48 also writes to localStorage independently, creating triple storage of the same value.

### ui.store addToast setTimeout not cleared on early removeToast — potential double-removal
- **Category:** correctness
- **Location:** `frontend/src/store/ui.store.ts` : 99-108
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** addToast creates a setTimeout (line 106) that calls removeToast(id) after `duration` ms. If removeToast is called earlier (e.g., user manually dismisses), the setTimeout still fires and calls removeToast again with the same id. The second call does a filter that finds no matching toast (already removed) and sets toasts to the same filtered array — harmless but wastes a re-render.
- **Impact:** Minor: unnecessary setState call causes a render. In rapid-trading scenarios with many toasts, this could accumulate. Not a correctness bug since the filter handles missing ids gracefully.
- **Fix:** Store the timer ID and clear it in removeToast: `const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})`. In addToast: `timers.current[id] = setTimeout(...)`. In removeToast: `clearTimeout(timers.current[id]); delete timers.current[id]`. This also ensures timers are cleaned up when the component unmounts.

### RSI calculateRSI missing first data point: first RSI value emitted at period+1 skipping period index
- **Category:** accuracy
- **Location:** `frontend/src/utils/indicators.ts` : 33-62
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** calculateRSI initializes avgGain and avgLoss over indices 1 through period (line 38-42), then emits RSI values starting at index period+1 (line 48). The RSI value corresponding to index `period` (the last candle of the initial window) is never emitted. Standard RSI implementations emit the first value at index `period`, not `period+1`. With period=14, this skips one valid RSI data point at the start of the series.
- **Impact:** The RSI line on a chart would start one candle later than expected. On a 300-candle dataset this is negligible. However if RSI is ever used for crossover detection (RSI crossing 50, 30, 70), the slightly shifted start could cause a missed signal at the very beginning of the dataset.
- **Fix:** After computing avgGain and avgLoss for the initial window (indices 1 to period), emit the first RSI value before entering the main loop: `const rs0 = avgGain / avgLoss; result.push({ time: getTime(data[period]), value: 100 - (100 / (1 + rs0)) })`. Then start the loop at `i = period + 1`.

### Strategy page ATM offset description has inverted ITM/OTM label for positive offset
- **Category:** accuracy
- **Location:** `frontend/src/pages/Strategy.tsx` : 550
- **Subsystem:** Frontend (real-time UI and state)
- **Detail:** Line 550: `Will select {form.atm_offset === 0 ? 'ATM' : `${form.atm_offset > 0 ? 'OTM' : 'ITM'} ${Math.abs(form.atm_offset)}`} strike.`. For NIFTY options, a positive ATM offset means adding points to the ATM strike, which for a CE option moves it ITM (lower strike for CE is deeper ITM). The config.ATM_OFFSETS also has this inverted: offset +50 is labeled 'ITM 1 (+50)' but the strategy description says OTM for positive values. The two sources contradict each other.
- **Impact:** A trader setting ATM_OFFSET to +50 sees the hint saying 'Will select OTM 50 strike' while the config dropdown label says 'ITM 1 (+50)'. This is confusing and could lead to wrong strike selection — the trader expects an ITM strike but the hint implies OTM.
- **Fix:** The config.ATM_OFFSETS labels should be the source of truth. Fix line 550 to: `form.atm_offset > 0 ? 'ITM' : 'OTM'`. Better yet, look up the label from config.ATM_OFFSETS by value and display that string directly to eliminate the inconsistency entirely.
