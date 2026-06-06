"""
Candle Service - Fetch and store candle data from Groww API
Stores in MongoDB for chart generation
Supports: 1min, 5min, 15min, 60min intervals
"""
import time
import random
import requests
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from config import config
from utils.time_utils import get_ist_now, IST

INDEX_MAPPING = {
    'NIFTY': 'NIFTY',
    'NIFTY 50': 'NIFTY',
    'NIFTY50': 'NIFTY',

    'NIFTY BANK': 'BANKNIFTY',
    'BANKNIFTY': 'BANKNIFTY',

    'SENSEX': 'SENSEX',
}

# Valid intervals supported by the API
VALID_INTERVALS = ['1', '5', '15', '60']

class CandleService:
    """Service to fetch and store candle data"""
    
    def __init__(self):
        raw_url = config.GROWW_API_BASE_URL if hasattr(config, 'GROWW_API_BASE_URL') else 'https://api.groww.in'
        self.base_url = raw_url.rstrip('/').replace('/v1', '')
    
    def fetch_candles_from_groww(
        self, 
        trading_symbol: str, 
        start_time: str, 
        end_time: str,
        interval: int = 5,
        exchange: str = 'NSE', 
        segment: str = 'CASH',
        access_token: str = None
    ) -> List[Dict]:
        """
        Fetch real candles from Groww API (v1)
        
        Args:
            trading_symbol: Symbol name (NIFTY, BANKNIFTY, SENSEX)
            start_time: Start datetime string (YYYY-MM-DD HH:MM:SS)
            end_time: End datetime string (YYYY-MM-DD HH:MM:SS)
            interval: Candle interval in minutes (1, 5, 15, 60)
            exchange: NSE or BSE
            segment: CASH or FNO
            access_token: Groww API access token
        
        Returns:
            List of candle dictionaries with OHLCV data
        """
        try:
            # Validate interval
            if str(interval) not in VALID_INTERVALS:
                print(f"Warning: Invalid interval {interval}, defaulting to 5")
                interval = 5
            
            final_symbol = INDEX_MAPPING.get(trading_symbol, trading_symbol)
            final_exchange = 'BSE' if trading_symbol == 'SENSEX' else exchange

            url = f"{self.base_url}/v1/historical/candle/range"
            headers = {
                'Accept': 'application/json',
                'Authorization': f'Bearer {access_token}' if access_token else '',
                'X-API-VERSION': '1.0'
            }
            
            params = {
                'exchange': final_exchange,
                'segment': segment,
                'trading_symbol': final_symbol,
                'start_time': start_time,
                'end_time': end_time,
                'intervalInMinutes': int(interval)  # Critical: This determines candle timeframe
            }
            
            # Retry/backoff on transient errors (GET is idempotent/safe to retry).
            response = None
            for attempt in range(3):
                try:
                    response = requests.get(url, headers=headers, params=params, timeout=30)
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                    if attempt < 2:
                        time.sleep(min(0.5 * (2 ** attempt), 4.0) + random.uniform(0, 0.3))
                        continue
                    print(f"Candle fetch network error: {e}")
                    return []
                if response.status_code == 429 and attempt < 2:
                    ra = response.headers.get('Retry-After')
                    try:
                        wait = float(ra) if ra else float(2 ** attempt)
                    except (ValueError, TypeError):
                        wait = float(2 ** attempt)
                    time.sleep(min(wait, 30.0))
                    continue
                if 500 <= response.status_code < 600 and attempt < 2:
                    time.sleep(min(0.5 * (2 ** attempt), 4.0))
                    continue
                break

            if response is not None and response.status_code == 200:
                data = response.json()
                candles = []
                
                # Handle different Groww API response formats
                if 'payload' in data and 'candles' in data['payload']:
                    candles = data['payload']['candles']
                elif 'candles' in data:
                    candles = data['candles']

                if not candles:
                    print(f"⚠️ No candles returned for {trading_symbol} {interval}min")
                    return []

                formatted = []
                for c in candles:
                    try:
                        # Safety check for volume index
                        vol = c[5] if (len(c) > 5 and c[5] is not None) else 0
                        formatted.append({
                            'timestamp': int(c[0]),
                            # IST-aware ISO string (epoch is absolute; render in IST
                            # so stored display time matches the Indian session).
                            'datetime': datetime.fromtimestamp(int(c[0]), tz=IST).isoformat(),
                            'open': float(c[1]),
                            'high': float(c[2]),
                            'low': float(c[3]),
                            'close': float(c[4]),
                            'volume': int(vol),
                            'symbol': trading_symbol,
                            'interval': str(interval)  # Store as string for consistency
                        })
                    except (ValueError, TypeError) as e:
                        continue

                # Drop the still-forming (incomplete) last candle. A bar that
                # opens at t for `interval` minutes is only CLOSED once
                # now >= t + interval*60. Indicators/signals must use closed
                # bars only, otherwise every signal repaints within the period.
                now_epoch = int(time.time())
                interval_sec = int(interval) * 60
                closed = [c for c in formatted if c['timestamp'] + interval_sec <= now_epoch]
                dropped = len(formatted) - len(closed)
                if dropped:
                    print(f"⏳ Dropped {dropped} forming candle(s) for {trading_symbol} ({interval}min)")
                formatted = closed

                print(f"✅ Fetched {len(formatted)} closed x {interval}min candles for {trading_symbol}")
                return formatted
            else:
                print(f"API Fail {response.status_code}: {response.text[:200]}")
                return []
            
        except Exception as e:
            print(f"Fetch Crash: {e}")
            return []

    def _get_smart_window(self, interval: int = 5):
        """
        Helper to get last valid trading window (handling weekends/nights).
        Uses IST so fetch windows are correct regardless of server timezone
        (a UTC host would otherwise think the market is closed during the session).
        Adjusts fetch window based on interval to ensure enough candles.
        """
        now = get_ist_now()
        target_end = now
        
        # Rewind if Weekend (Sat=5, Sun=6)
        if target_end.weekday() >= 5: 
            days_back = target_end.weekday() - 4 
            target_end = target_end - timedelta(days=days_back)
            target_end = target_end.replace(hour=15, minute=30, second=0, microsecond=0)
            
        # Rewind if Night/Morning (Before Market Open)
        elif target_end.hour < 9 or (target_end.hour == 9 and target_end.minute < 15):
             target_end = (target_end - timedelta(days=1)).replace(hour=15, minute=30, second=0)
             if target_end.weekday() == 6: target_end -= timedelta(days=2)
        
        end_dt = target_end
        
        # Adjust lookback based on interval to get meaningful data
        # 1min  -> 7 days (lots of candles)
        # 5min  -> 7 days
        # 15min -> 14 days
        # 60min -> 30 days
        if interval == 1:
            lookback_days = 7
        elif interval == 5:
            lookback_days = 7
        elif interval == 15:
            lookback_days = 14
        else:  # 60min or other
            lookback_days = 30
            
        start_dt = end_dt - timedelta(days=lookback_days)
        return start_dt, end_dt

    def sync_candles(self, db, symbol: str, interval: str = '5', access_token: str = None) -> Dict:
        """FULL SYNC: Fetches historical candles based on interval."""
        if not access_token: 
            return {'success': False, 'error': 'No access token'}
        
        int_interval = int(interval)
        start_dt, end_dt = self._get_smart_window(int_interval)
        return self._execute_sync(db, symbol, interval, start_dt, end_dt, access_token, mode='full')

    def _get_realtime_window(self, interval: int = 1):
        """Short, incremental window for realtime sync: just the current IST
        session. Avoids refetching ~7 days of candles every minute (which risks
        Groww rate-limit bans). Upsert dedups, so a session window is enough.
        Falls back to the wide smart window before the open / on weekends."""
        now = get_ist_now()
        open_dt = now.replace(hour=config.MARKET_OPEN_HOUR,
                              minute=config.MARKET_OPEN_MINUTE,
                              second=0, microsecond=0)
        if now.weekday() >= 5 or now < open_dt:
            return self._get_smart_window(interval)
        return open_dt, now

    def sync_realtime(self, db, symbol: str, interval: str = '5', access_token: str = None) -> Dict:
        """REALTIME SYNC: Fetches the current session's candles (Upsert)."""
        if not access_token:
            return {'success': False, 'error': 'No token'}

        int_interval = int(interval)
        start_dt, end_dt = self._get_realtime_window(int_interval)
        return self._execute_sync(db, symbol, interval, start_dt, end_dt, access_token, mode='realtime')

    def _execute_sync(self, db, symbol, interval, start_dt, end_dt, token, mode='full'):
        """Helper to execute the fetch and save safely"""
        start_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')

        candles = self.fetch_candles_from_groww(
            trading_symbol=symbol,
            start_time=start_str,
            end_time=end_str,
            interval=int(interval),
            access_token=token
        )
        
        # ======================================================================
        # CRITICAL SAFETY CHECK
        # Only save if we actually received data. Do NOT delete if list is empty.
        # This prevents wiping the DB when the API is down or market is closed.
        # ======================================================================
        if candles and len(candles) > 0:
            if mode == 'full':
                self._save_to_db(db, symbol, interval, candles)
            else:
                self._upsert_to_db(db, symbol, interval, candles)
            return {'success': True, 'count': len(candles), 'interval': interval, 'mode': mode}
        
        # Return failure but leave DB untouched
        return {'success': False, 'error': 'No data fetched - Database preserved', 'interval': interval}

    def _save_to_db(self, db, symbol: str, interval: str, candles: List[Dict]):
        """Bulk Replace (Delete Old -> Insert New)"""
        try:
            # Only delete now that we know 'candles' has data
            db.candles.delete_many({'symbol': symbol, 'interval': str(interval)})
            db.candles.insert_many(candles)
            print(f"✅ Full Sync: Saved {len(candles)} candles for {symbol} ({interval}min)")
        except Exception as e:
            print(f"DB Save Error: {e}")

    def _upsert_to_db(self, db, symbol: str, interval: str, candles: List[Dict]) -> int:
        """Upsert (Update Existing / Insert New)"""
        count = 0
        try:
            for c in candles:
                result = db.candles.update_one(
                    {
                        'symbol': symbol, 
                        'interval': str(interval),
                        'timestamp': c['timestamp']
                    },
                    {'$set': c},
                    upsert=True
                )
                if result.upserted_id or result.modified_count:
                    count += 1
            
            if count > 0:
                print(f"⚡ Realtime: Updated {count} candles for {symbol} ({interval}min)")
            return count
        except Exception as e:
            print(f"Upsert Error: {e}")
            return 0

    def get_candles(self, db, symbol: str, interval: str = '5', limit: int = 200) -> List[Dict]:
        """Get candles from MongoDB"""
        try:
            candles = list(db.candles.find(
                {'symbol': symbol, 'interval': str(interval)},
                {'_id': 0}
            ).sort('timestamp', -1).limit(limit))
            return candles[::-1]  # Return oldest first
        except Exception as e:
            print(f"Get candles error: {e}")
            return []

    def get_candles_for_analysis(self, db, symbol: str, interval: str = '5') -> List[Dict]:
        """Get larger dataset for analysis"""
        return self.get_candles(db, symbol, interval, 500)

candle_service = CandleService()