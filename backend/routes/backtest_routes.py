"""Backtesting Machine API (JWT-protected). Runs are user-scoped.

Synchronous execution today, but the run row is written before/after work so an
async worker can later flip it to QUEUED -> RUNNING -> COMPLETED/FAILED without
changing the API shape.
"""
import csv
import io
import json

from flask import Blueprint, request, jsonify, Response
from flask_jwt_extended import jwt_required, get_jwt_identity

from database import db
from backtest.runner import (run_backtest_for_user, run_walk_forward_for_user,
                             calibrate_model, calibration_status)

backtest_bp = Blueprint('backtest', __name__, url_prefix='/api/backtest')

_ALLOWED_TF = {'1', '3', '5', '10', '15', '30', '60', 'D'}


def _owned(run_id, user_id):
    return db.get_backtest_run(run_id, user_id) is not None


@backtest_bp.route('/runs', methods=['POST'])
@jwt_required()
def create_run():
    """Create + run a backtest (synchronous)."""
    user_id = get_jwt_identity()
    cfg = request.get_json(force=True, silent=True) or {}
    if not (cfg.get('symbol') or cfg.get('index')):
        return jsonify({'error': 'symbol/index is required'}), 400
    tf = str(cfg.get('timeframe', cfg.get('interval', '5')))
    if tf not in _ALLOWED_TF:
        return jsonify({'error': f'timeframe must be one of {sorted(_ALLOWED_TF)}'}), 400

    result = run_backtest_for_user(user_id, cfg)
    status = result.get('status')
    code = 200 if status == 'COMPLETED' else (400 if status == 'FAILED' else 202)
    return jsonify(result), code


@backtest_bp.route('/runs', methods=['GET'])
@jwt_required()
def list_runs():
    user_id = get_jwt_identity()
    limit = min(int(request.args.get('limit', 50)), 200)
    return jsonify({'runs': db.list_backtest_runs(user_id, limit)})


@backtest_bp.route('/runs/<run_id>', methods=['GET'])
@jwt_required()
def get_run(run_id):
    run = db.get_backtest_run(run_id, get_jwt_identity())
    if not run:
        return jsonify({'error': 'Run not found'}), 404
    return jsonify(run)


@backtest_bp.route('/runs/<run_id>/trades', methods=['GET'])
@jwt_required()
def get_trades(run_id):
    user_id = get_jwt_identity()
    if not _owned(run_id, user_id):
        return jsonify({'error': 'Run not found'}), 404
    skip = int(request.args.get('skip', 0))
    limit = min(int(request.args.get('limit', 100)), 500)
    return jsonify({
        'trades': db.get_backtest_trades(run_id, skip, limit),
        'total': db.count_backtest_trades(run_id),
        'skip': skip, 'limit': limit,
    })


@backtest_bp.route('/runs/<run_id>/equity', methods=['GET'])
@jwt_required()
def get_equity(run_id):
    user_id = get_jwt_identity()
    if not _owned(run_id, user_id):
        return jsonify({'error': 'Run not found'}), 404
    m = (db.get_backtest_report(run_id) or {}).get('metrics', {})
    return jsonify({
        'equity_curve': m.get('equity_curve', []),
        'drawdown_curve': m.get('drawdown_curve', []),
        'daily_pnl': m.get('daily_pnl', []),
    })


@backtest_bp.route('/runs/<run_id>/report', methods=['GET'])
@jwt_required()
def get_report(run_id):
    user_id = get_jwt_identity()
    run = db.get_backtest_run(run_id, user_id)
    if not run:
        return jsonify({'error': 'Run not found'}), 404
    return jsonify({'run': run, 'report': db.get_backtest_report(run_id) or {}})


@backtest_bp.route('/runs/<run_id>/cancel', methods=['POST'])
@jwt_required()
def cancel_run(run_id):
    user_id = get_jwt_identity()
    run = db.get_backtest_run(run_id, user_id)
    if not run:
        return jsonify({'error': 'Run not found'}), 404
    if run.get('status') in ('QUEUED', 'RUNNING'):
        db.update_backtest_run(run_id, {'status': 'CANCELLED'})
        return jsonify({'status': 'CANCELLED'})
    return jsonify({'status': run.get('status'),
                    'message': 'Not cancellable (already finished; synchronous execution).'})


@backtest_bp.route('/walk-forward', methods=['POST'])
@jwt_required()
def walk_forward_route():
    user_id = get_jwt_identity()
    cfg = request.get_json(force=True, silent=True) or {}
    if not (cfg.get('symbol') or cfg.get('index')):
        return jsonify({'error': 'symbol/index is required'}), 400
    return jsonify(run_walk_forward_for_user(user_id, cfg))


@backtest_bp.route('/calibrate', methods=['POST'])
@jwt_required()
def calibrate():
    data = request.get_json(force=True, silent=True) or {}
    min_samples = int(data.get('min_samples', 50))
    result = calibrate_model(min_samples=min_samples)
    return jsonify(result), (200 if result.get('success') else 400)


@backtest_bp.route('/calibration/status', methods=['GET'])
@jwt_required()
def calibration_status_route():
    return jsonify(calibration_status())


@backtest_bp.route('/compare', methods=['POST'])
@jwt_required()
def compare():
    user_id = get_jwt_identity()
    data = request.get_json(force=True, silent=True) or {}
    ids = data.get('run_ids') or []
    if not (2 <= len(ids) <= 5):
        return jsonify({'error': 'Provide 2-5 run_ids'}), 400
    out = []
    for rid in ids:
        run = db.get_backtest_run(rid, user_id)
        if not run:
            continue
        m = (db.get_backtest_report(rid) or {}).get('metrics', {})
        out.append({
            'run_id': rid, 'symbol': run.get('symbol'), 'timeframe': run.get('timeframe'),
            'mode': run.get('mode'), 'parameters': run.get('parameters'),
            'summary': run.get('summary'),
            'equity_curve': m.get('equity_curve', []),
            'by_regime': m.get('by_regime', {}),
        })
    return jsonify({'runs': out})


@backtest_bp.route('/export', methods=['POST'])
@jwt_required()
def export():
    user_id = get_jwt_identity()
    data = request.get_json(force=True, silent=True) or {}
    run_id = data.get('run_id')
    fmt = (data.get('format') or 'json').lower()
    target = (data.get('target') or 'trades').lower()
    if not _owned(run_id, user_id):
        return jsonify({'error': 'Run not found'}), 404

    if target == 'report':
        payload = db.get_backtest_report(run_id) or {}
        return Response(json.dumps(payload, default=str), mimetype='application/json',
                        headers={'Content-Disposition': f'attachment; filename=report_{run_id}.json'})

    trades = db.get_backtest_trades(run_id, 0, 100000)
    if fmt == 'json':
        return Response(json.dumps(trades, default=str), mimetype='application/json',
                        headers={'Content-Disposition': f'attachment; filename=trades_{run_id}.json'})

    cols = ['entry_time', 'exit_time', 'direction', 'entry_index', 'exit_index',
            'entry_premium', 'exit_premium', 'qty', 'lots', 'gross', 'charges',
            'slippage', 'net', 'exit_reason', 'confidence', 'regime', 'entry_bar', 'exit_bar']
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction='ignore')
    writer.writeheader()
    for t in trades:
        writer.writerow(t)
    return Response(buf.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename=trades_{run_id}.csv'})
