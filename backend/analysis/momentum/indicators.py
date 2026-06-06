"""
Momentum Engine - 17 Indicators
"""
import pandas as pd
import numpy as np
from typing import Dict

def safe_div(a, b, default=0.0):
    """Helper for safe division"""
    return np.divide(a, b, out=np.full_like(a, default, dtype=float), where=b!=0)

def calculate_rsi(df: pd.DataFrame, period: int = 14) -> Dict:
    close = df['close'].values
    delta = np.diff(close)
    gains = np.where(delta > 0, delta, 0)
    losses = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gains).rolling(period).mean().iloc[-1]
    avg_loss = pd.Series(losses).rolling(period).mean().iloc[-1]
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
    
    if rsi > 70: signal, strength = "BEARISH", (rsi - 70) / 30
    elif rsi < 30: signal, strength = "BULLISH", (30 - rsi) / 30
    else: signal, strength = "NEUTRAL", 0.3
    return {"indicator": "rsi", "value": rsi, "signal": signal, "strength": min(strength, 1)}

def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal_period: int = 9) -> Dict:
    close = pd.Series(df['close'].values)
    ema_fast = close.ewm(span=fast).mean()
    ema_slow = close.ewm(span=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period).mean()
    histogram = macd_line - signal_line
    
    macd_val = macd_line.iloc[-1]
    signal_val = signal_line.iloc[-1]
    hist_val = histogram.iloc[-1]
    
    if macd_val > signal_val and hist_val > 0:
        signal, strength = "BULLISH", min(abs(hist_val) / (close.iloc[-1] or 1) * 100, 1)
    elif macd_val < signal_val and hist_val < 0:
        signal, strength = "BEARISH", min(abs(hist_val) / (close.iloc[-1] or 1) * 100, 1)
    else:
        signal, strength = "NEUTRAL", 0.3
    return {"indicator": "macd", "value": macd_val, "signal_line": signal_val, "histogram": hist_val, "signal": signal, "strength": strength}

def calculate_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Dict:
    high, low, close = df['high'].values, df['low'].values, df['close'].values
    lowest_low = pd.Series(low).rolling(k_period).min().iloc[-1]
    highest_high = pd.Series(high).rolling(k_period).max().iloc[-1]
    
    denom = highest_high - lowest_low
    k = ((close[-1] - lowest_low) / denom) * 100 if denom != 0 else 50
    d = k 
    
    if k > 80: signal, strength = "BEARISH", (k - 80) / 20
    elif k < 20: signal, strength = "BULLISH", (20 - k) / 20
    else: signal, strength = "NEUTRAL", 0.3
    return {"indicator": "stochastic", "value": k, "k": k, "d": d, "signal": signal, "strength": min(strength, 1)}

def calculate_adx(df: pd.DataFrame, period: int = 14) -> Dict:
    high, low, close = df['high'].values, df['low'].values, df['close'].values
    plus_dm = np.zeros(len(df))
    minus_dm = np.zeros(len(df))
    tr = np.zeros(len(df))
    
    for i in range(1, len(df)):
        up = high[i] - high[i-1]
        down = low[i-1] - low[i]
        plus_dm[i] = up if up > down and up > 0 else 0
        minus_dm[i] = down if down > up and down > 0 else 0
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
        
    atr = pd.Series(tr).rolling(period).mean()
    # Handle zero ATR
    atr_vals = atr.replace(0, 1) 
    
    plus_di = 100 * pd.Series(plus_dm).rolling(period).mean() / atr_vals
    minus_di = 100 * pd.Series(minus_dm).rolling(period).mean() / atr_vals
    
    sum_di = plus_di + minus_di
    dx = 100 * np.abs(plus_di - minus_di) / sum_di.replace(0, 1)
    
    adx = dx.rolling(period).mean().iloc[-1]
    
    if pd.isna(adx): adx = 0
    
    if adx > 25:
        signal = "BULLISH" if plus_di.iloc[-1] > minus_di.iloc[-1] else "BEARISH"
        strength = min(adx / 50, 1)
    else:
        signal, strength = "NEUTRAL", 0.3
    return {"indicator": "adx", "value": adx, "plus_di": plus_di.iloc[-1], "minus_di": minus_di.iloc[-1], "signal": signal, "strength": strength}

def calculate_mfi(df: pd.DataFrame, period: int = 14) -> Dict:
    tp = (df['high'].values + df['low'].values + df['close'].values) / 3
    rmf = tp * df['volume'].values
    pos_mf, neg_mf = np.zeros(len(df)), np.zeros(len(df))
    
    for i in range(1, len(df)):
        if tp[i] > tp[i-1]: pos_mf[i] = rmf[i]
        else: neg_mf[i] = rmf[i]
        
    pos_sum = np.sum(pos_mf[-period:])
    neg_sum = np.sum(neg_mf[-period:])
    
    if neg_sum > 0:
        mfi = 100 - (100 / (1 + pos_sum / neg_sum))
    else:
        mfi = 100 if pos_sum > 0 else 50
        
    if mfi > 80: signal, strength = "BEARISH", (mfi - 80) / 20
    elif mfi < 20: signal, strength = "BULLISH", (20 - mfi) / 20
    else: signal, strength = "NEUTRAL", 0.3
    return {"indicator": "mfi", "value": mfi, "signal": signal, "strength": min(strength, 1)}

