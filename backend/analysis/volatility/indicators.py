"""
Volatility Engine - 13 Indicators
"""
import pandas as pd
import numpy as np
from typing import Dict


def calculate_atr(df: pd.DataFrame, period: int = 14) -> Dict:
    """Average True Range"""
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    
    tr = np.zeros(len(df))
    for i in range(1, len(df)):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i-1]),
            abs(low[i] - close[i-1])
        )
    
    atr = pd.Series(tr).rolling(period).mean().iloc[-1]
    atr_percent = (atr / close[-1]) * 100
    
    # Volatility regime
    if atr_percent < 1:
        regime = "LOW"
    elif atr_percent < 2:
        regime = "NORMAL"
    else:
        regime = "HIGH"
    
    return {
        "indicator": "atr",
        "value": atr,
        "atr_percent": atr_percent,
        "regime": regime,
        "signal": "NEUTRAL",
        "strength": min(atr_percent / 3, 1)
    }


def calculate_bollinger(df: pd.DataFrame, period: int = 20, std_dev: float = 2) -> Dict:
    """Bollinger Bands"""
    close = df['close'].values
    
    sma = pd.Series(close).rolling(period).mean().iloc[-1]
    std = pd.Series(close).rolling(period).std().iloc[-1]
    
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    current = close[-1]
    
    # Bandwidth
    bandwidth = ((upper - lower) / sma) * 100
    
    # Position in bands
    if current > upper:
        signal = "BEARISH"  # Overbought
        strength = 0.7
    elif current < lower:
        signal = "BULLISH"  # Oversold
        strength = 0.7
    else:
        signal = "NEUTRAL"
        strength = 0.3
    
    # %B indicator
    percent_b = (current - lower) / (upper - lower) if (upper - lower) != 0 else 0.5
    
    return {
        "indicator": "bollinger",
        "value": bandwidth,
        "upper": upper,
        "middle": sma,
        "lower": lower,
        "percent_b": percent_b,
        "signal": signal,
        "strength": strength
    }


def calculate_keltner(df: pd.DataFrame, period: int = 20, atr_mult: float = 2) -> Dict:
    """Keltner Channels"""
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    
    # EMA
    ema = pd.Series(close).ewm(span=period).mean().iloc[-1]
    
    # ATR
    tr = np.maximum(high[1:] - low[1:], 
                    np.maximum(np.abs(high[1:] - close[:-1]), 
                               np.abs(low[1:] - close[:-1])))
    atr = np.mean(tr[-period:])
    
    upper = ema + atr_mult * atr
    lower = ema - atr_mult * atr
    current = close[-1]
    
    if current > upper:
        signal = "BEARISH"
        strength = 0.65
    elif current < lower:
        signal = "BULLISH"
        strength = 0.65
    else:
        signal = "NEUTRAL"
        strength = 0.3
    
    return {
        "indicator": "keltner",
        "value": (upper - lower) / ema * 100,
        "upper": upper,
        "middle": ema,
        "lower": lower,
        "signal": signal,
        "strength": strength
    }


def calculate_historical_vol(df: pd.DataFrame, period: int = 20) -> Dict:
    """Historical Volatility (Standard Deviation of Returns)"""
    close = df['close'].values
    returns = np.diff(np.log(close))
    
    hv = np.std(returns[-period:]) * np.sqrt(252) * 100  # Annualized
    
    if hv < 15:
        regime = "LOW"
    elif hv < 25:
        regime = "NORMAL"
    else:
        regime = "HIGH"
    
    return {
        "indicator": "historical_vol",
        "value": hv,
        "regime": regime,
        "signal": "NEUTRAL",
        "strength": min(hv / 40, 1)
    }


def calculate_parkinson_vol(df: pd.DataFrame, period: int = 20) -> Dict:
    """Parkinson Volatility (High-Low based)"""
    high = df['high'].values[-period:]
    low = df['low'].values[-period:]
    
    hl_ratio = np.log(high / low)
    parkinson = np.sqrt(np.mean(hl_ratio ** 2) / (4 * np.log(2))) * np.sqrt(252) * 100
    
    return {
        "indicator": "parkinson_vol",
        "value": parkinson,
        "signal": "NEUTRAL",
        "strength": min(parkinson / 40, 1)
    }


def calculate_nadaraya_watson(df: pd.DataFrame, bandwidth: float = 8) -> Dict:
    """Nadaraya-Watson Envelope"""
    close = df['close'].values
    n = len(close)
    
    # Kernel regression
    y_hat = np.zeros(n)
    for i in range(n):
        weights = np.exp(-0.5 * ((np.arange(n) - i) / bandwidth) ** 2)
        y_hat[i] = np.sum(weights * close) / np.sum(weights)
    
    # Envelope
    residuals = close - y_hat
    std_residual = np.std(residuals)
    upper = y_hat[-1] + 2 * std_residual
    lower = y_hat[-1] - 2 * std_residual
    
    current = close[-1]
    if current > upper:
        signal = "BEARISH"
    elif current < lower:
        signal = "BULLISH"
    else:
        signal = "NEUTRAL"
    
    return {
        "indicator": "nadaraya_watson",
        "value": y_hat[-1],
        "upper": upper,
        "lower": lower,
        "signal": signal,
        "strength": 0.6 if signal != "NEUTRAL" else 0.3
    }


