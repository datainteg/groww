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

from database import db
from backtest import engine as bt_engine
from analysis.decision_engine import analyze_market

_IST = timezone(timedelta(hours=5, minutes=30))
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

    try:
        if mode == 'OPTION_PREMIUM':
            err = ('OPTION_PREMIUM mode needs per-strike option-premium candles, which '
                   'are not stored yet. Use INDEX_PROXY for directional validation only.')
            db.update_backtest_run(run_id, {'status': 'FAILED',
                                            'finished_at': datetime.utcnow(), 'error': err})
            return {'run_id': run_id, 'status': 'FAILED', 'error': err}

        candles = _load_candles(symbol, interval, start_epoch, end_epoch)
        if len(candles) < 2:
            err = (f'Not enough candle data for {symbol} {interval}m in the selected range '
                   f'(need >= 2, got {len(candles)}). Sync candles first.')
            db.update_backtest_run(run_id, {'status': 'FAILED',
                                            'finished_at': datetime.utcnow(), 'error': err})
            return {'run_id': run_id, 'status': 'FAILED', 'error': err}

        decision_fn = make_decision_fn(symbol, params)
        result = bt_engine.run_backtest(
            candles, decision_fn,
            lot_size=int(risk.get('lot_size', 50)),
            capital=float(risk.get('capital', 1_000_000)),
            risk_pct=float(risk.get('risk_pct', 0.01)),
            sl_points=float(params.get('sl_points', 20)),
            target_points=float(params.get('target_points', 40)),
            slippage_pct=float(costs.get('slippage_pct', 0.0005)),
            brokerage_per_order=float(costs.get('brokerage_per_order', 20)),
        )
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
