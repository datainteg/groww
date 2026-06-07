"""
Decision Engine - Main Trading Brain
Combines all 67 indicators to generate signals with confidence scores
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

from .patterns import detect_all_patterns
from .momentum import calculate_all_momentum
from .volatility import calculate_all_volatility
from .support_resistance import calculate_all_support_resistance

try:
    from utils.time_utils import get_ist_now
except Exception:  # keep analysis importable in isolation
    from datetime import datetime as _dt
    def get_ist_now():
        return _dt.now()

# ---------------------------------------------------------------------------
# Feature-flagged accuracy modules — lazy imports; never crash if absent.
# ---------------------------------------------------------------------------
import os as _os_flag
try:
    from .regime import detect_regime as _ext_detect_regime  # type: ignore[import]
    # OPT-IN: the external regime classifier changes weight-profile selection and
    # therefore the entry gate. Keep it OFF by default so live behavior is
    # unchanged until validated in the backtest; enable with USE_REGIME_MODULE=true.
    _HAVE_REGIME_MODULE = _os_flag.getenv('USE_REGIME_MODULE', 'false').lower() == 'true'
except Exception:
    _HAVE_REGIME_MODULE = False

# Calibration model path (relative to this file so it works wherever the
# package root lives).  The model is loaded once on first call and cached.
import os as _os
_CALIBRATION_MODEL_PATH = _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)),
    "..", "models", "calibration.json"
)
_calibration_model = None   # None => not yet attempted; False => failed/absent
_calibration_loaded = False  # sentinel so we only attempt the load once

logger = logging.getLogger(__name__)


def _get_calibration_model():
    """Lazily load the calibration model from JSON (once). Returns the
    Calibrator instance if the file exists and is fitted, otherwise None.
    Never raises — a missing/broken model file is treated as 'no model'."""
    global _calibration_model, _calibration_loaded
    if _calibration_loaded:
        return _calibration_model
    _calibration_loaded = True
    try:
        if not _os.path.isfile(_CALIBRATION_MODEL_PATH):
            _calibration_model = None
            return None
        from .calibration import Calibrator  # type: ignore[import]
        model = Calibrator.load(_CALIBRATION_MODEL_PATH)
        _calibration_model = model if model.is_fitted else None
        if _calibration_model is not None:
            logger.info("Calibration model loaded from %s", _CALIBRATION_MODEL_PATH)
        else:
            logger.debug("Calibration model file exists but is unfitted — skipping p_win.")
    except Exception as exc:
        logger.debug("Could not load calibration model: %s", exc)
        _calibration_model = None
    return _calibration_model


def to_python_type(obj):
    """Convert numpy types to native Python types"""
    if obj is None:
        return None
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float64, np.float32)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, np.ndarray):
        return [to_python_type(x) for x in obj.tolist()]
    if isinstance(obj, dict):
        return {k: to_python_type(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_python_type(x) for x in obj]
    return obj


class DecisionEngine:
    """
    Main Decision Engine
    
    Weights:
    - Patterns: 30%
    - Momentum: 25%
    - Volatility: 15%
    - Support/Resistance: 15%
    - Volume: 15%
    
    Generates BULLISH/BEARISH signal with confidence >= 70%
    """
    
    # Directional weight profiles, each summing to 1.0. Volatility is NOT a
    # directional component — it selects the regime/profile and (later) sizing,
    # and must never be added into the confidence numerator.
    WEIGHT_PROFILES = {
        # Trend regime: momentum + structure lead; reversal patterns down-weighted.
        'TRENDING': {'patterns': 0.20, 'momentum': 0.40, 'support_resistance': 0.25, 'volume': 0.15},
        # Range regime: patterns (reversals) + S/R fades lead; trend momentum muted.
        'RANGING':  {'patterns': 0.35, 'momentum': 0.15, 'support_resistance': 0.30, 'volume': 0.20},
        # Volatile regime: balanced, conviction comes only from broad agreement.
        'VOLATILE': {'patterns': 0.25, 'momentum': 0.25, 'support_resistance': 0.25, 'volume': 0.25},
    }
    # Fallback profile if regime is unknown.
    WEIGHTS = {'patterns': 0.30, 'momentum': 0.30, 'support_resistance': 0.20, 'volume': 0.20}

    # Engine FLOOR for emitting a directional signal on the net-score scale
    # (|bullish-bearish|, weights sum to 1.0). This is a low directional floor;
    # the real gate is each strategy's min_confidence, and 4b calibration will
    # set thresholds empirically from signal_log. 0.70 on the new net scale made
    # the RANGING regime effectively unreachable.
    CONFIDENCE_THRESHOLD = 0.50
    
    def __init__(self):
        self.last_analysis = None
        self.analysis_cache = {}
    
    def analyze(self, df: pd.DataFrame, symbol: str = "UNKNOWN") -> Dict:
        """Run complete analysis and generate signal"""
        if df is None or len(df) < 50:
            return self._empty_result("Insufficient data")
        
        try:
            # 1. Pattern Analysis
            patterns = detect_all_patterns(df)
            pattern_score, pattern_signal = self._analyze_patterns(patterns)
            
            # 2. Momentum Analysis
            momentum = calculate_all_momentum(df)
            momentum_score, momentum_signal = self._analyze_momentum(momentum)
            
            # 3. Volatility Analysis
            volatility = calculate_all_volatility(df)
            volatility_score, volatility_regime = self._analyze_volatility(volatility)
            
            # 4. Support/Resistance Analysis
            sr = calculate_all_support_resistance(df)
            current_price = float(df['close'].iloc[-1])
            sr_score, sr_signal = self._analyze_support_resistance(sr, current_price)
            
            # 5. Volume Analysis (now returns the direction it actually confirms)
            volume_score, volume_confirmed, volume_dir = self._analyze_volume(df, momentum)

            # 6. Regime first, then a regime-specific directional weight profile.
            #    Volatility informs the regime ONLY — never the confidence numerator.
            market_regime = self._detect_regime(momentum, volatility_regime, df=df)
            W = self.WEIGHT_PROFILES.get(market_regime, self.WEIGHTS)

            bullish_score = 0.0
            bearish_score = 0.0

            def _add(sig, score, weight):
                nonlocal bullish_score, bearish_score
                if sig == "BULLISH":
                    bullish_score += float(score) * weight
                elif sig == "BEARISH":
                    bearish_score += float(score) * weight

            _add(pattern_signal, pattern_score, W['patterns'])
            _add(momentum_signal, momentum_score, W['momentum'])
            _add(sr_signal, sr_score, W['support_resistance'])
            # Volume is a binary directional CONFIRM (from OBV/AD): contribute
            # full purity (1.0) when confirmed, keeping every leg on the same
            # purity scale. It confirms a DIRECTION, not "whichever side leads".
            if volume_confirmed:
                _add(volume_dir, 1.0, W['volume'])

            # 7. Net directional conviction. Weights sum to 1.0, so |net| in [0,1].
            #    Conflicting signals (both sides high) correctly yield LOW confidence.
            net = bullish_score - bearish_score
            confidence = min(abs(net), 1.0)

            if confidence >= self.CONFIDENCE_THRESHOLD and net != 0:
                signal = "BULLISH" if net > 0 else "BEARISH"
            else:
                signal = None

            result = {
                "symbol": symbol,
                "signal": signal,
                "confidence": float(confidence),
                "market_regime": market_regime,
                "patterns": to_python_type(patterns[:5]) if patterns else [],
                "pattern_count": int(len(patterns)) if patterns else 0,
                "bullish_score": float(bullish_score),
                "bearish_score": float(bearish_score),
                "net_score": float(net),
                "momentum": {
                    "score": float(momentum_score),
                    "signal": momentum_signal,
                    "details": to_python_type(self._summarize_momentum(momentum))
                },
                "volatility": {
                    "score": float(volatility_score),
                    "regime": volatility_regime,
                    "details": to_python_type(self._summarize_volatility(volatility))
                },
                "support_resistance": {
                    "score": float(sr_score),
                    "signal": sr_signal,
                    "levels": to_python_type(self._summarize_sr(sr))
                },
                "volume": {
                    "score": float(volume_score),
                    "signal": volume_dir,
                    "confirmed": bool(volume_confirmed)
                },
                # Feature breakdown for calibration/logging (4b).
                "components": {
                    "patterns": {"score": float(pattern_score), "signal": pattern_signal},
                    "momentum": {"score": float(momentum_score), "signal": momentum_signal},
                    "support_resistance": {"score": float(sr_score), "signal": sr_signal},
                    "volume": {"score": float(volume_score), "signal": volume_dir, "confirmed": bool(volume_confirmed)},
                    "weights": W
                },
                "current_price": float(current_price),
                "timestamp": get_ist_now().isoformat()
            }

            # Persist the exact feature vector so calibration trains on the SAME
            # features the live p_win uses (logged into signal_log, labeled later).
            result["calibration_features"] = [
                float(confidence), float(bullish_score), float(bearish_score), float(net),
            ]

            # --- Feature-flagged: calibrated P(win) via Calibrator model ---
            # Exposed as an EXTRA field 'p_win' only when the model is loaded
            # and fitted.  The existing 'confidence' gate is NEVER modified.
            try:
                _cal = _get_calibration_model()
                if _cal is not None:
                    import numpy as _np
                    feat_vec = _np.array([[
                        float(confidence),
                        float(bullish_score),
                        float(bearish_score),
                        float(net),
                    ]], dtype=_np.float64)
                    p_win_arr = _cal.predict_proba(feat_vec)
                    result["p_win"] = float(p_win_arr[0])
            except Exception as _cal_exc:
                logger.debug("p_win computation failed: %s", _cal_exc)

            self.last_analysis = result
            return to_python_type(result)
            
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            return self._empty_result(str(e))
    
    def _analyze_patterns(self, patterns: List) -> Tuple[float, str]:
        """Analyze patterns and return score + direction"""
        if not patterns:
            return 0.5, "NEUTRAL"
        
        # Detectors emit the directional field as 'signal' (see patterns/base.py),
        # NOT 'direction' — reading the wrong key silently zeroed the pattern leg.
        bullish = sum(1 for p in patterns if p.get('signal') == 'BULLISH')
        bearish = sum(1 for p in patterns if p.get('signal') == 'BEARISH')
        directional = bullish + bearish
        if directional == 0:
            return 0.5, "NEUTRAL"

        # Score = directional purity (0.5..1.0). No flat +0.3 floor: a single
        # weak pattern no longer reads as high conviction.
        if bullish > bearish:
            return float(bullish) / directional, "BULLISH"
        elif bearish > bullish:
            return float(bearish) / directional, "BEARISH"
        return 0.5, "NEUTRAL"
    
    def _analyze_momentum(self, momentum: Dict) -> Tuple[float, str]:
        """Analyze momentum, collapsing correlated indicators into family votes.

        RSI / Stochastic / Williams %R / CCI are highly correlated oscillators —
        counting all four separately over-weights the oscillator family. We reduce
        them to ONE combined vote, and MACD/ADX to one trend vote, so momentum is
        at most two orthogonal votes (range -2..+2).
        """
        def family_vote(keys: List[str]) -> int:
            b = sum(1 for k in keys if momentum.get(k, {}).get('signal') == "BULLISH")
            s = sum(1 for k in keys if momentum.get(k, {}).get('signal') == "BEARISH")
            return 1 if b > s else (-1 if s > b else 0)

        oscillator_vote = family_vote(['rsi', 'stochastic', 'williams_r', 'cci'])
        # MACD only for the trend vote. ADX is excluded here because it already
        # drives regime selection (_detect_regime) — counting it again would
        # compound the same adx>=25 threshold crossing into the directional score.
        trend_vote = family_vote(['macd'])

        net = oscillator_vote + trend_vote  # -2 .. +2
        if net > 0:
            return float(net) / 2.0, "BULLISH"
        elif net < 0:
            return float(-net) / 2.0, "BEARISH"
        return 0.5, "NEUTRAL"
    
    def _analyze_volatility(self, volatility: Dict) -> Tuple[float, str]:
        """Analyze volatility regime"""
        atr = volatility.get('atr', {})
        bollinger = volatility.get('bollinger', {})
        
        atr_regime = atr.get('regime', 'NORMAL')
        bb_width = bollinger.get('width_percentile', 50)
        
        if atr_regime == "HIGH" or bb_width > 80:
            return 0.8, "HIGH"
        elif atr_regime == "LOW" or bb_width < 20:
            return 0.4, "LOW"
        return 0.6, "NORMAL"
    
    def _analyze_support_resistance(self, sr: Dict, current_price: float) -> Tuple[float, str]:
        """Analyze S/R levels"""
        bullish_signals = 0
        bearish_signals = 0
        key_indicators = ['pivot_points', 'fibonacci', 'vwap', 'ichimoku', 'moving_averages']
        
        for key in key_indicators:
            if key in sr and 'signal' in sr[key]:
                if sr[key]['signal'] == "BULLISH":
                    bullish_signals += 1
                elif sr[key]['signal'] == "BEARISH":
                    bearish_signals += 1
        
        total = bullish_signals + bearish_signals
        if total == 0:
            return 0.5, "NEUTRAL"
        
        if bullish_signals > bearish_signals:
            return float(bullish_signals) / len(key_indicators), "BULLISH"
        elif bearish_signals > bullish_signals:
            return float(bearish_signals) / len(key_indicators), "BEARISH"
        return 0.5, "NEUTRAL"
    
    def _analyze_volume(self, df: pd.DataFrame, momentum: Dict) -> Tuple[float, bool, str]:
        """Analyze volume confirmation and the DIRECTION it supports.

        Returns (score, confirmed, direction). Direction comes from OBV/AD flow,
        so volume confirms an actual side rather than amplifying whichever side
        already leads.
        """
        vol = df['volume'].values
        # Non-overlapping baseline (bars -25..-5) vs the recent window (last 5)
        # so a surge isn't diluted by including itself in the baseline.
        recent = float(np.mean(vol[-5:]))
        if len(vol) >= 25:
            baseline = float(np.mean(vol[-25:-5]))
        elif len(vol) > 5:
            baseline = float(np.mean(vol[:-5]))
        else:
            baseline = recent
        volume_ratio = recent / baseline if baseline > 0 else 1.0

        obv_signal = momentum.get('obv', {}).get('signal', 'NEUTRAL')
        ad_signal = momentum.get('ad_line', {}).get('signal', 'NEUTRAL')

        # Direction = agreement of the volume-flow indicators.
        votes = [s for s in (obv_signal, ad_signal) if s in ("BULLISH", "BEARISH")]
        if votes and all(v == votes[0] for v in votes):
            direction = votes[0]
        else:
            direction = "NEUTRAL"

        # Require a real surge (>1.2x) before confirming, not a coin-flip >1.0.
        confirmed = volume_ratio > 1.2 and direction != "NEUTRAL"
        score = min(volume_ratio / 2, 1.0)

        return float(score), bool(confirmed), direction

    def _detect_regime(self, momentum: Dict, volatility_regime: str,
                        df: "pd.DataFrame | None" = None) -> str:
        """Classify the market regime to pick a directional weight profile.

        Delegates to ``analysis.regime.detect_regime`` when that module is
        available (feature-flagged).  Falls back to the original inline logic
        on any import or runtime error so live trading is never affected by the
        accuracy module's absence or a bug in it.

        Args:
            momentum: Momentum dict from ``calculate_all_momentum``.
            volatility_regime: String regime label from ``_analyze_volatility``.
            df: Optional OHLC DataFrame (closed bars) for the external module
                to compute vol_ratio / ADX from raw data when pre-computed
                values are not available.  May be None — the external module
                degrades gracefully.
        """
        if _HAVE_REGIME_MODULE and df is not None:
            try:
                # Pass pre-computed ADX from the momentum dict to avoid
                # double-computing it inside the external module.
                adx_val = momentum.get('adx', {}).get('value')
                adx_float = float(adx_val) if adx_val is not None else None
                return _ext_detect_regime(df, adx_value=adx_float)
            except Exception as exc:
                logger.debug("regime.detect_regime failed, using fallback: %s", exc)

        # --- Original inline fallback (unchanged behaviour) ---
        if volatility_regime == "HIGH":
            return "VOLATILE"
        adx_val = momentum.get('adx', {}).get('value')
        try:
            if adx_val is not None and float(adx_val) >= 25:
                return "TRENDING"
        except (TypeError, ValueError):
            pass
        return "RANGING"
    
    def _summarize_momentum(self, momentum: Dict) -> Dict:
        """Summarize momentum for details"""
        summary = {}
        for key in ['rsi', 'macd', 'stochastic', 'adx', 'williams_r', 'cci', 'roc', 'mfi']:
            if key in momentum:
                summary[key] = {
                    'value': momentum[key].get('value'),
                    'signal': momentum[key].get('signal')
                }
        return summary
    
    def _summarize_volatility(self, volatility: Dict) -> Dict:
        """Summarize volatility for details"""
        summary = {}
        for key in ['atr', 'bollinger', 'keltner', 'donchian', 'india_vix']:
            if key in volatility:
                summary[key] = {
                    'value': volatility[key].get('value'),
                    'regime': volatility[key].get('regime', 'N/A')
                }
        return summary
    
    def _summarize_sr(self, sr: Dict) -> Dict:
        """Summarize S/R for details"""
        summary = {}
        if 'pivot_points' in sr:
            summary['pivot'] = sr['pivot_points'].get('pivot')
            summary['r1'] = sr['pivot_points'].get('r1')
            summary['r2'] = sr['pivot_points'].get('r2')
            summary['s1'] = sr['pivot_points'].get('s1')
            summary['s2'] = sr['pivot_points'].get('s2')
        if 'vwap' in sr:
            summary['vwap'] = sr['vwap'].get('vwap')
        if 'fibonacci' in sr:
            summary['fib_382'] = sr['fibonacci'].get('level_382')
            summary['fib_500'] = sr['fibonacci'].get('level_500')
            summary['fib_618'] = sr['fibonacci'].get('level_618')
        return summary
    
    def _empty_result(self, error: str = None) -> Dict:
        """Return empty result"""
        return {
            "signal": None,
            "confidence": 0.0,
            "error": error,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_quick_signal(self, df: pd.DataFrame) -> Tuple[Optional[str], float]:
        """Quick signal without full analysis"""
        result = self.analyze(df)
        return result.get('signal'), result.get('confidence', 0.0)


# Singleton instance
decision_engine = DecisionEngine()


def analyze_market(df: pd.DataFrame, symbol: str = "UNKNOWN") -> Dict:
    """Wrapper function for easy import"""
    return decision_engine.analyze(df, symbol)


def get_signal(df: pd.DataFrame) -> Tuple[Optional[str], float]:
    """Get quick signal"""
    return decision_engine.get_quick_signal(df)
