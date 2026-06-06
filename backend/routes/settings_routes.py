"""Settings Routes"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from services.telegram_alert import TelegramAlert
from bson import ObjectId

settings_bp = Blueprint('settings', __name__, url_prefix='/api/settings')

# Helper to ensure we update the correct user document
def update_user_field(user_id, field, value):
    try:
        # Try updating by string ID first
        result = db.users.update_one({'_id': user_id}, {'$set': {field: value}})
        if result.modified_count == 0:
            # Fallback to ObjectId
            db.users.update_one({'_id': ObjectId(user_id)}, {'$set': {field: value}})
        return True
    except Exception as e:
        print(f"Error updating user field: {e}")
        return False

@settings_bp.route('/', methods=['GET'])
@jwt_required()
def get_settings():
    """Get user settings"""
    user_id = get_jwt_identity()
    
    # 1. Fetch User Config (Execution Mode is here)
    user = db.get_user_by_id(user_id)
    
    # 2. Fetch extended settings (Risk limits, etc.)
    settings = db.get_settings(user_id)
    
    if not settings:
        settings = {}

    # Merge Execution Mode from User Document into Settings response
    settings['execution_mode'] = user.get('execution_mode', 'PAPER') if user else 'PAPER'
    
    # Defaults
    settings.setdefault('theme', 'dark')
    settings.setdefault('kill_switch', False)
    settings.setdefault('alerts_enabled', True)
    settings.setdefault('overall_max_profit', 10000)
    settings.setdefault('overall_max_loss', 5000)
    settings.setdefault('max_concurrent_trades', 3)
    settings.setdefault('telegram_configured', False)
    
    return jsonify(settings)


@settings_bp.route('/', methods=['PUT'])
@jwt_required()
def update_settings():
    """Update user settings"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    # Allowed fields for 'settings' collection
    allowed_fields = [
        'theme', 'kill_switch', 'alerts_enabled',
        'overall_max_profit', 'overall_max_loss', 'max_concurrent_trades',
        'telegram_bot_token', 'telegram_chat_id'
    ]
    
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    
    if update_data:
        db.upsert_settings(user_id, update_data)
        
    # Handle 'execution_mode' separately (lives in users collection)
    if 'execution_mode' in data:
        mode = data['execution_mode'].upper()
        if mode in ['PAPER', 'LIVE']:
            update_user_field(user_id, 'execution_mode', mode)
    
    return jsonify({'message': 'Settings updated'})


@settings_bp.route('/mode', methods=['PUT'])
@jwt_required()
def update_execution_mode():
    """Update execution mode (PAPER/LIVE)"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    mode = data.get('mode', 'PAPER').upper()
    if mode not in ['PAPER', 'LIVE']:
        return jsonify({'error': 'Invalid mode. Must be PAPER or LIVE'}), 400
    
    # Single source of truth: execution_mode lives in the users collection only.
    success = update_user_field(user_id, 'execution_mode', mode)

    if success:
        return jsonify({'message': f'Execution mode set to {mode}', 'execution_mode': mode})
    else:
        return jsonify({'error': 'Failed to update mode in database'}), 500


@settings_bp.route('/theme', methods=['PUT'])
@jwt_required()
def update_theme():
    """Update theme (dark/light)"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    theme = data.get('theme', 'dark').lower()
    if theme not in ['dark', 'light']:
        return jsonify({'error': 'Invalid theme. Must be dark or light'}), 400
    
    db.upsert_settings(user_id, {'theme': theme})
    
    return jsonify({'message': f'Theme set to {theme}', 'theme': theme})


