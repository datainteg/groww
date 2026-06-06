"""
Support/Resistance Engine - 13 Indicators
"""
import pandas as pd
import numpy as np
from typing import Dict, List


def calculate_pivot_points(df: pd.DataFrame) -> Dict:
    """Standard Pivot Points"""
    high, low, close = df['high'].iloc[-1], df['low'].iloc[-1], df['close'].iloc[-1]
    pivot = (high + low + close) / 3
    r1, r2, r3 = 2 * pivot - low, pivot + (high - low), high + 2 * (pivot - low)
    s1, s2, s3 = 2 * pivot - high, pivot - (high - low), low - 2 * (high - pivot)
    current = close
    if current > r1:
        signal = "BULLISH"
    elif current < s1:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"
    return {"indicator": "pivot_points", "pivot": pivot, "r1": r1, "r2": r2, "r3": r3, "s1": s1, "s2": s2, "s3": s3, "signal": signal, "strength": 0.6}


def calculate_fibonacci(df: pd.DataFrame, lookback: int = 50) -> Dict:
    """Fibonacci Retracement Levels"""
    high = np.max(df['high'].values[-lookback:])
    low = np.min(df['low'].values[-lookback:])
    diff = high - low
    levels = {
        "0": high, "23.6": high - 0.236 * diff, "38.2": high - 0.382 * diff,
        "50": high - 0.5 * diff, "61.8": high - 0.618 * diff, "78.6": high - 0.786 * diff, "100": low
    }
    current = df['close'].iloc[-1]
    nearest = min(levels.values(), key=lambda x: abs(x - current))
    signal = "NEUTRAL"
    if current > levels["38.2"]:
        signal = "BULLISH"
    elif current < levels["61.8"]:
        signal = "BEARISH"
    return {"indicator": "fibonacci", "levels": levels, "nearest": nearest, "signal": signal, "strength": 0.65}


def calculate_camarilla(df: pd.DataFrame) -> Dict:
    """Camarilla Pivot Points"""
    high, low, close = df['high'].iloc[-1], df['low'].iloc[-1], df['close'].iloc[-1]
    diff = high - low
    h4 = close + diff * 1.1 / 2
    h3 = close + diff * 1.1 / 4
    l3 = close - diff * 1.1 / 4
    l4 = close - diff * 1.1 / 2
    current = close
    signal = "NEUTRAL"
    if current > h3:
        signal = "BULLISH"
    elif current < l3:
        signal = "BEARISH"
    return {"indicator": "camarilla", "h4": h4, "h3": h3, "l3": l3, "l4": l4, "signal": signal, "strength": 0.6}


def calculate_moving_averages(df: pd.DataFrame) -> Dict:
    """Moving Average Support/Resistance"""
    close = pd.Series(df['close'].values)
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else ma20
    ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else ma50
    current = close.iloc[-1]
    if current > ma20 > ma50:
        signal = "BULLISH"
    elif current < ma20 < ma50:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"
    return {"indicator": "moving_averages", "ma20": ma20, "ma50": ma50, "ma200": ma200, "signal": signal, "strength": 0.7}


def calculate_vwap(df: pd.DataFrame) -> Dict:
    """Volume Weighted Average Price (Safe Division Fix)"""
    typical = (df['high'].values + df['low'].values + df['close'].values) / 3
    volume = df['volume'].values
    
    # --- SAFE DIVISION ---
    cum_vol = np.cumsum(volume)
    cum_vol_safe = np.where(cum_vol == 0, 1, cum_vol)
    
    vwap = np.cumsum(typical * volume) / cum_vol_safe
    
    current_vwap = vwap[-1]
    current = df['close'].iloc[-1]
    std = np.std(typical[-20:])
    upper = current_vwap + 2 * std
    lower = current_vwap - 2 * std
    
    if current_vwap == 0:
        signal = "NEUTRAL"
    elif current > current_vwap:
        signal = "BULLISH"
    elif current < current_vwap:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"
        
    return {"indicator": "vwap", "vwap": current_vwap, "upper": upper, "lower": lower, "signal": signal, "strength": 0.65}


def calculate_volume_profile(df: pd.DataFrame, bins: int = 20) -> Dict:
    """Volume Profile POC"""
    close = df['close'].values
    volume = df['volume'].values
    price_range = np.linspace(np.min(close), np.max(close), bins)
    vol_at_price = np.zeros(bins - 1)
    for i in range(len(close)):
        for j in range(bins - 1):
            if price_range[j] <= close[i] < price_range[j + 1]:
                vol_at_price[j] += volume[i]
                break
    poc_idx = np.argmax(vol_at_price)
    poc = (price_range[poc_idx] + price_range[poc_idx + 1]) / 2
    current = close[-1]
    if current > poc:
        signal = "BULLISH"
    elif current < poc:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"
    return {"indicator": "volume_profile", "poc": poc, "signal": signal, "strength": 0.6}