def calculate_cci(df: pd.DataFrame, period: int = 20) -> Dict:
    tp = (df['high'].values + df['low'].values + df['close'].values) / 3
    sma = pd.Series(tp).rolling(period).mean().iloc[-1]
    mad = pd.Series(tp).rolling(period).apply(lambda x: np.mean(np.abs(x - np.mean(x)))).iloc[-1]
    
    cci = (tp[-1] - sma) / (0.015 * mad) if mad != 0 else 0
    
    if cci > 100: signal, strength = "BULLISH", min((cci - 100) / 200, 1)
    elif cci < -100: signal, strength = "BEARISH", min((-100 - cci) / 200, 1)
    else: signal, strength = "NEUTRAL", 0.3
    return {"indicator": "cci", "value": cci, "signal": signal, "strength": strength}

def calculate_williams_r(df: pd.DataFrame, period: int = 14) -> Dict:
    high, low, close = df['high'].values, df['low'].values, df['close'].values
    hh = np.max(high[-period:])
    ll = np.min(low[-period:])
    
    denom = hh - ll
    wr = ((hh - close[-1]) / denom) * -100 if denom != 0 else -50
    
    if wr > -20: signal, strength = "BEARISH", (-wr) / 20
    elif wr < -80: signal, strength = "BULLISH", (wr + 100) / 20
    else: signal, strength = "NEUTRAL", 0.3
    return {"indicator": "williams_r", "value": wr, "signal": signal, "strength": min(strength, 1)}

def calculate_ema_crossover(df: pd.DataFrame, fast: int = 9, slow: int = 21) -> Dict:
    close = pd.Series(df['close'].values)
    ef = close.ewm(span=fast).mean().iloc[-1]
    es = close.ewm(span=slow).mean().iloc[-1]
    
    diff = ef - es
    if ef > es: signal, strength = "BULLISH", diff / es * 10
    elif ef < es: signal, strength = "BEARISH", (es - ef) / es * 10
    else: signal, strength = "NEUTRAL", 0.3
    return {"indicator": "ema_crossover", "value": diff, "signal": signal, "strength": min(abs(strength), 1)}

def calculate_roc(df: pd.DataFrame, period: int = 12) -> Dict:
    close = df['close'].values
    prev = close[-period]
    roc = ((close[-1] - prev) / prev) * 100 if prev != 0 else 0
    
    if roc > 5: signal, strength = "BULLISH", min(roc / 10, 1)
    elif roc < -5: signal, strength = "BEARISH", min(abs(roc) / 10, 1)
    else: signal, strength = "NEUTRAL", 0.3
    return {"indicator": "roc", "value": roc, "signal": signal, "strength": strength}

def calculate_momentum(df: pd.DataFrame, period: int = 10) -> Dict:
    close = df['close'].values
    mom = close[-1] - close[-period]
    prev = close[-period]
    perc = (mom / prev) * 100 if prev != 0 else 0
    
    if perc > 2: signal, strength = "BULLISH", min(perc / 5, 1)
    elif perc < -2: signal, strength = "BEARISH", min(abs(perc) / 5, 1)
    else: signal, strength = "NEUTRAL", 0.3
    return {"indicator": "momentum", "value": mom, "percent": perc, "signal": signal, "strength": strength}

def calculate_force_index(df: pd.DataFrame, period: int = 13) -> Dict:
    close, volume = df['close'].values, df['volume'].values
    force = np.diff(close) * volume[1:]
    force_ema = pd.Series(force).ewm(span=period).mean().iloc[-1]
    if pd.isna(force_ema): force_ema = 0
    
    signal = "BULLISH" if force_ema > 0 else "BEARISH" if force_ema < 0 else "NEUTRAL"
    return {"indicator": "force_index", "value": force_ema, "signal": signal, "strength": 0.6 if signal != "NEUTRAL" else 0.3}

def calculate_ad_line(df: pd.DataFrame) -> Dict:
    high, low, close, volume = df['high'].values, df['low'].values, df['close'].values, df['volume'].values
    denom = high - low
    clv = np.where(denom != 0, ((close - low) - (high - close)) / denom, 0)
    ad = np.cumsum(clv * volume)
    curr, prev = ad[-1], ad[-10] if len(ad) >= 10 else ad[0]
    
    signal = "BULLISH" if curr > prev else "BEARISH" if curr < prev else "NEUTRAL"
    return {"indicator": "ad_line", "value": curr, "signal": signal, "strength": 0.6 if signal != "NEUTRAL" else 0.3}

