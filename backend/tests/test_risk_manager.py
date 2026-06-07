"""Risk gating + min_confidence normalization (Sprint 1/4a/5 correctness)."""
from utils.risk_manager import RiskManager as RM


# --- min_confidence normalization (the documented percent-vs-fraction bug) ---
def test_normalize_percent_to_fraction():
    assert RM.normalize_min_confidence(70) == 0.70
    assert RM.normalize_min_confidence(75) == 0.75
    assert RM.normalize_min_confidence(100) == 1.0


def test_normalize_fraction_unchanged():
    assert RM.normalize_min_confidence(0.72) == 0.72


def test_normalize_none_and_invalid_default():
    assert RM.normalize_min_confidence(None) == 0.6
    assert RM.normalize_min_confidence("abc") == 0.6


def test_normalize_zero_defers_to_engine():
    assert RM.normalize_min_confidence(0) == 0


def test_confidence_072_passes_70_fails_75():
    # The core fixed bug: a 0.72 engine confidence must clear a "70" threshold
    # and fail a "75" threshold.
    assert 0.72 >= RM.normalize_min_confidence(70)
    assert 0.72 < RM.normalize_min_confidence(75)


# --- portfolio limits ---
def test_overall_kill_switch_blocks():
    ok, _ = RM.can_overall_trade({'kill_switch': True})
    assert ok is False


def test_overall_max_concurrent():
    assert RM.can_overall_trade({'max_concurrent_trades': 3}, active_trades=3)[0] is False
    assert RM.can_overall_trade({'max_concurrent_trades': 3}, active_trades=2)[0] is True


def test_overall_loss_limit():
    ok, _ = RM.can_overall_trade({'overall_max_loss': 5000, 'overall_pnl_today': -5000})
    assert ok is False


def test_overall_none_settings_ok():
    assert RM.can_overall_trade(None)[0] is True


# --- per-strategy limits ---
def test_strategy_kill_switch_blocks():
    assert RM.can_strategy_trade({}, {'kill_switch': True})[0] is False


def test_strategy_max_orders_blocks():
    assert RM.can_strategy_trade({'orders_today': 2, 'max_orders_per_day': 2})[0] is False


def test_strategy_ok_defaults():
    assert RM.can_strategy_trade({}, {})[0] is True
