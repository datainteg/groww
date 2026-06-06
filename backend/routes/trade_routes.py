"""Trade Routes"""
import time
from contextlib import contextmanager
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from bson import ObjectId
from database import db, redis_client
from config import config

trade_bp = Blueprint('trade', __name__, url_prefix='/api/trade')

# ==========================================
# HELPER: Redis Distributed Lock
# ==========================================
@contextmanager
def acquire_trade_lock(user_id, timeout=5):
    """
    Prevents race conditions (e.g. double spending, duplicate orders).
    Uses Redis SETNX to ensure only one trade operation runs at a time per user.
    """
    client = redis_client.client
    # If Redis is down, we allow the trade but log a warning (Fail-open)
    if not client:
        print("Warning: Redis lock unavailable, proceeding without lock.")
        yield True
        return

    lock_key = f"trade_lock:{user_id}"
    identifier = str(time.time())
    
    # Try to acquire lock
    # nx=True -> Only set if not exists
    # ex=timeout -> Auto-expire after 5s to prevent deadlocks
    if client.set(lock_key, identifier, nx=True, ex=timeout):
        try:
            yield True
        finally:
            # Release lock only if we own it
            current_value = client.get(lock_key)
            if current_value and current_value == identifier:
                client.delete(lock_key)
    else:
        # Lock acquisition failed
        yield False

# ==========================================
# HELPER: Get Execution Mode
# ==========================================
def get_user_execution_mode(user_id):
    """
    Fetches the execution mode (PAPER/LIVE).
    Single source of truth = users collection. Settings is only a legacy
    fallback for old documents; config default is the final safety net.
    """
    try:
        # 1. Users collection is authoritative.
        user = db.users.find_one({'_id': user_id})
        if not user:
            try:
                user = db.users.find_one({'_id': ObjectId(user_id)})
            except Exception:
                pass
        if user and user.get('execution_mode'):
            return user.get('execution_mode')

        # 2. Legacy fallback: execution_mode previously stored in settings.
        settings = db.get_settings(user_id)
        if settings and settings.get('execution_mode'):
            return settings.get('execution_mode')

    except Exception as e:
        print(f"Error fetching execution mode: {e}")

    # 3. Fallback to config default (safety).
    from config import config
    return config.EXECUTION_MODE

def get_paper_broker(user_id):
    """Get paper broker instance"""
    from services import get_paper_broker
    return get_paper_broker(user_id)


# ==========================================
# ROUTES
# ==========================================

