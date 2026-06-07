# Production 10/10 Audit (pre-edit)

Audit of the real code (not the README) before the 10/10 hardening pass.

## Architecture summary
- **Backend:** Flask app factory (`app.py`, `config.validate()` fail-fast) + APScheduler
  workers (`run_scheduler.py`, Redis leader-lock). MongoDB state; Redis cache/locks/heartbeat.
- **Order brokers:** `paper_broker` (simulated) and `groww_client` (LIVE REST).
- **Decision:** `analysis/decision_engine.analyze()` (regime-weighted net-score, optional p_win).
- **Safety spine:** `services/trade_safety.py` (validate gate + per-user Redis lock) used by
  `TradingEngine.execute_entry`. Reconciliation in `TradingEngine.reconcile_positions`.
- **Backtest:** `backtest/{engine,metrics,cost_model,walk_forward,runner}.py` — INDEX_PROXY +
  OPTION_PREMIUM (dual-series); persisted to `backtest_*` collections.
- **Frontend:** React/TS, Zustand stores, Safety Center, Backtest Lab, dashboards.

## Order-placement paths
1. **Scheduler auto-entry** → `evaluate_strategies` → `execute_entry` (gated ✅).
2. **Manual execute-strategy** → `trade_routes.execute_strategy_trade` → `execute_entry(source=MANUAL)` (gated ✅).
3. **quick-trade** → `trade_routes.quick_trade` → `validate_trade_allowed(MANUAL)` on BUY (gated ✅).
4. **Direct place-order** → `trade_routes.place_order` → **broker directly, NO central gate ❌ (Phase 1).**
5. **Exits** → `execute_exit` / `exit-all` (correctly not entry-gated).

## Safety gates (trade_safety.validate_trade_allowed)
kill switch · broker-feed dead (LIVE) · data freshness (LIVE) · per-strategy limits +
duplicate · overall limits (concurrent / daily P&L) · LIVE-auto requires AUTO_TRADING_ENABLED.
Lock fails **closed** in LIVE when Redis down; open in PAPER.

## Backtesting flow
`runner.run_backtest_for_user` → load candles → `make_decision_fn` (live analyze + thresholds)
→ engine (bar-close, no look-ahead, pessimistic SL, EOD) → metrics → persist. INDEX_PROXY uses
a realistic proxy premium for costs; OPTION_PREMIUM uses real strike candles aligned by ts.
Walk-forward returns pooled OOS + stability + overfit flag.

## Frontend flow
Health store polls `/api/health` + `/trade/reconciliation`; GlobalAlertBanner + Safety Center
surface mode/scheduler/feed/token/reconciliation/kill-switch. Backtest Lab (tabs incl. WF +
Review). LIVE actions use typed confirmation.

## Remaining gaps (this pass)
1. **Direct `/place-order` bypasses central safety** (Phase 1).
2. **`_log_signal` does not write `calibration_features`** → calibration can't train (Phase 2).
3. **Scheduler leadership fail-open in LIVE when Redis down** (Phase 3).
4. **`order_reference_id` generated AFTER broker call** (Phase 4).
5. **`check_data_freshness` fails OPEN on checker crash in LIVE** (Phase 5).
6. **Backtest `min_p_win` silently skips when p_win missing** (Phase 7).
7. Order lifecycle / reconciliation 2.0 incomplete (Phases 4, 6).
8. Frontend production UX polish (Phase 8).
9. Test coverage of every safety path (Phase 10).

## Implementation checklist
- [x] Phase 0 — this audit
- [ ] Phase 1 — place-order through central safety
- [ ] Phase 2 — calibration_features in _log_signal + runner backfill/validation
- [ ] Phase 3 — scheduler LIVE fail-closed
- [ ] Phase 4 — order_reference_id before placement + lifecycle
- [ ] Phase 5 — data quality fail-closed in LIVE
- [ ] Phase 6 — reconciliation 2.0 (report collection + manual run route)
- [ ] Phase 7 — backtest validation, alignment, gating stats, verdict
- [ ] Phase 8 — frontend safety/UX
- [ ] Phase 9 — security hardening
- [ ] Phase 10 — tests
- [ ] Phase 11 — docs (PRODUCTION_READINESS, LIVE checklist)