def calculate_swing_levels(df: pd.DataFrame, order: int = 5) -> Dict:
    """Swing High/Low Levels"""
    high, low = df['high'].values, df['low'].values
    swing_highs, swing_lows = [], []
    for i in range(order, len(high) - order):
        if high[i] == max(high[i-order:i+order+1]):
            swing_highs.append(high[i])
        if low[i] == min(low[i-order:i+order+1]):
            swing_lows.append(low[i])
    resistance = swing_highs[-1] if swing_highs else high[-1]
    support = swing_lows[-1] if swing_lows else low[-1]
    current = df['close'].iloc[-1]
    if current > resistance * 0.99:
        signal = "BULLISH"
    elif current < support * 1.01:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"
    return {"indicator": "swing_levels", "resistance": resistance, "support": support, "signal": signal, "strength": 0.65}


def calculate_zigzag(df: pd.DataFrame, threshold: float = 0.03) -> Dict:
    """ZigZag Indicator (Safe Division Fix)"""
    close = df['close'].values
    pivots = []
    direction = 0
    last_pivot = close[0]
    
    for i in range(1, len(close)):
        # Avoid division by zero
        if last_pivot == 0: 
            last_pivot = 0.01 
            
        change = (close[i] - last_pivot) / last_pivot
        
        if direction == 0:
            if change > threshold:
                direction = 1
                pivots.append(("LOW", last_pivot))
                last_pivot = close[i]
            elif change < -threshold:
                direction = -1
                pivots.append(("HIGH", last_pivot))
                last_pivot = close[i]
        elif direction == 1:
            if close[i] > last_pivot:
                last_pivot = close[i]
            elif (last_pivot - close[i]) / last_pivot > threshold:
                pivots.append(("HIGH", last_pivot))
                direction = -1
                last_pivot = close[i]
        else:
            if close[i] < last_pivot:
                last_pivot = close[i]
            elif (close[i] - last_pivot) / last_pivot > threshold:
                pivots.append(("LOW", last_pivot))
                direction = 1
                last_pivot = close[i]
                
    signal = "BULLISH" if direction == 1 else ("BEARISH" if direction == -1 else "NEUTRAL")
    return {"indicator": "zigzag", "pivots": pivots[-5:] if pivots else [], "direction": direction, "signal": signal, "strength": 0.6}


def calculate_regression_channel(df: pd.DataFrame, period: int = 50) -> Dict:
    """Linear Regression Channel"""
    close = df['close'].values[-period:]
    if len(close) < 2: return {"indicator": "regression_channel", "signal": "NEUTRAL", "value": 0, "upper": 0, "lower": 0, "strength": 0}
    
    x = np.arange(len(close))
    slope, intercept = np.polyfit(x, close, 1)
    regression = slope * x + intercept
    std = np.std(close - regression)
    upper = regression[-1] + 2 * std
    lower = regression[-1] - 2 * std
    current = close[-1]
    if current > upper:
        signal = "BEARISH"
    elif current < lower:
        signal = "BULLISH"
    else:
        signal = "BULLISH" if slope > 0 else "BEARISH"
    return {"indicator": "regression_channel", "value": regression[-1], "upper": upper, "lower": lower, "slope": slope, "signal": signal, "strength": 0.65}


def calculate_order_blocks(df: pd.DataFrame) -> Dict:
    """Order Blocks (Institutional Zones)"""
    high, low, close, volume = df['high'].values, df['low'].values, df['close'].values, df['volume'].values
    avg_vol = np.mean(volume)
    bullish_ob, bearish_ob = None, None
    for i in range(len(df) - 3, 0, -1):
        if volume[i] > avg_vol * 1.5:
            if close[i] < close[i+1] and close[i+2] > close[i]:
                bullish_ob = (low[i], high[i])
                break
    for i in range(len(df) - 3, 0, -1):
        if volume[i] > avg_vol * 1.5:
            if close[i] > close[i+1] and close[i+2] < close[i]:
                bearish_ob = (low[i], high[i])
                break
    current = close[-1]
    signal = "NEUTRAL"
    if bullish_ob and current >= bullish_ob[0] and current <= bullish_ob[1]:
        signal = "BULLISH"
    elif bearish_ob and current >= bearish_ob[0] and current <= bearish_ob[1]:
        signal = "BEARISH"
    return {"indicator": "order_blocks", "bullish_ob": bullish_ob, "bearish_ob": bearish_ob, "signal": signal, "strength": 0.7}


