"""Backtest performance and risk metrics.

Pure-numpy summary statistics for a list of closed trades produced by the
scalper backtester (``groww/nifty_scalper_bt.py``), the paper broker, or any
reconciled live-trade log.

Design constraints
------------------
* **Pure numpy** only. No pandas / scipy / sklearn dependency, no DB or network
  access. Every public function in this module is pure: given the same input it
  returns the same output and has no side effects.
* **Defensive by construction.** Empty input, single trade, all-flat P&L,
  zero-variance returns, and all-win / all-loss books must never raise. Every
  division is guarded; degenerate cases collapse to ``0.0`` (or ``inf`` only
  where that is the financially meaningful answer, e.g. profit factor with no
  losing trades).

The single net-P&L field per trade is treated as the realized result *after*
costs and slippage. This module does not model costs itself; the caller (the
backtester) is responsible for putting cost/slippage-adjusted figures into
``net`` so that ``expectancy`` here is a true per-trade edge.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import numpy as np

__all__ = ["compute_metrics"]

_IST = timezone(timedelta(hours=5, minutes=30))


# --------------------------------------------------------------------------- #
# Internal helpers (pure)                                                      #
# --------------------------------------------------------------------------- #
def _extract_net(trades: List[Dict[str, Any]]) -> np.ndarray:
    """Return a 1-D ``float64`` array of the ``net`` field for each trade.

    Trades missing ``net`` or carrying a non-finite / non-numeric value are
    treated as ``0.0`` so a single malformed row cannot poison the whole
    summary or raise mid-computation.

    Args:
        trades: List of trade dicts, each expected to expose a ``net`` key.

    Returns:
        A finite ``float64`` ndarray with one element per trade.
    """
    out = np.zeros(len(trades), dtype=np.float64)
    for i, trade in enumerate(trades):
        value = trade.get("net", 0.0)
        try:
            scalar = float(value)
        except (TypeError, ValueError):
            scalar = 0.0
        if not np.isfinite(scalar):
            scalar = 0.0
        out[i] = scalar
    return out


def _max_drawdown(net: np.ndarray) -> float:
    """Maximum peak-to-trough drawdown of the cumulative net-P&L curve.

    Drawdown is reported as a non-negative magnitude in P&L units (the same
    units as ``net``): the largest drop from a running equity peak. Returns
    ``0.0`` for an empty book or a monotonically non-decreasing curve.

    Args:
        net: 1-D array of per-trade net P&L in chronological order.

    Returns:
        Non-negative float. ``0.0`` when there is no drawdown.
    """
    if net.size == 0:
        return 0.0
    equity = np.cumsum(net)
    running_peak = np.maximum.accumulate(equity)
    drawdowns = running_peak - equity  # >= 0 by construction
    worst = float(np.max(drawdowns)) if drawdowns.size else 0.0
    return worst if worst > 0.0 else 0.0


def _sharpe(net: np.ndarray) -> float:
    """Per-trade Sharpe-style ratio: ``mean(net) / std(net)``.

    This is an un-annualized, per-trade ratio (mean edge divided by the
    dispersion of trade outcomes). Annualization is intentionally left to the
    caller, which must know bars/trades per session to scale correctly --
    blindly multiplying by ``sqrt(252)`` is one of the known modeling bugs this
    codebase is fixing.

    Population standard deviation (``ddof=0``) is used so a single trade yields
    ``std == 0`` and a guarded ``0.0`` rather than a NaN.

    Args:
        net: 1-D array of per-trade net P&L.

    Returns:
        The ratio, or ``0.0`` when ``std`` is zero / non-finite or the book is
        empty.
    """
    if net.size == 0:
        return 0.0
    std = float(np.std(net))
    if std <= 0.0 or not np.isfinite(std):
        return 0.0
    return float(np.mean(net)) / std


def _bucket_stats(net: np.ndarray) -> Dict[str, float]:
    """Count, win-rate, and expectancy for one already-sliced bucket of trades.

    Used both for the whole book and for per-regime slices to keep the win /
    expectancy definitions identical everywhere.

    A win is ``net > 0`` (a flat ``net == 0`` scratch is neither win nor loss
    for win-rate purposes but is still included in count and expectancy).

    Args:
        net: 1-D array of per-trade net P&L for this bucket.

    Returns:
        Mapping with ``count`` (int), ``win_rate`` (fraction in ``[0, 1]``) and
        ``expectancy`` (mean net per trade).
    """
    count = int(net.size)
    if count == 0:
        return {"count": 0, "win_rate": 0.0, "expectancy": 0.0}
    wins = int(np.count_nonzero(net > 0.0))
    win_rate = wins / count
    expectancy = float(np.mean(net))
    return {"count": count, "win_rate": win_rate, "expectancy": expectancy}


def _ts_to_dt(ts: Any):
    """Coerce a candle timestamp (epoch int/float or ISO string) to an IST
    datetime, or None."""
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(float(ts), tz=timezone.utc).astimezone(_IST)
        dt = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_IST)
    except Exception:
        return None


def _sortino(net: np.ndarray) -> float:
    """Per-trade Sortino-style ratio: mean / downside-deviation."""
    if net.size == 0:
        return 0.0
    downside = net[net < 0.0]
    dd = float(np.std(downside)) if downside.size else 0.0
    if dd <= 0.0 or not np.isfinite(dd):
        return 0.0
    return float(np.mean(net)) / dd


def _consecutive(net: np.ndarray):
    """(max_consecutive_wins, max_consecutive_losses)."""
    mw = ml = cw = cl = 0
    for v in net:
        if v > 0:
            cw += 1; cl = 0; mw = max(mw, cw)
        elif v < 0:
            cl += 1; cw = 0; ml = max(ml, cl)
        else:
            cw = cl = 0
    return mw, ml


def _frac_bucket(value: Any) -> str:
    """Bucket a 0-1 (or 0-100) score into labeled bands; 'unknown' if non-numeric."""
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 'unknown'
    if c != c:
        return 'unknown'
    if c > 1.0:
        c /= 100.0
    if c < 0.5:
        return '0.0-0.5'
    if c < 0.6:
        return '0.5-0.6'
    if c < 0.7:
        return '0.6-0.7'
    if c < 0.8:
        return '0.7-0.8'
    return '0.8-1.0'


def _extended_metrics(trades: List[Dict[str, Any]], net: np.ndarray) -> Dict[str, Any]:
    """Additional metrics, equity/drawdown/daily curves, and time/regime/score
    breakdowns. Safe for an empty book (returns zeros + empty collections)."""
    n = int(net.size)
    wins = net[net > 0.0]
    losses = net[net < 0.0]
    gross_profit = float(np.sum(wins)) if wins.size else 0.0
    gross_loss = float(-np.sum(losses)) if losses.size else 0.0
    avg_win = float(np.mean(wins)) if wins.size else 0.0
    avg_loss = float(np.mean(losses)) if losses.size else 0.0
    payoff = (avg_win / abs(avg_loss)) if avg_loss != 0 else (float('inf') if avg_win > 0 else 0.0)

    mdd = _max_drawdown(net)
    equity = np.cumsum(net) if n else np.asarray([], dtype=np.float64)
    total_net = float(np.sum(net)) if n else 0.0
    recovery = (total_net / mdd) if mdd > 0 else (float('inf') if total_net > 0 else 0.0)
    peak = float(np.max(equity)) if equity.size else 0.0
    mdd_pct = (mdd / peak * 100.0) if peak > 0 else 0.0
    mw, ml = _consecutive(net)

    holds = [t['exit_bar'] - t['entry_bar'] for t in trades
             if isinstance(t.get('exit_bar'), (int, float)) and isinstance(t.get('entry_bar'), (int, float))]
    avg_hold = float(np.mean(holds)) if holds else 0.0

    equity_curve: List[Dict[str, Any]] = []
    dd_curve: List[Dict[str, Any]] = []
    daily: Dict[str, float] = {}
    tod: Dict[int, List[float]] = {}
    wd: Dict[str, List[float]] = {}
    confb: Dict[str, List[float]] = {}
    pwinb: Dict[str, List[float]] = {}
    run_peak = 0.0
    for i, (t, v) in enumerate(zip(trades, net)):
        cum = float(equity[i])
        run_peak = max(run_peak, cum)
        dt = _ts_to_dt(t.get('exit_time') or t.get('entry_time'))
        tlabel = dt.isoformat() if dt else None
        equity_curve.append({'i': i, 'equity': round(cum, 2), 'time': tlabel})
        dd_curve.append({'i': i, 'drawdown': round(run_peak - cum, 2), 'time': tlabel})
        if dt:
            day = dt.strftime('%Y-%m-%d')
            daily[day] = daily.get(day, 0.0) + float(v)
            tod.setdefault(dt.hour, []).append(float(v))
            wd.setdefault(dt.strftime('%a'), []).append(float(v))
        confb.setdefault(_frac_bucket(t.get('confidence')), []).append(float(v))
        pw = (t.get('signal_meta') or {}).get('p_win', t.get('p_win'))
        pwinb.setdefault(_frac_bucket(pw) if pw is not None else 'none', []).append(float(v))

    daily_pnl = [{'date': d, 'net': round(p, 2)} for d, p in sorted(daily.items())]
    best_day = float(max(daily.values())) if daily else 0.0
    worst_day = float(min(daily.values())) if daily else 0.0
    n_days = len(daily)

    def _b(d):
        return {k: _bucket_stats(np.asarray(v, dtype=np.float64)) for k, v in d.items()}

    return {
        'loss_rate': float(losses.size) / n if n else 0.0,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'payoff_ratio': payoff,
        'sortino': _sortino(net),
        'recovery_factor': recovery,
        'max_drawdown_pct': mdd_pct,
        'avg_holding_bars': avg_hold,
        'trades_per_day': (n / n_days) if n_days else 0.0,
        'best_day': best_day,
        'worst_day': worst_day,
        'trading_days': n_days,
        'max_consecutive_wins': mw,
        'max_consecutive_losses': ml,
        'equity_curve': equity_curve,
        'drawdown_curve': dd_curve,
        'daily_pnl': daily_pnl,
        'by_time_of_day': {str(k): _bucket_stats(np.asarray(v, dtype=np.float64)) for k, v in sorted(tod.items())},
        'by_weekday': _b(wd),
        'by_confidence_bucket': _b(confb),
        'by_p_win_bucket': _b(pwinb),
    }


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #
def compute_metrics(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute summary performance and risk metrics for a list of trades.

    Each trade dict must expose at least a ``net`` field (realized P&L after
    costs/slippage). Optional fields used when present:

    * ``regime`` (str): market-regime label used to build the ``by_regime``
      breakdown. Missing / empty labels are bucketed under ``"unknown"``.
    * ``entry_time`` (str): accepted for forward compatibility (e.g. ordering /
      time-of-day analysis); not used by this function but documented so
      callers know it is preserved upstream.

    All statistics are computed with pure numpy and every division is guarded.

    Args:
        trades: Chronologically ordered list of closed-trade dicts. Order
            matters only for ``max_drawdown`` (cumulative curve); all other
            metrics are order-invariant. An empty list is valid and yields a
            fully zeroed result.

    Returns:
        Dict with keys:

        * ``count`` (int): number of trades.
        * ``total_net`` (float): sum of net P&L.
        * ``win_rate`` (float): fraction of trades with ``net > 0`` in
          ``[0, 1]``.
        * ``avg_win`` (float): mean net of winning trades (``0.0`` if none).
        * ``avg_loss`` (float): mean net of losing trades, a negative number
          (``0.0`` if none).
        * ``expectancy`` (float): mean net per trade.
        * ``profit_factor`` (float): gross profit / gross loss. ``0.0`` when
          there is no gross profit; ``inf`` when there is profit but no loss.
        * ``max_drawdown`` (float): largest peak-to-trough drop of the
          cumulative net curve, as a non-negative magnitude.
        * ``sharpe`` (float): per-trade ``mean / std`` (un-annualized), guarded
          for ``std == 0``.
        * ``by_regime`` (dict): ``{regime: {count, win_rate, expectancy}}``.

    Raises:
        Never raises on malformed/empty input; degenerate values are coerced.
    """
    count = len(trades)

    # Empty book: return a fully-zeroed, type-stable summary.
    if count == 0:
        base = {
            "count": 0,
            "total_net": 0.0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "sharpe": 0.0,
            "by_regime": {},
        }
        base.update(_extended_metrics([], np.zeros(0, dtype=np.float64)))
        return base

    net = _extract_net(trades)

    wins = net[net > 0.0]
    losses = net[net < 0.0]

    total_net = float(np.sum(net))
    win_rate = float(wins.size) / count
    avg_win = float(np.mean(wins)) if wins.size else 0.0
    avg_loss = float(np.mean(losses)) if losses.size else 0.0
    expectancy = float(np.mean(net))

    gross_profit = float(np.sum(wins)) if wins.size else 0.0
    gross_loss = float(-np.sum(losses)) if losses.size else 0.0  # positive magnitude
    if gross_loss > 0.0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0.0:
        profit_factor = float("inf")  # profit with zero loss
    else:
        profit_factor = 0.0  # no profit at all (all flat / all loss handled above)

    max_drawdown = _max_drawdown(net)
    sharpe = _sharpe(net)

    # Per-regime breakdown. Group net values by their (normalized) regime label
    # while preserving chronological order within each bucket.
    regime_nets: Dict[str, List[float]] = {}
    for trade, value in zip(trades, net):
        label = trade.get("regime")
        if not isinstance(label, str) or not label.strip():
            label = "unknown"
        regime_nets.setdefault(label, []).append(float(value))

    by_regime: Dict[str, Dict[str, float]] = {
        label: _bucket_stats(np.asarray(values, dtype=np.float64))
        for label, values in regime_nets.items()
    }

    result = {
        "count": count,
        "total_net": total_net,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": expectancy,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "sharpe": sharpe,
        "by_regime": by_regime,
    }
    result.update(_extended_metrics(trades, net))
    return result
