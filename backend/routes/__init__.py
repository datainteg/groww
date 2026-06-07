from .auth_routes import auth_bp
from .market_routes import market_bp
from .strategy_routes import strategy_bp
from .trade_routes import trade_bp
from .settings_routes import settings_bp
from .instruments_routes import instruments_bp
from .backtest_routes import backtest_bp

__all__ = [
    'auth_bp',
    'market_bp',
    'strategy_bp',
    'trade_bp',
    'settings_bp',
    'instruments_bp',
    'backtest_bp',
]
