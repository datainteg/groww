"""
Primary Chart Patterns - 13 Patterns
Each has detect(df) -> dict | None
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional


# ==================== HEAD AND SHOULDERS ====================
def detect_head_shoulders(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Head and Shoulders pattern (Bearish)"""
    if len(df) < 50:
        return None
    
    close = df['close'].values
    high = df['high'].values
    
    # Find peaks
    peaks = []
    for i in range(5, len(high) - 5):
        if high[i] == max(high[i-5:i+6]):
            peaks.append((i, high[i]))
    
    if len(peaks) < 3:
        return None
    
    # Check last 3 peaks for H&S pattern
    for i in range(len(peaks) - 3, -1, -1):
        left_shoulder = peaks[i]
        head = peaks[i + 1]
        right_shoulder = peaks[i + 2]
        
        # Head must be highest
        if head[1] > left_shoulder[1] and head[1] > right_shoulder[1]:
            # Shoulders roughly equal (within 3%)
            shoulder_diff = abs(left_shoulder[1] - right_shoulder[1]) / left_shoulder[1]
            if shoulder_diff < 0.03:
                # Calculate neckline
                neckline = min(close[left_shoulder[0]:right_shoulder[0]])
                target = neckline - (head[1] - neckline)
                
                return {
                    "pattern": "head_shoulders",
                    "signal": "BEARISH",
                    "confidence": 0.75 + (1 - shoulder_diff) * 0.1,
                    "entry": close[-1],
                    "target": target,
                    "stop_loss": head[1] * 1.01,
                    "details": {
                        "left_shoulder": left_shoulder[1],
                        "head": head[1],
                        "right_shoulder": right_shoulder[1],
                        "neckline": neckline
                    }
                }
    return None