@trade_bp.route('/place-order', methods=['POST'])
@jwt_required()
def place_order():
    """Place an order with Concurrency Locking"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    required = ['trading_symbol', 'quantity', 'transaction_type']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    # 1. Acquire Lock
    with acquire_trade_lock(user_id) as acquired:
        if not acquired:
            return jsonify({'error': 'System busy. Previous order processing...'}), 429
            
        # 2. Determine Execution Mode
        execution_mode = get_user_execution_mode(user_id)

        # 3. Execution Logic
        if execution_mode == 'PAPER':
            broker = get_paper_broker(user_id)
            result = broker.place_order(
                trading_symbol=data['trading_symbol'],
                quantity=data['quantity'],
                transaction_type=data['transaction_type'],
                order_type=data.get('order_type', 'MARKET'),
                price=data.get('price'),
                segment=data.get('segment', 'FNO')
            )
        else:
            # LIVE MODE
            from services import get_groww_client
            groww = get_groww_client(user_id)
            if not groww:
                return jsonify({'error': 'Broker not connected'}), 400
                
            result = groww.place_order(
                trading_symbol=data['trading_symbol'],
                quantity=data['quantity'],
                transaction_type=data['transaction_type'],
                order_type=data.get('order_type', 'MARKET'),
                price=data.get('price', 0),
                trigger_price=data.get('trigger_price'),
                product=data.get('product', 'MIS'),
                segment=data.get('segment', 'FNO')
            )
        
        if result.get('success'):
            return jsonify(result)
        return jsonify({'error': result.get('error', 'Order failed')}), 400


@trade_bp.route('/orders', methods=['GET'])
@jwt_required()
def get_orders():
    """Get order list"""
    user_id = get_jwt_identity()
    segment = request.args.get('segment', 'FNO')
    execution_mode = get_user_execution_mode(user_id)
    
    if execution_mode == 'PAPER':
        broker = get_paper_broker(user_id)
        orders = broker.get_orders()
        return jsonify({'success': True, 'data': orders})
    else:
        from services import get_groww_client
        groww = get_groww_client(user_id)
        if not groww:
            return jsonify({'success': False, 'error': 'Broker not connected', 'data': []})
        result = groww.get_order_list(segment)
        return jsonify({'success': True, 'data': result.get('data', [])})


@trade_bp.route('/order/<order_id>', methods=['GET'])
@jwt_required()
def get_order_status(order_id):
    """Get status of a specific order"""
    user_id = get_jwt_identity()
    segment = request.args.get('segment', 'FNO')
    execution_mode = get_user_execution_mode(user_id)
    
    if execution_mode == 'PAPER':
        # For paper trading, find the order in trades
        broker = get_paper_broker(user_id)
        orders = broker.get_orders()
        order = next((o for o in orders if o.get('order_id') == order_id), None)
        if order:
            return jsonify({'success': True, 'data': order})
        return jsonify({'error': 'Order not found'}), 404
    else:
        from services import get_groww_client
        groww = get_groww_client(user_id)
        if not groww:
             return jsonify({'error': 'Broker not connected'}), 400
        result = groww.get_order_status(order_id, segment)
        if result.get('success'):
            return jsonify(result)
        return jsonify({'error': result.get('error', 'Order not found')}), 404


@trade_bp.route('/positions', methods=['GET'])
@jwt_required()
def get_positions():
    """Get positions"""
    user_id = get_jwt_identity()
    execution_mode = get_user_execution_mode(user_id)
    
    if execution_mode == 'PAPER':
        broker = get_paper_broker(user_id)
        positions = broker.get_positions()
        return jsonify({'positions': positions})
    else:
        # LIVE MODE: Fetch from Groww
        from services import get_groww_client
        groww = get_groww_client(user_id)
        if not groww:
            return jsonify({'positions': []})
            
        result = groww.get_positions()
        return jsonify({'positions': result.get('data', []) if result.get('success') else []})


@trade_bp.route('/trades', methods=['GET'])
@jwt_required()
def get_trades():
    """Get trade history"""
    user_id = get_jwt_identity()
    limit = int(request.args.get('limit', 50))
    
    trades = db.get_trades_by_user(user_id, limit)
    return jsonify(trades)


@trade_bp.route('/active-trades', methods=['GET'])
@jwt_required()
def get_active_trades():
    """Get active/open trades"""
    user_id = get_jwt_identity()
    trades = db.get_active_trades(user_id)
    return jsonify(trades)


@trade_bp.route('/<trade_id>/exit', methods=['POST'])
@jwt_required()
def exit_trade(trade_id):
    """Exit a trade manually with Locking"""
    user_id = get_jwt_identity()
    
    # 1. Acquire Lock
    with acquire_trade_lock(user_id) as acquired:
        if not acquired:
            return jsonify({'error': 'Processing previous request...'}), 429
            
        trade = db.get_trade_by_id(trade_id)
        if not trade:
            return jsonify({'error': 'Trade not found'}), 404
        
        if str(trade.get('user_id')) != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        if trade.get('status') != 'OPEN':
            return jsonify({'error': 'Trade already closed'}), 400
        
        # Use Trading Engine for consistent exit logic
        from services import get_trading_engine
        engine = get_trading_engine(user_id)
        
        # Determine exit price
        # For manual exit, we let the broker fetch the latest price
        result = engine.execute_exit(
            trade, 
            exit_type='MANUAL'
        )
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'message': 'Trade closed', 
                'pnl': result.get('pnl'),
                'exit_price': result.get('exit_price')
            })
        
        return jsonify({'error': result.get('error', 'Exit failed')}), 400


@trade_bp.route('/<trade_id>/modify', methods=['PUT'])
@jwt_required()
def modify_trade(trade_id):
    """Modify stop loss or target of an open trade"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    trade = db.get_trade_by_id(trade_id)
    if not trade:
        return jsonify({'error': 'Trade not found'}), 404
    
    if str(trade.get('user_id')) != user_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    if trade.get('status') != 'OPEN':
        return jsonify({'error': 'Cannot modify closed trade'}), 400
    
    # Fields that can be modified
    update_data = {}
    
    if 'stop_loss' in data:
        update_data['stop_loss'] = float(data['stop_loss'])
        update_data['current_sl'] = float(data['stop_loss'])
    
    if 'target' in data:
        update_data['target'] = float(data['target'])
    
    if 'trailing_sl_enabled' in data:
        update_data['trailing_sl_enabled'] = bool(data['trailing_sl_enabled'])
    
    if 'trailing_sl_value' in data:
        update_data['trailing_sl_value'] = float(data['trailing_sl_value'])
    
    if not update_data:
        return jsonify({'error': 'No valid fields to update'}), 400
    
    # Update the trade
    success = db.update_trade(trade_id, update_data)
    
    if success:
        # Get updated trade
        updated_trade = db.get_trade_by_id(trade_id)
        return jsonify({
            'success': True,
            'message': 'Trade modified successfully',
            'trade': updated_trade
        })
    
    return jsonify({'error': 'Failed to modify trade'}), 500


