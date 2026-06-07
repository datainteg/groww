"""
AI Trading System - Main Application
Flask backend with Groww API integration
"""
import sys
# Force UTF-8 stdout/stderr so emoji log lines don't crash on a cp1252 console
# (Windows). Must run before any module that prints emoji at import.
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

import json
import os
import time
import numpy as np
from datetime import datetime, date
from flask import Flask, jsonify, request
from flask.json.provider import JSONProvider
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import config


class CustomJSONProvider(JSONProvider):
    """Custom JSON Provider to handle numpy types"""
    
    def default(self, obj):
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
    
    def dumps(self, obj, **kwargs):
        return json.dumps(obj, default=self.default, **kwargs)
    
    def loads(self, s, **kwargs):
        return json.loads(s, **kwargs)


def create_app():
    """Create Flask application"""
    app = Flask(__name__)

    # Fail fast on unsafe configuration (insecure secrets, DEBUG+LIVE, ...)
    warnings = config.validate()
    for w in warnings:
        app.logger.warning("CONFIG WARNING: %s (insecure — fix before production)", w)

    # Use custom JSON provider for numpy types
    app.json = CustomJSONProvider(app)
    
    # Configuration
    app.config['SECRET_KEY'] = config.SECRET_KEY
    app.config['JWT_SECRET_KEY'] = config.JWT_SECRET_KEY
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = config.JWT_ACCESS_TOKEN_EXPIRES
    
    # CORS: explicit origin allowlist (env CORS_ORIGINS, comma-separated).
    # NEVER pair a wildcard origin with credentials. flask-cors handles the
    # preflight for allowed origins, so no manual Origin reflection is needed
    # (the old after_request echoed any Origin back with credentials -> CSRF risk).
    cors_origins = [o.strip() for o in os.getenv(
        'CORS_ORIGINS', 'http://localhost:3000,http://localhost:5173'
    ).split(',') if o.strip()]
    CORS(app,
         resources={r"/api/*": {"origins": cors_origins}},
         supports_credentials=True,
         allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

    jwt = JWTManager(app)

    # JWT revocation: a logged-out token's JTI is stored in Redis; reject it here.
    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        jti = jwt_payload.get('jti')
        if not jti:
            return False
        from database.redis_client import redis_client
        client = getattr(redis_client, 'client', None)
        if not client:
            return False
        try:
            return client.get(f'jwt_blocklist:{jti}') is not None
        except Exception:
            return False
    
    # JWT Error Handlers
    @jwt.unauthorized_loader
    def unauthorized_callback(callback):
        return jsonify({'error': 'Missing Authorization Header'}), 401
    
    @jwt.invalid_token_loader
    def invalid_token_callback(callback):
        return jsonify({'error': 'Invalid token'}), 401
    
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({'error': 'Token expired'}), 401
    
    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        return jsonify({'error': 'Token revoked'}), 401
    
    # Import and register blueprints
    from routes import auth_bp, market_bp, strategy_bp, trade_bp, settings_bp, instruments_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(strategy_bp)
    app.register_blueprint(trade_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(instruments_bp)
    
    # Optionally start the background scheduler inside the web process.
    # Recommended production topology is a DEDICATED process (see run_scheduler.py),
    # so this is opt-in via START_SCHEDULER_IN_APP=true. The Redis leader-lock
    # inside the scheduler prevents multi-worker double-start regardless.
    if os.getenv('START_SCHEDULER_IN_APP', 'false').lower() == 'true':
        # Avoid double start under the Werkzeug auto-reloader in dev.
        if not config.DEBUG or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            from services import scheduler_service, start_direction_scheduler
            scheduler_service.start()
            start_direction_scheduler()

    # Health check (also reports background-scheduler liveness)
    @app.route('/api/health', methods=['GET'])
    def health():
        from database.redis_client import redis_client
        hb, stale, sched = None, None, None
        client = getattr(redis_client, 'client', None)
        if client:
            try:
                raw = client.get('scheduler:last_heartbeat')
                if raw:
                    hb = int(raw)
                    stale = (int(time.time()) - hb) > 30
            except Exception:
                pass
            try:
                import json as _json
                raw_status = client.get('scheduler:status')
                if raw_status:
                    sched = _json.loads(raw_status)
            except Exception:
                pass
        return jsonify({
            'status': 'healthy',
            'execution_mode': config.EXECUTION_MODE,
            'auto_trading_enabled': bool(config.AUTO_TRADING_ENABLED),
            'version': '4.0.0',
            'scheduler_last_heartbeat': hb,
            'scheduler_stale': stale,
            'scheduler': sched
        })
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'Endpoint not found'}), 404
    
    @app.errorhandler(500)
    def server_error(e):
        return jsonify({'error': 'Internal server error'}), 500
    
    return app


app = create_app()

if __name__ == '__main__':
    print(f"Starting AI Trading System v4.0.0 in {config.EXECUTION_MODE} mode")

    # Dev single-process: start background workers here (idempotent + leader-locked).
    # Guard against the Werkzeug auto-reloader forking a second process and
    # double-starting the schedulers (only the reloaded child sets WERKZEUG_RUN_MAIN).
    # For production use gunicorn for the API + a dedicated `python run_scheduler.py`.
    if not config.DEBUG or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        from services import scheduler_service, start_direction_scheduler
        scheduler_service.start()
        start_direction_scheduler()

    app.run(host='0.0.0.0', port=5000, debug=config.DEBUG)