def calculate_obv(df: pd.DataFrame) -> Dict:
    close, volume = df['close'].values, df['volume'].values
    obv = np.zeros(len(df))
    obv[0] = volume[0]
    for i in range(1, len(df)):
        if close[i] > close[i-1]: obv[i] = obv[i-1] + volume[i]
        elif close[i] < close[i-1]: obv[i] = obv[i-1] - volume[i]
        else: obv[i] = obv[i-1]
        
    curr, prev = obv[-1], obv[-10] if len(obv) >= 10 else obv[0]
    signal = "BULLISH" if curr > prev else "BEARISH" if curr < prev else "NEUTRAL"
    return {"indicator": "obv", "value": curr, "signal": signal, "strength": 0.6 if signal != "NEUTRAL" else 0.3}

def calculate_vwap_momentum(df: pd.DataFrame) -> Dict:
    """VWAP Momentum with Zero-Volume Protection"""
    tp = (df['high'].values + df['low'].values + df['close'].values) / 3
    volume = df['volume'].values
    
    # Safe Division: Convert 0 to 1 in denominator
    cum_vol = np.cumsum(volume)
    cum_vol_safe = np.where(cum_vol == 0, 1, cum_vol)
    
    vwap = np.cumsum(tp * volume) / cum_vol_safe
    
    curr_vwap = vwap[-1]
    close = df['close'].values[-1]
    
    if curr_vwap == 0: deviation = 0
    else: deviation = ((close - curr_vwap) / curr_vwap) * 100
    
    if deviation > 1: signal, strength = "BULLISH", min(deviation / 3, 1)
    elif deviation < -1: signal, strength = "BEARISH", min(abs(deviation) / 3, 1)
    else: signal, strength = "NEUTRAL", 0.3
    return {"indicator": "vwap_momentum", "value": curr_vwap, "deviation": deviation, "signal": signal, "strength": strength}

def calculate_trend_slope(df: pd.DataFrame, period: int = 20) -> Dict:
    close = df['close'].values[-period:]
    if len(close) < 2: return {"indicator": "trend_slope", "value": 0, "signal": "NEUTRAL", "strength": 0}
    
    x = np.arange(len(close))
    slope, _ = np.polyfit(x, close, 1)
    
    start_price = close[0] if close[0] != 0 else 1
    slope_perc = (slope / start_price) * 100 * period
    
    if slope_perc > 2: signal, strength = "BULLISH", min(slope_perc / 5, 1)
    elif slope_perc < -2: signal, strength = "BEARISH", min(abs(slope_perc) / 5, 1)
    else: signal, strength = "NEUTRAL", 0.3
    return {"indicator": "trend_slope", "value": slope, "slope_percent": slope_perc, "signal": signal, "strength": strength}

def calculate_velocity(df: pd.DataFrame, period: int = 5) -> Dict:
    close = df['close'].values
    vel = (close[-1] - close[-period]) / period
    prev = close[-period] if close[-period] != 0 else 1
    perc = (vel / prev) * 100
    
    if perc > 0.5: signal, strength = "BULLISH", min(perc / 2, 1)
    elif perc < -0.5: signal, strength = "BEARISH", min(abs(perc) / 2, 1)
    else: signal, strength = "NEUTRAL", 0.3
    return {"indicator": "velocity", "value": vel, "percent": perc, "signal": signal, "strength": strength}

def calculate_acceleration(df: pd.DataFrame, period: int = 5) -> Dict:
    close = df['close'].values
    v1 = (close[-1] - close[-period]) / period
    v2 = (close[-period] - close[-2*period]) / period if len(close) >= 2*period else v1
    acc = v1 - v2
    prev = close[-period] if close[-period] != 0 else 1
    perc = (acc / prev) * 100
    
    if perc > 0.2: signal, strength = "BULLISH", min(perc / 1, 1)
    elif perc < -0.2: signal, strength = "BEARISH", min(abs(perc) / 1, 1)
    else: signal, strength = "NEUTRAL", 0.3
    return {"indicator": "acceleration", "value": acc, "percent": perc, "signal": signal, "strength": strength}

def calculate_all_momentum(df: pd.DataFrame) -> Dict:
    results = {}
    calculators = [
        ("rsi", calculate_rsi), ("macd", calculate_macd), ("stochastic", calculate_stochastic),
        ("adx", calculate_adx), ("mfi", calculate_mfi), ("cci", calculate_cci),
        ("williams_r", calculate_williams_r), ("ema_crossover", calculate_ema_crossover),
        ("roc", calculate_roc), ("momentum", calculate_momentum), ("force_index", calculate_force_index),
        ("ad_line", calculate_ad_line), ("obv", calculate_obv), ("vwap_momentum", calculate_vwap_momentum),
        ("trend_slope", calculate_trend_slope), ("velocity", calculate_velocity), ("acceleration", calculate_acceleration)
    ]
    for name, calc in calculators:
        try:
            results[name] = calc(df)
        except Exception as e:
            results[name] = {"indicator": name, "error": str(e), "signal": "NEUTRAL", "value": 0}
    return results