@trade_bp.route('/daily-pnl', methods=['GET'])
@jwt_required()
def get_daily_pnl():
    """Get daily P&L summary"""
    user_id = get_jwt_identity()
    execution_mode = get_user_execution_mode(user_id)
    
    if execution_mode == 'PAPER':
        broker = get_paper_broker(user_id)
        return jsonify(broker.get_daily_pnl())
    
    # For LIVE, we calculate from local DB trades for today
    trades = db.get_today_trades(user_id)
    
    total_pnl = sum(t.get('pnl', 0) for t in trades if t.get('status') == 'CLOSED')
    realized_pnl = total_pnl
    unrealized_pnl = sum(t.get('pnl', 0) for t in trades if t.get('status') == 'OPEN')
    
    winning = len([t for t in trades if t.get('pnl', 0) > 0 and t.get('status') == 'CLOSED'])
    losing = len([t for t in trades if t.get('pnl', 0) < 0 and t.get('status') == 'CLOSED'])
    total_closed = winning + losing
    
    return jsonify({
        'total_pnl': total_pnl,
        'realized_pnl': realized_pnl,
        'unrealized_pnl': unrealized_pnl,
        'trades_today': len(trades),
        'winning': winning,
        'losing': losing,
        'win_rate': (winning / total_closed * 100) if total_closed > 0 else 0
    })


@trade_bp.route('/limits', methods=['GET'])
@jwt_required()
def get_limits():
    """Get margin/capital limits"""
    user_id = get_jwt_identity()
    execution_mode = get_user_execution_mode(user_id)
    
    if execution_mode == 'PAPER':
        broker = get_paper_broker(user_id)
        return jsonify(broker.get_limits())
    
    # LIVE mode - fetch from Groww
    from services import get_groww_client
    groww = get_groww_client(user_id)
    if not groww:
        return jsonify({
            'available_balance': 0,
            'used_margin': 0,
            'message': 'Broker not connected'
        })

    # Return dummy for Live if not implemented, or fetch if available
    return jsonify({
        'available_balance': 0,
        'used_margin': 0, 
        'message': 'Live balance fetch not fully implemented in demo'
    })


@trade_bp.route('/paper/reset', methods=['POST'])
@jwt_required()
def reset_paper_account():
    """Reset paper trading account"""
    user_id = get_jwt_identity()
    db.reset_paper_account(user_id, config.PAPER_INITIAL_CAPITAL)
    return jsonify({'success': True, 'message': 'Paper account reset'})


