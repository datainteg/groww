from .primary import detect_all_primary
from .candlestick import detect_all_candlestick
from .harmonic import detect_all_harmonic

def detect_all_patterns(df):
    """Run all pattern detections"""
    patterns = []
    patterns.extend(detect_all_primary(df))
    patterns.extend(detect_all_candlestick(df))
    patterns.extend(detect_all_harmonic(df))
    return patterns

__all__ = ['detect_all_patterns', 'detect_all_primary', 'detect_all_candlestick', 'detect_all_harmonic']
