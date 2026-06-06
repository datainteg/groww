"""
Trading Engine - FIXED VERSION
Handles trade execution, monitoring, and dynamic strike selection
"""
from typing import Dict, Optional, List, Tuple
from datetime import datetime
import time

from database import db
try:
    from database import redis_client
except ImportError:
    from database.redis_client import redis_client 

from config import config
from services.groww_client import get_groww_client
from services.paper_broker import get_paper_broker
from services.telegram_alert import telegram_alert
from analysis.decision_engine import analyze_market as get_signal
from services.candle_service import candle_service
from utils import risk_manager
from utils.time_utils import get_ist_now, is_market_open


class TradingEngine:
    """Main trading engine for executing and monitoring trades"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.settings = db.get_settings(user_id) or {}
        
        # FIX 1: Get execution mode from user settings, not global config
        self.execution_mode = self._get_user_execution_mode()
        
        # Brokers
        self.groww = get_groww_client(user_id)
        self.paper = get_paper_broker(user_id)
        
        self.active_strategies = []
        self._load_active_strategies()
    
    def _get_user_execution_mode(self) -> str:
        """
        Get execution mode (PAPER/LIVE).
        Single source of truth = users collection. Settings is a legacy fallback;
        config default is the final safety net.
        """
        try:
            # 1. Users record is authoritative (Sprint 1 source-of-truth).
            user = db.get_user_by_id(self.user_id)
            if user and user.get('execution_mode'):
                return user.get('execution_mode')

            # 2. Legacy fallback: execution_mode previously stored in settings.
            if self.settings and self.settings.get('execution_mode'):
                return self.settings.get('execution_mode')

        except Exception as e:
            print(f"Error getting execution mode: {e}")

        # 3. Fallback to config default.
        return config.EXECUTION_MODE
    
    def _log_signal(self, strategy: Dict, signal_data: Dict):
        """Persist a signal snapshot at entry for later confidence calibration (4b).
        Outcome (win/loss) is recovered by joining on strategy_id + time to the
        resulting trade's P&L. Best-effort; never blocks trading."""
        try:
            sid = str(strategy.get('_id'))
            # Throttle: at most one snapshot per strategy per minute, so a
            # persistent-but-blocked signal can't spam the calibration log.
            rc = getattr(redis_client, 'client', None)
            if rc and not rc.set(f'signal_log:{sid}', '1', nx=True, ex=60):
                return
            db.log_signal({
                'user_id': self.user_id,
                'strategy_id': sid,
                'symbol': signal_data.get('symbol'),
                'signal': signal_data.get('signal'),
                'confidence': signal_data.get('confidence'),
                'net_score': signal_data.get('net_score'),
                'bullish_score': signal_data.get('bullish_score'),
                'bearish_score': signal_data.get('bearish_score'),
                'market_regime': signal_data.get('market_regime'),
                'components': signal_data.get('components'),
                'current_price': signal_data.get('current_price'),
            })
        except Exception as e:
            print(f"Signal log error: {e}")

    def _load_active_strategies(self):
        """Load strategies marked as active from DB"""
        strategies = db.get_strategies_by_user(self.user_id)
        self.active_strategies = [s for s in strategies if s.get('is_active', False)]

    def _get_broker(self):
        """Get appropriate broker based on execution mode"""
        # Refresh execution mode in case it changed
        self.execution_mode = self._get_user_execution_mode()
        
        if self.execution_mode == 'PAPER':
            return self.paper
        return self.groww
    
    def _get_option_ltp(self, trading_symbol: str) -> float:
        """
        FIX 2: Unified LTP fetching that works for both PAPER and LIVE modes
        Returns the current price of an option
        """
        try:
            if self.execution_mode == 'PAPER':
                # Paper broker has get_ltp(trading_symbol: str)
                return self.paper.get_ltp(trading_symbol, segment='FNO')
            else:
                # Groww client has get_ltp(exchange_symbols: List[str])
                # FIX: Use NFO exchange for F&O instruments
                exchange_symbol = f"NFO_{trading_symbol}"
                result = self.groww.get_ltp([exchange_symbol], segment='FNO')
                
                if result.get('success') and result.get('data'):
                    # Try different key formats
                    data = result['data']
                    if exchange_symbol in data:
                        return float(data[exchange_symbol])
                    # Try without exchange prefix
                    if trading_symbol in data:
                        return float(data[trading_symbol])
                    # Try first available value
                    for key, value in data.items():
                        if trading_symbol in key:
                            return float(value)
                
                return 0
        except Exception as e:
            print(f"Error getting LTP for {trading_symbol}: {e}")
            return 0

    # =========================================================
    # 1. MARKET HEARTBEAT METHODS (Called by Scheduler)
    # =========================================================

    def evaluate_strategies(self, index_symbol: str, current_ltp: float):
        """
        Called every 5s. Checks if any active strategy for this Index needs to ENTER.
        """
        # Reload settings
        self.settings = db.get_settings(self.user_id) or {}
        if self.settings.get('kill_switch', False):
            return

        # Data-feed kill switch: a prior 401 marks the Groww feed dead. Never
        # trade on a stale/expired feed until it recovers (flag auto-clears on
        # the next successful LTP fetch).
        try:
            rc = getattr(redis_client, 'client', None)
            if rc and rc.get(f'groww:feed_dead:{self.user_id}'):
                return
        except Exception:
            pass

        # 1. Get all active strategies for this Index (e.g., NIFTY)
        strategies = list(db.strategies.find({
            'user_id': self.user_id,
            'is_active': True, 
            'index': index_symbol 
        }))
        
        if not strategies:
            return

        # 2. Get Analysis Signal (Using cached 5-min candles + current LTP)
        candles = candle_service.get_candles(db, index_symbol, '5', 500)
        # Closed-candle rule: drop a still-forming final 5m bar so signals do not
        # repaint intrabar and live behaviour matches a bar-close backtest.
        if candles:
            now_epoch = int(time.time())
            candles = [c for c in candles if c.get('timestamp', 0) + 300 <= now_epoch]
        if not candles or len(candles) < 20:
            return

        # Convert candles to df format expected by analysis
        import pandas as pd
        df = pd.DataFrame(candles)
        if 'datetime' not in df.columns:
             df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
        df.set_index('datetime', inplace=True)

        signal_data = get_signal(df, index_symbol)
        
        signal = signal_data.get('signal')  # BULLISH / BEARISH
        confidence = signal_data.get('confidence', 0)

        # 3. Check each strategy
        for strategy in strategies:
            try:
                # Skip if already in a trade for this strategy
                active_trade = db.trades.find_one({
                    'strategy_id': str(strategy['_id']),
                    'status': 'OPEN'
                })
                if active_trade:
                    continue

                # Check Signal Thresholds.
                # The engine's `confidence` is a 0-1 fraction, but strategies
                # may store `min_confidence` as a percent (e.g. 70). Normalize
                # percents to a fraction so e.g. 0.72 correctly passes a "70".
                min_confidence = strategy.get('min_confidence', 0.6)
                if min_confidence is None:
                    min_confidence = 0.6
                if min_confidence > 1:
                    min_confidence = min_confidence / 100.0
                if confidence < min_confidence:
                    continue

                if signal in ("BULLISH", "BEARISH"):
                    # 4b: log the signal snapshot at the moment of entry so its
                    # features can later be calibrated against the trade outcome.
                    self._log_signal(strategy, signal_data)
                    self.execute_entry(strategy, signal_data,
                                       "CE" if signal == "BULLISH" else "PE")

            except Exception as e:
                print(f"Error evaluating strategy {strategy.get('name')}: {e}")

    def monitor_active_trades(self, index_symbol: str, current_index_ltp: float):
        """
        FIX 3: Called every 5s. Updates Trailing SL and checks Exits for active trades.
        Now properly handles LTP fetching for both PAPER and LIVE modes.
        """
        trades = db.get_active_trades(self.user_id)
        
        for trade in trades:
            # Simple check: Does trade symbol belong to this index update?
            if index_symbol not in trade.get('symbol', ''):
                continue

            try:
                # FIX: Use unified LTP fetching method
                trading_symbol = trade.get('trading_symbol') or trade.get('symbol')
                if not trading_symbol:
                    continue
                    
                option_ltp = self._get_option_ltp(trading_symbol)

                if option_ltp <= 0: 
                    print(f"Could not get LTP for {trading_symbol}, skipping...")
                    continue

                # 2. Check Hard SL / Target
                current_sl = trade.get('current_sl', trade.get('stop_loss', 0))
                target = trade.get('target', 0)
                
                if current_sl <= 0 and target <= 0:
                    # No SL/Target set, skip monitoring
                    continue
                
                exit_check = risk_manager.check_exit_condition(
                    current_price=option_ltp,
                    stop_loss=current_sl,
                    target=target
                )

                if exit_check['exit_triggered']:
                    print(f"Exit triggered for {trading_symbol}: {exit_check['exit_type']}")
                    self.execute_exit(
                        trade, 
                        exit_check['exit_type'], 
                        exit_price=option_ltp
                    )
                    continue

                # 3. Momentum Trailing SL Logic
                if trade.get('trailing_sl_enabled'):
                    new_sl = risk_manager.calculate_trailing_sl(
                        entry_price=trade['entry_price'],
                        current_price=option_ltp,
                        initial_sl=trade.get('stop_loss', 0),
                        current_sl=current_sl,
                        trailing_value=trade.get('trailing_sl_value', 5.0),
                        trailing_enabled=True
                    )
                    
                    if new_sl > current_sl:
                        db.update_trade(trade['_id'], {'current_sl': new_sl})
                        print(f"Trailing SL updated for {trading_symbol}: {current_sl} -> {new_sl}")

            except Exception as e:
                print(f"Error monitoring trade {trade.get('_id')}: {e}")

    # =========================================================
    # 2. DYNAMIC SYMBOL RESOLUTION
    # =========================================================

    def resolve_dynamic_symbol(self, index_symbol: str, option_type: str, offset: int = 0) -> str:
        """
        Finds the correct Option Symbol (e.g., NIFTY24JAN24500CE) based on live Index LTP.
        """
        # 1. Get Index Spot Price
        ltp_str = redis_client.get_cached_ltp(index_symbol)
        if ltp_str:
            spot_price = float(ltp_str)
        else:
            result = self.groww.get_ltp([f"NSE_{index_symbol}"])
            if result.get('success') and result.get('data'):
                spot_price = result['data'].get(f"NSE_{index_symbol}", 0)
            else:
                spot_price = 0

        if spot_price == 0:
            raise Exception(f"Could not fetch spot price for {index_symbol}")

        # 2. Calculate ATM Strike
        step = 100 if index_symbol in ['BANKNIFTY', 'SENSEX'] else 50
        atm_strike = round(spot_price / step) * step
        
        # 3. Apply Offset
        target_strike = atm_strike + offset
        
        # 4. Find Symbol in DB (Nearest Expiry)
        instrument = db.instruments.find_one({
            'trading_symbol': {'$regex': f'^{index_symbol}.*{target_strike}{option_type}$'}
        }, sort=[('expiry', 1)])  # Sort by date ascending

        if not instrument:
             raise Exception(f"No instrument found for {index_symbol} {target_strike} {option_type}")

        return instrument['trading_symbol']

    # =========================================================
    # 3. EXECUTION METHODS - FIXED
    # =========================================================

    def execute_entry(self, strategy: Dict, signal: Dict, option_type: str) -> Dict:
        """Execute entry trade - FIXED for both PAPER and LIVE"""
        if not is_market_open() and self.execution_mode == 'LIVE':
             return {'success': False, 'error': 'Market is closed'}

        # 1. Resolve Symbol
        offset = strategy.get('atm_offset', 0) 
        try:
            if strategy.get('selection_mode') == 'MANUAL':
                trading_symbol = strategy['ce_symbol'] if option_type == 'CE' else strategy['pe_symbol']
            else:
                trading_symbol = self.resolve_dynamic_symbol(strategy['index'], option_type, offset)
        except Exception as e:
            return {'success': False, 'error': str(e)}

        if not trading_symbol:
            return {'success': False, 'error': 'Could not resolve trading symbol'}

        quantity = strategy.get('quantity', 50)
        product = strategy.get('product', 'MIS')
        
        # 2. Execute Order via broker
        broker = self._get_broker()
        
        # FIX 4: Unified order placement for both PAPER and LIVE
        result = broker.place_order(
            trading_symbol=trading_symbol,
            quantity=quantity,
            transaction_type='BUY',
            order_type='MARKET',
            product=product,  # FIX: Use 'product' not 'product_type'
            segment='FNO'
        )
        
        if not result.get('success'):
            return result
        
        # FIX 5: Get execution price - handle both broker responses
        execution_price = (
            result.get('execution_price') or 
            result.get('average_price') or 
            0
        )
        
        # FIX 6: For LIVE mode, we may need to fetch order details for actual fill price
        if self.execution_mode == 'LIVE' and execution_price == 0:
            order_id = result.get('order_id')
            if order_id:
                execution_price = self._get_order_fill_price(order_id)
        
        # If still no price, get current LTP as estimate
        if execution_price == 0:
            execution_price = self._get_option_ltp(trading_symbol)
        
        # 3. Record Trade
        trade_data = {
            'user_id': self.user_id,
            'strategy_id': str(strategy['_id']),
            'strategy_name': strategy.get('name', 'Unknown'),
            'trading_symbol': trading_symbol,
            'symbol': trading_symbol,
            'option_type': option_type,
            'transaction_type': 'BUY',
            'quantity': quantity,
            'entry_price': execution_price,
            'order_id': result.get('order_id', ''),
            'stop_loss': 0,
            'target': 0,
            'current_sl': 0,
            'trailing_sl_enabled': strategy.get('trailing_sl_enabled', False),
            'trailing_sl_value': strategy.get('trailing_sl_value', 5.0),
            'status': 'OPEN',
            'execution_mode': self.execution_mode,
            'entry_time': get_ist_now(),
            'product': product
        }
        
        # Calculate SL/Target based on filled price
        if execution_price > 0:
            sl_points = strategy.get('stop_loss', 20)
            target_points = strategy.get('target', 40)
            
            sl_params = risk_manager.calculate_sl_target(
                execution_price, 
                sl_points, 
                target_points,
                option_type
            )
            trade_data.update(sl_params)
            trade_data['current_sl'] = trade_data['stop_loss']

        trade_id = db.create_trade(trade_data)
        
        # 4. Alert
        try:
            telegram_alert.send_entry_alert(trade_data)
        except Exception as e:
            print(f"Telegram alert error: {e}")
        
        return {
            'success': True, 
            'trade_id': trade_id,
            'trading_symbol': trading_symbol,
            'entry_price': execution_price,
            'quantity': quantity,
            'execution_mode': self.execution_mode
        }

    def _get_order_fill_price(self, order_id: str, max_retries: int = 3) -> float:
        """
        FIX: Get actual fill price from broker after order execution
        Retries a few times as orders may take a moment to fill
        """
        for attempt in range(max_retries):
            try:
                result = self.groww.get_order_details(order_id, segment='FNO')
                if result.get('success'):
                    data = result.get('data', {})
                    # Try different field names that might contain the fill price
                    fill_price = (
                        data.get('average_price') or
                        data.get('filled_price') or
                        data.get('price') or
                        0
                    )
                    if fill_price > 0:
                        return float(fill_price)
                
                # Wait before retry
                time.sleep(0.5)
            except Exception as e:
                print(f"Error fetching order fill price (attempt {attempt + 1}): {e}")
        
        return 0

    def execute_exit(self, trade: Dict, exit_type: str, exit_price: float = None) -> Dict:
        """Execute exit trade - FIXED for both PAPER and LIVE"""
        broker = self._get_broker()
        
        # Use trading_symbol if available, fall back to symbol
        trading_symbol = trade.get('trading_symbol') or trade.get('symbol')
        
        if not trading_symbol:
            return {'success': False, 'error': 'No trading symbol found for trade'}
        
        product = trade.get('product', 'MIS')
        
        # FIX: Unified exit order
        result = broker.place_order(
            trading_symbol=trading_symbol,
            quantity=trade['quantity'],
            transaction_type='SELL',
            order_type='MARKET',
            product=product,
            segment='FNO'
        )
        
        if not result.get('success'):
            return result
        
        # Get actual exit price
        final_exit_price = (
            result.get('execution_price') or 
            result.get('average_price') or 
            exit_price or 
            0
        )
        
        # For LIVE, try to get actual fill price
        if self.execution_mode == 'LIVE' and final_exit_price == 0:
            order_id = result.get('order_id')
            if order_id:
                final_exit_price = self._get_order_fill_price(order_id)
        
        # Calculate P&L
        entry_price = trade.get('entry_price', 0)
        pnl = (final_exit_price - entry_price) * trade['quantity']
        
        db.close_trade(trade['_id'], {
            'exit_price': final_exit_price,
            'pnl': pnl,
            'exit_reason': exit_type,
            'exit_time': get_ist_now()
        })
        
        # Update strategy P&L if linked
        if trade.get('strategy_id'):
            db.update_strategy_pnl(trade['strategy_id'], pnl)
        
        # Send Alert
        try:
            trade['exit_price'] = final_exit_price
            trade['pnl'] = pnl
            trade['exit_reason'] = exit_type
            telegram_alert.send_exit_alert(trade, {})
        except Exception as e:
            print(f"Telegram alert error: {e}")
        
        return {'success': True, 'pnl': pnl, 'exit_price': final_exit_price}

    def reconcile_positions(self, broker_positions: List[Dict]):
        """Syncs DB with Broker."""
        # TODO: Implement full reconciliation logic
        pass

    # =========================================================
    # 4. STATUS METHOD
    # =========================================================
    def get_engine_status(self):
        """
        Returns the current health and status of the trading engine.
        Called by: GET /api/strategy/status
        """
        self._load_active_strategies()
        
        # Ensure settings is not None
        settings = self.settings or {}
        
        return {
            'is_running': not settings.get('kill_switch', False),
            'active_strategies': len(self.active_strategies),
            'market_open': is_market_open(),
            'execution_mode': self.execution_mode,  # Now shows actual user mode
            'kill_switch': settings.get('kill_switch', False)
        }


def get_trading_engine(user_id: str) -> TradingEngine:
    return TradingEngine(user_id)
