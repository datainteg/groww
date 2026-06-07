# Accuracy & Profitability Plan — Groww AI Trading System

**Goal:** maximize **expectancy after costs**, not raw "accuracy".
Profit per trade ≈ `win% × avg_win − loss% × avg_loss − brokerage − STT − exchange − GST − slippage − option_spread`.
A directionally-correct index call can still LOSE on option theta/spread — so every change is judged by **net-of-cost expectancy in an honest backtest**, never by gut feel.

**Hard go-live gate (non-negotiable):** trade real money only after the system shows
**positive net-of-cost expectancy out-of-sample over ≥200 trades**, then 2 weeks of paper
matching backtest, then live at tiny size — scale only while live tracks backtest.

Legend: `[improve]` existing file · `[new]` new component · each phase ends with a measurable **Accept**.

---

## Phase A0 — Data Integrity Gate  (foundation; mostly done — verify + harden)
Garbage in → garbage signals. No model is "accurate" on bad candles.

- Already fixed: `interval_in_minutes` param, closed-candle gating, IST time base, 1D session anchor, VWAP session reset.
- `[new] analysis/data_quality.py` — validate candles before analysis: detect gaps, duplicate timestamps, zero/negative volume, stale (last bar too old), price spikes; return a quality flag.
- `[improve] services/candle_service.py`, `services/scheduler.py` — refuse to emit a signal when quality flag is bad; log + alert instead of trading on holes.

**Accept:** every decision runs on validated, gap-free, closed, IST-correct candles; bad data → no trade (not a wrong trade).

---

## Phase A1 — Measurement: cost-aware backtester  (DO THIS FIRST — can't improve blind)
You cannot improve accuracy you don't measure. This is the scoreboard for every later phase.

- `[improve] groww/nifty_scalper_bt.py`, `groww/run_backtest.py` — drive the SAME `decision_engine` code path on historical candles, bar-by-bar, with strict bar-close (no look-ahead).
- `[new] backtest/cost_model.py` — exact Indian F&O charges: brokerage (flat/percent), STT (sell-side options), exchange txn, SEBI, GST, stamp duty, + modeled slippage and option bid/ask spread.
- `[new] backtest/engine.py` — event-driven loop: signal → strike resolve → fill at modeled price → SL/target/trailing exits → P&L net of cost_model.
- `[new] backtest/metrics.py` — expectancy/trade, profit factor, win-rate, avg R, max drawdown, Sharpe, exposure, **broken down by regime and by hour-of-day**.

**Accept:** backtest reproduces a hand-checked trade set; every report is **net of costs**; results stored for comparison across phases.

---

## Phase A2 — Signal calibration: confidence → real P(win)  (biggest signal lever)
Today `confidence` is a 0–1 net-score, NOT a probability. "0.70" must mean ~70% win.

- Already done: `signal_log` collection + per-entry feature logging at entry.
- `[new] scripts/label_signals.py` + `[new]` scheduler labeling job — N bars after each logged signal, compute realized forward return + win/loss; write outcome back to `signal_log`.
- `[new] analysis/calibration.py` — fit logistic/Platt (and/or isotonic) mapping engine features → empirical P(win); persist coefficients (file/DB).
- `[improve] analysis/decision_engine.py` — output calibrated P(win); set the entry threshold from **P(win) × payoff_ratio > 1 + cost_buffer**, not an arbitrary 0.50/0.70.

**Accept:** reliability curve shows predicted ≈ actual win-rate; threshold derived from expectancy, validated in the A1 backtest.

---

## Phase A3 — Option-aware signal layer  (the missing piece: you signal on index, trade options)
A correct index direction loses if the strike/IV/spread is wrong.

- `[new] analysis/options_engine.py` — strike selection by **delta** (e.g. ~0.3–0.5), IV rank/percentile, theta/vega awareness, expected option-premium move (`delta×ΔS − theta×Δt`), and a **liquidity filter** (min OI, max bid/ask spread).
- `[improve] services/groww_client.py` usage — pull Greeks/option-chain (OI, IV) via existing `get_greeks` / option-chain endpoints.
- `[improve] analysis/decision_engine.py` / `market_direction_engine.py` — gate entries on **option-level** positive expectancy + liquidity, not just index signal.

