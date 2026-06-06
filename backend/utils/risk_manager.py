"""
Risk Management Utilities
"""
from typing import Dict, Tuple, Optional
from config import config


class RiskManager:
    """Handle risk management calculations"""
    
    @staticmethod
    def can_strategy_trade(strategy: Dict, settings: Dict = None) -> Tuple[bool, str]:
        """
        Check if strategy can place a new trade
        
        Returns:
            Tuple of (can_trade, reason)
        """
        # Check kill switch
        if settings and settings.get('kill_switch'):
            return False, "Kill switch is active"
        
        # Check max orders per day
        if strategy.get('orders_today', 0) >= strategy.get('max_orders_per_day', 2):
            return False, f"Max daily orders reached ({strategy['orders_today']}/{strategy['max_orders_per_day']})"
        
        # Check profit limit
        if strategy.get('pnl_today', 0) >= strategy.get('max_profit_limit', 10000):
            return False, f"Daily profit limit reached (₹{strategy['pnl_today']:.0f})"
        
        # Check loss limit
        if strategy.get('pnl_today', 0) <= -strategy.get('max_loss_limit', 5000):
            return False, f"Daily loss limit reached (₹{strategy['pnl_today']:.0f})"
        
        return True, "OK"
    
    @staticmethod
    def can_overall_trade(settings: Dict, active_trades: int = 0) -> Tuple[bool, str]:
        """
        Check overall trading limits
        
        Returns:
            Tuple of (can_trade, reason)
        """
        if not settings:
            return True, "OK"
        
        # Check kill switch
        if settings.get('kill_switch'):
            return False, "Kill switch is active"
        
        # Check overall profit limit
        overall_pnl = settings.get('overall_pnl_today', 0)
        max_profit = settings.get('overall_max_profit', config.DEFAULT_MAX_DAILY_PROFIT)
        if overall_pnl >= max_profit:
            return False, f"Overall daily profit limit reached (₹{overall_pnl:.0f})"
        
        # Check overall loss limit
        max_loss = settings.get('overall_max_loss', config.DEFAULT_MAX_DAILY_LOSS)
        if overall_pnl <= -max_loss:
            return False, f"Overall daily loss limit reached (₹{overall_pnl:.0f})"
        
        # Check max concurrent trades
        max_concurrent = settings.get('max_concurrent_trades', config.DEFAULT_MAX_CONCURRENT_TRADES)
        if active_trades >= max_concurrent:
            return False, f"Max concurrent trades reached ({active_trades}/{max_concurrent})"

        return True, "OK"

    @staticmethod
    def normalize_min_confidence(value, default: float = 0.6) -> float:
        """Strategies may store min_confidence as a percent (e.g. 70) or as a
        0-1 fraction. The engine's confidence is a 0-1 fraction, so normalize:
        None/invalid -> default; >1 -> /100; otherwise unchanged (0 disables the
        per-strategy gate and defers to the engine threshold)."""
        if value is None:
            return default
        try:
            v = float(value)
        except (TypeError, ValueError):
            return default
        return v / 100.0 if v > 1 else v
    
    @staticmethod
    def calculate_sl_target(
        entry_price: float,
        stop_loss_points: float,
        target_points: float,
        option_type: str
    ) -> Dict:
        """
        Calculate stop loss and target prices
        
        Args:
            entry_price: Entry price of option
            stop_loss_points: SL in points
            target_points: Target in points
            option_type: 'CE' or 'PE'
        
        Returns:
            Dict with sl_price, target_price
        """
        # For buying options, SL is below entry, target is above
        sl_price = max(0.05, entry_price - stop_loss_points)
        target_price = entry_price + target_points
        
        return {
            'stop_loss': round(sl_price, 2),
            'target': round(target_price, 2),
            'entry': round(entry_price, 2),
            'risk': round(stop_loss_points, 2),
            'reward': round(target_points, 2),
            'risk_reward_ratio': round(target_points / stop_loss_points, 2) if stop_loss_points > 0 else 0
        }
    
    @staticmethod
    def calculate_trailing_sl(
        entry_price: float,
        current_price: float,
        initial_sl: float,
        current_sl: float,
        trailing_value: float,
        trailing_enabled: bool
    ) -> float:
        """
        Calculate trailing stop loss
        
        Returns:
            New stop loss price
        """
        if not trailing_enabled:
            return current_sl
        
        profit = current_price - entry_price
        
        # Only trail if in profit
        if profit <= 0:
            return current_sl
        
        # Calculate new SL based on profit
        # Move SL by trailing_value for every trailing_value profit
        trail_steps = int(profit / trailing_value)
        
        if trail_steps > 0:
            new_sl = initial_sl + (trail_steps * trailing_value)
            # Only move SL up, never down
            return max(current_sl, new_sl)
        
        return current_sl
    
    @staticmethod
    def calculate_break_even_sl(
        entry_price: float,
        current_price: float,
        current_sl: float,
        break_even_trigger_percent: float = 50
    ) -> float:
        """
        Calculate break-even stop loss
        Move SL to entry when profit reaches trigger percent
        
        Args:
            entry_price: Entry price
            current_price: Current market price
            current_sl: Current SL price
            break_even_trigger_percent: Profit % to trigger break-even
        
        Returns:
            New stop loss price
        """
        profit_percent = ((current_price - entry_price) / entry_price) * 100
        
        if profit_percent >= break_even_trigger_percent:
            # Move SL to entry (break-even)
            return max(current_sl, entry_price)
        
        return current_sl
    
    @staticmethod
    def calculate_partial_exit(
        quantity: int,
        exit_percent: float = 50
    ) -> Tuple[int, int]:
        """
        Calculate partial exit quantities
        
        Returns:
            Tuple of (exit_qty, remaining_qty)
        """
        exit_qty = int(quantity * (exit_percent / 100))
        remaining_qty = quantity - exit_qty
        
        return exit_qty, remaining_qty
    
    @staticmethod
    def calculate_position_size(
        capital: float,
        risk_percent: float,
        stop_loss_points: float,
        lot_size: int
    ) -> int:
        """
        Calculate position size based on risk management
        
        Args:
            capital: Available capital
            risk_percent: % of capital to risk (e.g., 1-2%)
            stop_loss_points: SL in points
            lot_size: Lot size for the instrument
        
        Returns:
            Number of lots to trade
        """
        risk_amount = capital * (risk_percent / 100)
        lots_based_on_risk = int(risk_amount / stop_loss_points)
        
        # Ensure at least 1 lot
        return max(1, lots_based_on_risk)
    
    @staticmethod
    def check_exit_condition(
        current_price: float,
        stop_loss: float,
        target: float,
        partial_target_1: float = None
    ) -> Dict:
        """
        Check if exit condition is met
        
        Returns:
            Dict with exit_triggered, exit_type, exit_price
        """
        result = {
            'exit_triggered': False,
            'exit_type': None,
            'exit_price': None
        }
        
        # Check target
        if current_price >= target:
            result['exit_triggered'] = True
            result['exit_type'] = 'TARGET'
            result['exit_price'] = current_price
            return result
        
        # Check stop loss
        if current_price <= stop_loss:
            result['exit_triggered'] = True
            result['exit_type'] = 'STOP_LOSS'
            result['exit_price'] = current_price
            return result
        
        # Check partial target
        if partial_target_1 and current_price >= partial_target_1:
            result['exit_triggered'] = True
            result['exit_type'] = 'PARTIAL_TARGET_1'
            result['exit_price'] = current_price
            return result
        
        return result


risk_manager = RiskManager()
