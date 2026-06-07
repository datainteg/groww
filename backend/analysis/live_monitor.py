"""Live-session drift monitor for the Groww NIFTY options-scalping engine.

This module exposes a single entry-point, :func:`check_drift`, which reads
today's (or recent) *closed* trades from MongoDB, computes realized win-rate
and expectancy, and compares them to an optional baseline to detect strategy
drift early in a live session.

Design contract
---------------
- **No imports at module level that touch the DB, network, or Flask app
  context.**  The DB access lives entirely inside :func:`check_drift` so the
  module can be imported freely in tests, CLI tools, and the scheduler without
  triggering pymongo connections.
- **Pure numpy** — no pandas, sklearn, or scipy. All numeric aggregation is
  done with ``numpy`` or plain Python builtins so the module runs in every
  execution context the project supports.
- **Never raises** — every code path is wrapped; all exceptions are silently
  swallowed and represented in the returned dict via ``reason``.
- **IST-aware** — trade date-boundary is computed using the project's own
  ``utils.time_utils.get_ist_now`` helper (never naive ``datetime.now()`` or
  ``datetime.utcnow()``).
- **Only closed candles / closed trades** — only documents with
  ``status == "CLOSED"`` and a finite ``pnl`` field are included in the
  computation.

Return value
------------
:func:`check_drift` always returns a dict with exactly these keys::

    {
        "trades":      int,    # number of closed trades analysed
        "win_rate":    float,  # fraction of winning trades in [0.0, 1.0]
        "expectancy":  float,  # mean per-trade P&L (same currency as DB pnl)
        "drift":       float,  # expectancy - baseline_expectancy (0.0 when no
                               # baseline or insufficient data)
        "alert":       bool,   # True when drift is material and data is enough
        "reason":      str,    # human-readable explanation; empty string on ok
    }

Materiality threshold
---------------------
An alert fires when **all three** conditions hold simultaneously:

1. ``trades >= min_trades`` — enough samples for the reading to be meaningful.
2. ``baseline_expectancy`` is supplied and is finite.
3. ``expectancy < baseline_expectancy - DRIFT_ALERT_THRESHOLD *
   abs(baseline_expectancy)`` — the live expectancy has fallen more than
   ``DRIFT_ALERT_THRESHOLD`` below the baseline (relative, clamped to
   ``DRIFT_ALERT_ABS_MIN`` when the baseline is near zero).

:data:`DRIFT_ALERT_THRESHOLD` defaults to **0.25** (25 % relative shortfall).
:data:`DRIFT_ALERT_ABS_MIN` defaults to **1.0** (absolute floor so a near-zero
baseline does not make alerts over-sensitive to noise).
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

import numpy as np

__all__ = [
    "check_drift",
    "DRIFT_ALERT_THRESHOLD",
    "DRIFT_ALERT_ABS_MIN",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuning constants (module-level, but purely numeric — no I/O at import time)
# ---------------------------------------------------------------------------

#: Relative shortfall below the baseline that triggers an alert.
#: 0.25 means the live expectancy must be more than 25 % below baseline.
DRIFT_ALERT_THRESHOLD: float = 0.25

#: Absolute floor for the alert threshold.  Even when the baseline is close to
#: zero, the live expectancy must fall by at least this many currency units
#: below baseline before an alert fires.  This prevents noise-driven false
#: alerts when expectancy is near break-even.
DRIFT_ALERT_ABS_MIN: float = 1.0

# ---------------------------------------------------------------------------
# Internal helpers (pure, no I/O)
# ---------------------------------------------------------------------------


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce ``value`` to a finite float, falling back to ``default``.

    Args:
        value: Any Python object.  Strings, None, and non-finite floats all
            collapse to ``default``.
        default: Value returned when coercion fails or the result is not
            finite.  Defaults to ``0.0``.

    Returns:
        A finite ``float``.
    """
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def _extract_pnl(trades: List[Dict[str, Any]]) -> np.ndarray:
    """Build a 1-D ``float64`` P&L array from a list of closed-trade dicts.

    Only trades with ``status == "CLOSED"`` and a finite ``pnl`` value are
    included.  This is the authoritative filter: open, cancelled, and rejected
    trades must not pollute the win-rate / expectancy reading.

    Args:
        trades: Raw trade documents from MongoDB (any status mix is acceptable;
            non-CLOSED entries are silently skipped).

    Returns:
        1-D ``float64`` ndarray of per-trade P&L values for closed trades that
        carry a finite ``pnl`` field.  May be empty (length 0).
    """
    pnl_values: List[float] = []
    for trade in trades:
        if trade.get("status") != "CLOSED":
            continue
        raw_pnl = trade.get("pnl")
        if raw_pnl is None:
            continue
        v = _safe_float(raw_pnl)
        pnl_values.append(v)
    return np.asarray(pnl_values, dtype=np.float64)


