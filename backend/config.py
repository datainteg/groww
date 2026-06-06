"""
Configuration module for AI Trading System
"""
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Base configuration"""
    
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('DEBUG', 'true').lower() == 'true'
    
    # JWT
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key-change-in-production')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(seconds=int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 86400)))
    
    # MongoDB
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
    MONGO_DB_NAME = os.getenv('MONGO_DB_NAME', 'ai_trading_system')
    
    # Redis
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_DB = int(os.getenv('REDIS_DB', 0))
    REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)
    REDIS_SSL = os.getenv('REDIS_SSL', 'false').lower() == 'true'
    
    # Encryption
    ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', 'default-32-byte-key-for-dev-only!')
    
    # Groww API
    GROWW_API_BASE_URL = os.getenv('GROWW_API_BASE_URL', 'https://api.groww.in')
    GROWW_INSTRUMENTS_URL = "https://growwapi-assets.groww.in/instruments/instrument.csv"
    
    # Execution & Risk
    EXECUTION_MODE = os.getenv('EXECUTION_MODE', 'PAPER')
    SLIPPAGE_PERCENT = float(os.getenv('SLIPPAGE_PERCENT', 0.0005))
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
    
    # Trading Hours (IST)
    MARKET_OPEN_HOUR = 9
    MARKET_OPEN_MINUTE = 15
    MARKET_CLOSE_HOUR = 15
    MARKET_CLOSE_MINUTE = 30

    # Auto-exit: force-close all open positions before the close (IST)
    AUTO_EXIT_HOUR = int(os.getenv('AUTO_EXIT_HOUR', 15))
    AUTO_EXIT_MINUTE = int(os.getenv('AUTO_EXIT_MINUTE', 15))

    # Strategy Thresholds (engine confidence is a 0-1 fraction)
    CONFIDENCE_THRESHOLD = 0.70
    
    # Risk Management Defaults
    DEFAULT_MAX_DAILY_PROFIT = 10000.0
    DEFAULT_MAX_DAILY_LOSS = 5000.0
    DEFAULT_MAX_CONCURRENT_TRADES = 3
    PAPER_INITIAL_CAPITAL = 1000000.0

    # Known insecure development defaults that must never reach production.
    _INSECURE_DEFAULTS = {
        'dev-secret-key-change-in-production',
        'jwt-secret-key-change-in-production',
        'default-32-byte-key-for-dev-only!',
    }

    def validate(self):
        """Fail-fast on unsafe configuration. Call once at app startup.

        Returns a list of warnings (non-empty only when running in DEBUG with
        insecure defaults). Raises RuntimeError when the configuration is unsafe
        for a non-DEBUG or LIVE deployment.
        """
        problems = []
        if self.SECRET_KEY in self._INSECURE_DEFAULTS:
            problems.append('SECRET_KEY is an insecure default')
        if self.JWT_SECRET_KEY in self._INSECURE_DEFAULTS:
            problems.append('JWT_SECRET_KEY is an insecure default')
        if self.ENCRYPTION_KEY in self._INSECURE_DEFAULTS:
            problems.append('ENCRYPTION_KEY is an insecure default')

        is_live = str(self.EXECUTION_MODE).upper() == 'LIVE'
        if is_live and self.DEBUG:
            problems.append('DEBUG must be False when EXECUTION_MODE=LIVE')

        # Refuse to start when secrets are weak in any non-DEBUG run, and always in LIVE.
        if problems and (is_live or not self.DEBUG):
            raise RuntimeError(
                'Refusing to start due to insecure configuration: '
                + '; '.join(problems)
                + '. Set strong SECRET_KEY / JWT_SECRET_KEY / ENCRYPTION_KEY '
                  'environment variables (see backend/.env.example).'
            )
        return problems


config = Config()