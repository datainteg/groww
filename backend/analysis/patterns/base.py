"""
Base Pattern Detection Class
All patterns inherit from this
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional
from abc import ABC, abstractmethod


class BasePattern(ABC):
    """Base class for all pattern detectors"""
    
    def __init__(self, name: str, pattern_type: str):
        self.name = name
        self.pattern_type = pattern_type  # PRIMARY, CANDLESTICK, HARMONIC
    
    @abstractmethod
    def detect(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Detect pattern in dataframe
        
        Args:
            df: DataFrame with columns [timestamp, open, high, low, close, volume]
        
        Returns:
            None if not detected, or dict with:
            {
                "pattern": str,
                "signal": "BULLISH" | "BEARISH",
                "confidence": float (0-1),
                "entry": float,
                "target": float,
                "stop_loss": float,
                "details": dict
            }
        """
        pass
    
    def _find_peaks(self, data: np.ndarray, order: int = 5) -> np.ndarray:
        """Find local maxima"""
        peaks = []
        for i in range(order, len(data) - order):
            if all(data[i] > data[i-j] for j in range(1, order+1)) and \
               all(data[i] > data[i+j] for j in range(1, order+1)):
                peaks.append(i)
        return np.array(peaks)
    
    def _find_troughs(self, data: np.ndarray, order: int = 5) -> np.ndarray:
        """Find local minima"""
        troughs = []
        for i in range(order, len(data) - order):
            if all(data[i] < data[i-j] for j in range(1, order+1)) and \
               all(data[i] < data[i+j] for j in range(1, order+1)):
                troughs.append(i)
        return np.array(troughs)
    
    def _is_within_tolerance(self, val1: float, val2: float, tolerance: float = 0.02) -> bool:
        """Check if two values are within tolerance"""
        if val2 == 0:
            return False
        return abs(val1 - val2) / val2 <= tolerance


def detect(df: pd.DataFrame) -> Optional[Dict]:
    """Wrapper function - override in each pattern file"""
    return None
