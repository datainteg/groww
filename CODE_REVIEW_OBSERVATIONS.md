# Groww Code Review Observations

Date: 2026-06-07

Scope: full repository review of the Flask backend, React/Vite frontend, configuration, tests, and runtime contracts. No application code was changed for this review.

Repository state note: local `main` advanced while this review was being written. This report reflects the current HEAD observed during final verification: `8823fbe`.

## Validation Run

| Check | Result | Notes |
| --- | --- | --- |
| Backend tests | PASS | `python -m pytest -q` -> 164 passed |
| Backend syntax | PASS | `python -m compileall -q .` |
| Frontend build | PASS | `npm run build` completed; Vite warns `caniuse-lite` is outdated |
| Frontend lint | FAIL | `npm run lint` calls `eslint`, but ESLint is not installed/configured |
| Frontend npm audit | FAIL | 4 production vulnerabilities reported: `axios`, `follow-redirects`, `react-router`, `react-router-dom` |
| Python dependency consistency | FAIL | `python -m pip check` reports version conflicts for `awscli`, `neo-api-client`, `pydantic-settings`, and `sse-starlette` |
| Python dependency audit | NOT RUN | `python -m pip_audit -r requirements.txt` failed because `pip_audit` is not installed |

## Executive Summary

The project has a meaningful structure: central safety checks exist, test coverage exists for core analytical modules, config validation is stronger than a typical prototype, and the frontend builds successfully.

The largest gaps are around trade execution consistency, API contract drift, multi-user behavior, production security, and dependency hygiene. Several paths can place or record trades outside the main safety and accounting model. For a trading app, these are not cosmetic issues; they can create real broker positions that the local database does not represent correctly.

Top risks:

1. Direct order placement now has a BUY safety gate, but it can still create positions without local trade records.
2. Manual `SELL` quick trades are recorded as new closed trades, not exits of existing open trades.
3. LIVE exit execution can close a trade at price `0` when broker fill details are unavailable.
4. Dynamic option-symbol lookup sorts by a field that does not exist in the instrument model.
5. Several frontend API calls expect response shapes or routes that the backend does not provide.
6. Admin/global endpoints are authenticated but not authorization protected.
7. Scheduler and calibration logic still need stronger multi-user and reload guarantees.
8. Dependency and lint hygiene are not at production standard.

## Critical And High Findings

### 1. Direct place-order route still bypasses local trade lifecycle persistence

Severity: Critical

Evidence:

- `backend/routes/trade_routes.py:208` to `backend/routes/trade_routes.py:258` implements `/api/trade/place-order`.
- The current HEAD does call `services.trade_safety.validate_trade_allowed` for `BUY` orders before locking.
- The route still directly calls `PaperBroker.place_order` or `GrowwAPIClient.place_order`.
- It still does not create or update a local trade document after order placement.
- `SELL` orders are treated as broker passthrough exits and are not tied to a specific open local trade.
- The central gate exists at `backend/services/trade_safety.py:165` to `backend/services/trade_safety.py:215`.
- The main trading engine entry path does use that gate at `backend/services/trading_engine.py:364` to `backend/services/trading_engine.py:459`.

Impact:

Manual or API-driven orders can create broker or paper positions that are not represented in the local trade table. In PAPER mode, the paper account position changes but the order list reads from the trade table, so positions and order history can disagree. In LIVE mode, a broker position can exist without a local trade row and later reconciliation has to treat it as an unmanaged position.

Recommendation:

Make every order-entry path go through one execution service. Direct routes should either call the trading engine or the same central safety, persistence, and reconciliation workflow. If the route is intended for broker passthrough only, label it clearly and exclude it from normal UI paths.

### 2. Manual quick-trade SELL creates an orphan closed trade instead of exiting an open trade

Severity: High

Evidence:

