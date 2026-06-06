"""
Analysis Module - 67 Technical Indicators + Market Direction Engine
"""

from .decision_engine import DecisionEngine, analyze_market, get_signal
from .patterns import detect_all_patterns
from .momentum import calculate_all_momentum
from .volatility import calculate_all_volatility
from .support_resistance import calculate_all_support_resistance

# New Market Direction Engine
from .market_direction_engine import (
    MarketDirectionEngine,
    market_direction_engine,
    analyze_direction,
    get_direction,
    DirectionResult,
    Direction
)

# Timeframe Aggregator
from .timeframe_aggregator import (
    TimeframeAggregator,
    timeframe_aggregator,
    aggregate_to_timeframe,
    aggregate_all_timeframes,
    LiveCandle,
    CandleBuffer
)

__all__ = [
    # Legacy Decision Engine (67 indicators)
    'DecisionEngine',
    'analyze_market',
    'get_signal',
    'detect_all_patterns',
    'calculate_all_momentum',
    'calculate_all_volatility',
    'calculate_all_support_resistance',
    
    # New Market Direction Engine
    'MarketDirectionEngine',
    'market_direction_engine',
    'analyze_direction',
    'get_direction',
    'DirectionResult',
    'Direction',
    
    # Timeframe Aggregator
    'TimeframeAggregator',
    'timeframe_aggregator',
    'aggregate_to_timeframe',
    'aggregate_all_timeframes',
    'LiveCandle',
    'CandleBuffer'
]