def calculate_garch(df: pd.DataFrame) -> Dict:
    """Simple GARCH(1,1) approximation"""
    close = df['close'].values
    returns = np.diff(np.log(close))
    
    # Simple EWMA variance as GARCH proxy
    alpha = 0.06
    beta = 0.94
    
    variance = np.zeros(len(returns))
    variance[0] = np.var(returns)
    
    for i in range(1, len(returns)):
        variance[i] = alpha * returns[i-1]**2 + beta * variance[i-1]
    
    garch_vol = np.sqrt(variance[-1]) * np.sqrt(252) * 100
    
    return {
        "indicator": "garch",
        "value": garch_vol,
        "signal": "NEUTRAL",
        "strength": min(garch_vol / 40, 1)
    }


def calculate_implied_vol(df: pd.DataFrame) -> Dict:
    """Implied Volatility proxy (from ATR ratio)"""
    atr_result = calculate_atr(df)
    hv_result = calculate_historical_vol(df)
    
    # IV proxy based on ATR to HV ratio
    iv_proxy = atr_result['atr_percent'] * 15  # Approximate annualized
    iv_hv_ratio = iv_proxy / hv_result['value'] if hv_result['value'] != 0 else 1
    
    if iv_hv_ratio > 1.2:
        signal = "HIGH_IV"  # Options expensive
    elif iv_hv_ratio < 0.8:
        signal = "LOW_IV"  # Options cheap
    else:
        signal = "NEUTRAL"
    
    return {
        "indicator": "implied_vol",
        "value": iv_proxy,
        "iv_hv_ratio": iv_hv_ratio,
        "signal": signal,
        "strength": abs(iv_hv_ratio - 1)
    }


def calculate_cv(df: pd.DataFrame, period: int = 20) -> Dict:
    """Coefficient of Variation"""
    close = df['close'].values[-period:]
    cv = (np.std(close) / np.mean(close)) * 100
    
    return {
        "indicator": "cv",
        "value": cv,
        "signal": "NEUTRAL",
        "strength": min(cv / 5, 1)
    }


def calculate_volatility_ratio(df: pd.DataFrame) -> Dict:
    """Volatility Ratio (Short-term vs Long-term)"""
    close = df['close'].values
    
    short_vol = np.std(np.diff(np.log(close[-10:]))) * np.sqrt(252) * 100
    long_vol = np.std(np.diff(np.log(close[-50:]))) * np.sqrt(252) * 100 if len(close) >= 50 else short_vol
    
    ratio = short_vol / long_vol if long_vol != 0 else 1
    
    if ratio > 1.3:
        signal = "EXPANDING"
    elif ratio < 0.7:
        signal = "CONTRACTING"
    else:
        signal = "STABLE"
    
    return {
        "indicator": "volatility_ratio",
        "value": ratio,
        "short_vol": short_vol,
        "long_vol": long_vol,
        "signal": signal,
        "strength": abs(ratio - 1)
    }


def calculate_india_vix(df: pd.DataFrame) -> Dict:
    """India VIX proxy (based on market data)"""
    # In production, fetch actual India VIX
    # This is a proxy based on ATR and historical vol
    atr = calculate_atr(df)
    hv = calculate_historical_vol(df)
    
    vix_proxy = (atr['atr_percent'] * 10 + hv['value']) / 2
    
    if vix_proxy < 12:
        regime = "LOW_FEAR"
    elif vix_proxy < 20:
        regime = "NORMAL"
    elif vix_proxy < 30:
        regime = "ELEVATED"
    else:
        regime = "HIGH_FEAR"
    
    return {
        "indicator": "india_vix",
        "value": vix_proxy,
        "regime": regime,
        "signal": "NEUTRAL",
        "strength": min(vix_proxy / 30, 1)
    }


def calculate_realized_vol(df: pd.DataFrame, period: int = 20) -> Dict:
    """Realized Volatility"""
    close = df['close'].values
    returns = np.diff(np.log(close[-period-1:]))
    rv = np.sqrt(np.sum(returns**2) / period) * np.sqrt(252) * 100
    
    return {
        "indicator": "realized_vol",
        "value": rv,
        "signal": "NEUTRAL",
        "strength": min(rv / 40, 1)
    }


def calculate_evt(df: pd.DataFrame) -> Dict:
    """Extreme Value Theory indicator"""
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    
    # Max drawdown
    peak = np.maximum.accumulate(close)
    drawdown = (peak - close) / peak * 100
    max_dd = np.max(drawdown[-50:])
    
    # Extreme move detection
    returns = np.diff(np.log(close))
    extreme_threshold = np.std(returns) * 2
    extreme_moves = np.sum(np.abs(returns[-20:]) > extreme_threshold)
    
    return {
        "indicator": "evt",
        "value": max_dd,
        "extreme_moves": extreme_moves,
        "signal": "HIGH_RISK" if extreme_moves > 3 else "NORMAL",
        "strength": min(max_dd / 10, 1)
    }


def calculate_all_volatility(df: pd.DataFrame) -> Dict:
    """Calculate all volatility indicators"""
    results = {}
    
    calculators = [
        ("atr", calculate_atr),
        ("bollinger", calculate_bollinger),
        ("keltner", calculate_keltner),
        ("historical_vol", calculate_historical_vol),
        ("parkinson_vol", calculate_parkinson_vol),
        ("nadaraya_watson", calculate_nadaraya_watson),
        ("garch", calculate_garch),
        ("implied_vol", calculate_implied_vol),
        ("cv", calculate_cv),
        ("volatility_ratio", calculate_volatility_ratio),
        ("india_vix", calculate_india_vix),
        ("realized_vol", calculate_realized_vol),
        ("evt", calculate_evt)
    ]
    
    for name, calc in calculators:
        try:
            results[name] = calc(df)
        except Exception as e:
            results[name] = {"indicator": name, "error": str(e)}
    
    return results