def calculate_ichimoku(df: pd.DataFrame) -> Dict:
    """Ichimoku Cloud"""
    high, low, close = df['high'].values, df['low'].values, df['close'].values
    tenkan = (np.max(high[-9:]) + np.min(low[-9:])) / 2
    kijun = (np.max(high[-26:]) + np.min(low[-26:])) / 2 if len(high) >= 26 else tenkan
    senkou_a = (tenkan + kijun) / 2
    senkou_b = (np.max(high[-52:]) + np.min(low[-52:])) / 2 if len(high) >= 52 else senkou_a
    current = close[-1]
    cloud_top, cloud_bottom = max(senkou_a, senkou_b), min(senkou_a, senkou_b)
    if current > cloud_top and tenkan > kijun:
        signal = "BULLISH"
    elif current < cloud_bottom and tenkan < kijun:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"
    return {"indicator": "ichimoku", "tenkan": tenkan, "kijun": kijun, "senkou_a": senkou_a, "senkou_b": senkou_b, "signal": signal, "strength": 0.75}


def calculate_pitchfork(df: pd.DataFrame) -> Dict:
    """Andrew's Pitchfork"""
    high, low, close = df['high'].values, df['low'].values, df['close'].values
    # Find 3 recent pivots
    p1_idx, p2_idx, p3_idx = -30, -15, -1
    if len(close) < 30: return {"indicator": "pitchfork", "signal": "NEUTRAL", "strength": 0}
    
    p1 = (close[p1_idx] + high[p1_idx] + low[p1_idx]) / 3
    p2 = (close[p2_idx] + high[p2_idx] + low[p2_idx]) / 3
    p3 = (close[p3_idx] + high[p3_idx] + low[p3_idx]) / 3
    median = (p2 + p3) / 2
    
    denom = abs(p3_idx - p1_idx)
    slope = (median - p1) / denom if denom != 0 else 0
    
    signal = "BULLISH" if slope > 0 else "BEARISH"
    return {"indicator": "pitchfork", "p1": p1, "p2": p2, "p3": p3, "median": median, "slope": slope, "signal": signal, "strength": 0.55}


def calculate_market_profile(df: pd.DataFrame, bins: int = 30) -> Dict:
    """Market Profile VAH/VAL/POC"""
    close, volume = df['close'].values, df['volume'].values
    price_range = np.linspace(np.min(close), np.max(close), bins)
    tpo = np.zeros(bins - 1)
    for i in range(len(close)):
        for j in range(bins - 1):
            if price_range[j] <= close[i] < price_range[j + 1]:
                tpo[j] += 1
                break
    poc_idx = np.argmax(tpo)
    poc = (price_range[poc_idx] + price_range[poc_idx + 1]) / 2
    total_tpo = np.sum(tpo)
    cumsum = np.cumsum(tpo)
    val_idx = np.searchsorted(cumsum, total_tpo * 0.3)
    vah_idx = np.searchsorted(cumsum, total_tpo * 0.7)
    val = (price_range[val_idx] + price_range[min(val_idx + 1, bins - 1)]) / 2
    vah = (price_range[vah_idx] + price_range[min(vah_idx + 1, bins - 1)]) / 2
    current = close[-1]
    if current > vah:
        signal = "BULLISH"
    elif current < val:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"
    return {"indicator": "market_profile", "poc": poc, "vah": vah, "val": val, "signal": signal, "strength": 0.65}


def calculate_all_support_resistance(df: pd.DataFrame) -> Dict:
    """Calculate all S/R indicators"""
    results = {}
    calculators = [
        ("pivot_points", calculate_pivot_points), ("fibonacci", calculate_fibonacci),
        ("camarilla", calculate_camarilla), ("moving_averages", calculate_moving_averages),
        ("vwap", calculate_vwap), ("volume_profile", calculate_volume_profile),
        ("swing_levels", calculate_swing_levels), ("zigzag", calculate_zigzag),
        ("regression_channel", calculate_regression_channel), ("order_blocks", calculate_order_blocks),
        ("ichimoku", calculate_ichimoku), ("pitchfork", calculate_pitchfork), ("market_profile", calculate_market_profile)
    ]
    for name, calc in calculators:
        try:
            results[name] = calc(df)
        except Exception as e:
            results[name] = {"indicator": name, "error": str(e), "signal": "NEUTRAL"}
    return results