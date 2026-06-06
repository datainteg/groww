"""Market Routes - Live data, instruments, and Market Direction Engine"""
import json
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
import pandas as pd

from database import db, redis_client
from services import instrument_sync
from services.candle_service import candle_service
from services.groww_client import GrowwClient
from config import config

market_bp = Blueprint('market', __name__, url_prefix='/api/market')

# Helper to find a valid Groww client (even for Paper users)
def get_data_client(current_user_id):
    """
    Get a Groww client instance.
    If current user is not connected, try to find a system-wide connected user
    to fetch global market data (like NIFTY index).
    """
    from services import get_groww_client
    
    # 1. Try current user
    user = db.get_user_by_id(current_user_id)
    if user and user.get('broker_connected'):
        return get_groww_client(current_user_id)
        
    # 2. If Paper User, try to find an 'Admin' or any connected user
    admin_user = db.users.find_one({'broker_connected': True})
    if admin_user:
        return get_groww_client(str(admin_user['_id']))
        
    return None


# ============================================================
# NEW: MARKET DIRECTION ENGINE ENDPOINTS
# ============================================================

@market_bp.route('/direction', methods=['GET'])
@jwt_required()
def get_all_directions():
    """
    Get market direction for all indices
    Returns direction (UP/DOWN/NEUTRAL) and strength (0-100) for NIFTY, BANKNIFTY, SENSEX
    """
    from services.direction_scheduler import get_cached_direction

    # Prefer the cross-process Redis cache so any API worker serves what the
    # (separate) scheduler process computed, with staleness flagged.
    indices = ['NIFTY', 'BANKNIFTY', 'SENSEX']
    directions = {}
    for sym in indices:
        d = get_cached_direction(sym)
        if d:
            directions[sym] = d

    if not directions:
        # Fallback: Calculate on-demand if scheduler hasn't published yet.
        directions = _calculate_directions_on_demand()

    return jsonify({
        'directions': directions,
        'timestamp': datetime.now().isoformat()
    })


@market_bp.route('/direction/<symbol>', methods=['GET'])
@jwt_required()
def get_symbol_direction(symbol):
    """
    Get market direction for a specific symbol
    Query params: force_refresh=true
    """
    from services.direction_scheduler import get_cached_direction
    from analysis import analyze_direction, aggregate_to_timeframe

    symbol = symbol.upper()
    force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'

    # Try the cross-process cache first (Redis, staleness-flagged).
    if not force_refresh:
        cached = get_cached_direction(symbol)
        if cached:
            return jsonify(cached)

    # Calculate on-demand
    try:
        candles_1m = candle_service.get_candles(db, symbol, '1', 200)
        candles_5m = candle_service.get_candles(db, symbol, '5', 100)
        candles_15m = candle_service.get_candles(db, symbol, '15', 100)

        # Require REAL 1m data — never substitute 5m as 1m (corrupts the
        # 1m-weighted component of the direction engine).
        if not candles_1m or len(candles_1m) < 50:
            return jsonify({
                'symbol': symbol, 'direction': 'NEUTRAL', 'confidence': 0.0,
                'degraded': True, 'reason': 'insufficient 1m data'
            }), 200

        if candles_5m and len(candles_5m) >= 20:
            df_5m = pd.DataFrame(candles_5m)
            df_1m = pd.DataFrame(candles_1m)

            if candles_15m and len(candles_15m) >= 20:
                df_15m = pd.DataFrame(candles_15m)
            else:
                df_15m = aggregate_to_timeframe(df_5m, '15')

            # Get live LTP
            ltp_str = redis_client.get_cached_ltp(symbol)
            live_ltp = float(ltp_str) if ltp_str else None

            result = analyze_direction(
                df_1m=df_1m,
                df_5m=df_5m,
                df_15m=df_15m,
                symbol=symbol,
                live_ltp=live_ltp
            )

            return jsonify(result)
        else:
            return jsonify({
                'error': 'Insufficient candle data',
                'symbol': symbol,
                'direction': 'NEUTRAL',
                'strength': 50
            }), 400
            
    except Exception as e:
        return jsonify({
            'error': str(e),
            'symbol': symbol,
            'direction': 'NEUTRAL',
            'strength': 50
        }), 500


