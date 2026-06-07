"""Backtest runner — wires the LIVE decision logic into the bar-close engine and
persists runs/trades/reports.

The decision wrapper calls the SAME `analysis.decision_engine.analyze_market` the
live scheduler uses, with the SAME confidence/p_win thresholds, so a backtest is a
faithful replay of live decisions (subject to the INDEX_PROXY P&L caveat).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

import os

from database import db
from backtest import engine as bt_engine
from backtest import walk_forward as bt_wf
from analysis.decision_engine import analyze_market

_IST = timezone(timedelta(hours=5, minutes=30))
_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'models', 'calibration.json')
_MIN_HISTORY = 30  # bars needed before indicators are meaningful

_SUMMARY_KEYS = ('count', 'total_net', 'win_rate', 'expectancy', 'profit_factor',
                 'max_drawdown', 'max_drawdown_pct', 'sharpe', 'sortino',
                 'trades_per_day', 'gross_profit', 'gross_loss')


def _date_to_epoch(d: Any, end: bool = False) -> Optional[int]:
    """'YYYY-MM-DD' (IST) -> epoch seconds. end=True -> end of that day."""
    if not d:
        return None
    try:
        dt = datetime.fromisoformat(str(d))
    except Exception:
        return None
    if end and dt.hour == 0 and dt.minute == 0:
        dt = dt + timedelta(hours=23, minutes=59, seconds=59)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_IST)
    return int(dt.timestamp())


def _load_candles(symbol: str, interval: str, start_epoch: Optional[int],
                  end_epoch: Optional[int]) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {'symbol': symbol, 'interval': str(interval)}
    if start_epoch or end_epoch:
        ts: Dict[str, int] = {}
        if start_epoch:
            ts['$gte'] = int(start_epoch)
        if end_epoch:
            ts['$lte'] = int(end_epoch)
        q['timestamp'] = ts
    return list(db.candles.find(q, {'_id': 0}).sort('timestamp', 1))


def make_decision_fn(symbol: str, params: Dict[str, Any]) -> Callable[[List[Dict]], Dict]:
    """Build a decision_fn(history)->{signal,confidence,p_win,expected_value,regime}
    using the live analyze_market + the same threshold gates."""
    min_conf = float(params.get('min_confidence', 0) or 0)
    if min_conf > 1:
        min_conf /= 100.0
    min_pwin = float(params.get('min_p_win', 0) or 0)
    min_ev = float(params.get('min_expected_value', 0) or 0)

    def decision_fn(history: List[Dict[str, Any]]) -> Dict[str, Any]:
        if len(history) < _MIN_HISTORY:
            return {'signal': None, 'confidence': 0}
        try:
            res = analyze_market(pd.DataFrame(history), symbol)
        except Exception:
            return {'signal': None, 'confidence': 0}
        signal = res.get('signal')
        conf = res.get('confidence', 0) or 0
        if conf > 1:
            conf /= 100.0
        p_win = res.get('p_win')
        ev = res.get('expected_value')
        regime = res.get('market_regime') or res.get('regime')
        if min_conf and conf < min_conf:
            return {'signal': None, 'confidence': conf}
        if min_pwin and p_win is not None and p_win < min_pwin:
            return {'signal': None, 'confidence': conf, 'p_win': p_win}
        if min_ev and ev is not None and ev < min_ev:
            return {'signal': None, 'confidence': conf}
        return {'signal': signal, 'confidence': conf, 'p_win': p_win,
                'expected_value': ev, 'regime': regime}

    return decision_fn


def run_backtest_for_user(user_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Create + execute a backtest run synchronously. Persists run/trades/report
    and returns {run_id, status, summary|error}. Structured for an async worker:
    the run row is written QUEUED/RUNNING before work and COMPLETED/FAILED after."""
    run_id = uuid.uuid4().hex
    symbol = config.get('symbol') or config.get('index') or 'NIFTY'
    interval = str(config.get('timeframe', config.get('interval', '5')))
    mode = (config.get('mode') or 'INDEX_PROXY').upper()
    params = config.get('parameters', {}) or {}
    risk = config.get('risk', {}) or {}
    costs = config.get('costs', {}) or {}
    start_epoch = config.get('start_epoch') or _date_to_epoch(config.get('start_date'))
    end_epoch = config.get('end_epoch') or _date_to_epoch(config.get('end_date'), end=True)

    db.create_backtest_run({
        'run_id': run_id, 'user_id': user_id,
        'strategy_id': config.get('strategy_id'),
        'strategy_config': config.get('strategy_config'),
        'symbol': symbol, 'timeframe': interval,
        'start_date': config.get('start_date'), 'end_date': config.get('end_date'),
        'start_epoch': start_epoch, 'end_epoch': end_epoch,
        'data_source': 'mongodb_candles', 'mode': mode,
        'parameters': params, 'risk': risk, 'costs': costs,
        'status': 'RUNNING', 'started_at': datetime.utcnow(),
    })

    def _fail(err):
        db.update_backtest_run(run_id, {'status': 'FAILED', 'finished_at': datetime.utcnow(), 'error': err})
        return {'run_id': run_id, 'status': 'FAILED', 'error': err}

    try:
        decision_fn = make_decision_fn(symbol, params)
        common = dict(
            lot_size=int(risk.get('lot_size', 50)),
            capital=float(risk.get('capital', 1_000_000)),
            risk_pct=float(risk.get('risk_pct', 0.01)),
            sl_points=float(params.get('sl_points', 20)),
            target_points=float(params.get('target_points', 40)),
            slippage_pct=float(costs.get('slippage_pct', 0.0005)),
            brokerage_per_order=float(costs.get('brokerage_per_order', 20)),
        )

        index_candles = _load_candles(symbol, interval, start_epoch, end_epoch)
        if len(index_candles) < 2:
            return _fail(f'Not enough index candle data for {symbol} {interval}m in the selected '
                         f'range (need >= 2, got {len(index_candles)}). Sync candles first.')

        if mode == 'OPTION_PREMIUM':
            option_symbol = config.get('option_symbol')
            if not option_symbol:
                return _fail("OPTION_PREMIUM requires 'option_symbol' (the strike's trading symbol).")
            option_candles = _load_candles(option_symbol, interval, start_epoch, end_epoch)
            if len(option_candles) < 2:
                return _fail(f"No option-premium candles for {option_symbol} {interval}m. Sync them "
                             f"first (POST /api/strategy/candles/{option_symbol}/sync) or use INDEX_PROXY.")
            option_type = config.get('option_type') or ('CE' if str(option_symbol).upper().endswith('CE') else 'PE')
            result = bt_engine.run_option_premium_backtest(
                index_candles, option_candles, decision_fn, option_type, **common)
        else:
            result = bt_engine.run_backtest(index_candles, decision_fn, **common)

        trades = result.pop('trades', [])
        db.save_backtest_trades(run_id, trades)
        db.save_backtest_report(run_id, {'metrics': result, 'mode': mode,
                                         'symbol': symbol, 'timeframe': interval,
                                         'index_proxy_warning': mode == 'INDEX_PROXY'})
        summary = {k: result.get(k) for k in _SUMMARY_KEYS}
        db.update_backtest_run(run_id, {'status': 'COMPLETED', 'finished_at': datetime.utcnow(),
                                        'summary': summary, 'trade_count': len(trades)})
        return {'run_id': run_id, 'status': 'COMPLETED', 'summary': summary}
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.update_backtest_run(run_id, {'status': 'FAILED',
                                        'finished_at': datetime.utcnow(), 'error': str(e)})
        return {'run_id': run_id, 'status': 'FAILED', 'error': str(e)}