@trade_bp.route('/statistics', methods=['GET'])
@jwt_required()
def get_statistics():
    """Get trading statistics"""
    user_id = get_jwt_identity()
    days = int(request.args.get('days', 30))
    
    summaries = db.get_daily_summaries(user_id, days)
    trades = db.get_trades_by_user(user_id, 500)
    
    if not trades:
        return jsonify({
            'total_pnl': 0,
            'total_trades': 0,
            'win_rate': 0,
            'avg_pnl': 0,
            'best_trade': 0,
            'worst_trade': 0,
            'equity_curve': []
        })
    
    closed = [t for t in trades if t.get('status') == 'CLOSED']
    total_pnl = sum(t.get('pnl', 0) for t in closed)
    winning = len([t for t in closed if t.get('pnl', 0) > 0])
    
    pnls = [t.get('pnl', 0) for t in closed]
    
    return jsonify({
        'total_pnl': total_pnl,
        'total_trades': len(closed),
        'win_rate': (winning / len(closed) * 100) if closed else 0,
        'avg_pnl': total_pnl / len(closed) if closed else 0,
        'best_trade': max(pnls) if pnls else 0,
        'worst_trade': min(pnls) if pnls else 0,
        'equity_curve': [{'date': s['date'], 'pnl': s.get('total_pnl', 0)} for s in reversed(summaries)]
    })


@trade_bp.route('/journal', methods=['GET'])
@jwt_required()
def get_journal():
    """Get trade journal entries"""
    user_id = get_jwt_identity()
    limit = int(request.args.get('limit', 50))
    
    entries = db.get_user_journal(user_id, limit)
    return jsonify(entries)