**Accept:** entries rejected when option illiquid or premium expectancy negative; backtest expectancy improves vs index-only.

---

## Phase A4 — Regime detection + adaptive indicators
- `[new] analysis/regime.py` — classify TRENDING / RANGING / VOLATILE (ADX, vol-ratio, trend slope) → selects the decision-engine weight profile (profiles already exist; make selection data-driven).
- `[improve] analysis/volatility/indicators.py` — fix `sqrt(252)` intraday annualization; replace hardcoded HIGH/LOW cutoffs with **rolling per-symbol percentiles/z-scores**.
- `[improve] analysis/support_resistance/indicators.py` — prior-session pivots, swing-anchored Fibonacci.
- `[improve] analysis/momentum/indicators.py` — confirm formulas vs references (unit-tested).

**Accept:** per-regime win-rate measured in backtest; adaptive thresholds beat fixed ones out-of-sample.

---

## Phase A5 — Risk, exits & position sizing  (turns accuracy INTO profit)
Often matters more than entry accuracy.

- `[new] utils/position_sizing.py` — fixed-fractional risk per trade (e.g. risk 1% of capital), capped by margin + daily-loss limit; size from SL distance.
- `[improve] utils/risk_manager.py` — R-multiple SL/target, enforce daily max-loss hard stop.
- `[improve] services/trading_engine.py` — ATR-based trailing, partial exits at +1R, **time/theta-aware exit** for options (don't hold decaying premium late in session).

**Accept:** backtest shows higher expectancy and lower max-drawdown with sizing/exit rules than without.

---

## Phase A6 — Walk-forward validation + live drift monitoring  (anti-overfit + safety)
- `[new] backtest/walk_forward.py` — train calibration/weights on a rolling in-sample window, test on the next out-of-sample window; report OOS expectancy (kills curve-fitting).
- `[new] analysis/live_monitor.py` — track live win-rate / expectancy vs backtest; alert (Telegram) on drift beyond tolerance; auto-throttle or kill-switch on sustained underperformance.

**Accept:** OOS expectancy positive across multiple windows; live tracks backtest within tolerance or auto-halts.

---

## Phase A7 — (Stretch) ML signal model
- `[new] models/ml_signal.py` — gradient-boosted / logistic model on the engineered features already in `signal_log`, with **time-series cross-validation** (no leakage); ensemble with the rule engine only if it beats it OOS.

**Accept:** OOS AUC/expectancy beats the calibrated rule engine before any ensembling.

---

## New components summary
| Component | Purpose |
|---|---|
| `backtest/cost_model.py` | exact Indian F&O charges + slippage/spread |
| `backtest/engine.py` | bar-close event-driven backtest on the live decision path |
| `backtest/metrics.py` | expectancy / PF / Sharpe / DD, by regime & hour |
| `backtest/walk_forward.py` | out-of-sample, anti-overfit validation |
| `analysis/data_quality.py` | reject bad/stale/gappy candles before analysis |
| `analysis/calibration.py` | confidence → empirical P(win) |
| `analysis/regime.py` | regime classifier → weight-profile selection |
| `analysis/options_engine.py` | delta/IV/theta + liquidity-aware strike & gate |
| `analysis/live_monitor.py` | live-vs-backtest drift + auto-throttle |
| `utils/position_sizing.py` | risk-per-trade sizing |
| `scripts/label_signals.py` (+ scheduler job) | label signal_log with forward outcomes |
| `models/ml_signal.py` (stretch) | ML signal, ensembled only if it wins OOS |

## Execution order (what makes money, in order)
**A1 (backtest)** → **A2 (calibration)** → **A3 (option-aware)** → **A4 (regime/indicators)** →
**A5 (risk/exits)** → **A6 (walk-forward + monitor)** → A7 (ML, optional).
Each phase must improve **net-of-cost OOS expectancy** in the A1 backtest, or it doesn't ship.

> Reality check: most retail options-scalping is net-negative after costs. This plan is built to
> find out HONESTLY whether this system has edge — and to stop you trading real money if it doesn't.
