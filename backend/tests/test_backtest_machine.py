"""Backtesting Machine tests: extended metrics, engine no-lookahead/fills, runner."""
import pytest

from backtest import metrics as M
from backtest import engine as E
from backtest import runner as R


# ----------------------------- metrics ----------------------------- #
def test_metrics_extended_keys_on_empty():
    e = M.compute_metrics([])
    for k in ('gross_profit', 'gross_loss', 'payoff_ratio', 'sortino', 'recovery_factor',
              'max_drawdown_pct', 'avg_holding_bars', 'trades_per_day', 'loss_rate',
              'max_consecutive_wins', 'max_consecutive_losses', 'equity_curve',
              'drawdown_curve', 'daily_pnl', 'by_time_of_day', 'by_weekday',
              'by_confidence_bucket', 'by_p_win_bucket'):
        assert k in e


def test_metrics_consecutive_payoff_equity():
    trades = [{'net': 10}, {'net': 20}, {'net': -5}, {'net': -5}, {'net': -5}, {'net': 30}]
    m = M.compute_metrics(trades)
    assert m['max_consecutive_wins'] == 2
    assert m['max_consecutive_losses'] == 3
    assert m['gross_profit'] == 60.0 and m['gross_loss'] == 15.0
    assert len(m['equity_curve']) == 6
    assert m['equity_curve'][-1]['equity'] == 45.0


# ----------------------------- engine ------------------------------ #
def _ramp(n, start=100.0, step=1.0):
    out = []
    for i in range(n):
        o = start + i * step
        out.append({'open': o, 'high': o + 0.5, 'low': o - 0.5, 'close': o + 0.4,
                    'timestamp': 1770000000 + i * 300})
    return out


def test_engine_empty_data():
    res = E.run_backtest([], lambda h: {'signal': 'BULLISH', 'confidence': 1},
                         lot_size=50, sl_points=5, target_points=5)
    assert res['count'] == 0 and res['trades'] == []


def test_engine_next_bar_open_fill_no_lookahead():
    candles = _ramp(10)
    res = E.run_backtest(candles, lambda h: {'signal': 'BULLISH', 'confidence': 0.9},
                         lot_size=50, sl_points=5, target_points=5)
    assert res['trades']
    t = res['trades'][0]
    # Fill is the NEXT bar's open, never the signal bar's close.
    assert t['entry_index'] == candles[t['entry_bar']]['open']
    assert t['entry_bar'] >= 1


def test_engine_pessimistic_sl_tie_break():
    candles = [
        {'open': 100, 'high': 101, 'low': 99, 'close': 100, 'timestamp': 1},   # signal bar
        {'open': 100, 'high': 100, 'low': 100, 'close': 100, 'timestamp': 2},  # fill bar
        {'open': 100, 'high': 120, 'low': 80, 'close': 100, 'timestamp': 3},   # straddles SL+target (managed)
        {'open': 100, 'high': 101, 'low': 99, 'close': 100, 'timestamp': 4},   # trailing bar (so #2 isn't EOD)
    ]
    res = E.run_backtest(
        candles,
        lambda h: {'signal': 'BULLISH', 'confidence': 1} if len(h) == 1 else {'signal': None, 'confidence': 0},
        lot_size=50, sl_points=5, target_points=5)
    assert res['trades'] and res['trades'][0]['exit_reason'] == 'SL'


# ----------------------------- runner ------------------------------ #
def test_date_to_epoch():
    assert R._date_to_epoch('2026-06-05') is not None
    assert R._date_to_epoch(None) is None


def test_decision_fn_threshold(monkeypatch):
    monkeypatch.setattr(R, 'analyze_market',
                        lambda df, sym: {'signal': 'BULLISH', 'confidence': 0.4,
                                         'p_win': 0.6, 'market_regime': 'TRENDING'})
    blocked = R.make_decision_fn('NIFTY', {'min_confidence': 0.6})([{}] * 40)
    assert blocked['signal'] is None
    passed = R.make_decision_fn('NIFTY', {'min_confidence': 0.3})([{}] * 40)
    assert passed['signal'] == 'BULLISH' and passed['regime'] == 'TRENDING'


class _EmptyColl:
    def find(self, *a, **k):
        return []


class _FakeDB:
    def __init__(self):
        self.runs, self.trades, self.reports = {}, {}, {}
        self.signal_log = _EmptyColl()

    def create_backtest_run(self, d):
        self.runs[d['run_id']] = d
        return d['run_id']

    def update_backtest_run(self, rid, u):
        self.runs.setdefault(rid, {}).update(u)
        return True

    def save_backtest_trades(self, rid, t):
        self.trades[rid] = t
        return len(t)

    def save_backtest_report(self, rid, r):
        self.reports[rid] = r
        return True


def test_runner_option_premium_fails(monkeypatch):
    monkeypatch.setattr(R, 'db', _FakeDB())
    res = R.run_backtest_for_user('u', {'symbol': 'NIFTY', 'mode': 'OPTION_PREMIUM'})
    assert res['status'] == 'FAILED' and 'OPTION_PREMIUM' in res['error']


def test_runner_insufficient_data(monkeypatch):
    monkeypatch.setattr(R, 'db', _FakeDB())
    monkeypatch.setattr(R, '_load_candles', lambda *a, **k: [])
    res = R.run_backtest_for_user('u', {'symbol': 'NIFTY', 'mode': 'INDEX_PROXY'})
    assert res['status'] == 'FAILED' and 'enough' in res['error'].lower()


def test_runner_happy_path_persists(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr(R, 'db', fake)
    monkeypatch.setattr(R, '_load_candles', lambda *a, **k: _ramp(50))
    monkeypatch.setattr(R, 'analyze_market',
                        lambda df, sym: {'signal': 'BULLISH', 'confidence': 0.9,
                                         'p_win': 0.7, 'market_regime': 'TRENDING'})
    res = R.run_backtest_for_user('u', {'symbol': 'NIFTY', 'mode': 'INDEX_PROXY',
                                        'parameters': {'sl_points': 5, 'target_points': 5}})
    assert res['status'] == 'COMPLETED'
    rid = res['run_id']
    assert fake.runs[rid]['status'] == 'COMPLETED'
    assert rid in fake.reports and 'metrics' in fake.reports[rid]
    assert 'summary' in res and res['summary']['count'] >= 0


def test_walk_forward_runner(monkeypatch):
    monkeypatch.setattr(R, '_load_candles', lambda *a, **k: _ramp(300))
    monkeypatch.setattr(R, 'analyze_market',
                        lambda df, sym: {'signal': 'BULLISH', 'confidence': 0.9,
                                         'market_regime': 'TRENDING'})
    wf = R.run_walk_forward_for_user('u', {'symbol': 'NIFTY', 'train_bars': 100, 'test_bars': 50,
                                           'parameters': {'sl_points': 5, 'target_points': 5}})
    assert wf['ok'] is True and wf['n_windows'] >= 1
    assert 'stability_score' in wf and 'overfit_warning' in wf and 'pooled' in wf


def test_calibrate_insufficient_samples(monkeypatch):
    monkeypatch.setattr(R, 'db', _FakeDB())
    res = R.calibrate_model(min_samples=50)
    assert res['success'] is False and 'Not enough' in res['reason']