@market_bp.route('/direction/scheduler/status', methods=['GET'])
@jwt_required()
def get_direction_scheduler_status():
    """Get status of the direction scheduler"""
    from services.direction_scheduler import direction_scheduler
    return jsonify(direction_scheduler.get_status())


@market_bp.route('/direction/scheduler/start', methods=['POST'])
@jwt_required()
def start_direction_scheduler():
    """Start the direction scheduler (admin only)"""
    from services.direction_scheduler import direction_scheduler
    direction_scheduler.start()
    return jsonify({'message': 'Direction scheduler started', 'status': direction_scheduler.get_status()})


@market_bp.route('/direction/scheduler/stop', methods=['POST'])
@jwt_required()
def stop_direction_scheduler():
    """Stop the direction scheduler (admin only)"""
    from services.direction_scheduler import direction_scheduler
    direction_scheduler.stop()
    return jsonify({'message': 'Direction scheduler stopped'})


def _calculate_directions_on_demand():
    """Calculate directions for all indices when scheduler not running"""
    from analysis import analyze_direction, aggregate_to_timeframe
    
    directions = {}
    indices = ['NIFTY', 'BANKNIFTY', 'SENSEX']
    
    for symbol in indices:
        try:
            candles_1m = candle_service.get_candles(db, symbol, '1', 200)
            candles_5m = candle_service.get_candles(db, symbol, '5', 100)

            # Require REAL 1m data; do not fake it from 5m.
            if not candles_1m or len(candles_1m) < 50:
                directions[symbol] = {
                    'symbol': symbol, 'direction': 'NEUTRAL', 'confidence': 0.0,
                    'degraded': True, 'reason': 'insufficient 1m data'
                }
                continue

            if candles_5m and len(candles_5m) >= 20:
                df_5m = pd.DataFrame(candles_5m)
                df_1m = pd.DataFrame(candles_1m)
                df_15m = aggregate_to_timeframe(df_5m, '15')

                ltp_str = redis_client.get_cached_ltp(symbol)
                live_ltp = float(ltp_str) if ltp_str else None

                result = analyze_direction(
                    df_1m=df_1m,
                    df_5m=df_5m,
                    df_15m=df_15m,
                    symbol=symbol,
                    live_ltp=live_ltp
                )

                directions[symbol] = result
        except Exception as e:
            directions[symbol] = {
                'direction': 'NEUTRAL',
                'strength': 50,
                'error': str(e)
            }
    
    return directions


# ============================================================
# LIVE MARKET DATA ENDPOINTS
# ============================================================

@market_bp.route('/status', methods=['GET'])
@jwt_required()
def get_status():
    """Get market status (Open/Closed)"""
    from utils import get_market_status
    return jsonify(get_market_status())


@market_bp.route('/indices', methods=['GET'])
@jwt_required()
def get_indices():
    """
    Get major indices (NIFTY, BANKNIFTY, SENSEX)
    Uses 'Get Quote' API to get accurate Day Change % directly from source.
    """
    # 1. Try Redis Cache
    cached_indices = redis_client.get('market:indices_summary')
    if cached_indices:
        return jsonify(json.loads(cached_indices))

    user_id = get_jwt_identity()
    client = get_data_client(user_id)
    
    if not client:
        return jsonify([])

    indices_config = [
        {'exchange': 'NSE', 'segment': 'CASH', 'symbol': 'NIFTY', 'display': 'NIFTY'},
        {'exchange': 'NSE', 'segment': 'CASH', 'symbol': 'BANKNIFTY', 'display': 'BANKNIFTY'},
        {'exchange': 'BSE', 'segment': 'CASH', 'symbol': 'SENSEX', 'display': 'SENSEX'}
    ]

    indices_data = []
    
    try:
        # We use loop here because 'Get Quote' is per symbol, 
        # but provides much richer data (change %, OHLC) than 'Get LTP'.
        for idx in indices_config:
            res = client.get_quote(idx['symbol'], idx['exchange'], idx['segment'])
            
            if res.get('success'):
                data = res['data']
                indices_data.append({
                    'symbol': idx['display'],
                    'price': data.get('last_price', 0),
                    'change': data.get('day_change', 0),
                    'change_percent': data.get('day_change_perc', 0),
                    'low': data.get('low_trade_range', 0), 
                    'high': data.get('high_trade_range', 0)
                })
        
        if indices_data:
            # Cache for 2 seconds
            redis_client.set('market:indices_summary', json.dumps(indices_data), expiry=2)
            return jsonify(indices_data)
            
    except Exception as e:
        print(f"Error fetching indices: {e}")
        
    return jsonify([])