- `backend/routes/trade_routes.py:633` to `backend/routes/trade_routes.py:785` implements `/api/trade/quick-trade`.
- `BUY` uses the central safety gate, but `SELL` skips it by design at `backend/routes/trade_routes.py:700` to `backend/routes/trade_routes.py:706`.
- The route then creates a new trade document with `status: 'CLOSED'` for a `SELL` at `backend/routes/trade_routes.py:743` to `backend/routes/trade_routes.py:763`.
- The frontend exposes manual SELL buttons at `frontend/src/pages/Trades.tsx:584` to `frontend/src/pages/Trades.tsx:589`.

Impact:

A manual SELL does not locate and close an existing open trade. It records `entry_price` as the sell price and does not compute realized PnL against the original entry. This can corrupt trade history, daily PnL, risk counters, and reconciliation.

Recommendation:

Split manual order entry from manual exit. A SELL that is meant to exit should require a target open trade and should use the same close-trade workflow as `exitTrade`. A naked sell should be modeled separately and should not look like a completed long trade.

### 3. LIVE trade exit can close at price 0 when broker fill price is missing

Severity: High

Evidence:

- `backend/services/trading_engine.py:615` to `backend/services/trading_engine.py:678` executes exits.
- If order placement succeeds but no execution price, average price, or detailed order price is available, `final_exit_price` falls back to `0`.
- PnL is then calculated from that value and the trade is closed in the database.
- Entry execution has a pending reconciliation path at `backend/services/trading_engine.py:494` to `backend/services/trading_engine.py:521`, but exit execution does not have the same protection.

Impact:

A LIVE exit with delayed or missing broker fill data can record a total-loss exit locally even when the actual broker exit happened at a normal price. This can trigger false max-loss behavior, wrong reporting, and incorrect future trade decisions.

Recommendation:

Do not close a LIVE trade with an exit price of `0` unless that is a verified exchange fill. Use a `PENDING_EXIT_RECONCILE` state or retry order-detail lookup before finalizing PnL.

### 4. Dynamic option symbol lookup can select the wrong expiry

Severity: High

Evidence:

- `backend/services/trading_engine.py:325` to `backend/services/trading_engine.py:358` resolves dynamic option symbols.
- The query sorts by `expiry`, but instrument documents use `expiry_date`.
- Instrument sync writes `expiry_date` in `backend/services/instrument_sync.py:69`.
- Mongo indexes use `expiry_date` in `backend/database/mongodb.py:342` to `backend/database/mongodb.py:352`.
- The regex pattern interpolates `index_symbol`, `target_strike`, and `option_type` directly.

Impact:

The engine can choose an arbitrary matching option contract instead of the nearest expiry. In LIVE mode this can place orders in the wrong instrument. Regex-based lookup also makes the contract resolution less reliable than using normalized structured fields.

Recommendation:

Resolve by `underlying_symbol`, `strike_price`, `instrument_type`, and sorted `expiry_date`. Avoid regex for contract selection unless inputs are escaped and used only as a fallback.

### 5. Admin/global mutation endpoints have no role authorization

Severity: High

Evidence:

- Direction scheduler start/stop routes are marked "admin only" in comments but only use `@jwt_required`: `backend/routes/market_routes.py:150` to `backend/routes/market_routes.py:165`.
- Instrument sync is callable by any authenticated user: `backend/routes/instruments_routes.py:10` to `backend/routes/instruments_routes.py:14`.
- Market instrument sync is also callable by any authenticated user: `backend/routes/market_routes.py:452` to `backend/routes/market_routes.py:459`.
- Backtest calibration is callable by any authenticated user: `backend/routes/backtest_routes.py:125` to `backend/routes/backtest_routes.py:137`.
- Instrument sync replaces global collections through staging rename in `backend/database/mongodb.py:314` to `backend/database/mongodb.py:336`.

Impact:

Any authenticated account can mutate global operational state, trigger heavy sync work, train or overwrite calibration, and start or stop shared schedulers. This is a multi-user security and stability risk.

