"""Safety-path tests: risk limits, central gate, locking, accuracy gate."""
from types import SimpleNamespace

import pytest

from config import config
from utils.risk_manager import risk_manager
from services import trade_safety
from services.trading_engine import TradingEngine


# --------------------------------------------------------------------------- #
# RiskManager field compatibility + limits
# --------------------------------------------------------------------------- #
def test_strategy_limit_today_orders_blocks():
    ok, reason = risk_manager.can_strategy_trade(
        {'today_orders': 2, 'max_orders_per_day': 2}, {})
    assert not ok and 'orders' in reason.lower()


def test_strategy_limit_backcompat_orders_today():
    # Legacy field name must still be honored.
    ok, reason = risk_manager.can_strategy_trade(
        {'orders_today': 5, 'max_orders_per_day': 2}, {})
    assert not ok


def test_strategy_kill_switch_blocks():
    ok, reason = risk_manager.can_strategy_trade({}, {'kill_switch': True})
    assert not ok and 'kill' in reason.lower()


def test_strategy_loss_limit_blocks():
    ok, reason = risk_manager.can_strategy_trade(
        {'today_pnl': -6000, 'max_loss_limit': 5000}, {})
    assert not ok and 'loss' in reason.lower()


def test_overall_max_concurrent_blocks():
    ok, reason = risk_manager.can_overall_trade({'max_concurrent_trades': 2}, active_trades=2)
    assert not ok


def test_overall_loss_blocks():
    ok, reason = risk_manager.can_overall_trade(
        {'overall_pnl_today': -99999, 'overall_max_loss': 5000}, active_trades=0)
    assert not ok and 'loss' in reason.lower()


# --------------------------------------------------------------------------- #
# acquire_user_trade_lock — PAPER fails open, LIVE fails closed (no Redis)
# --------------------------------------------------------------------------- #
def test_lock_paper_fails_open_without_redis(monkeypatch):
    monkeypatch.setattr(trade_safety, '_redis', lambda: None)
    monkeypatch.setattr(trade_safety, 'get_user_execution_mode', lambda uid: 'PAPER')
    with trade_safety.acquire_user_trade_lock('u1') as ok:
        assert ok is True


def test_lock_live_fails_closed_without_redis(monkeypatch):
    monkeypatch.setattr(trade_safety, '_redis', lambda: None)
    with trade_safety.acquire_user_trade_lock('u1', 'LIVE') as ok:
        assert ok is False


# --------------------------------------------------------------------------- #
# validate_trade_allowed master gate
# --------------------------------------------------------------------------- #
class _FakeColl:
    def __init__(self, doc=None):
        self._doc = doc

    def find_one(self, *a, **k):
        return self._doc


class _FakeDB:
    def __init__(self, settings=None, active=0, dup=None):
        self._settings = settings or {}
        self._active = active
        self.trades = _FakeColl(dup)

    def get_settings(self, uid):
        return self._settings

    def get_active_trades(self, uid):
        return [{}] * self._active


def _patch_gate(monkeypatch, mode, fake_db):
    monkeypatch.setattr(trade_safety, 'db', fake_db)
    monkeypatch.setattr(trade_safety, 'get_user_execution_mode', lambda uid: mode)
    monkeypatch.setattr(trade_safety, 'check_data_freshness', lambda *a, **k: (True, 'OK'))
    monkeypatch.setattr(trade_safety, 'check_broker_feed_health', lambda *a, **k: (True, 'OK'))


_GOOD_STRATEGY = {'_id': 's1', 'today_orders': 0, 'max_orders_per_day': 5,
                  'today_pnl': 0, 'max_profit_limit': 10000, 'max_loss_limit': 5000}


def test_gate_kill_switch_blocks(monkeypatch):
    _patch_gate(monkeypatch, 'PAPER', _FakeDB(settings={'kill_switch': True}))
    d = trade_safety.validate_trade_allowed('u1', strategy=_GOOD_STRATEGY, source='AUTO')
    assert d['blocked'] and 'kill_switch' in d['reason']


def test_gate_live_auto_disabled_blocks(monkeypatch):
    _patch_gate(monkeypatch, 'LIVE', _FakeDB())
    monkeypatch.setattr(config, 'AUTO_TRADING_ENABLED', False)
    d = trade_safety.validate_trade_allowed('u1', strategy=_GOOD_STRATEGY, source='AUTO')
    assert d['blocked'] and 'auto' in d['reason'].lower()