@market_bp.route('/ltp/<symbol>', methods=['GET'])
@jwt_required()
def get_ltp(symbol):
    """
    Get LTP for a symbol.
    Strategy: Redis (Heartbeat) -> Groww API
    """
    symbol = symbol.upper()
    
    # 1. Try Redis (Fastest - populated by Scheduler)
    cached_ltp = redis_client.get_cached_ltp(symbol)
    if cached_ltp:
        return jsonify({'symbol': symbol, 'ltp': cached_ltp, 'source': 'CACHE'})
    
    # 2. Try Groww API
    user_id = get_jwt_identity()
    client = get_data_client(user_id)
    
    if client:
        # Determine exchange prefix
        exchange_sym = f"NSE_{symbol}" if not symbol.startswith(('NSE_', 'BSE_')) else symbol
        
        try:
            result = client.get_ltp([exchange_sym])
            if result.get('success'):
                price = result['data'].get(exchange_sym, 0)
                if price > 0:
                    # Cache it since we fetched it
                    redis_client.cache_ltp(symbol, price)
                    return jsonify({'symbol': symbol, 'ltp': price, 'source': 'LIVE'})
        except:
            pass
            
    return jsonify({'symbol': symbol, 'ltp': 0, 'error': 'Unavailable'})


@market_bp.route('/quote/<symbol>', methods=['GET'])
@jwt_required()
def get_quote(symbol):
    """Get full quote (Open, High, Low, Close)"""
    user_id = get_jwt_identity()
    client = get_data_client(user_id)
    
    if not client:
        return jsonify({'error': 'Broker not connected'}), 400
        
    exchange_sym = symbol.upper()
    if not exchange_sym.startswith(('NSE_', 'BSE_')):
        # Simple heuristic if no prefix provided
        exchange_sym = f"NSE_{exchange_sym}" if exchange_sym != 'SENSEX' else 'BSE_SENSEX'
    
    # Extract params for get_quote. Split only on the FIRST underscore so
    # multi-part symbols (e.g. NSE_NIFTY_23JUN_19000CE) keep their full name.
    parts = exchange_sym.split('_', 1)
    exchange = parts[0]
    trading_symbol = parts[1] if len(parts) > 1 else exchange_sym
    
    try:
        result = client.get_quote(trading_symbol, exchange, 'CASH') # Default to CASH for basic quotes
        if result.get('success'):
            return jsonify(result['data'])
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
        
    return jsonify({'error': 'Quote unavailable'}), 404