Recommendation:

Add explicit role/permission checks for global operations. If this is intended to be a single-user local app, document that constraint and block public registration in deployed environments.

### 6. Scheduler evaluates only one arbitrary broker-connected user

Severity: High

Evidence:

- `_get_active_user` returns the first `broker_connected` user at `backend/services/scheduler.py:150` to `backend/services/scheduler.py:159` in the original layout; in the current working tree the method remains single-user oriented.
- Scheduler context caches one user/client/engine.
- Heartbeat and candle sync use that active user context, while order reconciliation separately iterates users.

Impact:

In a multi-user deployment, only one connected user gets normal automated strategy evaluation. If that user's token is stale, shared data sync and strategy evaluation can stall even when other users are valid.

Recommendation:

Either make the app explicitly single-user, or change scheduled strategy evaluation to iterate all eligible users with per-user isolation, rate limits, and error handling.

### 7. Trade lock TTL is shorter than broker network timeout

Severity: High

Evidence:

- Direct trade route lock timeout defaults to 5 seconds at `backend/routes/trade_routes.py:25` to `backend/routes/trade_routes.py:52`.
- Central trade safety lock timeout defaults to 5 seconds at `backend/services/trade_safety.py:67` to `backend/services/trade_safety.py:84`.
- Groww client request timeout defaults to 15 seconds at `backend/services/groww_client.py:124` to `backend/services/groww_client.py:132`.
- Groww client may also sleep and retry on rate limits inside `_make_request`.

Impact:

The lock can expire while an order request is still in flight. A second request can then acquire the lock and place a duplicate order.

Recommendation:

Set the lock TTL above the maximum broker operation window, or implement lock renewal/fencing. For LIVE trading, lock expiry should not be shorter than order placement plus persistence.

### 8. Overall-limit safety check still fails open on exceptions

Severity: High

Evidence:

- Current HEAD now fails closed for LIVE data-quality checker crashes at `backend/services/trade_safety.py:121` to `backend/services/trade_safety.py:141`.
- `backend/services/trade_safety.py:148` to `backend/services/trade_safety.py:155` still returns overall-limit OK on database exceptions.

Impact:

In LIVE mode, failure to read settings or active-trade state can allow trades instead of blocking them. For trading safety, a broken limit check should usually fail closed.

Recommendation:

Define fail-open versus fail-closed behavior per check. For LIVE execution, kill switch, duplicate detection, max open trades, and daily loss checks should fail closed unless there is a deliberate emergency override.

## Medium Findings

### 9. Settings API contract is broken after update

Severity: Medium

Evidence:

- Frontend store expects `settingsApi.update` to return `response.settings`: `frontend/src/store/ui.store.ts:48` to `frontend/src/store/ui.store.ts:52`.
- Frontend API type says the response contains `{ message, settings }`: `frontend/src/api/settings.api.ts:12` to `frontend/src/api/settings.api.ts:14`.
- Backend returns only `{ message: 'Settings updated' }`: `backend/routes/settings_routes.py:93`.

Impact:

After updating settings, the frontend can set local settings state to `undefined`. This can create stale UI, broken toggles, or confusing settings pages until a refetch happens.

Recommendation:

Make the backend return the updated settings document, or change the frontend to refetch after update.

### 10. Frontend calls a missing instruments info endpoint

Severity: Medium

Evidence:

- Frontend calls `GET /instruments/info/{index}` in `frontend/src/api/market.api.ts:73` to `frontend/src/api/market.api.ts:75`.
- Strategy page uses that call at `frontend/src/pages/Strategy.tsx:138` to `frontend/src/pages/Strategy.tsx:147`.
- Backend instrument routes provide `/sync`, `/search`, `/details/<trading_symbol>`, `/expiries/<underlying>`, `/count`, and `/last-sync`, but no `/info/<index>`.

Impact:

