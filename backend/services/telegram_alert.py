"""
Telegram Alert Service
Sends trading alerts and daily summaries via Telegram
"""
import requests
import logging
from typing import Dict, Optional
from datetime import datetime
from config import config

logger = logging.getLogger(__name__)

def get_ist_now():
    """Get current IST time"""
    from datetime import timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(IST)


class TelegramAlert:
    """Send alerts via Telegram bot"""
    
    def __init__(self, bot_token: str = None, chat_id: str = None):
        # Fallback to config if not provided (for system-wide alerts)
        self.bot_token = bot_token or config.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or config.TELEGRAM_CHAT_ID
        
        if self.bot_token:
            self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        else:
            self.base_url = None
    
    def _send_message(self, text: str, parse_mode: str = 'HTML') -> bool:
        """Send message to Telegram"""
        if not self.base_url or not self.chat_id:
            logger.warning("Telegram credentials missing or incomplete.")
            return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': parse_mode
            }
            response = requests.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                return True
            else:
                logger.error(f"Telegram API Error: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Telegram Exception: {e}")
            return False
    
    def send_alert(self, user_id: str, message: str) -> bool:
        """Send generic alert"""
        # In a single-user system, we ignore user_id and send to the configured chat_id
        return self._send_message(message)
    
    def send_signal_alert(self, signal: Dict) -> bool:
        """Send signal alert"""
        emoji = '🟢' if signal.get('signal') == 'BULLISH' else '🔴'
        
        text = f"""
{emoji} <b>SIGNAL ALERT</b> {emoji}

<b>Symbol:</b> {signal.get('symbol', 'N/A')}
<b>Signal:</b> {signal.get('signal', 'N/A')}
<b>Confidence:</b> {signal.get('confidence', 0) * 100:.0f}%
<b>Market Regime:</b> {signal.get('market_regime', 'N/A')}

<b>Patterns:</b> {', '.join(signal.get('patterns', [])[:3]) or 'None'}

<i>Time: {get_ist_now().strftime('%H:%M:%S')} IST</i>
"""
        return self._send_message(text)
    
    def send_entry_alert(self, trade: Dict) -> bool:
        """Send trade entry alert"""
        mode_emoji = '📝' if trade.get('execution_mode') == 'PAPER' else '💰'
        
        text = f"""
{mode_emoji} <b>ENTRY EXECUTED</b> {mode_emoji}

<b>Symbol:</b> {trade.get('symbol', 'N/A')}
<b>Type:</b> {trade.get('option_type', 'N/A')}
<b>Quantity:</b> {trade.get('quantity', 0)}
<b>Entry Price:</b> ₹{trade.get('entry_price', 0):.2f}

<b>Stop Loss:</b> ₹{trade.get('stop_loss', 0):.2f}
<b>Target:</b> ₹{trade.get('target', 0):.2f}

<b>Strategy:</b> {trade.get('strategy_name', 'N/A')}
<b>Mode:</b> {trade.get('execution_mode', 'PAPER')}

<i>Time: {get_ist_now().strftime('%H:%M:%S')} IST</i>
"""
        return self._send_message(text)
    
    def send_exit_alert(self, trade: Dict, exit_result: Dict) -> bool:
        """Send trade exit alert"""
        pnl = exit_result.get('pnl', 0)
        pnl_emoji = '✅' if pnl > 0 else '❌' if pnl < 0 else '➖'
        exit_type = exit_result.get('exit_type', 'MANUAL')
        
        text = f"""
{pnl_emoji} <b>EXIT - {exit_type}</b> {pnl_emoji}

<b>Symbol:</b> {trade.get('symbol', 'N/A')}
<b>Entry:</b> ₹{trade.get('entry_price', 0):.2f}
<b>Exit:</b> ₹{exit_result.get('exit_price', 0):.2f}

<b>P&L:</b> {'₹' + f'{pnl:.2f}' if pnl >= 0 else '-₹' + f'{abs(pnl):.2f}'}

<b>Strategy:</b> {trade.get('strategy_name', 'N/A')}

<i>Time: {get_ist_now().strftime('%H:%M:%S')} IST</i>
"""
        return self._send_message(text)
    
    def send_daily_summary(self, summary: Dict) -> bool:
        """Send daily trading summary"""
        total_pnl = summary.get('total_pnl', 0)
        pnl_emoji = '🎉' if total_pnl > 0 else '😔' if total_pnl < 0 else '➖'
        
        text = f"""
{pnl_emoji} <b>DAILY SUMMARY</b> {pnl_emoji}
<b>{get_ist_now().strftime('%d %B %Y')}</b>

📊 <b>Performance</b>
• Total P&L: {'₹' + f'{total_pnl:.2f}' if total_pnl >= 0 else '-₹' + f'{abs(total_pnl):.2f}'}
• Trades: {summary.get('total_trades', 0)}
• Winning: {summary.get('winning', 0)}
• Losing: {summary.get('losing', 0)}
• Win Rate: {summary.get('win_rate', 0):.1f}%

<i>Mode: {summary.get('execution_mode', 'PAPER')}</i>
"""
        return self._send_message(text)
    
    def send_kill_switch_alert(self, reason: str) -> bool:
        """Send kill switch activation alert"""
        text = f"""
🚨 <b>KILL SWITCH ACTIVATED</b> 🚨

<b>Reason:</b> {reason}

All trading has been stopped.
Manual intervention required.

<i>Time: {get_ist_now().strftime('%H:%M:%S')} IST</i>
"""
        return self._send_message(text)
    
    def test_connection(self, bot_token: str = None, chat_id: str = None) -> bool:
        """Test Telegram connection"""
        # If parameters provided, temporarily override for this test
        original_token = self.bot_token
        original_chat = self.chat_id
        
        if bot_token: self.bot_token = bot_token
        if chat_id: self.chat_id = chat_id
        
        # Re-construct base URL if token changed
        if bot_token:
            self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        
        text = f"""
✅ <b>Connection Test</b>

AI Trading System connected successfully!

<i>Time: {get_ist_now().strftime('%H:%M:%S')} IST</i>
"""
        result = self._send_message(text)
        
        # Restore original state if we modified it
        if bot_token:
            self.bot_token = original_token
            self.chat_id = original_chat
            if self.bot_token:
                self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
            
        return result


# Singleton instance (initialized with defaults from config)
telegram_alert = TelegramAlert()


def get_telegram_alert(bot_token: str = None, chat_id: str = None) -> TelegramAlert:
    """Factory: Get a new Telegram alert instance with specific credentials"""
    if bot_token and chat_id:
        return TelegramAlert(bot_token, chat_id)
    return telegram_alert