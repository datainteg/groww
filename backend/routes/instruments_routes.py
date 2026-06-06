"""Instruments Routes"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from database import db
# Explicit import to avoid package init cycles
from services.instrument_sync import instrument_sync 

instruments_bp = Blueprint('instruments', __name__, url_prefix='/api/instruments')

@instruments_bp.route('/sync', methods=['POST'])
@jwt_required()
def sync_instruments():
    result = instrument_sync.sync_instruments()
    return jsonify(result)

@instruments_bp.route('/search', methods=['GET'])
@jwt_required()
def search_instruments():
    query = request.args.get('q', '')
    underlying = request.args.get('underlying')
    expiry = request.args.get('expiry')
    limit = int(request.args.get('limit', 20))
    
    # Simple guard
    if not any([query, underlying, expiry]):
        return jsonify([])
    
    instruments = instrument_sync.search_instruments(
        query=query, 
        underlying=underlying, 
        expiry=expiry, 
        limit=limit
    )
    return jsonify(instruments)

@instruments_bp.route('/details/<path:trading_symbol>', methods=['GET'])
@jwt_required()
def get_instrument_details(trading_symbol):
    if not trading_symbol:
        return jsonify({'error': 'Trading symbol required'}), 400
    instrument = instrument_sync.get_instrument_by_symbol(trading_symbol)
    if instrument:
        return jsonify(instrument)
    return jsonify({'error': 'Instrument not found'}), 404

@instruments_bp.route('/expiries/<underlying>', methods=['GET'])
@jwt_required()
def get_expiries(underlying):
    pipeline = [
        {'$match': {'underlying_symbol': underlying}},
        {'$group': {'_id': '$expiry_date'}},
        {'$sort': {'_id': 1}}
    ]
    results = list(db.instruments.aggregate(pipeline))
    expiries = [item['_id'] for item in results if item['_id']]
    return jsonify({'expiries': expiries})

@instruments_bp.route('/count', methods=['GET'])
@jwt_required()
def get_count():
    return jsonify(instrument_sync.get_count())

@instruments_bp.route('/last-sync', methods=['GET'])
@jwt_required()
def get_last_sync():
    instrument = db.instruments.find_one()
    if instrument and 'synced_at' in instrument:
        return jsonify({
            'synced_at': instrument['synced_at'],
            'total': db.instruments.count_documents({})
        })
    return jsonify({'synced_at': None, 'total': 0})