Strategy form prefill for lot size and expiry fails silently. The UI falls back to defaults, which may be wrong for some instruments or future changes.

Recommendation:

Add the endpoint or remove the call and derive defaults from existing route data.

### 11. Order type contract differs between frontend and backend

Severity: Medium

Evidence:

- Backend accepts `SL_M`: `backend/routes/trade_routes.py:119`.
- Frontend type uses `SL-M`: `frontend/src/api/trade.api.ts:10` and `frontend/src/types/index.ts:330`.

Impact:

If the UI sends a stop-loss market order, the backend rejects it even though both sides appear to support the concept.

Recommendation:

Normalize enum names at the API boundary and keep frontend/backend generated or shared types in sync.

### 12. Groww credential update can leave user marked broker-connected after failure

Severity: Medium

Evidence:

- `backend/routes/auth_routes.py:331` to `backend/routes/auth_routes.py:390` handles credential update.
- The user is marked `broker_connected=True` before token generation.
- If token generation fails, the route returns a failure payload but does not clearly reset `broker_connected` to false in the database.

Impact:

The scheduler can pick a user that appears connected but does not have a valid broker token. This can break data sync or strategy evaluation.

Recommendation:

Only set `broker_connected=True` after successful token validation. On failure, explicitly clear connected status and token fields.

### 13. Refresh-token route is not a real refresh-token flow

Severity: Medium

Evidence:

- `backend/routes/auth_routes.py:393` to `backend/routes/auth_routes.py:405` requires a valid current JWT and returns a new access token.
- Frontend attempts refresh on 401 in `frontend/src/api/axios.ts:35` to `frontend/src/api/axios.ts:67`.

Impact:

Once the access token is expired, the refresh endpoint cannot be called successfully. Before expiry, a stolen access token can be extended. The frontend behavior suggests a refresh mechanism exists, but the backend does not implement a separate refresh credential.

Recommendation:

Either implement true refresh tokens with rotation/revocation, or remove the refresh retry and make session expiry explicit.

### 14. JWTs are stored in localStorage

Severity: Medium

Evidence:

- Axios reads token from localStorage in `frontend/src/api/axios.ts:15` to `frontend/src/api/axios.ts:17`.
- Auth store writes token and user to localStorage in `frontend/src/store/auth.store.ts:48` to `frontend/src/store/auth.store.ts:64`.

Impact:

Any XSS bug can expose the broker-enabled session token. In a trading app, the blast radius is high.

Recommendation:

Use httpOnly, Secure, SameSite cookies where possible, or pair bearer tokens with strict CSP, shorter TTLs, refresh rotation, and no third-party script exposure.

### 15. Telegram bot token is returned to the frontend

Severity: Medium

Evidence:

- `backend/routes/settings_routes.py:34` to `backend/routes/settings_routes.py:61` returns settings including Telegram fields.
- `frontend/src/pages/Settings.tsx:35` to `frontend/src/pages/Settings.tsx:45` pre-fills the Telegram token and chat id.
- `frontend/src/pages/Settings.tsx:332` to `frontend/src/pages/Settings.tsx:343` renders those fields in inputs.

Impact:

The bot token is exposed to the browser and any browser extensions or XSS. It is also stored unencrypted in user settings.

Recommendation:

Mask secrets on read. Accept new secret values on write, but do not send stored secret material back to the client.

### 16. Strategy update allows broad field mutation

Severity: Medium

Evidence:

- Strategy creation uses minimal validation in `backend/routes/strategy_routes.py:20` to `backend/routes/strategy_routes.py:99`.
- Strategy update writes arbitrary client-supplied fields at `backend/routes/strategy_routes.py:151`.

Impact:

An owner can mutate fields that should be server-controlled, such as counters, state, or ownership metadata. Even if cross-user access is checked before update, broad updates can corrupt risk controls and records.

Recommendation:

Use an allowlist for mutable fields and validate all numeric/range values server-side.