def run_walk_forward_for_user(user_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Rolling out-of-sample evaluation. Returns walk_forward() output augmented
    with a stability score + overfit warning. Same decision logic as the backtest."""
    symbol = config.get('symbol') or config.get('index') or 'NIFTY'
    interval = str(config.get('timeframe', config.get('interval', '5')))
    params = config.get('parameters', {}) or {}
    risk = config.get('risk', {}) or {}
    costs = config.get('costs', {}) or {}
    train_bars = int(config.get('train_bars', 500))
    test_bars = int(config.get('test_bars', 100))
    step_bars = config.get('step_bars')
    step_bars = int(step_bars) if step_bars else None
    start_epoch = config.get('start_epoch') or _date_to_epoch(config.get('start_date'))
    end_epoch = config.get('end_epoch') or _date_to_epoch(config.get('end_date'), end=True)

    candles = _load_candles(symbol, interval, start_epoch, end_epoch)
    decision_fn = make_decision_fn(symbol, params)

    def fit_fn(_train):
        return None  # same decision logic every window (no per-window refit)

    def run_fn(test, _fitted):
        if len(test) < 2:
            return []
        res = bt_engine.run_backtest(
            test, decision_fn,
            lot_size=int(risk.get('lot_size', 50)),
            capital=float(risk.get('capital', 1_000_000)),
            risk_pct=float(risk.get('risk_pct', 0.01)),
            sl_points=float(params.get('sl_points', 20)),
            target_points=float(params.get('target_points', 40)),
            slippage_pct=float(costs.get('slippage_pct', 0.0005)),
            brokerage_per_order=float(costs.get('brokerage_per_order', 20)),
        )
        return res.get('trades', [])

    wf = bt_wf.walk_forward(candles, fit_fn, run_fn,
                            train_bars=train_bars, test_bars=test_bars, step_bars=step_bars)

    exps = [w['metrics'].get('expectancy', 0.0) for w in wf.get('windows', [])]
    n = len(exps)
    pos = sum(1 for e in exps if e > 0)
    stability = (pos / n) if n else 0.0
    pooled_exp = wf.get('pooled', {}).get('expectancy', 0.0)
    wf['stability_score'] = round(stability, 3)
    wf['pooled_expectancy'] = pooled_exp
    # Overfit warning: windows mostly inconsistent or pooled OOS edge non-positive.
    wf['overfit_warning'] = bool(n > 0 and (stability < 0.5 or pooled_exp <= 0))
    wf['symbol'] = symbol
    wf['timeframe'] = interval
    return wf


def calibrate_model(min_samples: int = 50) -> Dict[str, Any]:
    """Fit the p_win calibrator from labeled signal_log snapshots (same 4 features
    the live engine uses) and save to backend/models/calibration.json.

    NOTE: saving a model does NOT enable live auto-entry — the live gate also
    requires OOS expectancy + explicit AUTO_TRADING_ENABLED."""
    # Label any pending signal_log docs first (best-effort).
    try:
        from scripts.label_signals import label_pending
        from services.candle_service import candle_service
        label_pending(db, candle_service)
    except Exception as e:
        print(f"[calibrate] labeling skipped: {e}")

    docs = list(db.signal_log.find(
        {'outcome.win': {'$exists': True}, 'calibration_features': {'$exists': True}},
        {'_id': 0, 'calibration_features': 1, 'outcome': 1}))
    X, y = [], []
    for d in docs:
        f = d.get('calibration_features')
        o = d.get('outcome', {})
        if isinstance(f, list) and len(f) == 4 and 'win' in o:
            try:
                X.append([float(v) for v in f])
                y.append(1 if o['win'] else 0)
            except (TypeError, ValueError):
                continue

    n = len(y)
    if n < min_samples:
        return {'success': False, 'n_samples': n,
                'reason': f'Not enough labeled samples ({n}/{min_samples}). '
                          f'Collect more live/paper signals and let labeling run.'}

    import numpy as np
    from analysis.calibration import Calibrator
    Xa = np.asarray(X, dtype=np.float64)
    ya = np.asarray(y, dtype=np.float64)
    cal = Calibrator().fit(Xa, ya)
    os.makedirs(os.path.dirname(_MODEL_PATH), exist_ok=True)
    cal.save(_MODEL_PATH)
    p = cal.predict_proba(Xa)
    brier = float(np.mean((p - ya) ** 2))
    return {'success': True, 'n_samples': n, 'win_rate': float(np.mean(ya)),
            'brier_score': round(brier, 4), 'model_path': _MODEL_PATH,
            'note': 'Model saved. Live auto-entry still requires OOS expectancy + AUTO_TRADING_ENABLED.'}


def calibration_status() -> Dict[str, Any]:
    if not os.path.isfile(_MODEL_PATH):
        return {'exists': False, 'fitted': False, 'path': _MODEL_PATH}
    try:
        from analysis.calibration import Calibrator
        cal = Calibrator.load(_MODEL_PATH)
        return {'exists': True, 'fitted': bool(cal.is_fitted), 'path': _MODEL_PATH}
    except Exception as e:
        return {'exists': True, 'fitted': False, 'error': str(e), 'path': _MODEL_PATH}
