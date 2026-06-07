"""Market regime classification for the Groww options-scalping engine.

This module answers a single question that must be settled *before* indicator
fusion: what kind of market are we in right now?

    - ``TRENDING``  : strong directional move (favour momentum / trend follow).
    - ``RANGING``   : low directional strength, mean-reverting chop.
    - ``VOLATILE``  : abnormally expanded range; signals are unreliable and
                      cost/slippage risk is elevated, so size down or stand aside.

The classification is derived from two regime-agnostic measures:

    - ADX(14) -- Wilder's Average Directional Index, a pure directional-strength
      reading (it does not care about up vs down).
    - A *volatility ratio*: recent ATR divided by a longer-lookback ATR. A value
      well above 1.0 means the market is expanding (a volatility spike) relative
      to its own recent baseline; this is what flags the ``VOLATILE`` regime.

Everything here is pure ``numpy`` / ``pandas``. There is no I/O, no DB, no network
and no global state, so the functions are safe to import and unit-test in
isolation and cheap to call inside the 1s direction loop.

Notes for callers
------------------
- All math runs on whatever ``df`` you pass. Per project convention the caller is
  responsible for having already dropped the still-forming last candle so that
  regime detection only ever sees *closed* bars.
- Short / malformed frames degrade gracefully to ``RANGING`` (the most
  conservative regime for an entry gate) rather than raising.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

__all__ = [
    "detect_regime",
    "regime_features",
    "compute_adx",
    "compute_atr",
    "compute_vol_ratio",
    "TRENDING",
    "RANGING",
    "VOLATILE",
    "ADX_TREND_THRESHOLD",
    "VOL_RATIO_THRESHOLD",
]

# --- Regime labels ---------------------------------------------------------
TRENDING: str = "TRENDING"
RANGING: str = "RANGING"
VOLATILE: str = "VOLATILE"

# --- Default tuning constants ----------------------------------------------
# ADX at or above this is treated as a meaningful directional trend.
ADX_TREND_THRESHOLD: float = 25.0
# recent_ATR / long_ATR at or above this flags a volatility expansion.
VOL_RATIO_THRESHOLD: float = 1.5

# Default lookbacks.
_ADX_PERIOD: int = 14
_ATR_PERIOD: int = 14
# Longer ATR baseline used as the denominator of the volatility ratio.
_LONG_ATR_PERIOD: int = 50

_REQUIRED_COLS = ("open", "high", "low", "close")


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------
def _has_columns(df: "pd.DataFrame") -> bool:
    """Return ``True`` if ``df`` is a usable OHLC frame."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return False
    return all(col in df.columns for col in _REQUIRED_COLS)


def _true_range(
    high: np.ndarray, low: np.ndarray, close: np.ndarray
) -> np.ndarray:
    """Vectorised Wilder true range.

    ``tr[i] = max(high[i]-low[i], |high[i]-close[i-1]|, |low[i]-close[i-1]|)``.
    The first element only has the intrabar range available.
    """
    n = len(close)
    tr = np.empty(n, dtype=float)
    if n == 0:
        return tr
    tr[0] = high[0] - low[0]
    if n == 1:
        return tr
    prev_close = close[:-1]
    hl = high[1:] - low[1:]
    hc = np.abs(high[1:] - prev_close)
    lc = np.abs(low[1:] - prev_close)
    tr[1:] = np.maximum(hl, np.maximum(hc, lc))
    return tr


def _wilder_smooth(values: np.ndarray, period: int) -> np.ndarray:
    """Wilder's recursive smoothing (RMA / running moving average).

    The seed is the simple mean of the first ``period`` values; subsequent
    values use ``prev - prev/period + current``-style smoothing. Leading
    positions that cannot be seeded are filled with ``NaN``.
    """
    n = len(values)
    out = np.full(n, np.nan, dtype=float)
    if n < period or period <= 0:
        return out
    seed = float(np.mean(values[:period]))
    out[period - 1] = seed
    prev = seed
    alpha = 1.0 / period
    for i in range(period, n):
        prev = prev + alpha * (values[i] - prev)
        out[i] = prev
    return out


# ---------------------------------------------------------------------------
# Public indicator computations
# ---------------------------------------------------------------------------
def compute_atr(df: "pd.DataFrame", period: int = _ATR_PERIOD) -> float:
    """Wilder ATR over the last ``period`` closed bars.

    Returns ``float('nan')`` when there is insufficient data.
    """
    if not _has_columns(df) or len(df) < period + 1:
        return float("nan")
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    tr = _true_range(high, low, close)
    # Exclude the seed-less first bar from smoothing for stability.
    atr_series = _wilder_smooth(tr[1:], period)
    if atr_series.size == 0:
        return float("nan")
    return float(atr_series[-1])