### 17. Backtest runs are synchronous and cancel is only cosmetic

Severity: Medium

Evidence:

- `backend/routes/backtest_routes.py:27` to `backend/routes/backtest_routes.py:42` runs backtests directly in the request.
- Cancel route at `backend/routes/backtest_routes.py:101` to `backend/routes/backtest_routes.py:112` says synchronous execution cannot really cancel.

Impact:

Large backtests can tie up API workers. The cancel API can mark a run as cancelled even though execution may already be done or still running.

Recommendation:

Move backtests to a job queue or background worker. Cancellation should affect a running job, not only the database status.

### 18. Calibration is global and may stay stale in live decision engine

Severity: Medium

Evidence:

- Calibration endpoint is global: `backend/routes/backtest_routes.py:125` to `backend/routes/backtest_routes.py:137`.
- Training reads all `signal_log` rows and writes `backend/models/calibration.json` in `backend/backtest/runner.py:226` to `backend/backtest/runner.py:271`.
- Decision engine lazy-loads calibration once at `backend/analysis/decision_engine.py:49` to `backend/analysis/decision_engine.py:70`.

Impact:

One user can train calibration using all users' historical signals. After calibration, already-running engine instances may continue using stale calibration until process restart.

Recommendation:

Scope calibration by user or environment. Add explicit reload after retraining, or store calibration in a database with versioning.

### 19. Public health endpoint exposes trading posture

Severity: Medium

Evidence:

- `backend/app.py:139` to `backend/app.py:170` exposes `/api/health` without JWT.
- The response includes execution mode, auto-trading status, scheduler leadership, instance id, and recent scheduler timestamps.

Impact:

Anyone who can reach the service can learn whether trading automation is active and can fingerprint scheduler state.

Recommendation:

Split public liveness from authenticated diagnostics. Public health should expose only coarse service status.

### 20. Direction refresh can be expensive and client-triggered

Severity: Medium

Evidence:

- Dashboard force-refreshes all directions initially and then every 15 seconds: `frontend/src/pages/Dashboard.tsx:272` to `frontend/src/pages/Dashboard.tsx:280`.
- Backend supports `force_refresh=true` in `backend/routes/market_routes.py:42` to `backend/routes/market_routes.py:139`.

Impact:

Multiple browser tabs or users can repeatedly bypass cache and run direction analysis from database data. This can become avoidable load.

Recommendation:

Throttle force refresh, cache per symbol/timeframe, and reserve force refresh for manual admin actions.

### 21. Production deployment posture is incomplete

Severity: Medium

Evidence:

- `docker-compose.yml` exposes Redis on `6379` without authentication.
- There is no clear production web server/process manager setup in the repository.
- MongoDB is expected externally; index creation happens at app startup.
- `.env.example` supports secrets, but production secret handling and rotation are not documented deeply.

Impact:

The project can run locally, but production hardening is not complete. Redis exposure, missing process manager defaults, and unclear deployment boundaries are risks.

Recommendation:

Create a production deployment guide with Redis auth/TLS, Mongo connectivity, process manager, TLS/reverse proxy, secret management, backup, monitoring, and rollback steps.

### 22. Dependency hygiene is not clean

Severity: Medium

Evidence:

- `npm audit --omit=dev --json` reports production vulnerabilities in `axios`, `follow-redirects`, `react-router`, and `react-router-dom`.
- `python -m pip check` reports installed-environment conflicts:
  - `awscli` versus `botocore` and `s3transfer`
  - `neo-api-client` versus `certifi`, `idna`, `PyJWT`, `requests`, and `websockets`
  - `pydantic-settings` versus `pydantic`
  - `sse-starlette` versus `anyio` and `starlette`

Impact:

Frontend packages have known vulnerabilities. Python runtime conflicts can create unstable behavior depending on import path and environment.

Recommendation:

