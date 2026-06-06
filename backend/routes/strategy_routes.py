"""Strategy Routes"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import pandas as pd
import numpy as np
from datetime import datetime
from database import db
from services import get_trading_engine, candle_service
from analysis import analyze_market
from utils import risk_manager

strategy_bp = Blueprint('strategy', __name__, url_prefix='/api/strategy')


@strategy_bp.route('/create', methods=['POST'])
@jwt_required()
def create_strategy():
    """Create new strategy with confidence configuration"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    required = ['name', 'quantity', 'stop_loss', 'target']
    for field in required:
        if field not in data:
            return jsonify({'error': f'{field} is required'}), 400
    
    # Determine Selection Mode
    is_dynamic = 'ce_symbol' not in data or not data['ce_symbol']
    
    if is_dynamic:
        if 'index' not in data:
             return jsonify({'error': 'index is required for dynamic strategies'}), 400
        selection_mode = 'DYNAMIC'
        ce_symbol = None
        pe_symbol = None
        atm_offset = int(data.get('atm_offset', 0)) 
    else:
        if 'pe_symbol' not in data:
            return jsonify({'error': 'pe_symbol is required for manual strategies'}), 400
        selection_mode = 'MANUAL'
        ce_symbol = data['ce_symbol']
        pe_symbol = data['pe_symbol']
        atm_offset = 0

    # Validate confidence configuration
    min_confidence = data.get('min_confidence', 70)
    if not 50 <= min_confidence <= 95:
        return jsonify({'error': 'min_confidence must be between 50 and 95'}), 400
    
    direction_min_strength = data.get('direction_min_strength', 60)
    if not 40 <= direction_min_strength <= 90:
        return jsonify({'error': 'direction_min_strength must be between 40 and 90'}), 400
    
    allowed_signals = data.get('allowed_signals', 'BOTH')
    if allowed_signals not in ['BOTH', 'BULLISH', 'BEARISH']:
        return jsonify({'error': 'allowed_signals must be BOTH, BULLISH, or BEARISH'}), 400

    strategy_data = {
        'user_id': user_id,
        'name': data['name'],
        'index': data.get('index', 'NIFTY'),
        'selection_mode': selection_mode,
        'atm_offset': atm_offset,
        'exchange_segment': data.get('exchange_segment', 'nse_fo'),
        'product': data.get('product', 'MIS'),
        'expiry': data.get('expiry', ''),
        'strike_price': data.get('strike_price', ''),
        'ce_symbol': ce_symbol,
        'pe_symbol': pe_symbol,
        'quantity': data['quantity'],
        'stop_loss': data['stop_loss'],
        'target': data['target'],
        'trailing_sl_enabled': data.get('trailing_sl_enabled', False),
        'trailing_sl_value': data.get('trailing_sl_value', 20),
        'break_even_enabled': data.get('break_even_enabled', False),
        'break_even_trigger': data.get('break_even_trigger', 50),
        'partial_exit_enabled': data.get('partial_exit_enabled', False),
        'partial_exit_percent': data.get('partial_exit_percent', 50),
        'partial_target_1': data.get('partial_target_1'),
        'time_exit_enabled': data.get('time_exit_enabled', True),
        'max_orders_per_day': data.get('max_orders_per_day', 2),
        'max_profit_limit': data.get('max_profit_limit', 5000),
        'max_loss_limit': data.get('max_loss_limit', 2000),
        
        # NEW: Confidence Configuration
        'confidence_preset': data.get('confidence_preset', 'balanced'),
        'min_confidence': min_confidence,
        'volume_confirmation': data.get('volume_confirmation', True),
        'volatility_filter': data.get('volatility_filter', True),
        'trend_alignment': data.get('trend_alignment', False),
        'allowed_signals': allowed_signals,
        'time_filter_enabled': data.get('time_filter_enabled', False),
        'time_filter_start': data.get('time_filter_start', '09:30'),
        'time_filter_end': data.get('time_filter_end', '15:00'),
        'use_direction_engine': data.get('use_direction_engine', True),
        'direction_min_strength': direction_min_strength,
        
        'is_active': False
    }
    
    strategy_id = db.create_strategy(strategy_data)
    return jsonify({
        'message': 'Strategy created successfully', 
        'strategy_id': strategy_id
    }), 201


@strategy_bp.route('/list', methods=['GET'])
@jwt_required()
def list_strategies():
    user_id = get_jwt_identity()
    return jsonify(db.get_strategies_by_user(user_id))


@strategy_bp.route('/<strategy_id>', methods=['GET'])
@jwt_required()
def get_strategy(strategy_id):
    strategy = db.get_strategy_by_id(strategy_id)
    if not strategy: return jsonify({'error': 'Strategy not found'}), 404
    return jsonify(strategy)


@strategy_bp.route('/<strategy_id>', methods=['PUT'])
@jwt_required()
def update_strategy(strategy_id):
    data = request.get_json()
    strategy = db.get_strategy_by_id(strategy_id)
    if strategy and strategy.get('is_active'):
        return jsonify({'error': 'Cannot update active strategy. Stop it first.'}), 400
    
    if 'atm_offset' in data:
        data['atm_offset'] = int(data['atm_offset'])

    db.update_strategy(strategy_id, data)
    return jsonify({'message': 'Strategy updated'})


@strategy_bp.route('/<strategy_id>', methods=['DELETE'])
@jwt_required()
def delete_strategy(strategy_id):
    strategy = db.get_strategy_by_id(strategy_id)
    if strategy and strategy.get('is_active'):
        return jsonify({'error': 'Cannot delete active strategy'}), 400
    db.delete_strategy(strategy_id)
    return jsonify({'message': 'Strategy deleted'})