def test_gate_duplicate_open_blocks(monkeypatch):
    _patch_gate(monkeypatch, 'PAPER', _FakeDB(dup={'_id': 'open1'}))
    d = trade_safety.validate_trade_allowed('u1', strategy=_GOOD_STRATEGY, source='MANUAL')
    assert d['blocked'] and 'duplicate' in d['reason'].lower()


def test_gate_paper_allows(monkeypatch):
    _patch_gate(monkeypatch, 'PAPER', _FakeDB())
    d = trade_safety.validate_trade_allowed('u1', strategy=_GOOD_STRATEGY, source='AUTO')
    assert d['allowed'] and not d['blocked']


# --------------------------------------------------------------------------- #
# Accuracy gate (LIVE auto-entry)
# --------------------------------------------------------------------------- #
def _engine():
    return TradingEngine.__new__(TradingEngine)


def test_accuracy_gate_requires_calibration(monkeypatch):
    monkeypatch.setattr(config, 'REQUIRE_CALIBRATION_FOR_LIVE', True)
    ok, reason = _engine()._accuracy_gate({'min_confidence': 0}, {'confidence': 0.9})  # no p_win
    assert not ok and 'calibrat' in reason.lower()


def test_accuracy_gate_low_confidence(monkeypatch):
    ok, reason = _engine()._accuracy_gate({'min_confidence': 70}, {'confidence': 0.4, 'p_win': 0.9})
    assert not ok and 'confidence' in reason.lower()


def test_accuracy_gate_pass(monkeypatch):
    monkeypatch.setattr(config, 'REQUIRE_CALIBRATION_FOR_LIVE', False)
    monkeypatch.setattr(config, 'MIN_P_WIN', 0.0)
    ok, reason = _engine()._accuracy_gate({'min_confidence': 0}, {'confidence': 0.8})
    assert ok


def test_data_freshness_no_candles_blocks_live():
    # An unknown symbol has no candles -> LIVE blocks.
    ok, _ = trade_safety.check_data_freshness('NO_SUCH_SYMBOL_ZZZ', '5', mode='LIVE')
    assert ok is False


def test_data_freshness_crash_live_fails_closed_paper_open(monkeypatch):
    from services.candle_service import candle_service

    def _boom(*a, **k):
        raise RuntimeError('checker boom')

    monkeypatch.setattr(candle_service, 'get_candles', _boom)
    assert trade_safety.check_data_freshness('NIFTY', '5', mode='LIVE')[0] is False
    assert trade_safety.check_data_freshness('NIFTY', '5', mode='PAPER')[0] is True


def test_reconcile_live_mismatch_trips_kill_switch(monkeypatch):
    from services import trading_engine as TE

    class _Coll:
        def find(self, *a, **k):
            return []

        def insert_one(self, *a, **k):
            return None

    class _FakeEngineDB:
        def __init__(self):
            self.trades = _Coll()
            self.db = {'reconciliation_mismatch': _Coll()}
            self.killed = None
            self.report = None

        def get_active_trades(self, uid):
            return [{'trading_symbol': 'NIFTY25000CE', 'quantity': 50, 'strategy_id': 's1'}]

        def upsert_settings(self, uid, d):
            self.killed = d

        def save_reconciliation_report(self, uid, r):
            self.report = r

    fake = _FakeEngineDB()
    monkeypatch.setattr(TE, 'db', fake)
    monkeypatch.setattr(TE, 'telegram_alert',
                        type('X', (), {'send_kill_switch_alert': staticmethod(lambda *a, **k: None)})())

    eng = TE.TradingEngine.__new__(TE.TradingEngine)
    eng.user_id = 'u1'
    eng.execution_mode = 'LIVE'
    res = eng.reconcile_positions([])  # broker flat, DB has an open trade -> mismatch
    assert res['healthy'] is False
    assert fake.killed and fake.killed.get('kill_switch') is True
    assert fake.report and fake.report['status'] == 'blocked'


def test_accuracy_gate_low_pwin(monkeypatch):
    monkeypatch.setattr(config, 'MIN_P_WIN', 0.55)
    ok, reason = _engine()._accuracy_gate({'min_confidence': 0}, {'confidence': 0.9, 'p_win': 0.50})
    assert not ok and 'p_win' in reason.lower()