@trade_bp.route('/journal/<trade_id>', methods=['POST'])
@jwt_required()
def add_journal_entry(trade_id):
    """Add journal entry for a trade"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    entry_id = db.add_journal_entry(trade_id, user_id, {
        'notes': data.get('notes', ''),
        'tags': data.get('tags', []),
        'rating': data.get('rating'),
        'lessons': data.get('lessons', '')
    })
    
    return jsonify({'message': 'Journal entry added', 'entry_id': entry_id}), 201


@trade_bp.route('/execute-strategy', methods=['POST'])
@jwt_required()
def execute_strategy_trade():
    """
    INSTANT EXECUTE: Execute a trade based on strategy settings.
    This is called when user clicks "Execute" button on a strategy.
    It picks ATM strike dynamically and places the order immediately.
    """
    user_id = get_jwt_identity()
    data = request.get_json()
    
    strategy_id = data.get('strategy_id')
    option_type = data.get('option_type', 'CE')  # CE or PE
    
    if not strategy_id:
        return jsonify({'error': 'strategy_id is required'}), 400
    
    # 1. Get strategy
    strategy = db.get_strategy_by_id(strategy_id)
    if not strategy:
        return jsonify({'error': 'Strategy not found'}), 404
    
    if str(strategy.get('user_id')) != user_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # 2. Acquire Lock
    with acquire_trade_lock(user_id) as acquired:
        if not acquired:
            return jsonify({'error': 'System busy. Previous order processing...'}), 429
        
        try:
            from services import get_trading_engine
            engine = get_trading_engine(user_id)
            
            # Build minimal signal data for execute_entry
            signal_data = {
                'signal': 'BULLISH' if option_type == 'CE' else 'BEARISH',
                'confidence': 1.0,
                'manual_execution': True
            }
            
            # Note: execute_entry inside trading_engine needs to handle PAPER/LIVE check
            # but usually it relies on self.broker which is initialized with the correct mode.
            result = engine.execute_entry(strategy, signal_data, option_type)
            
            if result.get('success'):
                return jsonify({
                    'success': True,
                    'message': f'{option_type} order executed successfully',
                    'trade_id': result.get('trade_id'),
                    'option_type': option_type
                })
            else:
                return jsonify({'error': result.get('error', 'Execution failed')}), 400
                
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@trade_bp.route('/quick-trade', methods=['POST'])
@jwt_required()
def quick_trade():
    """
    MANUAL QUICK TRADE: Place a manual order with strategy context.
    Ensures user settings (Paper/Live) are respected.
    """
    user_id = get_jwt_identity()
    data = request.get_json()
    
    required = ['strategy_id', 'option_type', 'transaction_type']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    strategy_id = data.get('strategy_id')
    option_type = data.get('option_type')  # CE or PE
    transaction_type = data.get('transaction_type')  # BUY or SELL
    quantity_override = data.get('quantity')  # Optional override
    
    # 1. Get strategy
    strategy = db.get_strategy_by_id(strategy_id)
    if not strategy:
        return jsonify({'error': 'Strategy not found'}), 404
    
    if str(strategy.get('user_id')) != user_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # 2. Determine quantity
    quantity = quantity_override or strategy.get('quantity', 50)
    
    # 3. Resolve trading symbol (ATM Logic)
    try:
        from services import get_trading_engine
        engine = get_trading_engine(user_id)
        
        if strategy.get('selection_mode') == 'MANUAL':
            trading_symbol = strategy['ce_symbol'] if option_type == 'CE' else strategy['pe_symbol']
        else:
            offset = strategy.get('atm_offset', 0)
            trading_symbol = engine.resolve_dynamic_symbol(strategy['index'], option_type, offset)
    except Exception as e:
        return jsonify({'error': f'Symbol resolution failed: {str(e)}'}), 400
    
    if not trading_symbol:
        return jsonify({'error': 'Could not determine trading symbol'}), 400
    
    # 4. Acquire Lock and Execute
    with acquire_trade_lock(user_id) as acquired:
        if not acquired:
            return jsonify({'error': 'System busy. Previous order processing...'}), 429
        
        try:
            # --- CRITICAL FIX: Fetch Mode from DB ---
            execution_mode = get_user_execution_mode(user_id)

            if execution_mode == 'PAPER':
                broker = get_paper_broker(user_id)
            else:
                from services import get_groww_client
                broker = get_groww_client(user_id)
                if not broker:
                    return jsonify({'error': 'Broker not connected for LIVE trade'}), 400
            
            # Place Order
            result = broker.place_order(
                trading_symbol=trading_symbol,
                quantity=quantity,
                transaction_type=transaction_type,
                order_type='MARKET',
                product=strategy.get('product', 'MIS'),
                segment='FNO'
            )
            
            if result.get('success'):
                # Record trade with strategy link
                trade_data = {
                    'user_id': user_id,
                    'strategy_id': strategy_id,
                    'strategy_name': strategy.get('name'),
                    'trading_symbol': trading_symbol,
                    'symbol': trading_symbol,
                    'option_type': option_type,
                    'transaction_type': transaction_type,
                    'quantity': quantity,
                    'entry_price': result.get('execution_price', result.get('average_price', 0)),
                    'order_id': result.get('order_id'),
                    'status': 'OPEN' if transaction_type == 'BUY' else 'CLOSED',
                    
                    # --- CRITICAL FIX: Save Correct Mode ---
                    'execution_mode': execution_mode,
                    
                    'entry_time': datetime.utcnow(),
                    'stop_loss': strategy.get('stop_loss', 0),
                    'target': strategy.get('target', 0),
                    'current_sl': strategy.get('stop_loss', 0),
                    'trailing_sl_enabled': strategy.get('trailing_sl_enabled', False),
                    'pnl': 0
                }
                
                trade_id = db.create_trade(trade_data)
                
                return jsonify({
                    'success': True,
                    'message': f'{transaction_type} {option_type} order executed ({execution_mode})',
                    'trade_id': trade_id,
                    'order_id': result.get('order_id'),
                    'trading_symbol': trading_symbol,
                    'entry_price': result.get('execution_price', 0),
                    'quantity': quantity
                })
            else:
                return jsonify({'error': result.get('error', 'Order failed')}), 400
                
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@trade_bp.route('/exit-all', methods=['POST'])
@jwt_required()
def exit_all_trades():
    """Exit all open trades immediately"""
    user_id = get_jwt_identity()
    
    with acquire_trade_lock(user_id) as acquired:
        if not acquired:
            return jsonify({'error': 'System busy'}), 429
        
        trades = db.get_active_trades(user_id)
        
        if not trades:
            return jsonify({'success': True, 'exited_count': 0, 'total_pnl': 0})
        
        from services import get_trading_engine
        engine = get_trading_engine(user_id)
        
        total_pnl = 0
        exited_count = 0
        errors = []
        
        for trade in trades:
            try:
                result = engine.execute_exit(trade, exit_type='MANUAL')
                if result.get('success'):
                    total_pnl += result.get('pnl', 0)
                    exited_count += 1
                else:
                    errors.append(f"{trade.get('symbol')}: {result.get('error')}")
            except Exception as e:
                errors.append(f"{trade.get('symbol')}: {str(e)}")
        
        response = {
            'success': True,
            'exited_count': exited_count,
            'total_pnl': total_pnl
        }
        
        if errors:
            response['errors'] = errors
        
        return jsonify(response)