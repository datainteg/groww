"""
Authentication Routes
Handles user registration, login, and profile management
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, jwt_required, get_jwt_identity
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

from database import db
from config import config
from utils import encryption
# Import GrowwClient to verify credentials immediately
from services.groww_client import GrowwClient

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


def get_token_expiry_time():
    """Get token expiry time (24 hours from now)"""
    from datetime import timedelta
    return datetime.utcnow() + timedelta(hours=24)


def is_token_expired(expiry_time):
    """Check if token is expired"""
    if not expiry_time:
        return True
    return datetime.utcnow() > expiry_time


@auth_bp.route('/register', methods=['POST'])
def register():
    """Register a new user"""
    try:
        data = request.get_json(force=True)
    except:
        return jsonify({'error': 'Invalid JSON data'}), 400
    
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid request format'}), 400
    
    email = data.get('email', '').strip()
    password = data.get('password', '')
    
    if not email:
        return jsonify({'error': 'Email is required'}), 400
    if not password:
        return jsonify({'error': 'Password is required'}), 400
    
    # Check if user exists
    if db.get_user_by_email(email):
        return jsonify({'error': 'Email already registered'}), 400
    
    # Create user
    user_data = {
        'email': email,
        'password': generate_password_hash(password),
        'groww_api_key': encryption.encrypt(data.get('groww_api_key', '') or ''),
        'groww_api_secret': encryption.encrypt(data.get('groww_api_secret', '') or ''),
        'groww_access_token': None,
        'groww_token_expiry': None,
        'broker_connected': False,
        'execution_mode': 'PAPER'
    }
    
    user_id = db.create_user(user_data)
    
    # Create default settings
    db.upsert_settings(user_id, {
        'alerts_enabled': True,
        'kill_switch': False,
        'overall_max_profit': config.DEFAULT_MAX_DAILY_PROFIT,
        'overall_max_loss': config.DEFAULT_MAX_DAILY_LOSS,
        'max_concurrent_trades': 5, # Default value since config might be missing it
        'overall_pnl_today': 0,
        'execution_mode': 'PAPER',
        'theme': 'dark',
        'telegram_configured': False
    })
    
    # Initialize paper account
    db.reset_paper_account(user_id, config.PAPER_INITIAL_CAPITAL)
    
    # Auto-login after registration - generate JWT
    access_token = create_access_token(identity=user_id)
    
    return jsonify({
        'message': 'User registered successfully',
        'access_token': access_token,
        'user': {
            'id': user_id,
            'email': email,
            'broker_connected': False,
            'execution_mode': 'PAPER'
        }
    }), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    """Login with email and password (Groww credentials optional)"""
    try:
        data = request.get_json(force=True)
    except:
        return jsonify({'error': 'Invalid JSON data'}), 400
    
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid request format'}), 400
    
    email = data.get('email', '').strip()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    
    # Get user
    user = db.get_user_by_email(email)
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Verify password
    if not check_password_hash(user['password'], password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    user_id = str(user['_id'])
    
    # Optionally update Groww credentials if provided
    groww_api_key = data.get('groww_api_key', '').strip()
    groww_api_secret = data.get('groww_api_secret', '').strip()
    
    if groww_api_key and groww_api_secret:
        # Store encrypted credentials (actual token generation would happen with Groww)
        db.update_user(user_id, {
            'groww_api_key': encryption.encrypt(groww_api_key),
            'groww_api_secret': encryption.encrypt(groww_api_secret),
            'broker_connected': True
        })
    
    # Generate JWT
    access_token = create_access_token(identity=user_id)
    
    return jsonify({
        'message': 'Login successful',
        'access_token': access_token,
        'user': {
            'id': user_id,
            'email': user['email'],
            'broker_connected': user.get('broker_connected', False),
            'execution_mode': user.get('execution_mode', 'PAPER')
        }
    })


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Get current user info"""
    user_id = get_jwt_identity()
    user = db.get_user_by_id(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({
        'id': str(user['_id']),
        'email': user['email'],
        'broker_connected': user.get('broker_connected', False),
        'execution_mode': user.get('execution_mode', 'PAPER'),
        'created_at': user.get('created_at').isoformat() if user.get('created_at') else None
    })


@auth_bp.route('/profile', methods=['GET'])
@jwt_required()
def get_profile():
    """Get user profile"""
    user_id = get_jwt_identity()
    user = db.get_user_by_id(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Mask API key
    api_key = encryption.decrypt(user.get('groww_api_key', ''))
    masked_key = f"****{api_key[-4:]}" if api_key and len(api_key) > 4 else None
    
    return jsonify({
        'id': str(user['_id']),
        'email': user['email'],
        'broker_connected': user.get('broker_connected', False),
        'execution_mode': user.get('execution_mode', 'PAPER'),
        'groww_api_key_masked': masked_key,
        'created_at': user.get('created_at').isoformat() if user.get('created_at') else None,
        'updated_at': user.get('updated_at').isoformat() if user.get('updated_at') else None
    })


@auth_bp.route('/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    """Update user profile"""
    user_id = get_jwt_identity()
    
    try:
        data = request.get_json(force=True)
    except:
        return jsonify({'error': 'Invalid JSON data'}), 400
    
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid request format'}), 400
    
    update_data = {}
    
    # Update email if provided
    if data.get('email'):
        existing = db.get_user_by_email(data['email'])
        if existing and str(existing['_id']) != user_id:
            return jsonify({'error': 'Email already in use'}), 400
        update_data['email'] = data['email']
    
    # Update password if provided
    if data.get('new_password'):
        if not data.get('current_password'):
            return jsonify({'error': 'Current password required'}), 400
        
        user = db.get_user_by_id(user_id)
        if not check_password_hash(user['password'], data['current_password']):
            return jsonify({'error': 'Current password incorrect'}), 400
        
        update_data['password'] = generate_password_hash(data['new_password'])
    
    if update_data:
        db.update_user(user_id, update_data)
    
    return jsonify({'message': 'Profile updated successfully'})


@auth_bp.route('/update-groww-credentials', methods=['POST'])
@jwt_required()
def update_groww_credentials():
    """Update Groww API credentials AND generate Access Token immediately"""
    user_id = get_jwt_identity()
    
    try:
        data = request.get_json(force=True)
    except:
        return jsonify({'error': 'Invalid JSON data'}), 400
    
    api_key = data.get('groww_api_key', '').strip()
    api_secret = data.get('groww_api_secret', '').strip()
    
    if not api_key or not api_secret:
        return jsonify({'error': 'API key and secret required'}), 400
    
    # 1. Update user with keys immediately
    db.update_user(user_id, {
        'groww_api_key': encryption.encrypt(api_key),
        'groww_api_secret': encryption.encrypt(api_secret),
        'broker_connected': True,
        'updated_at': datetime.utcnow()
    })
    
    # 2. --- CRITICAL FIX: Generate Access Token Immediately ---
    try:
        client = GrowwClient(user_id)
        print(f"Attempting to generate token for user {user_id}...")
        
        token_response = client.generate_access_token(api_key, api_secret)
        
        if token_response.get('success') and token_response.get('token'):
            access_token = token_response['token']
            encrypted_token = encryption.encrypt(access_token)
            
            # Save the VALID token to DB
            db.update_user(user_id, {
                "groww_access_token": encrypted_token,
                "token_generated_at": datetime.utcnow()
            })
            print("✅ Access Token generated and saved successfully.")
            return jsonify({
                'message': 'Credentials updated and Access Token generated successfully',
                'broker_connected': True
            })
        else:
            print(f"⚠️ Credentials saved, but Token generation failed: {token_response.get('error')}")
            return jsonify({
                'message': 'API Keys saved, but could not verify with Groww. Please check credentials.',
                'warning': token_response.get('error'),
                'broker_connected': False
            }), 200 # Return 200 so UI doesn't crash, but show warning
            
    except Exception as e:
        print(f"Error generating token: {e}")
        # Even if token generation fails, keys are saved
        return jsonify({'message': 'Credentials updated (Token generation failed)', 'error': str(e)}), 200


@auth_bp.route('/refresh-token', methods=['POST'])
@jwt_required()
def refresh_groww_token():
    """Refresh JWT token"""
    user_id = get_jwt_identity()
    
    # Generate new JWT
    access_token = create_access_token(identity=user_id)
    
    return jsonify({
        'message': 'Token refreshed successfully',
        'access_token': access_token
    })


@auth_bp.route('/logout', methods=['POST'])
@jwt_required(optional=True)
def logout():
    """Logout user - accepts both authenticated and unauthenticated requests"""
    return jsonify({'message': 'Logged out successfully'})