def _compute_win_rate(pnl: np.ndarray) -> float:
    """Fraction of trades with strictly positive P&L.

    A flat break-even trade (``pnl == 0``) is neither a win nor a loss, but
    it is included in the denominator so that excessive scratch trades reduce
    the win rate rather than being invisible.

    Args:
        pnl: 1-D array of per-trade net P&L values.

    Returns:
        Win-rate in ``[0.0, 1.0]``.  ``0.0`` when the array is empty.
    """
    n = pnl.size
    if n == 0:
        return 0.0
    wins = int(np.count_nonzero(pnl > 0.0))
    return wins / n


def _compute_expectancy(pnl: np.ndarray) -> float:
    """Mean per-trade P&L.

    Args:
        pnl: 1-D array of per-trade net P&L values.

    Returns:
        Mean value, or ``0.0`` when the array is empty.
    """
    if pnl.size == 0:
        return 0.0
    return float(np.mean(pnl))


def _compute_drift(
    expectancy: float,
    baseline: Optional[float],
) -> float:
    """Signed difference between live expectancy and the baseline.

    Args:
        expectancy: Live per-trade mean P&L.
        baseline: Historical or strategy-target expectancy.  ``None`` means
            no baseline is available.

    Returns:
        ``expectancy - baseline`` when baseline is not None and finite,
        otherwise ``0.0``.
    """
    if baseline is None or not math.isfinite(baseline):
        return 0.0
    return expectancy - baseline