@strategy_bp.route('/<strategy_id>/start', methods=['POST'])
@jwt_required()
def start_strategy(strategy_id):
    user_id = get_jwt_identity()
    strategy = db.get_strategy_by_id(strategy_id)
    if not strategy: return jsonify({'error': 'Strategy not found'}), 404
    
    settings = db.get_settings(user_id)
    can_trade, reason = risk_manager.can_strategy_trade(strategy, settings)
    
    if not can_trade: return jsonify({'success': False, 'message': reason}), 400
    
    db.update_strategy(strategy_id, {'is_active': True})
    return jsonify({'success': True, 'message': 'Strategy started'})


@strategy_bp.route('/<strategy_id>/stop', methods=['POST'])
@jwt_required()
def stop_strategy(strategy_id):
    data = request.get_json() or {}
    reason = data.get('reason', 'Manual')
    db.update_strategy(strategy_id, {'is_active': False})
    return jsonify({'success': True, 'message': f'Strategy stopped: {reason}'})


@strategy_bp.route('/stop-all', methods=['POST'])
@jwt_required()
def stop_all_strategies():
    user_id = get_jwt_identity()
    strategies = db.get_active_strategies(user_id)
    for s in strategies: db.update_strategy(s['_id'], {'is_active': False})
    return jsonify({'message': f'Stopped {len(strategies)} strategies'})


@strategy_bp.route('/status', methods=['GET'])
@jwt_required()
def get_engine_status():
    user_id = get_jwt_identity()
    engine = get_trading_engine(user_id)
    return jsonify(engine.get_engine_status())


@strategy_bp.route('/decision', methods=['GET'])
@jwt_required()
def get_decision():
    """Get decision - STRICTLY from MongoDB (No Auto-Sync)"""
    symbol = request.args.get('symbol', 'NIFTY')
    interval = request.args.get('interval', '5')
    
    candles = candle_service.get_candles_for_analysis(db, symbol, interval)
    
    if not candles:
        return jsonify({'error': f'No data for {symbol}. Check Scheduler.', 'count': 0}), 400
        
    if len(candles) < 20:
        return jsonify({'error': 'Insufficient data', 'count': len(candles)}), 400
    
    try:
        df = pd.DataFrame(candles)
        if 'datetime' not in df.columns and 'timestamp' in df.columns:
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
        df.set_index('datetime', inplace=True)
        
        result = analyze_market(df, symbol)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@strategy_bp.route('/candles/<symbol>', methods=['GET'])
@jwt_required()
def get_candles(symbol):
    """
    Get candles for chart.
    If no data exists, return MOCK data for visualization,
    BUT DO NOT SAVE IT TO DB.
    """
    interval = request.args.get('interval', '5')
    limit = int(request.args.get('limit', 100))
    
    candles = candle_service.get_candles(db, symbol, interval, limit)
    
    if not candles or len(candles) < 10:
        print(f"⚠️ Serving MOCK data for {symbol} chart (Visual Only)")
        candles = candle_service.generate_mock_candles(symbol, int(interval), limit)
        # CRITICAL FIX: DO NOT CALL _save_to_db HERE
    
    return jsonify({
        'symbol': symbol,
        'interval': interval,
        'candles': candles,
        'count': len(candles)
    })


@strategy_bp.route('/candles/<symbol>/sync', methods=['POST'])
@jwt_required()
def sync_candles(symbol):
    user_id = get_jwt_identity()
    interval = request.args.get('interval', '5')
    user = db.get_user_by_id(user_id)
    access_token = user.get('groww_access_token') if user else None
    
    result = candle_service.sync_candles(db, symbol, interval, access_token)
    return jsonify(result)


@strategy_bp.route('/indicators/<symbol>', methods=['GET'])
@jwt_required()
def get_all_indicators(symbol):
    from analysis import (
        calculate_all_momentum, calculate_all_volatility,
        calculate_all_support_resistance, detect_all_patterns
    )
    from analysis.decision_engine import to_python_type
    
    interval = request.args.get('interval', '5')
    candles = candle_service.get_candles_for_analysis(db, symbol, interval)
    
    if not candles: return jsonify({'error': 'No data'}), 400
    
    df = pd.DataFrame(candles)
    if 'datetime' not in df.columns and 'timestamp' in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
    df.set_index('datetime', inplace=True)
    
    result = {
        'symbol': symbol,
        'current_price': float(df['close'].iloc[-1]),
        'momentum': to_python_type(calculate_all_momentum(df)),
        'volatility': to_python_type(calculate_all_volatility(df)),
        'patterns': to_python_type(detect_all_patterns(df)),
        'timestamp': datetime.now().isoformat()
    }
    return jsonify(result)

@strategy_bp.route('/<strategy_id>/analyze', methods=['GET'])
@jwt_required()
def analyze_strategy(strategy_id):
    strategy = db.get_strategy_by_id(strategy_id)
    if not strategy: return jsonify({'error': 'Strategy not found'}), 404
    
    symbol = strategy.get('index', 'NIFTY')
    candles = candle_service.get_candles_for_analysis(db, symbol, '5')
    
    if not candles: return jsonify({'error': 'No candle data'}), 400
    
    df = pd.DataFrame(candles)
    if 'datetime' not in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
    df.set_index('datetime', inplace=True)
    
    result = analyze_market(df, symbol)
    return jsonify(result)