def compute_adx(df: "pd.DataFrame", period: int = _ADX_PERIOD) -> float:
    """Wilder's ADX(``period``) using the last available value.

    ADX measures *directional strength* irrespective of sign. Needs roughly
    ``2 * period`` bars to produce a stable reading; returns ``float('nan')``
    if the frame is too short.
    """
    n = 0 if df is None or not isinstance(df, pd.DataFrame) else len(df)
    if not _has_columns(df) or n < 2 * period + 1:
        return float("nan")

    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)

    up_move = high[1:] - high[:-1]
    down_move = low[:-1] - low[1:]

    plus_dm = np.where((up_move > down_move) & (up_move > 0.0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0.0), down_move, 0.0)

    tr = _true_range(high, low, close)[1:]

    atr = _wilder_smooth(tr, period)
    plus_dm_s = _wilder_smooth(plus_dm, period)
    minus_dm_s = _wilder_smooth(minus_dm, period)

    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = np.where(atr > 0.0, 100.0 * plus_dm_s / atr, 0.0)
        minus_di = np.where(atr > 0.0, 100.0 * minus_dm_s / atr, 0.0)
        di_sum = plus_di + minus_di
        dx = np.where(di_sum > 0.0, 100.0 * np.abs(plus_di - minus_di) / di_sum, 0.0)

    # DX is only meaningful where the DI components were seeded.
    dx = np.where(np.isnan(atr), np.nan, dx)
    valid_dx = dx[~np.isnan(dx)]
    if valid_dx.size < period:
        return float("nan")
    adx_series = _wilder_smooth(valid_dx, period)
    last = adx_series[-1] if adx_series.size else float("nan")
    return float(last) if not np.isnan(last) else float("nan")


def compute_vol_ratio(
    df: "pd.DataFrame",
    short_period: int = _ATR_PERIOD,
    long_period: int = _LONG_ATR_PERIOD,
) -> float:
    """Recent ATR divided by a longer-baseline ATR.

    Values ``> 1`` mean the market is currently expanding relative to its own
    recent history (a volatility spike); ``~1`` is steady-state; ``< 1`` is
    contraction. Returns ``float('nan')`` when the longer ATR cannot be
    computed or is non-positive.
    """
    if not _has_columns(df) or len(df) < long_period + 1:
        return float("nan")
    short_atr = compute_atr(df, short_period)
    long_atr = compute_atr(df, long_period)
    if np.isnan(short_atr) or np.isnan(long_atr) or long_atr <= 0.0:
        return float("nan")
    return float(short_atr / long_atr)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def regime_features(
    df: "pd.DataFrame",
    adx_period: int = _ADX_PERIOD,
    atr_period: int = _ATR_PERIOD,
    long_atr_period: int = _LONG_ATR_PERIOD,
) -> Dict[str, float]:
    """Compute the raw regime inputs from an OHLC frame.

    Parameters
    ----------
    df:
        DataFrame containing at least ``open``, ``high``, ``low`` and ``close``
        columns of *closed* candles (caller drops the forming bar).
    adx_period, atr_period, long_atr_period:
        Lookbacks for ADX, the recent ATR and the long baseline ATR.

    Returns
    -------
    dict
        ``{"adx": float, "vol_ratio": float, "atr": float}``. Any value that
        cannot be computed from the supplied data is returned as ``float('nan')``
        rather than raising, so callers can decide how to degrade.
    """
    adx = compute_adx(df, adx_period)
    atr = compute_atr(df, atr_period)
    vol_ratio = compute_vol_ratio(df, atr_period, long_atr_period)
    return {"adx": adx, "vol_ratio": vol_ratio, "atr": atr}


def detect_regime(
    df: "pd.DataFrame",
    adx_value: Optional[float] = None,
    vol_ratio: Optional[float] = None,
    adx_threshold: float = ADX_TREND_THRESHOLD,
    vol_threshold: float = VOL_RATIO_THRESHOLD,
) -> str:
    """Classify the current market regime.

    The decision order matters: a volatility expansion overrides everything,
    because a strong ADX during a vol spike is still an unreliable, costly
    environment to scalp into.

        1. ``vol_ratio >= vol_threshold``  -> ``VOLATILE``
        2. ``adx_value  >= adx_threshold`` -> ``TRENDING``
        3. otherwise                        -> ``RANGING``

    Parameters
    ----------
    df:
        OHLC frame of closed candles. Used to derive ``adx_value`` and/or
        ``vol_ratio`` when they are not supplied by the caller (e.g. when the
        engine already computed ADX for indicator fusion and can pass it in to
        avoid recomputation).
    adx_value:
        Pre-computed ADX. If ``None`` it is computed from ``df``.
    vol_ratio:
        Pre-computed volatility ratio. If ``None`` it is computed from ``df``.
    adx_threshold, vol_threshold:
        Tunable decision boundaries.

    Returns
    -------
    str
        One of ``"TRENDING"``, ``"RANGING"`` or ``"VOLATILE"``. Falls back to
        ``"RANGING"`` (the most conservative entry gate) when neither input is
        available, e.g. a too-short frame.
    """
    if adx_value is None or vol_ratio is None:
        feats = regime_features(df)
        if adx_value is None:
            adx_value = feats["adx"]
        if vol_ratio is None:
            vol_ratio = feats["vol_ratio"]

    have_vol = vol_ratio is not None and not np.isnan(vol_ratio)
    have_adx = adx_value is not None and not np.isnan(adx_value)

    if have_vol and float(vol_ratio) >= vol_threshold:
        return VOLATILE
    if have_adx and float(adx_value) >= adx_threshold:
        return TRENDING
    return RANGING