@market_bp.route('/option-chain/<underlying>', methods=['GET'])
@jwt_required()
def get_option_chain(underlying):
    """
    Get Option Chain. 
    Returns data from Groww API formatted for frontend.
    """
    expiry = request.args.get('expiry')
    if not expiry:
        return jsonify({'error': 'expiry required'}), 400
    
    user_id = get_jwt_identity()
    client = get_data_client(user_id)
    
    if client:
        try:
            # 1. Fetch from Groww
            res = client.get_option_chain(underlying, expiry)
            
            if res.get('success'):
                payload = res['data']
                raw_strikes = payload.get('strikes', {})
                underlying_ltp = payload.get('underlying_ltp', 0)
                
                # 2. Transform nested dictionary to list for frontend
                # Groww returns: { "23400": { "CE": {...}, "PE": {...} } }
                # Frontend likely expects: [ {strike: 23400, CE: {...}, PE: {...}} ]
                formatted_data = []
                
                for strike_price, options in raw_strikes.items():
                    entry = {
                        'strike_price': float(strike_price),
                        'CE': options.get('CE'),
                        'PE': options.get('PE')
                    }
                    formatted_data.append(entry)
                
                # Sort by strike price
                formatted_data.sort(key=lambda x: x['strike_price'])
                
                return jsonify({
                    'underlying': underlying,
                    'expiry': expiry,
                    'underlying_ltp': underlying_ltp,
                    'data': formatted_data,
                    'source': 'LIVE'
                })
        except Exception as e:
            print(f"API Error: {e}")

    # Fallback to DB if API fails
    instruments = db.get_instruments_by_underlying(underlying, expiry)
    
    # Enrich DB data with live LTP from Redis
    enriched_data = []
    for inst in instruments:
        ltp = redis_client.get_cached_ltp(inst['trading_symbol'])
        if ltp:
            inst['ltp'] = ltp
        enriched_data.append(inst)
    
    return jsonify({
        'underlying': underlying, 
        'expiry': expiry, 
        'data': enriched_data,
        'source': 'DATABASE'
    })


@market_bp.route('/ohlc', methods=['GET'])
@jwt_required()
def get_ohlc_data():
    """Get OHLC for specific symbols"""
    symbols = request.args.get('symbols', '').split(',')
    if not symbols:
        return jsonify({})
        
    user_id = get_jwt_identity()
    client = get_data_client(user_id)
    
    # Format symbols (NSE_PREFIX)
    exchange_symbols = [f"NSE_{s}" if not s.startswith(('NSE_', 'BSE_')) else s for s in symbols]
    
    if client:
        res = client.get_ohlc(exchange_symbols)
        if res.get('success'):
            return jsonify(res['data'])
            
    return jsonify({'error': 'Failed to fetch OHLC'})


@market_bp.route('/instruments', methods=['GET'])
@jwt_required()
def get_instruments():
    """Get instruments from database"""
    underlying = request.args.get('underlying')
    expiry = request.args.get('expiry')
    option_type = request.args.get('option_type')
    
    instruments = db.get_instruments_by_underlying(underlying, expiry, option_type)
    return jsonify(instruments)


@market_bp.route('/instruments/sync', methods=['POST'])
@jwt_required()
def sync_instruments():
    """Trigger instrument sync"""
    result = instrument_sync.sync_instruments()
    if result['success']:
        return jsonify(result)
    return jsonify({'error': result.get('error', 'Sync failed')}), 400


@market_bp.route('/expiries/<underlying>', methods=['GET'])
@jwt_required()
def get_expiries(underlying):
    """Get available expiries"""
    expiries = db.get_available_expiries(underlying)
    return jsonify({'expiries': expiries})


@market_bp.route('/atm/<underlying>/<expiry>', methods=['GET'])
@jwt_required()
def get_atm_options(underlying, expiry):
    """Get ATM options with Live Spot Price"""
    # 1. Get Spot Price
    ltp_response = get_ltp(underlying)
    spot_data = ltp_response.get_json()
    spot_price = spot_data.get('ltp', 0)
    
    if spot_price == 0:
         return jsonify({'error': 'Could not fetch spot price'}), 400

    # 2. Calculate ATM
    atm_data = db.get_atm_strikes(underlying, expiry, spot_price)
    
    return jsonify(atm_data)


@market_bp.route('/search', methods=['GET'])
@jwt_required()
def search_instruments():
    """Search instruments"""
    query = request.args.get('q', '')
    limit = int(request.args.get('limit', 20))
    
    instruments = instrument_sync.search_instruments(query, limit)
    return jsonify(instruments)