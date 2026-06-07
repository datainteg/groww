"""
Paper Trading Broker
Simulates trading using Groww live prices with realistic Slippage & Spread
"""
import random
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from database import db
from config import config
from services.groww_client import get_groww_client
from utils import get_ist_now, risk_manager

class PaperBroker:
    """Paper trading broker that simulates real market execution"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.groww = get_groww_client(user_id)
        self._ensure_account()
    
    def _ensure_account(self):
        """Ensure paper trading account exists"""
        account = db.get_paper_account(self.user_id)
        if not account:
            db.reset_paper_account(self.user_id, config.PAPER_INITIAL_CAPITAL)
    
    def get_account(self) -> Dict:
        """Get paper trading account details"""
        account = db.get_paper_account(self.user_id)
        
        # Calculate unrealized P&L from open positions
        unrealized = self._calculate_unrealized_pnl(account.get('positions', []))
        
        return {
            'balance': account.get('balance', config.PAPER_INITIAL_CAPITAL),
            'initial_capital': account.get('initial_capital', config.PAPER_INITIAL_CAPITAL),
            'realized_pnl': account.get('realized_pnl', 0),
            'unrealized_pnl': unrealized,
            'total_pnl': account.get('realized_pnl', 0) + unrealized,
            'positions': account.get('positions', []),
            'equity': account.get('balance', config.PAPER_INITIAL_CAPITAL) + unrealized
        }
    
    def _calculate_unrealized_pnl(self, positions: List[Dict]) -> float:
        """Calculate unrealized P&L from open positions"""
        if not positions:
            return 0.0
        
        total_unrealized = 0.0
        
        for pos in positions:
            try:
                # Get current LTP from Groww
                symbol = f"NSE_{pos['trading_symbol']}"
                # In a real loop, we should bulk fetch these to save API calls
                ltp_result = self.groww.get_ltp([symbol], segment='FNO')
                
                if ltp_result.get('success'):
                    # Use Bid/Ask logic if available, otherwise LTP
                    ltp = ltp_result['data'].get(symbol, pos['entry_price'])
                    
                    # For unrealized P&L, we just use LTP. 
                    # Slippage is applied only on Exit.
                    unrealized = (ltp - pos['entry_price']) * pos['quantity']
                    total_unrealized += unrealized
                    pos['ltp'] = ltp
                    pos['unrealized_pnl'] = unrealized
            except:
                pass
        
        return total_unrealized
    
    def get_ltp(self, trading_symbol_or_list, segment: str = 'FNO') -> float:
        """
        Get LTP for a symbol using Groww API.
        FIX: Now accepts both single string or list of symbols for compatibility
        
        Args:
            trading_symbol_or_list: Either a single trading symbol string, 
                                   or a list of symbols (for compatibility with GrowwClient)
            segment: Market segment (FNO/CASH)
            
        Returns:
            float: Last traded price
        """
        try:
            # Handle list input (for compatibility with GrowwClient interface)
            if isinstance(trading_symbol_or_list, list):
                if not trading_symbol_or_list:
                    return 0
                trading_symbol = trading_symbol_or_list[0]
                # Remove exchange prefix if present
                if '_' in trading_symbol:
                    trading_symbol = trading_symbol.split('_', 1)[1]
            else:
                trading_symbol = trading_symbol_or_list
            
            exchange_symbol = f"NSE_{trading_symbol}"
            result = self.groww.get_ltp([exchange_symbol], segment=segment)
            
            if result.get('success'):
                data = result.get('data', {})
                # Try different key formats
                if exchange_symbol in data:
                    return float(data[exchange_symbol])
                if trading_symbol in data:
                    return float(data[trading_symbol])
                # Try to find any matching key
                for key, value in data.items():
                    if trading_symbol in key:
                        return float(value)
                    
        except Exception as e:
            print(f"Error getting LTP: {e}")
        
        return 0
    
    def _calculate_slippage(self, ltp: float, transaction_type: str) -> float:
        """
        Simulate real-world slippage and spread.
        
        Mechanics:
        1. Base Spread: 0.05% (Standard execution cost)
        2. Volatility Noise: Random factor (0.8x to 1.5x)
        3. Buy Orders: Executed slightly ABOVE LTP (Ask Price)
        4. Sell Orders: Executed slightly BELOW LTP (Bid Price)
        """
        base_spread_percent = 0.0005  # 0.05%
        volatility_factor = random.uniform(0.8, 1.5)
        
        slippage_amount = ltp * base_spread_percent * volatility_factor
        
        if transaction_type == 'BUY':
            # You buy at the Ask (Higher)
            execution_price = ltp + slippage_amount
        else:
            # You sell at the Bid (Lower)
            execution_price = ltp - slippage_amount
            
        return round(execution_price, 2)

    def place_order(
        self,
        trading_symbol: str,
        quantity: int,
        transaction_type: str,
        order_type: str = 'MARKET',
        price: float = None,
        trigger_price: float = None,
        product: str = 'MIS',
        segment: str = 'FNO'
    ) -> Dict:
        """
        Simulate placing an order with Realistic Execution (Slippage enabled)
        """
        # 1. Get current price
        ltp = self.get_ltp(trading_symbol, segment)
        
        if ltp <= 0:
            return {
                'success': False,
                'error': 'Could not get current price'
            }
        
        # 2. Determine Execution Price with Slippage
        if order_type == 'MARKET':
            exec_price = self._calculate_slippage(ltp, transaction_type)
        elif order_type == 'LIMIT':
            # For Limit, we assume fill if LTP crosses price, but fill at Limit price
            # (Simplification for paper trading)
            exec_price = price or ltp
        else:
            exec_price = ltp
        
        # Generate paper order ID
        order_id = f"PAPER_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        
        # Get account
        account = db.get_paper_account(self.user_id)
        balance = account.get('balance', config.PAPER_INITIAL_CAPITAL)
        positions = account.get('positions', [])
        
        # Calculate order value
        order_value = exec_price * quantity
        
        if transaction_type == 'BUY':
            # Check if enough balance
            # For Options Buying, Margin = Premium * Qty
            required_margin = order_value
            
            if balance < required_margin:
                return {
                    'success': False,
                    'error': f'Insufficient funds. Required: ₹{required_margin:.2f}, Available: ₹{balance:.2f}'
                }
            
            # Add position
            position = {
                'trading_symbol': trading_symbol,
                'quantity': quantity,
                'entry_price': exec_price,
                'entry_time': get_ist_now().isoformat(),
                'order_id': order_id,
                'transaction_type': transaction_type,
                'segment': segment,
                'product': product,
                'ltp': exec_price,
                'unrealized_pnl': 0
            }
            positions.append(position)
            
            # Deduct full premium from balance
            new_balance = balance - required_margin
        
        else:  # SELL
            # Find matching position
            matching_pos = None
            pos_index = -1
            
            # Logic: FIFO or Specific Match
            for i, pos in enumerate(positions):
                if pos['trading_symbol'] == trading_symbol and pos['quantity'] >= quantity:
                    matching_pos = pos
                    pos_index = i
                    break
            
            if not matching_pos:
                return {
                    'success': False,
                    'error': 'No matching position to sell'
                }
            
            # Calculate P&L
            # Profit = (Sell Price - Buy Price) * Qty
            pnl = (exec_price - matching_pos['entry_price']) * quantity
            
            # Update or remove position
            if matching_pos['quantity'] == quantity:
                positions.pop(pos_index)
            else:
                positions[pos_index]['quantity'] -= quantity
            
            # Credit back the original capital + P&L
            # Originally locked capital = Entry Price * Qty
            original_capital = matching_pos['entry_price'] * quantity
            new_balance = balance + original_capital + pnl
            
            # Update realized P&L
            realized_pnl = account.get('realized_pnl', 0) + pnl
            db.upsert_paper_account(self.user_id, {
                'realized_pnl': realized_pnl
            })
        
        # Update account
        db.upsert_paper_account(self.user_id, {
            'balance': new_balance,
            'positions': positions
        })
        
        return {
            'success': True,
            'order_id': order_id,
            'status': 'COMPLETE',
            'trading_symbol': trading_symbol,
            'quantity': quantity,
            'transaction_type': transaction_type,
            'execution_price': exec_price,
            'slippage': round(abs(exec_price - ltp), 2), # Debug info
            'execution_time': get_ist_now().isoformat(),
            'is_paper': True
        }
    
    def get_positions(self) -> List[Dict]:
        """Get open positions with current LTP"""
        account = db.get_paper_account(self.user_id)
        positions = account.get('positions', [])
        
        # Update LTP for all positions
        for pos in positions:
            ltp = self.get_ltp(pos['trading_symbol'])
            if ltp > 0:
                pos['ltp'] = ltp
                pos['unrealized_pnl'] = (ltp - pos['entry_price']) * pos['quantity']
        
        return positions
    
    def get_orders(self) -> List[Dict]:
        """Get paper orders (from trades table)"""
        trades = db.get_trades_by_user(self.user_id, limit=50)
        
        orders = []
        for trade in trades:
            if trade.get('execution_mode') == 'PAPER':
                orders.append({
                    'order_id': trade.get('order_id', ''),
                    'trading_symbol': trade.get('symbol', ''),
                    'quantity': trade.get('quantity', 0),
                    'transaction_type': trade.get('transaction_type', ''),
                    'order_type': 'MARKET',
                    'status': 'COMPLETE',
                    'price': trade.get('entry_price', 0),
                    'created_at': trade.get('created_at', '')
                })
        
        return orders
    
    def get_daily_pnl(self) -> Dict:
        """Get today's P&L summary"""
        trades = db.get_today_trades(self.user_id)
        
        total_pnl = 0
        winning = 0
        losing = 0
        
        for trade in trades:
            # Trades are stored with status 'CLOSED' (uppercase). The old
            # lowercase 'closed' check matched nothing -> paper daily P&L always 0.
            if trade.get('execution_mode') == 'PAPER' and str(trade.get('status', '')).upper() == 'CLOSED':
                pnl = trade.get('pnl', 0)
                total_pnl += pnl
                
                if pnl > 0:
                    winning += 1
                elif pnl < 0:
                    losing += 1
        
        account = self.get_account()
        
        return {
            'total_pnl': total_pnl,
            'realized_pnl': account['realized_pnl'],
            'unrealized_pnl': account['unrealized_pnl'],
            'trades_today': len(trades),
            'winning': winning,
            'losing': losing
        }
    
    def get_limits(self) -> Dict:
        """Get margin/balance limits"""
        account = self.get_account()
        
        return {
            'available_balance': account['balance'],
            # For options buying, margin used is the premium paid. 
            # We track "Used Margin" as Initial Capital - Available Balance
            'used_margin': account['initial_capital'] - account['balance'],
            'total_balance': account['initial_capital'],
            'equity': account['equity']
        }
    
    def reset_account(self) -> Dict:
        """Reset paper trading account"""
        db.reset_paper_account(self.user_id, config.PAPER_INITIAL_CAPITAL)
        
        return {
            'success': True,
            'message': 'Paper account reset successfully',
            'balance': config.PAPER_INITIAL_CAPITAL
        }
    
    def check_sl_target(self, trade: Dict) -> Optional[Dict]:
        """
        Check if SL or target is hit for an open trade
        
        Returns:
            Dict with exit info if triggered, None otherwise
        """
        if trade.get('status') != 'OPEN':
            return None
        
        symbol = trade.get('symbol')
        current_sl = trade.get('current_sl', trade.get('stop_loss'))
        target = trade.get('target')
        partial_target_1 = trade.get('partial_target_1')
        
        # Get current LTP
        ltp = self.get_ltp(symbol)
        
        if ltp <= 0:
            return None
        
        # Check exit conditions
        exit_check = risk_manager.check_exit_condition(
            current_price=ltp,
            stop_loss=current_sl,
            target=target,
            partial_target_1=partial_target_1
        )
        
        if exit_check['exit_triggered']:
            # IMPORTANT: The actual exit price will be calculated in execute_exit -> place_order
            # Here we just flag that an exit MUST happen.
            return {
                'trade_id': trade.get('_id'),
                'exit_price': ltp, # This is just a trigger price, not execution price
                'exit_type': exit_check['exit_type'],
                'exit_time': get_ist_now().isoformat()
            }
        
        return None

def get_paper_broker(user_id: str) -> PaperBroker:
    """Get paper broker instance"""
    return PaperBroker(user_id)