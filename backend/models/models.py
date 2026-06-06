"""
Data Models - User, Strategy, Trade
Updated for Groww API integration
"""
from datetime import datetime
from typing import Optional, Dict, Any
from werkzeug.security import generate_password_hash, check_password_hash


class User:
    """User model with Groww credentials"""
    
    def __init__(self, email: str, password_hash: str,
                 groww_api_key: str = '', groww_api_secret: str = '',
                 groww_access_token: str = '', groww_token_expiry: datetime = None,
                 broker_connected: bool = False, execution_mode: str = 'PAPER',
                 _id: Optional[str] = None, is_active: bool = True,
                 created_at: Optional[datetime] = None, **kwargs):
        self._id = _id
        self.email = email
        self.password_hash = password_hash
        self.groww_api_key = groww_api_key
        self.groww_api_secret = groww_api_secret
        self.groww_access_token = groww_access_token
        self.groww_token_expiry = groww_token_expiry
        self.broker_connected = broker_connected
        self.execution_mode = execution_mode
        self.is_active = is_active
        self.created_at = created_at or datetime.utcnow()
    
    @staticmethod
    def hash_password(password: str) -> str:
        return generate_password_hash(password)
    
    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        return check_password_hash(password_hash, password)
    
    def to_safe_dict(self) -> Dict[str, Any]:
        return {
            'id': str(self._id) if self._id else None,
            'email': self.email,
            'broker_connected': self.broker_connected,
            'execution_mode': self.execution_mode,
            'is_active': self.is_active,
            'token_expiry': self.groww_token_expiry.isoformat() if self.groww_token_expiry else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'User':
        return cls(
            _id=str(data.get('_id')) if data.get('_id') else None,
            email=data.get('email', ''),
            password_hash=data.get('password', data.get('password_hash', '')),
            groww_api_key=data.get('groww_api_key', ''),
            groww_api_secret=data.get('groww_api_secret', ''),
            groww_access_token=data.get('groww_access_token', ''),
            groww_token_expiry=data.get('groww_token_expiry'),
            broker_connected=data.get('broker_connected', False),
            execution_mode=data.get('execution_mode', 'PAPER'),
            is_active=data.get('is_active', True),
            created_at=data.get('created_at')
        )


class Strategy:
    """User-defined trading strategy with limits and confidence configuration"""
    
    # Confidence Presets
    CONFIDENCE_PRESETS = {
        'conservative': {'min_confidence': 80, 'description': 'High confidence trades only'},
        'balanced': {'min_confidence': 70, 'description': 'Balanced risk/reward'},
        'aggressive': {'min_confidence': 60, 'description': 'More trades, higher risk'}
    }
    
    def __init__(self, user_id: str, name: str, index: str, exchange_segment: str,
                 product: str, expiry: str, strike_price: str, ce_symbol: str,
                 pe_symbol: str, quantity: int, stop_loss: float, target: float,
                 trailing_sl_enabled: bool = False, trailing_sl_value: float = 20,
                 break_even_enabled: bool = False, break_even_trigger: float = 50,
                 partial_exit_enabled: bool = False, partial_exit_percent: float = 50,
                 partial_target_1: float = None, time_exit_enabled: bool = True,
                 max_orders_per_day: int = 2, max_profit_limit: float = 5000,
                 max_loss_limit: float = 2000, is_active: bool = False,
                 orders_today: int = 0, pnl_today: float = 0,
                 # NEW: Confidence Configuration Fields
                 confidence_preset: str = 'balanced',
                 min_confidence: int = 70,
                 volume_confirmation: bool = True,
                 volatility_filter: bool = True,
                 trend_alignment: bool = False,
                 allowed_signals: str = 'BOTH',  # 'BOTH', 'BULLISH', 'BEARISH'
                 time_filter_enabled: bool = False,
                 time_filter_start: str = '09:30',
                 time_filter_end: str = '15:00',
                 use_direction_engine: bool = True,  # Use new direction engine vs old 67-indicator system
                 direction_min_strength: int = 60,  # Minimum direction strength (0-100)
                 _id: Optional[str] = None, created_at: Optional[datetime] = None, **kwargs):
        self._id = _id
        self.user_id = user_id
        self.name = name
        self.index = index
        self.exchange_segment = exchange_segment
        self.product = product
        self.expiry = expiry
        self.strike_price = strike_price
        self.ce_symbol = ce_symbol
        self.pe_symbol = pe_symbol
        self.quantity = quantity
        self.stop_loss = stop_loss
        self.target = target
        self.trailing_sl_enabled = trailing_sl_enabled
        self.trailing_sl_value = trailing_sl_value
        self.break_even_enabled = break_even_enabled
        self.break_even_trigger = break_even_trigger
        self.partial_exit_enabled = partial_exit_enabled
        self.partial_exit_percent = partial_exit_percent
        self.partial_target_1 = partial_target_1
        self.time_exit_enabled = time_exit_enabled
        self.max_orders_per_day = max_orders_per_day
        self.max_profit_limit = max_profit_limit
        self.max_loss_limit = max_loss_limit
        self.is_active = is_active
        self.orders_today = orders_today
        self.pnl_today = pnl_today
        
        # NEW: Confidence Configuration
        self.confidence_preset = confidence_preset
        self.min_confidence = min_confidence
        self.volume_confirmation = volume_confirmation
        self.volatility_filter = volatility_filter
        self.trend_alignment = trend_alignment
        self.allowed_signals = allowed_signals
        self.time_filter_enabled = time_filter_enabled
        self.time_filter_start = time_filter_start
        self.time_filter_end = time_filter_end
        self.use_direction_engine = use_direction_engine
        self.direction_min_strength = direction_min_strength
        
        self.created_at = created_at or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        return vars(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Strategy':
        return cls(**data)
    
    def can_trade(self) -> tuple:
        if self.orders_today >= self.max_orders_per_day:
            return False, f"Max orders reached ({self.orders_today}/{self.max_orders_per_day})"
        if self.pnl_today >= self.max_profit_limit:
            return False, f"Profit limit reached"
        if self.pnl_today <= -abs(self.max_loss_limit):
            return False, f"Loss limit reached"
        return True, "OK"
    
    def validate_signal(self, signal: str, confidence: float, direction_strength: float = None) -> tuple:
        """
        Validate if a signal passes this strategy's confidence filters
        
        Args:
            signal: 'BULLISH' or 'BEARISH'
            confidence: Signal confidence (0-100 or 0-1)
            direction_strength: Strength from direction engine (0-100)
        
        Returns:
            (passes: bool, reason: str)
        """
        # Normalize confidence to 0-100
        if confidence <= 1:
            confidence = confidence * 100
        
        # Check allowed signals
        if self.allowed_signals != 'BOTH':
            if self.allowed_signals == 'BULLISH' and signal != 'BULLISH':
                return False, "Strategy only allows BULLISH signals"
            if self.allowed_signals == 'BEARISH' and signal != 'BEARISH':
                return False, "Strategy only allows BEARISH signals"
        
        # Check minimum confidence
        if confidence < self.min_confidence:
            return False, f"Confidence {confidence:.1f}% below threshold {self.min_confidence}%"
        
        # Check direction strength (if using new engine)
        if self.use_direction_engine and direction_strength is not None:
            if direction_strength < self.direction_min_strength:
                return False, f"Direction strength {direction_strength:.1f} below threshold {self.direction_min_strength}"
        
        # Check time filter
        if self.time_filter_enabled:
            from datetime import datetime
            now = datetime.now()
            current_time = now.strftime('%H:%M')
            if current_time < self.time_filter_start or current_time > self.time_filter_end:
                return False, f"Outside trading hours ({self.time_filter_start}-{self.time_filter_end})"
        
        return True, "Signal validated"
    
    def get_confidence_description(self) -> str:
        """Get human-readable description of confidence settings"""
        preset_info = self.CONFIDENCE_PRESETS.get(self.confidence_preset, {})
        base_desc = preset_info.get('description', 'Custom configuration')
        
        filters = []
        if self.volume_confirmation:
            filters.append("Volume confirmation required")
        if self.volatility_filter:
            filters.append("Volatility filter active")
        if self.trend_alignment:
            filters.append("Trend alignment required")
        if self.time_filter_enabled:
            filters.append(f"Trading hours: {self.time_filter_start}-{self.time_filter_end}")
        
        return f"{base_desc}. Min confidence: {self.min_confidence}%. " + ", ".join(filters)


class Trade:
    """Trade record"""
    
    def __init__(self, user_id: str, strategy_id: str, strategy_name: str,
                 symbol: str, option_type: str, transaction_type: str, quantity: int,
                 entry_price: float = 0, exit_price: float = 0, stop_loss: float = 0,
                 target: float = 0, current_sl: float = 0, partial_target_1: float = None,
                 trailing_sl_enabled: bool = False, trailing_sl_value: float = 0,
                 break_even_enabled: bool = False, break_even_trigger: float = 50,
                 pnl: float = 0, status: str = 'open', order_id: str = '',
                 exit_order_id: str = '', signal_type: str = '', confidence: float = 0,
                 market_regime: str = '', exit_reason: str = '', execution_mode: str = 'PAPER',
                 entry_time: datetime = None, exit_time: datetime = None,
                 partial_exits: list = None, _id: Optional[str] = None,
                 created_at: Optional[datetime] = None, **kwargs):
        self._id = _id
        self.user_id = user_id
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.option_type = option_type
        self.transaction_type = transaction_type
        self.quantity = quantity
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.stop_loss = stop_loss
        self.target = target
        self.current_sl = current_sl
        self.partial_target_1 = partial_target_1
        self.trailing_sl_enabled = trailing_sl_enabled
        self.trailing_sl_value = trailing_sl_value
        self.break_even_enabled = break_even_enabled
        self.break_even_trigger = break_even_trigger
        self.pnl = pnl
        self.status = status
        self.order_id = order_id
        self.exit_order_id = exit_order_id
        self.signal_type = signal_type
        self.confidence = confidence
        self.market_regime = market_regime
        self.exit_reason = exit_reason
        self.execution_mode = execution_mode
        self.entry_time = entry_time
        self.exit_time = exit_time
        self.partial_exits = partial_exits or []
        self.created_at = created_at or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        return vars(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Trade':
        return cls(**data)


class Instrument:
    """F&O Instrument from Groww"""
    
    def __init__(self, exchange: str, exchange_token: str, trading_symbol: str,
                 groww_symbol: str, name: str = '', instrument_type: str = '',
                 segment: str = 'FNO', underlying_symbol: str = '', expiry_date: str = '',
                 strike_price: float = 0, lot_size: int = 1, tick_size: float = 0.05,
                 buy_allowed: bool = True, sell_allowed: bool = True,
                 synced_at: datetime = None, _id: Optional[str] = None, **kwargs):
        self._id = _id
        self.exchange = exchange
        self.exchange_token = exchange_token
        self.trading_symbol = trading_symbol
        self.groww_symbol = groww_symbol
        self.name = name
        self.instrument_type = instrument_type
        self.segment = segment
        self.underlying_symbol = underlying_symbol
        self.expiry_date = expiry_date
        self.strike_price = strike_price
        self.lot_size = lot_size
        self.tick_size = tick_size
        self.buy_allowed = buy_allowed
        self.sell_allowed = sell_allowed
        self.synced_at = synced_at or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        return vars(self)


class JournalEntry:
    """Trade journal entry"""
    
    def __init__(self, trade_id: str, user_id: str, notes: str = '',
                 tags: list = None, rating: int = None, lessons: str = '',
                 mistakes: str = '', _id: Optional[str] = None,
                 created_at: Optional[datetime] = None, **kwargs):
        self._id = _id
        self.trade_id = trade_id
        self.user_id = user_id
        self.notes = notes
        self.tags = tags or []
        self.rating = rating
        self.lessons = lessons
        self.mistakes = mistakes
        self.created_at = created_at or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        return vars(self)


class DailySummary:
    """Daily trading summary for equity curve"""
    
    def __init__(self, user_id: str, date: str, total_pnl: float = 0,
                 total_trades: int = 0, winning: int = 0, losing: int = 0,
                 win_rate: float = 0, largest_win: float = 0, largest_loss: float = 0,
                 avg_win: float = 0, avg_loss: float = 0, execution_mode: str = 'PAPER',
                 _id: Optional[str] = None, created_at: Optional[datetime] = None, **kwargs):
        self._id = _id
        self.user_id = user_id
        self.date = date
        self.total_pnl = total_pnl
        self.total_trades = total_trades
        self.winning = winning
        self.losing = losing
        self.win_rate = win_rate
        self.largest_win = largest_win
        self.largest_loss = largest_loss
        self.avg_win = avg_win
        self.avg_loss = avg_loss
        self.execution_mode = execution_mode
        self.created_at = created_at or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        return vars(self)