# ==================== INVERSE HEAD AND SHOULDERS ====================
def detect_inverse_head_shoulders(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Inverse Head and Shoulders pattern (Bullish)"""
    if len(df) < 50:
        return None
    
    close = df['close'].values
    low = df['low'].values
    
    # Find troughs
    troughs = []
    for i in range(5, len(low) - 5):
        if low[i] == min(low[i-5:i+6]):
            troughs.append((i, low[i]))
    
    if len(troughs) < 3:
        return None
    
    for i in range(len(troughs) - 3, -1, -1):
        left_shoulder = troughs[i]
        head = troughs[i + 1]
        right_shoulder = troughs[i + 2]
        
        # Head must be lowest
        if head[1] < left_shoulder[1] and head[1] < right_shoulder[1]:
            shoulder_diff = abs(left_shoulder[1] - right_shoulder[1]) / left_shoulder[1]
            if shoulder_diff < 0.03:
                neckline = max(close[left_shoulder[0]:right_shoulder[0]])
                target = neckline + (neckline - head[1])
                
                return {
                    "pattern": "inverse_head_shoulders",
                    "signal": "BULLISH",
                    "confidence": 0.75 + (1 - shoulder_diff) * 0.1,
                    "entry": close[-1],
                    "target": target,
                    "stop_loss": head[1] * 0.99,
                    "details": {
                        "left_shoulder": left_shoulder[1],
                        "head": head[1],
                        "right_shoulder": right_shoulder[1],
                        "neckline": neckline
                    }
                }
    return None


# ==================== DOUBLE TOP ====================
def detect_double_top(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Double Top pattern (Bearish)"""
    if len(df) < 30:
        return None
    
    close = df['close'].values
    high = df['high'].values
    
    peaks = []
    for i in range(3, len(high) - 3):
        if high[i] == max(high[i-3:i+4]):
            peaks.append((i, high[i]))
    
    if len(peaks) < 2:
        return None
    
    # Check last 2 peaks
    peak1 = peaks[-2]
    peak2 = peaks[-1]
    
    # Peaks must be similar height (within 2%)
    if abs(peak1[1] - peak2[1]) / peak1[1] < 0.02:
        # At least 10 bars apart
        if peak2[0] - peak1[0] >= 10:
            neckline = min(close[peak1[0]:peak2[0]])
            height = peak1[1] - neckline
            target = neckline - height
            
            return {
                "pattern": "double_top",
                "signal": "BEARISH",
                "confidence": 0.72,
                "entry": close[-1],
                "target": target,
                "stop_loss": max(peak1[1], peak2[1]) * 1.01,
                "details": {"top1": peak1[1], "top2": peak2[1], "neckline": neckline}
            }
    return None


# ==================== DOUBLE BOTTOM ====================
def detect_double_bottom(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Double Bottom pattern (Bullish)"""
    if len(df) < 30:
        return None
    
    close = df['close'].values
    low = df['low'].values
    
    troughs = []
    for i in range(3, len(low) - 3):
        if low[i] == min(low[i-3:i+4]):
            troughs.append((i, low[i]))
    
    if len(troughs) < 2:
        return None
    
    trough1 = troughs[-2]
    trough2 = troughs[-1]
    
    if abs(trough1[1] - trough2[1]) / trough1[1] < 0.02:
        if trough2[0] - trough1[0] >= 10:
            neckline = max(close[trough1[0]:trough2[0]])
            height = neckline - trough1[1]
            target = neckline + height
            
            return {
                "pattern": "double_bottom",
                "signal": "BULLISH",
                "confidence": 0.72,
                "entry": close[-1],
                "target": target,
                "stop_loss": min(trough1[1], trough2[1]) * 0.99,
                "details": {"bottom1": trough1[1], "bottom2": trough2[1], "neckline": neckline}
            }
    return None


# ==================== FLAG ====================
def detect_flag(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Flag pattern (Continuation)"""
    if len(df) < 25:
        return None
    
    close = df['close'].values
    
    # Check for strong prior move (flagpole)
    lookback = 15
    recent = close[-10:]
    prior = close[-25:-10]
    
    prior_move = (prior[-1] - prior[0]) / prior[0]
    recent_range = (max(recent) - min(recent)) / np.mean(recent)
    
    # Bullish flag: strong up move, then consolidation
    if prior_move > 0.03 and recent_range < 0.02:
        return {
            "pattern": "bull_flag",
            "signal": "BULLISH",
            "confidence": 0.68,
            "entry": close[-1],
            "target": close[-1] + (prior[-1] - prior[0]),
            "stop_loss": min(recent) * 0.99,
            "details": {"flagpole_move": prior_move, "consolidation_range": recent_range}
        }
    
    # Bearish flag
    if prior_move < -0.03 and recent_range < 0.02:
        return {
            "pattern": "bear_flag",
            "signal": "BEARISH",
            "confidence": 0.68,
            "entry": close[-1],
            "target": close[-1] - abs(prior[-1] - prior[0]),
            "stop_loss": max(recent) * 1.01,
            "details": {"flagpole_move": prior_move, "consolidation_range": recent_range}
        }
    return None


# ==================== PENNANT ====================
def detect_pennant(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Pennant pattern (Continuation)"""
    if len(df) < 25:
        return None
    
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    
    prior_move = (close[-15] - close[-25]) / close[-25]
    
    # Check for converging highs and lows
    recent_high = high[-10:]
    recent_low = low[-10:]
    
    high_slope = (recent_high[-1] - recent_high[0]) / 10
    low_slope = (recent_low[-1] - recent_low[0]) / 10
    
    # Converging (high going down, low going up)
    if high_slope < 0 and low_slope > 0:
        if prior_move > 0.03:
            return {
                "pattern": "bull_pennant",
                "signal": "BULLISH",
                "confidence": 0.65,
                "entry": close[-1],
                "target": close[-1] + abs(close[-15] - close[-25]),
                "stop_loss": min(recent_low) * 0.99,
                "details": {"prior_move": prior_move}
            }
        elif prior_move < -0.03:
            return {
                "pattern": "bear_pennant",
                "signal": "BEARISH",
                "confidence": 0.65,
                "entry": close[-1],
                "target": close[-1] - abs(close[-15] - close[-25]),
                "stop_loss": max(recent_high) * 1.01,
                "details": {"prior_move": prior_move}
            }
    return None


# ==================== ASCENDING TRIANGLE ====================
def detect_ascending_triangle(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Ascending Triangle (Bullish)"""
    if len(df) < 30:
        return None
    
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    
    recent_high = high[-20:]
    recent_low = low[-20:]
    
    # Flat resistance (high values similar)
    resistance_std = np.std(recent_high) / np.mean(recent_high)
    
    # Rising support (lows increasing)
    low_slope = np.polyfit(range(len(recent_low)), recent_low, 1)[0]
    
    if resistance_std < 0.01 and low_slope > 0:
        resistance = np.mean(recent_high)
        return {
            "pattern": "ascending_triangle",
            "signal": "BULLISH",
            "confidence": 0.70,
            "entry": close[-1],
            "target": resistance + (resistance - min(recent_low)),
            "stop_loss": min(recent_low) * 0.99,
            "details": {"resistance": resistance, "support_slope": low_slope}
        }
    return None


# ==================== DESCENDING TRIANGLE ====================
def detect_descending_triangle(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Descending Triangle (Bearish)"""
    if len(df) < 30:
        return None
    
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    
    recent_high = high[-20:]
    recent_low = low[-20:]
    
    support_std = np.std(recent_low) / np.mean(recent_low)
    high_slope = np.polyfit(range(len(recent_high)), recent_high, 1)[0]
    
    if support_std < 0.01 and high_slope < 0:
        support = np.mean(recent_low)
        return {
            "pattern": "descending_triangle",
            "signal": "BEARISH",
            "confidence": 0.70,
            "entry": close[-1],
            "target": support - (max(recent_high) - support),
            "stop_loss": max(recent_high) * 1.01,
            "details": {"support": support, "resistance_slope": high_slope}
        }
    return None


# ==================== SYMMETRICAL TRIANGLE ====================
def detect_symmetrical_triangle(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Symmetrical Triangle (Neutral - direction depends on breakout)"""
    if len(df) < 30:
        return None
    
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    
    recent_high = high[-20:]
    recent_low = low[-20:]
    
    high_slope = np.polyfit(range(len(recent_high)), recent_high, 1)[0]
    low_slope = np.polyfit(range(len(recent_low)), recent_low, 1)[0]
    
    # Converging (high going down, low going up)
    if high_slope < -0.001 and low_slope > 0.001:
        # Determine bias from prior trend
        prior_trend = close[-30] - close[-50] if len(close) >= 50 else 0
        signal = "BULLISH" if prior_trend > 0 else "BEARISH"
        
        return {
            "pattern": "symmetrical_triangle",
            "signal": signal,
            "confidence": 0.60,
            "entry": close[-1],
            "target": close[-1] * (1.03 if signal == "BULLISH" else 0.97),
            "stop_loss": close[-1] * (0.98 if signal == "BULLISH" else 1.02),
            "details": {"high_slope": high_slope, "low_slope": low_slope}
        }
    return None


# ==================== RISING WEDGE ====================
def detect_rising_wedge(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Rising Wedge (Bearish)"""
    if len(df) < 30:
        return None
    
    high = df['high'].values[-25:]
    low = df['low'].values[-25:]
    close = df['close'].values
    
    high_slope = np.polyfit(range(len(high)), high, 1)[0]
    low_slope = np.polyfit(range(len(low)), low, 1)[0]
    
    # Both rising but converging (low rising faster)
    if high_slope > 0 and low_slope > 0 and low_slope > high_slope:
        return {
            "pattern": "rising_wedge",
            "signal": "BEARISH",
            "confidence": 0.68,
            "entry": close[-1],
            "target": min(low),
            "stop_loss": max(high) * 1.01,
            "details": {"high_slope": high_slope, "low_slope": low_slope}
        }
    return None


# ==================== FALLING WEDGE ====================
def detect_falling_wedge(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Falling Wedge (Bullish)"""
    if len(df) < 30:
        return None
    
    high = df['high'].values[-25:]
    low = df['low'].values[-25:]
    close = df['close'].values
    
    high_slope = np.polyfit(range(len(high)), high, 1)[0]
    low_slope = np.polyfit(range(len(low)), low, 1)[0]
    
    # Both falling but converging (high falling faster)
    if high_slope < 0 and low_slope < 0 and high_slope < low_slope:
        return {
            "pattern": "falling_wedge",
            "signal": "BULLISH",
            "confidence": 0.68,
            "entry": close[-1],
            "target": max(high),
            "stop_loss": min(low) * 0.99,
            "details": {"high_slope": high_slope, "low_slope": low_slope}
        }
    return None


# ==================== CUP AND HANDLE ====================
def detect_cup_and_handle(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Cup and Handle pattern (Bullish)"""
    if len(df) < 60:
        return None
    
    close = df['close'].values
    
    # Look for U-shape in last 50 bars
    cup_data = close[-50:-10]
    handle_data = close[-10:]
    
    # Cup: starts high, dips, returns to similar level
    cup_start = cup_data[0]
    cup_bottom = min(cup_data)
    cup_end = cup_data[-1]
    
    # Cup characteristics
    if cup_bottom < cup_start * 0.9 and cup_end > cup_start * 0.95:
        # Handle: small pullback
        handle_high = max(handle_data)
        handle_low = min(handle_data)
        handle_depth = (handle_high - handle_low) / handle_high
        
        if handle_depth < 0.05:  # Handle is shallow
            return {
                "pattern": "cup_and_handle",
                "signal": "BULLISH",
                "confidence": 0.75,
                "entry": close[-1],
                "target": cup_end + (cup_end - cup_bottom),
                "stop_loss": handle_low * 0.99,
                "details": {
                    "cup_depth": (cup_start - cup_bottom) / cup_start,
                    "handle_depth": handle_depth
                }
            }
    return None


# ==================== RECTANGLE ====================
def detect_rectangle(df: pd.DataFrame) -> Optional[Dict]:
    """Detect Rectangle pattern (Continuation)"""
    if len(df) < 25:
        return None
    
    close = df['close'].values
    high = df['high'].values[-20:]
    low = df['low'].values[-20:]
    
    resistance_std = np.std(high) / np.mean(high)
    support_std = np.std(low) / np.mean(low)
    
    # Both support and resistance are flat
    if resistance_std < 0.015 and support_std < 0.015:
        resistance = np.mean(high)
        support = np.mean(low)
        
        # Determine direction from prior trend
        prior_close = df['close'].values[-40:-20] if len(df) >= 40 else close[-20:]
        prior_trend = prior_close[-1] - prior_close[0]
        signal = "BULLISH" if prior_trend > 0 else "BEARISH"
        
        height = resistance - support
        
        return {
            "pattern": "rectangle",
            "signal": signal,
            "confidence": 0.62,
            "entry": close[-1],
            "target": resistance + height if signal == "BULLISH" else support - height,
            "stop_loss": support * 0.99 if signal == "BULLISH" else resistance * 1.01,
            "details": {"resistance": resistance, "support": support, "height": height}
        }
    return None


# ==================== MAIN DETECTION FUNCTION ====================
def detect_all_primary(df: pd.DataFrame) -> list:
    """Run all primary pattern detections"""
    patterns = []
    
    detectors = [
        detect_head_shoulders,
        detect_inverse_head_shoulders,
        detect_double_top,
        detect_double_bottom,
        detect_flag,
        detect_pennant,
        detect_ascending_triangle,
        detect_descending_triangle,
        detect_symmetrical_triangle,
        detect_rising_wedge,
        detect_falling_wedge,
        detect_cup_and_handle,
        detect_rectangle
    ]
    
    for detector in detectors:
        try:
            result = detector(df)
            if result:
                patterns.append(result)
        except Exception:
            continue
    
    return patterns
