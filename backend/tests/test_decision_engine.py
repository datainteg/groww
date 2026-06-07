"""Decision engine signal-fusion correctness (Sprint 4a)."""
import numpy as np
import pandas as pd
from analysis.decision_engine import DecisionEngine

de = DecisionEngine()


def test_weight_profiles_sum_to_one():
    for name, w in DecisionEngine.WEIGHT_PROFILES.items():
        assert abs(sum(w.values()) - 1.0) < 1e-9, f"{name} weights must sum to 1.0"
    assert abs(sum(DecisionEngine.WEIGHTS.values()) - 1.0) < 1e-9


def test_detect_regime():
    assert de._detect_regime({'adx': {'value': 30}}, 'NORMAL') == 'TRENDING'
    assert de._detect_regime({'adx': {'value': 10}}, 'NORMAL') == 'RANGING'
    assert de._detect_regime({'adx': {'value': 30}}, 'HIGH') == 'VOLATILE'
    assert de._detect_regime({}, 'NORMAL') == 'RANGING'  # missing adx -> safe default


def test_patterns_read_signal_not_direction():
    # 'signal' is the real key; 'direction' must be ignored (the fixed bug).
    score, sig = de._analyze_patterns(
        [{'signal': 'BULLISH'}, {'signal': 'BULLISH'}, {'signal': 'BEARISH'}])
    assert sig == 'BULLISH'
    assert de._analyze_patterns([{'direction': 'BULLISH'}])[1] == 'NEUTRAL'


def test_patterns_no_flat_floor():
    # 2 bullish / 1 bearish -> purity 2/3, NOT 2/3 + 0.3.
    score, _ = de._analyze_patterns(
        [{'signal': 'BULLISH'}, {'signal': 'BULLISH'}, {'signal': 'BEARISH'}])
    assert abs(score - (2.0 / 3.0)) < 1e-9


def test_momentum_collapses_correlated_oscillators():
    # 4 correlated oscillators bullish = ONE vote; macd bearish = one vote -> net 0.
    mom = {'rsi': {'signal': 'BULLISH'}, 'stochastic': {'signal': 'BULLISH'},
           'williams_r': {'signal': 'BULLISH'}, 'cci': {'signal': 'BULLISH'},
           'macd': {'signal': 'BEARISH'}}
    assert de._analyze_momentum(mom)[1] == 'NEUTRAL'
    mom2 = dict(mom); mom2['macd'] = {'signal': 'BULLISH'}
    score, sig = de._analyze_momentum(mom2)
    assert sig == 'BULLISH' and abs(score - 1.0) < 1e-9


def test_volume_direction_and_surge_gate():
    df = pd.DataFrame({'volume': [100] * 20 + [300] * 5})  # 3x surge
    score, confirmed, direction = de._analyze_volume(
        df, {'obv': {'signal': 'BULLISH'}, 'ad_line': {'signal': 'BULLISH'}})
    assert direction == 'BULLISH' and confirmed is True
    # Disagreeing flow indicators -> neutral, not confirmed.
    _, c2, d2 = de._analyze_volume(
        df, {'obv': {'signal': 'BULLISH'}, 'ad_line': {'signal': 'BEARISH'}})
    assert d2 == 'NEUTRAL' and c2 is False


def _ohlcv(n=80):
    rng = np.random.default_rng(0)
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    high = close + np.abs(rng.normal(0, 0.3, n))
    low = close - np.abs(rng.normal(0, 0.3, n))
    open_ = close - rng.normal(0, 0.2, n)
    vol = rng.integers(1000, 5000, n)
    ts = [1717645500 + i * 300 for i in range(n)]
    return pd.DataFrame({'timestamp': ts, 'open': open_, 'high': high,
                         'low': low, 'close': close, 'volume': vol})


def test_analyze_smoke_and_net_score_relationship():
    r = de.analyze(_ohlcv(80), 'NIFTY')
    assert isinstance(r, dict)
    assert 0.0 <= float(r.get('confidence', 0)) <= 1.0
    if not r.get('error'):
        assert r.get('signal') in (None, 'BULLISH', 'BEARISH')
        assert r.get('market_regime') in ('TRENDING', 'RANGING', 'VOLATILE')
        # Net-score: confidence == |bullish - bearish| (volatility NOT added).
        assert abs(r['confidence'] - abs(r['bullish_score'] - r['bearish_score'])) < 1e-6
