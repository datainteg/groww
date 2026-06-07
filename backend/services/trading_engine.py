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
            def _f(v):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return 0.0

            conf = _f(signal_data.get('confidence'))
            bull = _f(signal_data.get('bullish_score'))
            bear = _f(signal_data.get('bearish_score'))
            net = _f(signal_data.get('net_score'))
            # Calibration trains on EXACTLY these 4 features (must match the live
            # p_win feature vector in decision_engine). feature_version guards
            # against silent schema drift.
            db.log_signal({
                'user_id': self.user_id,
                'strategy_id': sid,
                'symbol': signal_data.get('symbol'),
                'signal': signal_data.get('signal'),
                'confidence': conf,
                'net_score': net,
                'bullish_score': bull,
                'bearish_score': bear,
                'market_regime': signal_data.get('market_regime'),
                'components': signal_data.get('components'),
                'current_price': signal_data.get('current_price'),
                'calibration_features': [conf, bull, bear, net],
                'feature_version': 1,
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

        # --- Feature-flagged: data-quality gate before analysis ---
        # validate_candles is pure (no I/O).  Any import error, runtime error,
        # or a module that is simply not present must NEVER block the trade loop.
        try:
            from analysis.data_quality import validate_candles as _validate  # lazy
            _dq = _validate(candles, interval_min=5)
            if not _dq.get('ok', True):
                import logging as _log
                _log.getLogger(__name__).warning(
                    "Data quality check failed for %s — skipping signal: %s",
                    index_symbol, _dq.get('reason', '?')
                )
                return
        except Exception as _dq_exc:
            import logging as _log
            _log.getLogger(__name__).debug(
                "validate_candles error (ignored): %s", _dq_exc
            )
        # --- end data-quality gate ---

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

                # Engine confidence is a 0-1 fraction; strategies may store
                # min_confidence as a percent (e.g. 70). Normalize before compare.
                min_confidence = risk_manager.normalize_min_confidence(
                    strategy.get('min_confidence'))
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
        # Nearest expiry FIRST. Instruments store the date in 'expiry_date'
        # (sorting by the non-existent 'expiry' picked an arbitrary contract).
        instrument = db.instruments.find_one({
            'trading_symbol': {'$regex': f'^{index_symbol}.*{target_strike}{option_type}$'}
        }, sort=[('expiry_date', 1)])

        if not instrument:
             raise Exception(f"No instrument found for {index_symbol} {target_strike} {option_type}")

        return instrument['trading_symbol']

    # =========================================================
    # 3. EXECUTION METHODS - FIXED
    # =========================================================

    def execute_entry(self, strategy: Dict, signal: Dict, option_type: str, source: str = "AUTO") -> Dict:
        """Execute entry for PAPER/LIVE.

        Enforces the central safety gate + a per-user trade lock HERE so every
        entry path (auto scheduler, manual execute, quick-trade) is protected,
        even if a caller forgot to pre-validate."""
        if not is_market_open() and self.execution_mode == 'LIVE':
             return {'success': False, 'error': 'Market is closed'}

        # --- CENTRAL SAFETY GATE (defense in depth) ---
        from services.trade_safety import validate_trade_allowed
        _decision = validate_trade_allowed(
            self.user_id, strategy=strategy, symbol=strategy.get('index'),
            side=option_type, source=source)
        if not _decision.get('allowed'):
            print(f"[execute_entry] BLOCKED ({source}): {_decision.get('reason')}")
            return {'success': False, 'blocked': True,
                    'reason': _decision.get('reason'), 'source': source}

        # --- ACCURACY GATE for LIVE auto-entry (PAPER + manual are relaxed) ---
        if self.execution_mode == 'LIVE' and source == 'AUTO':
            _acc_ok, _acc_reason = self._accuracy_gate(strategy, signal)
            if not _acc_ok:
                print(f"[execute_entry] ACCURACY BLOCK ({source}): {_acc_reason}")
                return {'success': False, 'blocked': True,
                        'reason': f'[accuracy] {_acc_reason}', 'source': source}

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

        # --- Feature-flagged: risk-based position sizing ---
        # Only active when settings.get('use_risk_sizing') is explicitly True.
        # Keeps current quantity unchanged by default; any error falls back to
        # the strategy quantity so live trading is never blocked by this path.
        settings = self.settings or {}
        if settings.get('use_risk_sizing'):
            try:
                from utils.position_sizing import position_size  # lazy import
                capital = float(settings.get('capital', 0) or 0)
                risk_pct_raw = float(settings.get('risk_pct', 0) or 0)
                # Normalise percent storage (e.g. 1 => 0.01, 0.01 stays 0.01)
                risk_pct = risk_pct_raw / 100.0 if risk_pct_raw > 1 else risk_pct_raw
                sl_points = float(strategy.get('stop_loss', 0) or 0)
                lot_size = int(strategy.get('lot_size', 0) or 0)
                max_lots = strategy.get('max_lots')

                if capital > 0 and risk_pct > 0 and sl_points > 0 and lot_size > 0:
                    sizing = position_size(
                        capital=capital,
                        risk_pct=risk_pct,
                        sl_points=sl_points,
                        lot_size=lot_size,
                        max_lots=int(max_lots) if max_lots is not None else None,
                    )
                    if sizing['lots'] > 0:
                        quantity = sizing['quantity']
                        print(
                            f"[risk_sizing] {sizing['reason']} => qty={quantity} "
                            f"(lots={sizing['lots']}, risk=₹{sizing['risk_amount']:.2f})"
                        )
                    else:
                        print(
                            f"[risk_sizing] sizing returned 0 lots ({sizing['reason']}); "
                            "falling back to strategy quantity."
                        )
            except Exception as _sz_exc:
                print(f"[risk_sizing] error (using strategy quantity): {_sz_exc}")
        # --- end feature-flagged block ---

        # 2. Place + record under the per-user trade lock (serialize entries;
        #    LIVE fails closed if Redis is unavailable).
        from services.trade_safety import acquire_user_trade_lock
        with acquire_user_trade_lock(self.user_id, self.execution_mode) as locked:
            if not locked:
                return {'success': False, 'blocked': True,
                        'reason': 'Trade lock busy or Redis unavailable in LIVE (fail-closed)',
                        'source': source}
            # Re-check duplicate open trade inside the lock (avoid TOCTOU double-entry).
            if db.trades.find_one({'strategy_id': str(strategy['_id']), 'status': 'OPEN'}):
                return {'success': False, 'blocked': True,
                        'reason': 'Open trade already exists for this strategy', 'source': source}
            return self._place_and_record_entry(
                strategy, signal, option_type, trading_symbol, quantity, product, source)

    def _place_and_record_entry(self, strategy: Dict, signal: Dict, option_type: str,
                                trading_symbol: str, quantity: int, product: str,
                                source: str = "AUTO") -> Dict:
        """Broker placement + trade record. Runs only while holding the trade lock."""
        import uuid
        broker = self._get_broker()

        # Idempotency: generate the reference id + sent timestamp BEFORE the broker
        # call, so it survives an ambiguous/timed-out response and can be used for
        # reconciliation. (Stored locally; Groww REST has no client-ref tag today.)
        order_ref = uuid.uuid4().hex
        sent_at = get_ist_now()

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
            return {**result, 'order_reference_id': order_ref, 'order_state': 'REJECTED'}
        
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
        
        # LIVE: NEVER invent a fill from LTP. If the fill price is still unknown,
        # mark the trade PENDING_RECONCILE instead of opening at a fake price.
        if execution_price == 0:
            if self.execution_mode == 'LIVE':
                self._set_reconcile_block(True)
                db.create_trade({
                    'user_id': self.user_id,
                    'strategy_id': str(strategy['_id']),
                    'strategy_name': strategy.get('name', 'Unknown'),
                    'trading_symbol': trading_symbol, 'symbol': trading_symbol,
                    'option_type': option_type, 'transaction_type': 'BUY',
                    'quantity': quantity, 'entry_price': 0,
                    'order_id': result.get('order_id', ''),
                    'order_reference_id': order_ref,
                    'status': 'PENDING_RECONCILE',
                    'order_status': 'UNKNOWN_RECONCILE_REQUIRED',
                    'order_state': 'UNKNOWN_RECONCILE_REQUIRED',
                    'reconcile_required': True,
                    'sent_at': sent_at,
                    'execution_mode': self.execution_mode,
                    'entry_time': get_ist_now(), 'product': product,
                })
                try:
                    telegram_alert.send_kill_switch_alert(
                        f"LIVE order {result.get('order_id')} fill price unconfirmed "
                        f"for {trading_symbol} — marked PENDING_RECONCILE.")
                except Exception:
                    pass
                return {'success': False, 'pending': True, 'source': source,
                        'reason': 'LIVE fill price unconfirmed — trade marked for reconciliation',
                        'order_id': result.get('order_id')}
            # PAPER: LTP estimate is the simulated fill.
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
            'order_reference_id': order_ref,
            'order_status': 'COMPLETE',
            'order_state': 'COMPLETE',
            'reconcile_required': False,
            'sent_at': sent_at,
            'filled_at': get_ist_now(),
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

        # Count this order against the strategy's daily limit (was never done,
        # so max_orders_per_day never enforced).
        try:
            db.increment_strategy_orders(str(strategy['_id']))
        except Exception as _inc_exc:
            print(f"[execute_entry] increment_strategy_orders failed: {_inc_exc}")

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

        # LIVE: NEVER finalize an exit at price 0 (would record a false total loss).
        # Leave the trade OPEN, flag for reconciliation, and alert instead.
        if self.execution_mode == 'LIVE' and final_exit_price <= 0:
            self._set_reconcile_block(True)
            try:
                db.update_trade(trade['_id'], {'order_status': 'EXIT_UNCONFIRMED', 'reconcile_required': True})
            except Exception:
                pass
            try:
                telegram_alert.send_kill_switch_alert(
                    f"LIVE exit fill unconfirmed for {trading_symbol} — NOT closed at 0; reconcile required.")
            except Exception:
                pass
            return {'success': False, 'pending': True,
                    'reason': 'LIVE exit fill price unconfirmed — trade left open for reconciliation'}

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

    def _accuracy_gate(self, strategy: Dict, signal: Dict):
        """Confidence / calibrated p_win / expected-value gate for LIVE auto-entry.
        Returns (ok, reason). Raw confidence alone is NOT enough for live auto-entry."""
        conf = signal.get('confidence', 0) or 0
        min_conf = risk_manager.normalize_min_confidence(strategy.get('min_confidence'))
        if conf < min_conf:
            return False, f"confidence {conf:.2f} < {min_conf:.2f}"

        p_win = signal.get('p_win')
        if p_win is None:
            # No calibrated probability available.
            if config.REQUIRE_CALIBRATION_FOR_LIVE:
                return False, "no calibrated p_win — fit a calibration model or set REQUIRE_CALIBRATION_FOR_LIVE=false"
        else:
            if config.MIN_P_WIN > 0 and p_win < config.MIN_P_WIN:
                return False, f"p_win {p_win:.2f} < {config.MIN_P_WIN:.2f}"

        ev = signal.get('expected_value')
        if config.MIN_EXPECTED_VALUE > 0 and ev is not None and ev < config.MIN_EXPECTED_VALUE:
            return False, f"expected_value {ev} < {config.MIN_EXPECTED_VALUE}"

        return True, "OK"

    def _set_reconcile_block(self, blocked: bool):
        """Set/clear the per-user reconcile-block flag the scheduler reads to halt
        new auto-entries on a broker<->DB mismatch."""
        client = getattr(redis_client, 'client', None)
        if not client:
            return
        key = f'reconcile_blocked:{self.user_id}'
        try:
            client.set(key, '1') if blocked else client.delete(key)
        except Exception:
            pass

    def reconcile_positions(self, broker_positions: List[Dict]):
        """Compare broker positions vs DB open trades. On ANY mismatch (LIVE),
        trip the kill switch + reconcile-block flag and alert — never auto-correct
        silently. Returns a structured result for the status route."""
        try:
            db_open = db.get_active_trades(self.user_id)
        except Exception as e:
            print(f"[reconcile] DB read error: {e}")
            return {'success': False, 'error': str(e)}

        def _norm(s):
            return str(s or '').upper().strip()

        def _pos_qty(p):
            for k in ('net_quantity', 'netQty', 'net_qty', 'quantity'):
                if p.get(k) is not None:
                    try:
                        return int(float(p[k]))
                    except (TypeError, ValueError):
                        pass
            return 0

        # Broker side (net per symbol; drop flat positions).
        broker_map: Dict[str, int] = {}
        for p in (broker_positions or []):
            sym = _norm(p.get('trading_symbol') or p.get('symbol') or p.get('tradingSymbol'))
            if sym:
                broker_map[sym] = broker_map.get(sym, 0) + _pos_qty(p)
        broker_open = {s: q for s, q in broker_map.items() if q != 0}

        # DB side (open trades net per symbol).
        db_map: Dict[str, int] = {}
        for t in db_open:
            sym = _norm(t.get('trading_symbol') or t.get('symbol'))
            if sym:
                db_map[sym] = db_map.get(sym, 0) + int(t.get('quantity', 0) or 0)

        mismatches = []
        for sym, dq in db_map.items():
            bq = broker_open.get(sym, 0)
            if bq == 0:
                mismatches.append({'type': 'db_open_broker_flat', 'symbol': sym, 'db_qty': dq, 'broker_qty': 0})
            elif bq != dq:
                mismatches.append({'type': 'qty_mismatch', 'symbol': sym, 'db_qty': dq, 'broker_qty': bq})
        for sym, bq in broker_open.items():
            if sym not in db_map:
                mismatches.append({'type': 'broker_position_no_db', 'symbol': sym, 'db_qty': 0, 'broker_qty': bq})

        # Duplicate DB open trades for the same strategy+symbol.
        seen: Dict[tuple, int] = {}
        for t in db_open:
            key = (str(t.get('strategy_id')), _norm(t.get('trading_symbol') or t.get('symbol')))
            seen[key] = seen.get(key, 0) + 1
        for (sid, sym), n in seen.items():
            if n > 1:
                mismatches.append({'type': 'duplicate_db_open', 'symbol': sym, 'strategy_id': sid, 'count': n})

        # Trades stuck in PENDING_RECONCILE (LIVE unconfirmed fills).
        try:
            pend = list(db.trades.find(
                {'user_id': self.user_id, 'status': 'PENDING_RECONCILE'},
                {'_id': 0, 'trading_symbol': 1, 'order_id': 1, 'order_reference_id': 1}))
            for p in pend:
                mismatches.append({'type': 'pending_reconcile', 'symbol': _norm(p.get('trading_symbol')),
                                   'order_id': p.get('order_id'), 'order_reference_id': p.get('order_reference_id')})
        except Exception:
            pass

        is_live = self.execution_mode == 'LIVE'
        if not mismatches:
            self._set_reconcile_block(False)  # healthy -> clear any prior block
            status = 'healthy'
        else:
            status = 'blocked' if is_live else 'warning'
            print(f"[reconcile] MISMATCH user={self.user_id}: {mismatches}")
            if is_live:  # trip safety; never auto-correct
                try:
                    db.upsert_settings(self.user_id, {'kill_switch': True})
                except Exception as e:
                    print(f"[reconcile] kill-switch set failed: {e}")
                self._set_reconcile_block(True)
            try:
                db.db['reconciliation_mismatch'].insert_one({
                    'user_id': self.user_id, 'mismatches': mismatches,
                    'execution_mode': self.execution_mode, 'created_at': get_ist_now(),
                })
            except Exception as e:
                print(f"[reconcile] mismatch log failed: {e}")
            try:
                telegram_alert.send_kill_switch_alert(
                    f"Reconciliation mismatch ({len(mismatches)}) for {self.user_id}: {mismatches}")
            except Exception:
                pass

        report = {
            'status': status, 'healthy': not mismatches, 'mismatch_count': len(mismatches),
            'mismatches': mismatches, 'execution_mode': self.execution_mode,
            'reconcile_blocked': bool(is_live and mismatches),
            'last_checked_at': get_ist_now().isoformat(),
        }
        try:
            db.save_reconciliation_report(self.user_id, dict(report))
        except Exception as e:
            print(f"[reconcile] report save failed: {e}")

        return {'success': True, 'healthy': not mismatches, 'mismatches': mismatches, 'report': report}

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
