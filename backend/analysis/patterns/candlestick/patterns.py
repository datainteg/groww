"""
Candlestick Patterns - 7 Patterns
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional


def detect_doji(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Doji pattern (Indecision/Reversal)"""
    if len(df) < 5:
        return None
    
    row = df.iloc[-1]
    body = abs(row['close'] - row['open'])
    total_range = row['high'] - row['low']
    
    if total_range == 0:
        return None
    
    body_ratio = body / total_range
    
    # Doji: body is very small compared to range
    if body_ratio < 0.1:
        # Determine signal from prior trend
        prior_trend = df['close'].iloc[-5] - df['close'].iloc[-1]
        signal = "BULLISH" if prior_trend < 0 else "BEARISH"
        
        return {
            "pattern": "doji",
            "signal": signal,
            "confidence": 0.55,
            "entry": row['close'],
            "target": row['close'] * (1.015 if signal == "BULLISH" else 0.985),
            "stop_loss": row['low'] if signal == "BULLISH" else row['high'],
            "details": {"body_ratio": body_ratio}
        }
    return None


def detect_bullish_engulfing(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Bullish Engulfing pattern"""
    if len(df) < 3:
        return None
    
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    
    # Previous candle is bearish
    prev_bearish = prev['close'] < prev['open']
    # Current candle is bullish
    curr_bullish = curr['close'] > curr['open']
    # Current body engulfs previous body
    engulfs = curr['open'] < prev['close'] and curr['close'] > prev['open']
    
    if prev_bearish and curr_bullish and engulfs:
        return {
            "pattern": "bullish_engulfing",
            "signal": "BULLISH",
            "confidence": 0.72,
            "entry": curr['close'],
            "target": curr['close'] + (curr['close'] - curr['open']),
            "stop_loss": min(curr['low'], prev['low']),
            "details": {"prev_body": prev['open'] - prev['close'], "curr_body": curr['close'] - curr['open']}
        }
    return None


def detect_bearish_engulfing(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Bearish Engulfing pattern"""
    if len(df) < 3:
        return None
    
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    
    prev_bullish = prev['close'] > prev['open']
    curr_bearish = curr['close'] < curr['open']
    engulfs = curr['open'] > prev['close'] and curr['close'] < prev['open']
    
    if prev_bullish and curr_bearish and engulfs:
        return {
            "pattern": "bearish_engulfing",
            "signal": "BEARISH",
            "confidence": 0.72,
            "entry": curr['close'],
            "target": curr['close'] - (curr['open'] - curr['close']),
            "stop_loss": max(curr['high'], prev['high']),
            "details": {"prev_body": prev['close'] - prev['open'], "curr_body": curr['open'] - curr['close']}
        }
    return None


def detect_hammer(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Hammer pattern (Bullish reversal)"""
    if len(df) < 5:
        return None
    
    row = df.iloc[-1]
    body = abs(row['close'] - row['open'])
    lower_wick = min(row['open'], row['close']) - row['low']
    upper_wick = row['high'] - max(row['open'], row['close'])
    total_range = row['high'] - row['low']
    
    if total_range == 0 or body == 0:
        return None
    
    # Hammer: long lower wick, small upper wick, small body
    # Lower wick at least 2x body, upper wick less than body
    if lower_wick >= 2 * body and upper_wick < body:
        # Must be in downtrend
        prior_trend = df['close'].iloc[-10:-1].mean() - df['close'].iloc[-1]
        if prior_trend > 0:
            return {
                "pattern": "hammer",
                "signal": "BULLISH",
                "confidence": 0.68,
                "entry": row['close'],
                "target": row['close'] + total_range,
                "stop_loss": row['low'] * 0.995,
                "details": {"lower_wick_ratio": lower_wick / body}
            }
    return None


def detect_hanging_man(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Hanging Man pattern (Bearish reversal)"""
    if len(df) < 5:
        return None
    
    row = df.iloc[-1]
    body = abs(row['close'] - row['open'])
    lower_wick = min(row['open'], row['close']) - row['low']
    upper_wick = row['high'] - max(row['open'], row['close'])
    total_range = row['high'] - row['low']
    
    if total_range == 0 or body == 0:
        return None
    
    # Same shape as hammer but in uptrend
    if lower_wick >= 2 * body and upper_wick < body:
        prior_trend = df['close'].iloc[-1] - df['close'].iloc[-10:-1].mean()
        if prior_trend > 0:
            return {
                "pattern": "hanging_man",
                "signal": "BEARISH",
                "confidence": 0.65,
                "entry": row['close'],
                "target": row['close'] - total_range,
                "stop_loss": row['high'] * 1.005,
                "details": {"lower_wick_ratio": lower_wick / body}
            }
    return None


def detect_morning_star(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Morning Star pattern (Bullish reversal) - 3 candle pattern"""
    if len(df) < 5:
        return None
    
    first = df.iloc[-3]
    second = df.iloc[-2]
    third = df.iloc[-1]
    
    # First: large bearish candle
    first_bearish = first['close'] < first['open']
    first_body = first['open'] - first['close']
    
    # Second: small body (star) that gaps down
    second_body = abs(second['close'] - second['open'])
    second_small = second_body < first_body * 0.3
    second_gaps = max(second['open'], second['close']) < first['close']
    
    # Third: large bullish candle that closes above first's midpoint
    third_bullish = third['close'] > third['open']
    third_body = third['close'] - third['open']
    first_midpoint = (first['open'] + first['close']) / 2
    third_closes_high = third['close'] > first_midpoint
    
    if first_bearish and second_small and third_bullish and third_closes_high:
        return {
            "pattern": "morning_star",
            "signal": "BULLISH",
            "confidence": 0.75,
            "entry": third['close'],
            "target": third['close'] + first_body,
            "stop_loss": second['low'] * 0.995,
            "details": {"gap_down": second_gaps}
        }
    return None


def detect_evening_star(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Evening Star pattern (Bearish reversal) - 3 candle pattern"""
    if len(df) < 5:
        return None
    
    first = df.iloc[-3]
    second = df.iloc[-2]
    third = df.iloc[-1]
    
    # First: large bullish candle
    first_bullish = first['close'] > first['open']
    first_body = first['close'] - first['open']
    
    # Second: small body (star) that gaps up
    second_body = abs(second['close'] - second['open'])
    second_small = second_body < first_body * 0.3
    second_gaps = min(second['open'], second['close']) > first['close']
    
    # Third: large bearish candle that closes below first's midpoint
    third_bearish = third['close'] < third['open']
    first_midpoint = (first['open'] + first['close']) / 2
    third_closes_low = third['close'] < first_midpoint
    
    if first_bullish and second_small and third_bearish and third_closes_low:
        return {
            "pattern": "evening_star",
            "signal": "BEARISH",
            "confidence": 0.75,
            "entry": third['close'],
            "target": third['close'] - first_body,
            "stop_loss": second['high'] * 1.005,
            "details": {"gap_up": second_gaps}
        }
    return None


def detect_all_candlestick(df: pd.DataFrame) -> list:
    """Run all candlestick pattern detections"""
    patterns = []
    
    detectors = [
        detect_doji,
        detect_bullish_engulfing,
        detect_bearish_engulfing,
        detect_hammer,
        detect_hanging_man,
        detect_morning_star,
        detect_evening_star
    ]
    
    for detector in detectors:
        try:
            result = detector(df)
            if result:
                patterns.append(result)
        except Exception:
            continue
    
    return patterns
