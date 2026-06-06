"""
Market Direction Engine - New Simplified Analysis System
Runs every 1 second to determine market direction and strength

Output:
- direction: UP / DOWN / NEUTRAL
- strength: 0-100

Components (Weights):
- 15m Trend: 35% (EMA 50/100, RSI Zone)
- 5m Structure: 25% (EMA 20/50, HH/LL)
- 1m Momentum: 20% (EMA 9/21, RSI Slope, Candle Strength)
- Live Volume: 10% (Volume Spike Detection)
- Price vs VWAP: 10% (Institutional Reference)
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class Direction(Enum):
    UP = "UP"
    DOWN = "DOWN"
    NEUTRAL = "NEUTRAL"


@dataclass
class DirectionResult:
    """Result from Market Direction Engine"""
    direction: str  # UP, DOWN, NEUTRAL
    strength: float  # 0-100
    
    # Component scores
    trend_15m_score: float
    trend_15m_direction: str
    structure_5m_score: float
    structure_5m_direction: str
    momentum_1m_score: float
    momentum_1m_direction: str
    volume_score: float
    volume_confirmed: bool
    vwap_score: float
    vwap_position: str  # ABOVE, BELOW, AT
    
    # Additional data
    ema_9: float
    ema_21: float
    ema_50: float
    ema_100: float
    rsi_14: float
    rsi_slope: float
    vwap: float
    current_price: float
    avg_volume: float
    current_volume: float
    
    # Structure
    recent_high: float
    recent_low: float
    swing_high: float
    swing_low: float
    structure_type: str  # HH_HL (bullish), LH_LL (bearish), RANGING
    
    # Metadata
    symbol: str
    timestamp: str
    
    def to_dict(self) -> Dict:
        return {
            'direction': self.direction,
            'strength': round(self.strength, 2),
            'components': {
                'trend_15m': {
                    'score': round(self.trend_15m_score, 2),
                    'direction': self.trend_15m_direction,
                    'weight': 35
                },
                'structure_5m': {
                    'score': round(self.structure_5m_score, 2),
                    'direction': self.structure_5m_direction,
                    'weight': 25
                },
                'momentum_1m': {
                    'score': round(self.momentum_1m_score, 2),
                    'direction': self.momentum_1m_direction,
                    'weight': 20
                },
                'volume': {
                    'score': round(self.volume_score, 2),
                    'confirmed': self.volume_confirmed,
                    'weight': 10
                },
                'vwap': {
                    'score': round(self.vwap_score, 2),
                    'position': self.vwap_position,
                    'weight': 10
                }
            },
            'indicators': {
                'ema_9': round(self.ema_9, 2) if self.ema_9 else None,
                'ema_21': round(self.ema_21, 2) if self.ema_21 else None,
                'ema_50': round(self.ema_50, 2) if self.ema_50 else None,
                'ema_100': round(self.ema_100, 2) if self.ema_100 else None,
                'rsi_14': round(self.rsi_14, 2) if self.rsi_14 else None,
                'rsi_slope': round(self.rsi_slope, 4) if self.rsi_slope else None,
                'vwap': round(self.vwap, 2) if self.vwap else None
            },
            'structure': {
                'type': self.structure_type,
                'recent_high': round(self.recent_high, 2) if self.recent_high else None,
                'recent_low': round(self.recent_low, 2) if self.recent_low else None,
                'swing_high': round(self.swing_high, 2) if self.swing_high else None,
                'swing_low': round(self.swing_low, 2) if self.swing_low else None
            },
            'volume_data': {
                'current': round(self.current_volume, 0) if self.current_volume else None,
                'average': round(self.avg_volume, 0) if self.avg_volume else None,
                'ratio': round(self.current_volume / self.avg_volume, 2) if self.avg_volume and self.current_volume else None
            },
            'current_price': round(self.current_price, 2) if self.current_price else None,
            'symbol': self.symbol,
            'timestamp': self.timestamp
        }


class MarketDirectionEngine:
    """
    New Market Direction Engine
    Simplified analysis using ~12 key indicators
    """
    
    # Component Weights
    WEIGHTS = {
        'trend_15m': 0.35,
        'structure_5m': 0.25,
        'momentum_1m': 0.20,
        'volume': 0.10,
        'vwap': 0.10
    }
    
    # RSI Zones
    RSI_OVERBOUGHT = 70
    RSI_OVERSOLD = 30
    RSI_BULLISH_ZONE = 50
    RSI_BEARISH_ZONE = 50
    
    def __init__(self):
        self.last_result: Optional[DirectionResult] = None
        self.result_cache: Dict[str, DirectionResult] = {}
    
    def analyze(self, 
                df_1m: pd.DataFrame, 
                df_5m: pd.DataFrame, 
                df_15m: pd.DataFrame,
                symbol: str = "UNKNOWN",
                live_ltp: float = None,
                live_volume: float = None) -> DirectionResult:
        """
        Main analysis method
        
        Args:
            df_1m: 1-minute candle DataFrame (at least 50 candles)
            df_5m: 5-minute candle DataFrame (at least 50 candles)
            df_15m: 15-minute candle DataFrame (at least 50 candles)
            symbol: Symbol being analyzed
            live_ltp: Live last traded price (optional)
            live_volume: Live volume (optional)
        """
        
        try:
            # Get current price
            current_price = live_ltp or float(df_1m['close'].iloc[-1])
            current_volume = live_volume or float(df_1m['volume'].iloc[-1])
            
            # 1. Calculate 15m Trend (35%)
            trend_15m_score, trend_15m_dir, ema_50, ema_100, rsi_14 = self._analyze_15m_trend(df_15m, current_price)
            
            # 2. Calculate 5m Structure (25%)
            structure_5m_score, structure_5m_dir, ema_20_5m, ema_50_5m, structure_type, swing_high, swing_low = self._analyze_5m_structure(df_5m, current_price)
            
            # 3. Calculate 1m Momentum (20%)
            momentum_1m_score, momentum_1m_dir, ema_9, ema_21, rsi_slope, candle_strength = self._analyze_1m_momentum(df_1m, current_price)
            
            # 4. Calculate Volume Score (10%)
            volume_score, volume_confirmed, avg_volume = self._analyze_volume(df_1m, current_volume)
            
            # 5. Calculate VWAP Score (10%)
            vwap_score, vwap_position, vwap = self._analyze_vwap(df_5m, current_price)
            
            # 6. Calculate Weighted Direction & Strength
            direction, strength = self._calculate_final_signal(
                trend_15m_score, trend_15m_dir,
                structure_5m_score, structure_5m_dir,
                momentum_1m_score, momentum_1m_dir,
                volume_score, volume_confirmed,
                vwap_score, vwap_position
            )
            
            # Recent high/low from 5m structure
            recent_high = float(df_5m['high'].iloc[-5:].max())
            recent_low = float(df_5m['low'].iloc[-5:].min())
            
            result = DirectionResult(
                direction=direction,
                strength=strength,
                trend_15m_score=trend_15m_score,
                trend_15m_direction=trend_15m_dir,
                structure_5m_score=structure_5m_score,
                structure_5m_direction=structure_5m_dir,
                momentum_1m_score=momentum_1m_score,
                momentum_1m_direction=momentum_1m_dir,
                volume_score=volume_score,
                volume_confirmed=volume_confirmed,
                vwap_score=vwap_score,
                vwap_position=vwap_position,
                ema_9=ema_9,
                ema_21=ema_21,
                ema_50=ema_50,
                ema_100=ema_100,
                rsi_14=rsi_14,
                rsi_slope=rsi_slope,
                vwap=vwap,
                current_price=current_price,
                avg_volume=avg_volume,
                current_volume=current_volume,
                recent_high=recent_high,
                recent_low=recent_low,
                swing_high=swing_high,
                swing_low=swing_low,
                structure_type=structure_type,
                symbol=symbol,
                timestamp=datetime.now().isoformat()
            )
            
            self.last_result = result
            self.result_cache[symbol] = result
            
            return result
            
        except Exception as e:
            logger.error(f"Market Direction Engine error: {e}")
            return self._empty_result(symbol, str(e))
    
    def _analyze_15m_trend(self, df: pd.DataFrame, current_price: float) -> Tuple[float, str, float, float, float]:
        """
        Analyze 15-minute trend using EMA 50/100 and RSI Zone
        Returns: (score 0-100, direction, ema_50, ema_100, rsi_14)
        """
        if len(df) < 100:
            return 50.0, "NEUTRAL", 0, 0, 50
        
        close = df['close'].values
        
        # Calculate EMAs using Wilder's smoothing
        ema_50 = self._ema(close, 50)
        ema_100 = self._ema(close, 100)
        
        # Calculate RSI
        rsi_14 = self._rsi(close, 14)
        
        # Score calculation
        score = 50.0
        direction = "NEUTRAL"
        
        # EMA alignment score (0-50 points)
        if current_price > ema_50 > ema_100:
            # Strong uptrend
            score += 40
            direction = "UP"
        elif current_price > ema_50:
            # Above short EMA
            score += 20
            direction = "UP"
        elif current_price < ema_50 < ema_100:
            # Strong downtrend
            score -= 40
            direction = "DOWN"
        elif current_price < ema_50:
            # Below short EMA
            score -= 20
            direction = "DOWN"
        
        # RSI zone adjustment (0-30 points)
        if rsi_14 > 60:
            score += min((rsi_14 - 50) * 0.6, 30)  # Bullish RSI
            if direction == "NEUTRAL":
                direction = "UP"
        elif rsi_14 < 40:
            score -= min((50 - rsi_14) * 0.6, 30)  # Bearish RSI
            if direction == "NEUTRAL":
                direction = "DOWN"
        
        # EMA slope (0-20 points)
        ema_50_slope = (ema_50 - self._ema(close[:-5], 50)) / max(ema_50, 1) * 100
        if ema_50_slope > 0.1:
            score += min(ema_50_slope * 50, 20)
        elif ema_50_slope < -0.1:
            score -= min(abs(ema_50_slope) * 50, 20)
        
        # Clamp score
        score = max(0, min(100, score))
        
        return score, direction, ema_50, ema_100, rsi_14
    
    def _analyze_5m_structure(self, df: pd.DataFrame, current_price: float) -> Tuple[float, str, float, float, str, float, float]:
        """
        Analyze 5-minute structure using EMA 20/50 and HH/HL patterns
        Returns: (score, direction, ema_20, ema_50, structure_type, swing_high, swing_low)
        """
        if len(df) < 50:
            return 50.0, "NEUTRAL", 0, 0, "RANGING", 0, 0
        
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        # Calculate EMAs
        ema_20 = self._ema(close, 20)
        ema_50 = self._ema(close, 50)
        
        # Detect swing points (last 20 candles)
        swing_highs = []
        swing_lows = []
        
        for i in range(2, min(20, len(df) - 2)):
            idx = -i
            if high[idx] > high[idx-1] and high[idx] > high[idx+1]:
                swing_highs.append((idx, high[idx]))
            if low[idx] < low[idx-1] and low[idx] < low[idx+1]:
                swing_lows.append((idx, low[idx]))
        
        # Determine structure type
        structure_type = "RANGING"
        swing_high = max([sh[1] for sh in swing_highs]) if swing_highs else float(df['high'].iloc[-20:].max())
        swing_low = min([sl[1] for sl in swing_lows]) if swing_lows else float(df['low'].iloc[-20:].min())
        
        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            # Check for HH/HL (bullish) or LH/LL (bearish)
            recent_highs = sorted(swing_highs, key=lambda x: x[0])[-2:]
            recent_lows = sorted(swing_lows, key=lambda x: x[0])[-2:]
            
            hh = recent_highs[-1][1] > recent_highs[-2][1] if len(recent_highs) >= 2 else False
            hl = recent_lows[-1][1] > recent_lows[-2][1] if len(recent_lows) >= 2 else False
            lh = recent_highs[-1][1] < recent_highs[-2][1] if len(recent_highs) >= 2 else False
            ll = recent_lows[-1][1] < recent_lows[-2][1] if len(recent_lows) >= 2 else False
            
            if hh and hl:
                structure_type = "HH_HL"  # Bullish
            elif lh and ll:
                structure_type = "LH_LL"  # Bearish
        
        # Score calculation
        score = 50.0
        direction = "NEUTRAL"
        
        # EMA alignment (0-40 points)
        if current_price > ema_20 > ema_50:
            score += 35
            direction = "UP"
        elif current_price > ema_20:
            score += 15
            direction = "UP"
        elif current_price < ema_20 < ema_50:
            score -= 35
            direction = "DOWN"
        elif current_price < ema_20:
            score -= 15
            direction = "DOWN"
        
        # Structure adjustment (0-30 points)
        if structure_type == "HH_HL":
            score += 25
            if direction == "NEUTRAL":
                direction = "UP"
        elif structure_type == "LH_LL":
            score -= 25
            if direction == "NEUTRAL":
                direction = "DOWN"
        
        # Price position in range (0-20 points)
        range_size = swing_high - swing_low
        if range_size > 0:
            position = (current_price - swing_low) / range_size
            if position > 0.7:
                score += 15  # Near highs
            elif position < 0.3:
                score -= 15  # Near lows
        
        score = max(0, min(100, score))
        
        return score, direction, ema_20, ema_50, structure_type, swing_high, swing_low
    
    def _analyze_1m_momentum(self, df: pd.DataFrame, current_price: float) -> Tuple[float, str, float, float, float, float]:
        """
        Analyze 1-minute momentum using EMA 9/21, RSI slope, and candle strength
        Returns: (score, direction, ema_9, ema_21, rsi_slope, candle_strength)
        """
        if len(df) < 25:
            return 50.0, "NEUTRAL", 0, 0, 0, 0
        
        close = df['close'].values
        open_price = df['open'].values
        high = df['high'].values
        low = df['low'].values
        
        # Calculate EMAs
        ema_9 = self._ema(close, 9)
        ema_21 = self._ema(close, 21)
        
        # Calculate RSI and its slope
        rsi_values = [self._rsi(close[:i+1], 14) for i in range(max(len(close)-5, 14), len(close))]
        rsi_current = rsi_values[-1] if rsi_values else 50
        rsi_slope = (rsi_values[-1] - rsi_values[0]) / len(rsi_values) if len(rsi_values) > 1 else 0
        
        # Calculate candle body strength (last 5 candles)
        body_strengths = []
        for i in range(-5, 0):
            body = close[i] - open_price[i]
            range_size = high[i] - low[i]
            if range_size > 0:
                strength = body / range_size
                body_strengths.append(strength)
        
        candle_strength = np.mean(body_strengths) if body_strengths else 0
        
        # Score calculation
        score = 50.0
        direction = "NEUTRAL"
        
        # EMA crossover (0-40 points)
        if current_price > ema_9 > ema_21:
            score += 35
            direction = "UP"
        elif current_price > ema_9:
            score += 15
            direction = "UP"
        elif current_price < ema_9 < ema_21:
            score -= 35
            direction = "DOWN"
        elif current_price < ema_9:
            score -= 15
            direction = "DOWN"
        
        # RSI slope (0-30 points)
        if rsi_slope > 0.5:
            score += min(rsi_slope * 20, 25)
        elif rsi_slope < -0.5:
            score -= min(abs(rsi_slope) * 20, 25)
        
        # Candle strength (0-20 points)
        if candle_strength > 0.3:
            score += min(candle_strength * 30, 20)
        elif candle_strength < -0.3:
            score -= min(abs(candle_strength) * 30, 20)
        
        score = max(0, min(100, score))
        
        return score, direction, ema_9, ema_21, rsi_slope, candle_strength
    
    def _analyze_volume(self, df: pd.DataFrame, current_volume: float) -> Tuple[float, bool, float]:
        """
        Analyze volume spike
        Returns: (score, confirmed, avg_volume)
        """
        if len(df) < 20:
            return 50.0, False, 0
        
        volume = df['volume'].values
        avg_volume = np.mean(volume[-20:])
        
        if avg_volume == 0:
            return 50.0, False, 0
        
        volume_ratio = current_volume / avg_volume
        
        # Score based on volume ratio
        score = 50.0
        if volume_ratio > 1.5:
            score = min(50 + (volume_ratio - 1) * 25, 100)
        elif volume_ratio < 0.5:
            score = max(50 - (1 - volume_ratio) * 25, 0)
        
        confirmed = volume_ratio > 1.2
        
        return score, confirmed, avg_volume
    
    def _current_session_slice(self, df: pd.DataFrame) -> pd.DataFrame:
        """Rows belonging to the current IST trading session (>= today 09:15 IST).
        Used to reset cumulative intraday stats (e.g. VWAP) at each session."""
        try:
            if 'timestamp' in df.columns:
                from utils.time_utils import get_ist_now
                open_ist = get_ist_now().replace(hour=9, minute=15, second=0, microsecond=0)
                session_start = int(open_ist.timestamp())
                return df[df['timestamp'] >= session_start]
        except Exception:
            pass
        return df

    def _analyze_vwap(self, df: pd.DataFrame, current_price: float) -> Tuple[float, str, float]:
        """
        Analyze price position relative to VWAP (session-anchored).
        Returns: (score, position, vwap)
        """
        if len(df) < 10:
            return 50.0, "AT", current_price

        # Anchor VWAP to the current IST session. A cumulative VWAP that spans
        # multiple trading days is meaningless as an intraday reference.
        sdf = self._current_session_slice(df)
        if len(sdf) < 3:
            sdf = df  # too early in the session; use available rows

        # Calculate session VWAP
        typical_price = (sdf['high'] + sdf['low'] + sdf['close']) / 3
        volume = sdf['volume']

        cum_tp_vol = (typical_price * volume).cumsum()
        cum_vol = volume.cumsum()

        vwap = float(cum_tp_vol.iloc[-1] / cum_vol.iloc[-1]) if cum_vol.iloc[-1] > 0 else current_price
        
        # Score based on price vs VWAP
        score = 50.0
        position = "AT"
        
        diff_percent = (current_price - vwap) / vwap * 100 if vwap > 0 else 0
        
        if diff_percent > 0.2:
            score = min(50 + diff_percent * 15, 100)
            position = "ABOVE"
        elif diff_percent < -0.2:
            score = max(50 + diff_percent * 15, 0)
            position = "BELOW"
        
        return score, position, vwap
    
    def _calculate_final_signal(self, 
                                trend_score: float, trend_dir: str,
                                structure_score: float, structure_dir: str,
                                momentum_score: float, momentum_dir: str,
                                volume_score: float, volume_confirmed: bool,
                                vwap_score: float, vwap_position: str) -> Tuple[str, float]:
        """
        Calculate final direction and strength from all components
        """
        # Weighted score calculation
        weighted_score = (
            trend_score * self.WEIGHTS['trend_15m'] +
            structure_score * self.WEIGHTS['structure_5m'] +
            momentum_score * self.WEIGHTS['momentum_1m'] +
            volume_score * self.WEIGHTS['volume'] +
            vwap_score * self.WEIGHTS['vwap']
        )
        
        # Direction consensus
        directions = [trend_dir, structure_dir, momentum_dir]
        up_count = directions.count("UP")
        down_count = directions.count("DOWN")
        
        # VWAP alignment bonus
        if vwap_position == "ABOVE" and up_count > down_count:
            weighted_score += 5
        elif vwap_position == "BELOW" and down_count > up_count:
            weighted_score += 5
        
        # Volume confirmation bonus
        if volume_confirmed:
            weighted_score += 5
        
        # Determine final direction
        if weighted_score >= 60:
            direction = "UP"
        elif weighted_score <= 40:
            direction = "DOWN"
        else:
            direction = "NEUTRAL"
        
        # Convert score to strength (0-100)
        if direction == "UP":
            strength = min(weighted_score, 100)
        elif direction == "DOWN":
            strength = min(100 - weighted_score, 100)
        else:
            strength = 50 - abs(50 - weighted_score)
        
        return direction, strength
    
    def _ema(self, data: np.ndarray, period: int) -> float:
        """Calculate EMA using Wilder's smoothing"""
        if len(data) < period:
            return float(np.mean(data))
        
        alpha = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = alpha * price + (1 - alpha) * ema
        return float(ema)
    
    def _rsi(self, data: np.ndarray, period: int = 14) -> float:
        """Calculate RSI using Wilder's smoothing"""
        if len(data) < period + 1:
            return 50.0
        
        deltas = np.diff(data)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        # Wilder's smoothing
        alpha = 1 / period
        avg_gain = gains[0]
        avg_loss = losses[0]
        
        for i in range(1, len(gains)):
            avg_gain = alpha * gains[i] + (1 - alpha) * avg_gain
            avg_loss = alpha * losses[i] + (1 - alpha) * avg_loss
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi)
    
    def _empty_result(self, symbol: str, error: str = None) -> DirectionResult:
        """Return empty/neutral result"""
        return DirectionResult(
            direction="NEUTRAL",
            strength=50.0,
            trend_15m_score=50.0,
            trend_15m_direction="NEUTRAL",
            structure_5m_score=50.0,
            structure_5m_direction="NEUTRAL",
            momentum_1m_score=50.0,
            momentum_1m_direction="NEUTRAL",
            volume_score=50.0,
            volume_confirmed=False,
            vwap_score=50.0,
            vwap_position="AT",
            ema_9=0,
            ema_21=0,
            ema_50=0,
            ema_100=0,
            rsi_14=50,
            rsi_slope=0,
            vwap=0,
            current_price=0,
            avg_volume=0,
            current_volume=0,
            recent_high=0,
            recent_low=0,
            swing_high=0,
            swing_low=0,
            structure_type="RANGING",
            symbol=symbol,
            timestamp=datetime.now().isoformat()
        )
    
    def get_cached_result(self, symbol: str) -> Optional[DirectionResult]:
        """Get cached result for a symbol"""
        return self.result_cache.get(symbol)


# Singleton instance
market_direction_engine = MarketDirectionEngine()


def analyze_direction(df_1m: pd.DataFrame, 
                      df_5m: pd.DataFrame, 
                      df_15m: pd.DataFrame,
                      symbol: str = "UNKNOWN",
                      live_ltp: float = None,
                      live_volume: float = None) -> Dict:
    """Convenience function for analyzing market direction"""
    result = market_direction_engine.analyze(df_1m, df_5m, df_15m, symbol, live_ltp, live_volume)
    return result.to_dict()


def get_direction(symbol: str) -> Optional[Dict]:
    """Get cached direction for a symbol"""
    result = market_direction_engine.get_cached_result(symbol)
    return result.to_dict() if result else None
