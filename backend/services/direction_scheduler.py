"""
Direction Scheduler Service
High-frequency scheduler for Market Direction Engine
Runs every 1 second during market hours
"""

import time
import json
import threading
from datetime import datetime
from typing import Dict, Optional, List
import logging
import pandas as pd

from database.mongodb import db
from database.redis_client import redis_client
from config import config
from utils.time_utils import get_ist_now, is_market_open
from analysis.market_direction_engine import market_direction_engine, analyze_direction
from analysis.timeframe_aggregator import timeframe_aggregator, aggregate_all_timeframes
from services.candle_service import candle_service

logger = logging.getLogger(__name__)


class DirectionScheduler:
    """
    High-frequency scheduler for Market Direction Engine
    
    Features:
    - Runs every 1 second during market hours
    - Aggregates 1m candles to 5m, 15m, 30m
    - Caches direction results in Redis
    - Provides real-time direction data to frontend
    """
    
    INDICES = ['NIFTY', 'BANKNIFTY', 'SENSEX']
    UPDATE_INTERVAL = 1  # seconds
    
    def __init__(self):
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_update: Dict[str, datetime] = {}
        self.direction_cache: Dict[str, Dict] = {}
        self._lock = threading.Lock()
    
    def start(self):
        """Start the direction scheduler"""
        if self.running:
            logger.warning("Direction scheduler already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info(f"[{get_ist_now()}] 🚀 Direction Scheduler Started (1s interval)")
    
    def stop(self):
        """Stop the direction scheduler"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info(f"[{get_ist_now()}] 🛑 Direction Scheduler Stopped")
    
    def _run_loop(self):
        """Main loop that runs every 1 second"""
        while self.running:
            try:
                if is_market_open():
                    self._update_all_directions()
                time.sleep(self.UPDATE_INTERVAL)
            except Exception as e:
                logger.error(f"Direction loop error: {e}")
                time.sleep(1)
    
    def _update_all_directions(self):
        """Update direction for all indices"""
        for symbol in self.INDICES:
            try:
                self._update_direction(symbol)
            except Exception as e:
                logger.error(f"Error updating direction for {symbol}: {e}")
    
    def _update_direction(self, symbol: str):
        """
        Update direction for a single symbol
        
        Steps:
        1. Get 1m candles from cache/DB
        2. Aggregate to 5m, 15m
        3. Run Market Direction Engine
        4. Cache result in Redis
        """
        try:
            # 1. Get 1-minute candles (last 200)
            candles_1m = candle_service.get_candles(db, symbol, '1', 200)

            # Require REAL 1m data. Never substitute 5m candles for 1m: the
            # engine weights the 1m timeframe (~20%) and feeding 5m bars there
            # silently corrupts the signal. Publish a degraded NEUTRAL instead.
            if not candles_1m or len(candles_1m) < 50:
                self._publish_degraded(symbol, 'insufficient 1m data')
                return

            df_1m = pd.DataFrame(candles_1m)
            df_5m = timeframe_aggregator.aggregate(df_1m, '5')
            df_15m = timeframe_aggregator.aggregate(df_1m, '15')

            if len(df_5m) < 20 or len(df_15m) < 20:
                self._publish_degraded(symbol, 'insufficient aggregated data')
                return

            # 2. Get live LTP from Redis
            ltp_str = redis_client.get_cached_ltp(symbol)
            live_ltp = float(ltp_str) if ltp_str else None

            # 3. Run Market Direction Engine
            result = analyze_direction(
                df_1m=df_1m,
                df_5m=df_5m,
                df_15m=df_15m,
                symbol=symbol,
                live_ltp=live_ltp
            )

            # 4. Cache result (+ as_of for staleness detection by consumers)
            self._publish(symbol, result)

        except Exception as e:
            logger.error(f"Direction update error for {symbol}: {e}")

    def _publish(self, symbol: str, result: Dict):
        """Cache a direction result in-process and in Redis (as JSON, with as_of)."""
        payload = dict(result) if isinstance(result, dict) else {'value': result}
        payload['symbol'] = symbol
        payload['as_of'] = get_ist_now().isoformat()
        with self._lock:
            self.direction_cache[symbol] = payload
            self.last_update[symbol] = get_ist_now()
        # JSON (not str(dict)) so other processes can json.loads it.
        # NOTE: the RedisClient wrapper's kwarg is expiry= (not ex=).
        try:
            redis_client.set(f'direction:{symbol}', json.dumps(payload, default=str), expiry=15)
        except Exception as e:
            logger.warning(f"Direction Redis publish failed for {symbol}: {e}")

    def _publish_degraded(self, symbol: str, reason: str):
        """Publish a low-confidence NEUTRAL when real input data is missing."""
        self._publish(symbol, {
            'direction': 'NEUTRAL', 'confidence': 0.0,
            'degraded': True, 'reason': reason
        })
    
    def get_direction(self, symbol: str) -> Optional[Dict]:
        """Get cached direction for a symbol"""
        with self._lock:
            return self.direction_cache.get(symbol)
    
    def get_all_directions(self) -> Dict[str, Dict]:
        """Get all cached directions"""
        with self._lock:
            return self.direction_cache.copy()
    
    def get_status(self) -> Dict:
        """Get scheduler status"""
        return {
            'running': self.running,
            'last_updates': {
                symbol: update.isoformat() if update else None
                for symbol, update in self.last_update.items()
            },
            'cached_symbols': list(self.direction_cache.keys())
        }


# Singleton instance
direction_scheduler = DirectionScheduler()


def start_direction_scheduler():
    """Start the direction scheduler"""
    direction_scheduler.start()


def stop_direction_scheduler():
    """Stop the direction scheduler"""
    direction_scheduler.stop()


def get_market_direction(symbol: str) -> Optional[Dict]:
    """Get market direction for a symbol"""
    return direction_scheduler.get_direction(symbol)


def get_all_market_directions() -> Dict[str, Dict]:
    """Get all market directions"""
    return direction_scheduler.get_all_directions()


def get_cached_direction(symbol: str, max_age_seconds: int = 20) -> Optional[Dict]:
    """Read the latest direction from Redis (cross-process) so any API worker can
    serve what the scheduler process computed. Flags staleness via 'as_of'.
    Falls back to the in-process cache (same-process only)."""
    try:
        raw = redis_client.get(f'direction:{symbol}')
        if raw:
            data = json.loads(raw)
            as_of = data.get('as_of')
            if as_of:
                try:
                    age = (get_ist_now() - datetime.fromisoformat(as_of)).total_seconds()
                    data['stale'] = age > max_age_seconds
                    data['age_seconds'] = round(age, 1)
                except (ValueError, TypeError):
                    pass
            return data
    except Exception:
        pass
    return direction_scheduler.get_direction(symbol)
