"""
Timeframe Aggregator
Converts 1-minute candles to higher timeframes (5m, 15m, 30m, 60m)
Used by Market Direction Engine
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging
import pytz

logger = logging.getLogger(__name__)

# Define IST Timezone
IST_TZ = pytz.timezone('Asia/Kolkata')

class TimeframeAggregator:
    """
    Aggregates 1-minute candles to higher timeframes
    Supports: 5m, 15m, 30m, 60m
    """
    
    SUPPORTED_INTERVALS = {
        '1': 1,
        '5': 5,
        '15': 15,
        '30': 30,
        '60': 60
    }
    
    def __init__(self):
        self.cache: Dict[str, Dict[str, pd.DataFrame]] = {}  # symbol -> {interval -> df}
    
    def aggregate(self, df_1m: pd.DataFrame, target_interval: str) -> pd.DataFrame:
        """
        Aggregate 1-minute candles to target interval
        
        Args:
            df_1m: DataFrame with 1-minute OHLCV data
                   Must have columns: timestamp, open, high, low, close, volume
            target_interval: Target interval ('5', '15', '30', '60')
        
        Returns:
            DataFrame with aggregated OHLCV data
        """
        if target_interval == '1':
            return df_1m.copy()
        
        if target_interval not in self.SUPPORTED_INTERVALS:
            raise ValueError(f"Unsupported interval: {target_interval}")
        
        interval_minutes = self.SUPPORTED_INTERVALS[target_interval]
        
        try:
            # Ensure timestamp column exists and is proper format
            df = df_1m.copy()
            
            # --- FIX: Ensure Datetime is mapped to IST ---
            if 'timestamp' in df.columns:
                # 1. Convert Epoch to UTC-Aware Datetime
                # 2. Convert UTC to IST ('Asia/Kolkata')
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='s', utc=True).dt.tz_convert('Asia/Kolkata')
            elif 'datetime' in df.columns:
                # Fallback if only datetime string exists (Assume UTC string, convert to IST)
                df['datetime'] = pd.to_datetime(df['datetime'])
                if df['datetime'].dt.tz is None:
                    df['datetime'] = df['datetime'].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
                else:
                    df['datetime'] = df['datetime'].dt.tz_convert('Asia/Kolkata')
            else:
                raise ValueError("DataFrame must have 'timestamp' or 'datetime' column")
            
            # Set IST datetime as index
            df.set_index('datetime', inplace=True)
            
            # --- FIX: Resample logic using 'min' (deprecated 'T' removed) ---
            # label='left', closed='left' ensures 09:15:00 includes data from 09:15:00 to 09:19:59
            aggregated = df.resample(f'{interval_minutes}min', label='left', closed='left').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            
            # Reset index to get 'datetime' column back
            aggregated.reset_index(inplace=True)
            
            # Recalculate timestamp (Epoch is always UTC, but derived from our correct IST datetime)
            # .astype(np.int64) on a timezone-aware column returns UTC nanoseconds
            aggregated['timestamp'] = aggregated['datetime'].astype(np.int64) // 10**9
            
            return aggregated
            
        except Exception as e:
            logger.error(f"Aggregation error: {e}")
            return pd.DataFrame()
    
    def aggregate_all(self, df_1m: pd.DataFrame, symbol: str = "UNKNOWN") -> Dict[str, pd.DataFrame]:
        """
        Aggregate to all supported intervals
        
        Returns:
            Dict with keys '1', '5', '15', '30', '60' and DataFrame values
        """
        result = {
            '1': df_1m.copy(),
            '5': self.aggregate(df_1m, '5'),
            '15': self.aggregate(df_1m, '15'),
            '30': self.aggregate(df_1m, '30'),
            '60': self.aggregate(df_1m, '60')
        }
        
        # Cache results
        self.cache[symbol] = result
        
        return result
    
    def get_cached(self, symbol: str, interval: str) -> Optional[pd.DataFrame]:
        """Get cached aggregated data"""
        if symbol in self.cache and interval in self.cache[symbol]:
            return self.cache[symbol][interval]
        return None
    
    def clear_cache(self, symbol: str = None):
        """Clear cache for a symbol or all"""
        if symbol:
            self.cache.pop(symbol, None)
        else:
            self.cache.clear()


class LiveCandle:
    """
    Manages live candle formation from tick data
    """
    
    def __init__(self, interval_minutes: int = 1):
        self.interval = interval_minutes
        self.current_candle: Dict = None
        self.candle_start_time: datetime = None
    
    def update(self, price: float, volume: float = 0) -> Optional[Dict]:
        """
        Update with new tick data
        
        Returns:
            Completed candle dict if candle closed, None otherwise
        """
        # Get Current Time in IST
        now = datetime.now(IST_TZ)
        
        # Calculate candle start time (aligned to interval)
        # We perform math on the minutes to align (e.g., 9:17 -> 9:15 for 5m interval)
        candle_minute = (now.minute // self.interval) * self.interval
        candle_start = now.replace(minute=candle_minute, second=0, microsecond=0)
        
        # Check if we need to start a new candle
        if self.candle_start_time is None or candle_start > self.candle_start_time:
            # Save completed candle
            completed = self.current_candle.copy() if self.current_candle else None
            
            # Start new candle
            self.current_candle = {
                'timestamp': int(candle_start.timestamp()),
                'datetime': candle_start.isoformat(),
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': volume
            }
            self.candle_start_time = candle_start
            
            return completed
        
        # Update current candle
        if self.current_candle:
            self.current_candle['high'] = max(self.current_candle['high'], price)
            self.current_candle['low'] = min(self.current_candle['low'], price)
            self.current_candle['close'] = price
            self.current_candle['volume'] += volume
        
        return None
    
    def get_current(self) -> Optional[Dict]:
        """Get current forming candle"""
        return self.current_candle


class CandleBuffer:
    """
    Buffer for storing and managing historical candles
    Maintains rolling window of candles
    """
    
    def __init__(self, max_candles: int = 500):
        self.max_candles = max_candles
        self.candles: List[Dict] = []
    
    def add(self, candle: Dict):
        """Add a candle to the buffer"""
        self.candles.append(candle)
        
        # Trim if exceeds max
        if len(self.candles) > self.max_candles:
            self.candles = self.candles[-self.max_candles:]
    
    def get_dataframe(self) -> pd.DataFrame:
        """Convert buffer to DataFrame"""
        if not self.candles:
            return pd.DataFrame()
        return pd.DataFrame(self.candles)
    
    def get_last(self, n: int = 1) -> List[Dict]:
        """Get last N candles"""
        return self.candles[-n:]
    
    def clear(self):
        """Clear buffer"""
        self.candles = []


# Singleton instance
timeframe_aggregator = TimeframeAggregator()


def aggregate_to_timeframe(df_1m: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Convenience function for aggregation"""
    return timeframe_aggregator.aggregate(df_1m, interval)


def aggregate_all_timeframes(df_1m: pd.DataFrame, symbol: str = "UNKNOWN") -> Dict[str, pd.DataFrame]:
    """Convenience function for aggregating to all timeframes"""
    return timeframe_aggregator.aggregate_all(df_1m, symbol)