Pin and audit dependencies in an isolated virtual environment. Upgrade frontend vulnerable packages and add a Python audit tool such as `pip-audit` to CI.

## Low Findings And Maintainability Gaps

### 23. Frontend lint script exists but cannot run

Severity: Low

Evidence:

- `npm run lint` fails because `eslint` is not recognized.

Impact:

The project has no working static lint guard for frontend code.

Recommendation:

Either install/configure ESLint or remove the script. For production UI, keep lint in CI.

### 24. Broad exception handling and print logging reduce diagnosability

Severity: Low

Evidence:

- Backend uses many broad `except Exception` handlers and `print` statements across services and routes.
- Some client-facing errors return `str(e)`, such as broker credential and status flows in `backend/routes/auth_routes.py`.

Impact:

Failures are harder to trace, and some internal details can leak to clients.

Recommendation:

Use structured logging, correlation IDs, safe error messages, and centralized exception handling.

### 25. Instrument APIs are duplicated across route groups

Severity: Low

Evidence:

- Instrument sync/search/status behavior exists under both `/api/instruments/*` and `/api/market/instruments*` style routes.

Impact:

Duplicated API surfaces increase contract drift. The missing `/instruments/info/{index}` route is one visible symptom.

Recommendation:

Choose one canonical instrument API namespace and deprecate duplicate routes.

### 26. API request bodies are not consistently type-checked before use

Severity: Low

Evidence:

- `backend/routes/strategy_routes.py` assumes `request.get_json()` returns a dictionary.
- `backend/routes/trade_routes.py` modify endpoints also assume JSON body shape before all access.

Impact:

Malformed JSON or `null` bodies can produce 500 responses instead of clean 400 validation errors.

Recommendation:

Use schema validation for route bodies, or at minimum use `request.get_json(silent=True) or {}` plus explicit type checks.

### 27. Encoding should be verified

Severity: Low

Evidence:

- Terminal output shows mojibake-style characters in some documentation/log messages during review.

Impact:

This may be only console codepage rendering, but if stored in files it can make README/log output look broken.

Recommendation:

Verify repository files are UTF-8 and normalize terminal/runtime output. Keep generated logs ASCII or valid UTF-8.

## Test Coverage Gaps

Existing tests cover many analytical and backtest units well enough for a prototype. The riskiest missing tests are integration and contract tests:

1. Route tests for `/api/trade/place-order`, `/api/trade/quick-trade`, and `/api/trade/exit`.
2. Tests proving every trade-entry path calls the central safety gate.
3. Tests for LIVE exit behavior when broker execution price is missing.
4. Tests for dynamic symbol selection by nearest `expiry_date`.
5. Tests for frontend/backend API response contracts, especially settings update and instruments info.
6. Tests for auth refresh/logout lifecycle.
7. Tests for role authorization on global/admin endpoints.
8. Tests for scheduler behavior with multiple broker-connected users.
9. Tests for calibration reload behavior after retraining.
10. Frontend lint/type/e2e tests.

## Positive Observations

1. Backend test suite currently passes with 164 tests.
2. Frontend production build completes.
3. The code already has a central safety service, kill switch concepts, paper/live mode separation, and config validation.
4. Entry execution has pending reconciliation handling when LIVE fill price is missing.
5. Mongo index setup and instrument staging show awareness of data integrity.
6. Scheduler leadership in current HEAD fails closed for LIVE when Redis is unavailable or errors.

## Suggested Priority Order

1. Fix trade execution consistency: direct order persistence, quick-trade SELL, LIVE exit price reconciliation, and lock TTL.
2. Fix dynamic option contract selection.
3. Add authorization for global/admin endpoints.
4. Decide and document single-user versus multi-user architecture.
5. Fix frontend/backend API contract drift.
6. Clean dependency vulnerabilities and Python environment conflicts.
7. Add integration tests around trading routes and scheduler behavior.
8. Harden auth, secret handling, health endpoint exposure, and deployment docs.
