"""
Harmonic Patterns - 4 Patterns
ABCD, Gartley, Butterfly, Crab
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional, List, Tuple


def _find_swing_points(df: pd.DataFrame, order: int = 5) -> Tuple[List, List]:
    """Find swing highs and lows"""
    highs = []
    lows = []
    high = df['high'].values
    low = df['low'].values
    
    for i in range(order, len(df) - order):
        if high[i] == max(high[i-order:i+order+1]):
            highs.append((i, high[i]))
        if low[i] == min(low[i-order:i+order+1]):
            lows.append((i, low[i]))
    
    return highs, lows


def _fib_ratio(move1: float, move2: float) -> float:
    """Calculate fibonacci ratio between two moves"""
    if move1 == 0:
        return 0
    return abs(move2) / abs(move1)


def _is_near(value: float, target: float, tolerance: float = 0.03) -> bool:
    """Check if value is near target within tolerance"""
    return abs(value - target) / target <= tolerance if target != 0 else False


def detect_abcd(df: pd.DataFrame) -> Optional[Dict]:
    """
    Detect ABCD pattern
    Bullish: AB down, BC up (0.382-0.886 of AB), CD down (1.13-1.618 of BC)
    Bearish: AB up, BC down, CD up
    """
    if len(df) < 30:
        return None
    
    highs, lows = _find_swing_points(df)
    
    if len(highs) < 2 or len(lows) < 2:
        return None
    
    close = df['close'].values
    
    # Try to find ABCD in recent swings
    # Bullish ABCD: A(high) -> B(low) -> C(high) -> D(low)
    for i in range(len(highs) - 1):
        for j in range(len(lows) - 1):
            if highs[i][0] < lows[j][0] < highs[i+1][0] < lows[j+1][0]:
                A = highs[i][1]
                B = lows[j][1]
                C = highs[i+1][1]
                D = lows[j+1][1]
                
                AB = A - B
                BC = C - B
                CD = C - D
                
                # BC should be 0.382-0.886 of AB
                bc_ratio = _fib_ratio(AB, BC)
                # CD should be 1.13-1.618 of BC
                cd_ratio = _fib_ratio(BC, CD)
                
                if 0.35 <= bc_ratio <= 0.90 and 1.10 <= cd_ratio <= 1.65:
                    return {
                        "pattern": "abcd_bullish",
                        "signal": "BULLISH",
                        "confidence": 0.70,
                        "entry": close[-1],
                        "target": D + AB,
                        "stop_loss": D * 0.99,
                        "details": {"bc_ratio": bc_ratio, "cd_ratio": cd_ratio, "D": D}
                    }
    
    # Bearish ABCD: A(low) -> B(high) -> C(low) -> D(high)
    for i in range(len(lows) - 1):
        for j in range(len(highs) - 1):
            if lows[i][0] < highs[j][0] < lows[i+1][0] < highs[j+1][0]:
                A = lows[i][1]
                B = highs[j][1]
                C = lows[i+1][1]
                D = highs[j+1][1]
                
                AB = B - A
                BC = B - C
                CD = D - C
                
                bc_ratio = _fib_ratio(AB, BC)
                cd_ratio = _fib_ratio(BC, CD)
                
                if 0.35 <= bc_ratio <= 0.90 and 1.10 <= cd_ratio <= 1.65:
                    return {
                        "pattern": "abcd_bearish",
                        "signal": "BEARISH",
                        "confidence": 0.70,
                        "entry": close[-1],
                        "target": D - AB,
                        "stop_loss": D * 1.01,
                        "details": {"bc_ratio": bc_ratio, "cd_ratio": cd_ratio, "D": D}
                    }
    
    return None


def detect_gartley(df: pd.DataFrame) -> Optional[Dict]:
    """
    Detect Gartley pattern (5 points: X, A, B, C, D)
    Bullish: X(low) -> A(high) -> B(low at 0.618) -> C(high at 0.382-0.886) -> D(low at 0.786 of XA)
    """
    if len(df) < 40:
        return None
    
    highs, lows = _find_swing_points(df)
    close = df['close'].values
    
    if len(highs) < 2 or len(lows) < 3:
        return None
    
    # Bullish Gartley
    for xi in range(len(lows) - 2):
        for ai in range(len(highs) - 1):
            if lows[xi][0] < highs[ai][0]:
                X = lows[xi][1]
                A = highs[ai][1]
                XA = A - X
                
                # Find B (should be 0.618 retracement of XA)
                for bi in range(xi + 1, len(lows) - 1):
                    if lows[bi][0] > highs[ai][0]:
                        B = lows[bi][1]
                        AB = A - B
                        ab_ratio = _fib_ratio(XA, AB)
                        
                        if _is_near(ab_ratio, 0.618, 0.05):
                            # Find C
                            for ci in range(ai + 1, len(highs)):
                                if highs[ci][0] > lows[bi][0]:
                                    C = highs[ci][1]
                                    BC = C - B
                                    bc_ratio = _fib_ratio(AB, BC)
                                    
                                    if 0.35 <= bc_ratio <= 0.90:
                                        # Find D (0.786 of XA)
                                        target_D = A - 0.786 * XA
                                        
                                        for di in range(bi + 1, len(lows)):
                                            if lows[di][0] > highs[ci][0]:
                                                D = lows[di][1]
                                                xd_ratio = _fib_ratio(XA, A - D)
                                                
                                                if _is_near(xd_ratio, 0.786, 0.05):
                                                    return {
                                                        "pattern": "gartley_bullish",
                                                        "signal": "BULLISH",
                                                        "confidence": 0.78,
                                                        "entry": close[-1],
                                                        "target": D + XA * 0.618,
                                                        "stop_loss": X * 0.995,
                                                        "details": {
                                                            "ab_ratio": ab_ratio,
                                                            "bc_ratio": bc_ratio,
                                                            "xd_ratio": xd_ratio
                                                        }
                                                    }
    return None


def detect_butterfly(df: pd.DataFrame) -> Optional[Dict]:
    """
    Detect Butterfly pattern
    D extends beyond X (1.27 or 1.618 of XA)
    """
    if len(df) < 40:
        return None
    
    highs, lows = _find_swing_points(df)
    close = df['close'].values
    
    if len(highs) < 2 or len(lows) < 3:
        return None
    
    # Bullish Butterfly
    for xi in range(len(lows) - 2):
        for ai in range(len(highs) - 1):
            if lows[xi][0] < highs[ai][0]:
                X = lows[xi][1]
                A = highs[ai][1]
                XA = A - X
                
                for bi in range(xi + 1, len(lows) - 1):
                    if lows[bi][0] > highs[ai][0]:
                        B = lows[bi][1]
                        AB = A - B
                        ab_ratio = _fib_ratio(XA, AB)
                        
                        if _is_near(ab_ratio, 0.786, 0.05):
                            for ci in range(ai + 1, len(highs)):
                                if highs[ci][0] > lows[bi][0]:
                                    C = highs[ci][1]
                                    BC = C - B
                                    bc_ratio = _fib_ratio(AB, BC)
                                    
                                    if 0.35 <= bc_ratio <= 0.90:
                                        # D should be 1.27-1.618 of XA below X
                                        for di in range(bi + 1, len(lows)):
                                            if lows[di][0] > highs[ci][0]:
                                                D = lows[di][1]
                                                xd_extension = (A - D) / XA
                                                
                                                if 1.20 <= xd_extension <= 1.65:
                                                    return {
                                                        "pattern": "butterfly_bullish",
                                                        "signal": "BULLISH",
                                                        "confidence": 0.75,
                                                        "entry": close[-1],
                                                        "target": D + XA * 0.618,
                                                        "stop_loss": D * 0.99,
                                                        "details": {
                                                            "ab_ratio": ab_ratio,
                                                            "xd_extension": xd_extension
                                                        }
                                                    }
    return None


def detect_crab(df: pd.DataFrame) -> Optional[Dict]:
    """
    Detect Crab pattern
    D extends to 1.618 of XA
    """
    if len(df) < 40:
        return None
    
    highs, lows = _find_swing_points(df)
    close = df['close'].values
    
    if len(highs) < 2 or len(lows) < 3:
        return None
    
    # Bullish Crab
    for xi in range(len(lows) - 2):
        for ai in range(len(highs) - 1):
            if lows[xi][0] < highs[ai][0]:
                X = lows[xi][1]
                A = highs[ai][1]
                XA = A - X
                
                for bi in range(xi + 1, len(lows) - 1):
                    if lows[bi][0] > highs[ai][0]:
                        B = lows[bi][1]
                        AB = A - B
                        ab_ratio = _fib_ratio(XA, AB)
                        
                        if 0.35 <= ab_ratio <= 0.65:
                            for ci in range(ai + 1, len(highs)):
                                if highs[ci][0] > lows[bi][0]:
                                    C = highs[ci][1]
                                    BC = C - B
                                    bc_ratio = _fib_ratio(AB, BC)
                                    
                                    if 0.35 <= bc_ratio <= 0.90:
                                        # D at 1.618 extension
                                        for di in range(bi + 1, len(lows)):
                                            if lows[di][0] > highs[ci][0]:
                                                D = lows[di][1]
                                                xd_extension = (A - D) / XA
                                                
                                                if _is_near(xd_extension, 1.618, 0.08):
                                                    return {
                                                        "pattern": "crab_bullish",
                                                        "signal": "BULLISH",
                                                        "confidence": 0.80,
                                                        "entry": close[-1],
                                                        "target": D + XA * 0.618,
                                                        "stop_loss": D * 0.99,
                                                        "details": {
                                                            "ab_ratio": ab_ratio,
                                                            "xd_extension": xd_extension
                                                        }
                                                    }
    return None


def detect_all_harmonic(df: pd.DataFrame) -> list:
    """Run all harmonic pattern detections"""
    patterns = []
    
    detectors = [
        detect_abcd,
        detect_gartley,
        detect_butterfly,
        detect_crab
    ]
    
    for detector in detectors:
        try:
            result = detector(df)
            if result:
                patterns.append(result)
        except Exception:
            continue
    
    return patterns