@settings_bp.route('/kill-switch', methods=['POST'])
@jwt_required()
def toggle_kill_switch():
    """Toggle kill switch"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    enabled = data.get('enabled', False)
    db.upsert_settings(user_id, {'kill_switch': enabled})
    
    # If kill switch enabled, stop all strategies
    if enabled:
        strategies = db.get_strategies_by_user(user_id) 
        for s in strategies:
            db.update_strategy(s['_id'], {'is_active': False})
        
        # Send telegram alert using user's credentials
        settings = db.get_settings(user_id)
        if settings and settings.get('telegram_bot_token'):
            alert = TelegramAlert(settings['telegram_bot_token'], settings['telegram_chat_id'])
            alert.send_kill_switch_alert("User initiated manual kill switch")
    
    return jsonify({
        'message': f'Kill switch {"enabled" if enabled else "disabled"}',
        'kill_switch': enabled
    })


@settings_bp.route('/telegram', methods=['POST'])
@jwt_required()
def configure_telegram():
    """Configure Telegram notifications"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    bot_token = data.get('bot_token')
    chat_id = data.get('chat_id')
    
    if not bot_token or not chat_id:
        return jsonify({'error': 'Both bot_token and chat_id are required'}), 400
    
    # Test the connection with the NEW credentials
    alert_service = TelegramAlert(bot_token, chat_id)
    success = alert_service.test_connection()
    
    if success:
        db.upsert_settings(user_id, {
            'telegram_bot_token': bot_token,
            'telegram_chat_id': chat_id,
            'telegram_configured': True
        })
        return jsonify({'message': 'Telegram configured successfully', 'success': True})
    else:
        return jsonify({'error': 'Failed to send test message. Check Token/ID.', 'success': False}), 400


@settings_bp.route('/telegram/test', methods=['POST'])
@jwt_required()
def test_telegram():
    """Send test telegram message using saved settings"""
    user_id = get_jwt_identity()
    settings = db.get_settings(user_id)
    
    if not settings or not settings.get('telegram_configured'):
        return jsonify({'success': False, 'message': 'Telegram not configured'}), 400
    
    # Initialize service with user credentials
    bot_token = settings.get('telegram_bot_token')
    chat_id = settings.get('telegram_chat_id')
    alert_service = TelegramAlert(bot_token, chat_id)
    
    # Send Test
    success = alert_service.test_connection()
    
    if success:
        return jsonify({'success': True, 'message': 'Test message sent successfully'})
    else:
        return jsonify({'success': False, 'message': 'Failed to send message'}), 400


# --- NEW: Send Custom Message Endpoint ---
@settings_bp.route('/telegram/send', methods=['POST'])
@jwt_required()
def send_custom_message():
    """Send a custom message via Telegram"""
    user_id = get_jwt_identity()
    data = request.get_json()
    message = data.get('message')

    if not message:
        return jsonify({'success': False, 'error': 'Message content is required'}), 400

    settings = db.get_settings(user_id)
    if not settings or not settings.get('telegram_configured'):
        return jsonify({'success': False, 'error': 'Telegram not configured'}), 400

    # Initialize service
    bot_token = settings.get('telegram_bot_token')
    chat_id = settings.get('telegram_chat_id')
    alert_service = TelegramAlert(bot_token, chat_id)

    # Send the custom message
    # We use send_alert here which acts as a generic message sender wrapper
    success = alert_service.send_alert(user_id, message)

    if success:
        return jsonify({'success': True, 'message': 'Message sent successfully'})
    else:
        return jsonify({'success': False, 'error': 'Failed to send message to Telegram'}), 500


@settings_bp.route('/telegram', methods=['DELETE'])
@jwt_required()
def disconnect_telegram():
    """Disconnect Telegram"""
    user_id = get_jwt_identity()
    
    db.upsert_settings(user_id, {
        'telegram_bot_token': None,
        'telegram_chat_id': None,
        'telegram_configured': False
    })
    
    return jsonify({'message': 'Telegram disconnected', 'success': True})


@settings_bp.route('/reset-daily', methods=['POST'])
@jwt_required()
def reset_daily():
    """Reset daily counters for all strategies"""
    user_id = get_jwt_identity()
    
    strategies = db.get_strategies_by_user(user_id)
    for s in strategies:
        db.update_strategy(s['_id'], {
            'today_orders': 0,
            'today_pnl': 0
        })
    
    db.upsert_settings(user_id, {'overall_pnl_today': 0})
    
    return jsonify({'message': f'Reset daily counters for {len(strategies)} strategies'})