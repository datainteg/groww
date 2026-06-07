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

from typing import Any, Dict, List

import numpy as np

__all__ = ["compute_metrics"]


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
        return {
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

    return {
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