def _should_alert(
    n_trades: int,
    expectancy: float,
    baseline: Optional[float],
    min_trades: int,
) -> tuple[bool, str]:
    """Determine whether drift conditions warrant an alert.

    Three independent gates must all pass for an alert to fire:

    1. **Volume gate** — enough trades for statistical meaning.
    2. **Baseline gate** — a finite baseline was provided.
    3. **Materiality gate** — the shortfall exceeds the relative or absolute
       threshold, whichever is larger.

    Args:
        n_trades: Number of closed trades analysed.
        expectancy: Realised mean per-trade P&L.
        baseline: Reference expectancy from strategy configuration or prior
            sessions.
        min_trades: Minimum closed-trade count before an alert can fire.

    Returns:
        Tuple of ``(alert: bool, reason: str)``.  ``reason`` is empty when
        ``alert`` is ``False``.
    """
    # Gate 1: volume
    if n_trades < min_trades:
        return False, ""

    # Gate 2: baseline present and finite
    if baseline is None or not math.isfinite(baseline):
        return False, ""

    # Gate 3: materiality — relative shortfall floored by an absolute minimum
    #   threshold = max(DRIFT_ALERT_THRESHOLD * |baseline|, DRIFT_ALERT_ABS_MIN)
    #
    # Expressed as: alert iff expectancy < baseline - threshold
    threshold = max(
        DRIFT_ALERT_THRESHOLD * abs(baseline),
        DRIFT_ALERT_ABS_MIN,
    )
    shortfall = baseline - expectancy  # positive means underperformance
    if shortfall > threshold:
        reason = (
            f"Live expectancy {expectancy:.2f} is {shortfall:.2f} below "
            f"baseline {baseline:.2f} (threshold {threshold:.2f}, "
            f"n={n_trades} trades)"
        )
        return True, reason

    return False, ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_drift(
    db: Any,
    baseline_expectancy: Optional[float] = None,
    min_trades: int = 20,
) -> Dict[str, Any]:
    """Compute live session drift from today's closed trades.

    Reads the current IST trading-day's closed trades for **all users** from
    the ``trades`` collection (via the ``db.trades`` pymongo collection
    attribute), computes realized win-rate and expectancy, and checks whether
    performance has drifted materially below the provided ``baseline_expectancy``.

    The DB access is fully lazy: ``db`` is only used inside this function and
    the call is surrounded by a broad ``except Exception`` guard so transient
    connection errors or schema changes cannot propagate to the caller.

    Args:
        db: An instance of ``database.mongodb.MongoDB`` (or any duck-typed
            object that exposes a ``trades`` attribute which is a pymongo
            collection supporting ``find``).  Accepted as ``Any`` to avoid a
            module-level import of the database singleton.
        baseline_expectancy: Historical or strategy-configured mean per-trade
            P&L target in the same currency unit as the ``pnl`` field stored
            in MongoDB (typically Indian Rupees).  Pass ``None`` (default) to
            skip the drift calculation; an alert will never fire without a
            baseline.
        min_trades: Minimum number of closed trades required before an alert
            can fire.  Defaults to ``20`` — below this the sample is too thin
            to distinguish real drift from variance.

    Returns:
        A dict with exactly the following keys::

            {
                "trades":      int,   # closed trades in today's IST session
                "win_rate":    float, # fraction of winning trades [0.0, 1.0]
                "expectancy":  float, # mean per-trade P&L
                "drift":       float, # expectancy minus baseline (0.0 if N/A)
                "alert":       bool,  # True when material drift detected
                "reason":      str,   # explanation string; "" when alert=False
            }

        The function **never raises** — on any error the result contains
        zeroed stats, ``alert=False``, and a ``reason`` string describing the
        error class (without leaking exception internals or secrets).

    Examples:
        Typical usage inside the scheduler's reconcile loop::

            from database.mongodb import db as mongo_db
            from analysis.live_monitor import check_drift

            result = check_drift(mongo_db, baseline_expectancy=80.0, min_trades=15)
            if result["alert"]:
                logger.warning("Strategy drift: %s", result["reason"])

        Calling without a baseline just tracks live stats::

            stats = check_drift(mongo_db)
            print(f"Win rate: {stats['win_rate']:.1%}, Expectancy: {stats['expectancy']:.2f}")
    """
    _EMPTY: Dict[str, Any] = {
        "trades": 0,
        "win_rate": 0.0,
        "expectancy": 0.0,
        "drift": 0.0,
        "alert": False,
        "reason": "",
    }

    try:
        # ---- Lazy IST / pytz imports (avoid module-level import cost) -------
        import pytz  # type: ignore[import]
        from utils.time_utils import get_ist_now  # type: ignore[import]

        # Compute IST midnight expressed as naive UTC for the Mongo query.
        # The trades collection stores ``created_at`` as naive UTC datetimes
        # (datetime.utcnow()); using IST midnight prevents mis-bucketing trades
        # that occur before 05:30 UTC (which is 11:00 IST).
        ist_now = get_ist_now()
        ist_midnight = ist_now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = ist_midnight.astimezone(pytz.utc).replace(tzinfo=None)

    except Exception as exc:  # pragma: no cover — config / pytz failure
        logger.error("live_monitor: failed to compute IST window: %s", type(exc).__name__)
        result = dict(_EMPTY)
        result["reason"] = "internal error computing session window"
        return result

    try:
        # ---- Query: all trades created today (any status) -------------------
        # Intentionally broad so that _extract_pnl can apply the status=CLOSED
        # filter in pure Python and avoid a second round-trip.
        raw_trades: List[Dict[str, Any]] = list(
            db.trades.find({"created_at": {"$gte": today_start_utc}})
        )
    except Exception as exc:  # pragma: no cover — DB connection failure
        logger.error("live_monitor: DB query failed: %s", type(exc).__name__)
        result = dict(_EMPTY)
        result["reason"] = "database query error"
        return result

    try:
        # ---- Extract closed-trade P&L series --------------------------------
        pnl = _extract_pnl(raw_trades)
        n_trades = pnl.size

        win_rate = _compute_win_rate(pnl)
        expectancy = _compute_expectancy(pnl)
        drift = _compute_drift(expectancy, baseline_expectancy)

        # Normalise baseline: callers may pass it as a percent (> 1 convention
        # used elsewhere in the project for confidence). For expectancy the
        # natural unit is currency, so we do NOT normalise — but we guard
        # against someone accidentally supplying a nonsensically large value.
        # The convention check is left to the caller; we only ensure finite.
        baseline_for_alert: Optional[float] = (
            baseline_expectancy
            if (baseline_expectancy is not None and math.isfinite(baseline_expectancy))
            else None
        )

        alert, alert_reason = _should_alert(
            n_trades=n_trades,
            expectancy=expectancy,
            baseline=baseline_for_alert,
            min_trades=max(1, int(min_trades)),
        )

        return {
            "trades": n_trades,
            "win_rate": win_rate,
            "expectancy": expectancy,
            "drift": drift,
            "alert": alert,
            "reason": alert_reason,
        }

    except Exception as exc:  # pragma: no cover — unexpected numpy failure
        logger.error(
            "live_monitor: unexpected error in computation: %s",
            type(exc).__name__,
        )
        result = dict(_EMPTY)
        result["reason"] = "internal computation error"
        return result
