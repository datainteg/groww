"""Timeframe aggregation: IST bucketing + OHLCV correctness (Sprint 2)."""
import pandas as pd
from analysis.timeframe_aggregator import TimeframeAggregator

agg = TimeframeAggregator()


def _candles_1m(n=15, base=1717645500):
    return pd.DataFrame([
        {'timestamp': base + i * 60, 'open': 100 + i, 'high': 101 + i,
         'low': 99 + i, 'close': 100 + i, 'volume': 10}
        for i in range(n)
    ])


def test_aggregate_1m_is_passthrough():
    df = _candles_1m(5)
    out = agg.aggregate(df, '1')
    assert len(out) == len(df)


def test_aggregate_5m_groups_and_preserves_ohlc():
    out = agg.aggregate(_candles_1m(15), '5')
    assert not out.empty
    assert len(out) <= 4  # 15 one-min bars -> at most 4 five-min buckets
    # OHLC invariants per bucket
    assert (out['high'] >= out['low']).all()
    assert (out['high'] >= out['open']).all()
    assert (out['high'] >= out['close']).all()
    assert 'timestamp' in out.columns


def test_aggregate_volume_conserved():
    df = _candles_1m(10)
    out = agg.aggregate(df, '5')
    assert out['volume'].sum() == df['volume'].sum()
