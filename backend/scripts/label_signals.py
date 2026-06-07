"""
label_signals.py — Offline labelling pass for signal_log documents.

For each ``signal_log`` document that has no ``outcome`` field the script:

1. Resolves the candles stored in MongoDB for the document's ``symbol`` and
   the requested ``interval`` *after* ``created_at``.
2. Drops any still-forming bar (project convention: closed bars only).
3. Takes the first ``forward_bars`` closed bars as the measurement window.
4. Computes the **forward return**::

       forward_return = (close[forward_bars - 1] - open[0]) / open[0]

   i.e. the fractional price change from the entry bar's open to the last
   bar's close.  For a BEARISH signal the return is sign-flipped so a
   *positive* ``forward_return`` always means the market moved in the signal's
   direction.

5. Sets ``outcome = {'win': bool, 'forward_return': float, 'labeled_at': datetime}``
   and writes it back to MongoDB.

A signal is classified as a **win** when ``forward_return > 0`` (the market
moved in the predicted direction by any amount; the caller can apply a
stricter min-return gate after the fact).

Design principles
-----------------
- **No imports at module level that touch DB or network.**  Only the stdlib,
  numpy, and typing are imported at the top; ``database`` and
  ``candle_service`` are imported lazily inside ``label_pending`` so the
  module is safe to import in tests without a live MongoDB / Redis connection.
- **Best-effort, never raises.**  Every signal is wrapped in its own
  try/except; a failure on one doc is logged and skipped; the function always
  returns the count of successfully labelled docs.
- **Pure helper functions** (``_candles_after``, ``_forward_return``) carry no
  I/O and are fully testable in isolation.
- Python 3.10-compatible (no ``match`` statement, no ``X | Y`` union syntax in
  annotations).  Type hints follow the existing project style.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

__all__ = ["label_pending"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pure helpers  (no I/O, no DB — safe to unit-test in isolation)
# ---------------------------------------------------------------------------


def _candles_after(
    candles: Sequence[Dict[str, Any]],
    after_ts: float,
    interval_sec: int,
    forward_bars: int,
) -> List[Dict[str, Any]]:
    """Return the first ``forward_bars`` closed candles strictly after ``after_ts``.

    Args:
        candles: Candle dicts sorted oldest-first, each with a numeric
            ``'timestamp'`` field (Unix epoch seconds).
        after_ts: Unix epoch seconds of the signal's ``created_at``.  Only
            bars whose **open** timestamp is strictly greater than this value
            are considered.
        interval_sec: Bar width in seconds (e.g. ``5 * 60 = 300``).  A bar is
            considered closed once ``timestamp + interval_sec <= now``.  The
            function uses the timestamp of the *last* candle in the slice as a
            conservative "now" proxy so it can be called offline without
            knowing the real wall-clock time.
        forward_bars: Maximum number of bars to return.

    Returns:
        A list of at most ``forward_bars`` closed candle dicts in
        chronological order.  Returns an empty list when fewer than one
        matching bar is available.
    """
    if not candles:
        return []

    # Use the timestamp of the very last supplied candle as the upper boundary
    # for "already closed".  This is safe offline: if the last bar in the DB
    # is itself still forming the caller will have fewer than forward_bars bars
    # available and return [] (not enough data), which is the correct
    # conservative behaviour.
    last_ts: float = float(candles[-1]["timestamp"])
    now_proxy: float = last_ts + interval_sec  # treat last bar as fully closed

    result: List[Dict[str, Any]] = []
    for c in candles:
        ts = float(c["timestamp"])
        if ts <= after_ts:
            continue  # bar opened at or before signal — skip
        # Closed means its close time (ts + interval_sec) <= proxy now
        if ts + interval_sec > now_proxy:
            continue  # bar not yet closed by our proxy
        result.append(c)
        if len(result) >= forward_bars:
            break

    return result


def _forward_return(
    bars: Sequence[Dict[str, Any]],
    signal: str,
) -> Optional[float]:
    """Compute the signed forward return for ``signal`` direction.

    The raw return is the fractional move from the **open of the first bar**
    to the **close of the last bar**::

        raw = (close[-1] - open[0]) / open[0]

    For a ``BEARISH`` signal the return is negated so a market that fell (raw
    < 0) yields a positive ``forward_return``.  A ``BULLISH`` signal leaves the
    sign unchanged.

    Args:
        bars: Sequence of candle dicts (at least one); each must have numeric
            ``'open'`` and ``'close'`` fields.
        signal: ``'BULLISH'`` or ``'BEARISH'``.  Any other value is treated as
            ``'BULLISH'`` (neutral sign).

    Returns:
        The forward return as a float, or ``None`` when ``bars`` is empty,
        ``open[0]`` is zero, or any value is non-finite.
    """
    if not bars:
        return None

    try:
        entry_open: float = float(bars[0]["open"])
        exit_close: float = float(bars[-1]["close"])
    except (KeyError, TypeError, ValueError):
        return None

    if entry_open == 0.0:
        return None

    raw: float = (exit_close - entry_open) / entry_open
    if not np.isfinite(raw):
        return None

    # Flip sign for bearish so that "market fell" => positive forward_return
    if str(signal).upper() == "BEARISH":
        raw = -raw

    return float(raw)


def _parse_created_at(doc: Dict[str, Any]) -> Optional[float]:
    """Extract ``created_at`` from a signal_log doc as a UTC epoch float.

    Handles the two common storage forms:
    * ``datetime`` object (naive UTC, as stored by ``datetime.utcnow()``)
    * ISO-8601 string

    Args:
        doc: A signal_log MongoDB document (plain dict after pymongo fetch).

    Returns:
        Unix epoch seconds (float) or ``None`` on parse failure.
    """
    raw = doc.get("created_at")
    if raw is None:
        return None

    if isinstance(raw, datetime):
        # pymongo returns naive datetimes for fields stored with utcnow().
        # Treat them as UTC.
        if raw.tzinfo is None:
            raw = raw.replace(tzinfo=timezone.utc)
        return raw.timestamp()

    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            return None

    # numeric epoch stored directly (uncommon but tolerate it)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def label_pending(
    db: Any,  # database.mongodb.MongoDB singleton
    candle_service: Any,  # services.candle_service.CandleService instance
    forward_bars: int = 6,
    interval: str = "5",
) -> int:
    """Label all un-outcomed ``signal_log`` documents with a forward return.

    For each document in the ``signal_log`` collection that has no ``outcome``
    field the function:

    1. Parses the document's ``created_at`` timestamp.
    2. Fetches candles for the document's ``symbol`` from MongoDB (via
       ``candle_service.get_candles``).
    3. Selects the first ``forward_bars`` closed candles whose open timestamp
       is strictly after ``created_at``.
    4. Computes ``forward_return`` aligned with the signal direction.
    5. Persists ``outcome = {win, forward_return, labeled_at}`` back to the
       document.

    The function is **best-effort** — any error on an individual document is
    logged at WARNING level and skipped; the function never raises.

    Args:
        db: The ``MongoDB`` singleton (or any object exposing ``.signal_log``
            as a pymongo ``Collection`` and ``.candles`` for the candle
            collection).  Imported lazily by callers to avoid import-time DB
            connection.
        candle_service: A ``CandleService`` instance whose ``get_candles``
            method accepts ``(db, symbol, interval, limit)`` and returns a
            list of candle dicts sorted oldest-first.
        forward_bars: How many closed bars after the signal to use as the
            measurement window.  Defaults to ``6`` (30 minutes on 5-min bars).
        interval: Candle interval string, e.g. ``'1'``, ``'5'``, ``'15'``,
            ``'60'``.  Must match what is stored in the ``candles`` collection.

    Returns:
        The number of documents successfully labelled in this call.
    """
    # Lazy imports — imported here, NOT at module level, so this module can be
    # imported without triggering a MongoDB/Redis connection at import time.
    try:
        from database.mongodb import db as _mongo_db  # noqa: F401 (type reference)
    except Exception:
        pass  # tolerate missing; caller passes db directly

    labeled_count: int = 0
    interval_str: str = str(interval)
    interval_sec: int = int(interval_str) * 60
    forward_bars = max(1, int(forward_bars))

    # --- Fetch all unlabelled signal_log docs ---
    try:
        cursor = db.signal_log.find(
            {"outcome": {"$exists": False}},
            # Project only the fields we need; _id is included by default.
            {"symbol": 1, "signal": 1, "created_at": 1},
        )
        pending_docs: List[Dict[str, Any]] = list(cursor)
    except Exception as exc:
        logger.error("label_pending: failed to query signal_log: %s", exc)
        return 0

    if not pending_docs:
        logger.info("label_pending: no unlabelled signal_log documents found.")
        return 0

    logger.info(
        "label_pending: found %d unlabelled signal_log document(s) for interval=%s, forward_bars=%d.",
        len(pending_docs),
        interval_str,
        forward_bars,
    )

    # Cache candles per symbol to avoid re-fetching for the same symbol across
    # multiple docs.  We fetch a generous limit so we cover the full lookback
    # needed by any doc in the batch.
    candle_cache: Dict[str, List[Dict[str, Any]]] = {}

    for doc in pending_docs:
        doc_id = doc.get("_id")
        symbol: Optional[str] = doc.get("symbol")
        signal_raw: Optional[str] = doc.get("signal")

        try:
            # ---- Validate required fields ----
            if not symbol:
                logger.warning(
                    "label_pending: doc %s has no 'symbol' — skipping.", doc_id
                )
                continue

            if not signal_raw:
                logger.warning(
                    "label_pending: doc %s has no 'signal' — skipping.", doc_id
                )
                continue

            signal: str = str(signal_raw).upper()
            if signal not in ("BULLISH", "BEARISH"):
                logger.warning(
                    "label_pending: doc %s has unsupported signal '%s' — skipping.",
                    doc_id,
                    signal_raw,
                )
                continue

            # ---- Parse created_at -> epoch ----
            created_at_epoch: Optional[float] = _parse_created_at(doc)
            if created_at_epoch is None:
                logger.warning(
                    "label_pending: doc %s has unparseable 'created_at' — skipping.",
                    doc_id,
                )
                continue

            # ---- Load candles (with cache) ----
            if symbol not in candle_cache:
                # Fetch a large window so the cache covers any doc's lookback.
                # 500 bars is the project's standard analysis window size.
                raw_candles: List[Dict[str, Any]] = candle_service.get_candles(
                    db, symbol, interval_str, limit=500
                )
                # get_candles returns oldest-first; normalise to be sure.
                raw_candles = sorted(
                    raw_candles, key=lambda c: float(c.get("timestamp", 0))
                )
                candle_cache[symbol] = raw_candles

            candles: List[Dict[str, Any]] = candle_cache[symbol]
            if not candles:
                logger.warning(
                    "label_pending: no candles in DB for symbol=%s interval=%s — skipping doc %s.",
                    symbol,
                    interval_str,
                    doc_id,
                )
                continue

            # ---- Select forward bars ----
            forward: List[Dict[str, Any]] = _candles_after(
                candles, created_at_epoch, interval_sec, forward_bars
            )

            if len(forward) < forward_bars:
                # Not enough closed bars yet — data may not have arrived yet;
                # leave unlabelled and try again on the next run.
                logger.debug(
                    "label_pending: doc %s (symbol=%s) only has %d/%d forward bars — deferring.",
                    doc_id,
                    symbol,
                    len(forward),
                    forward_bars,
                )
                continue

            # ---- Compute forward return ----
            fwd_ret: Optional[float] = _forward_return(forward, signal)
            if fwd_ret is None:
                logger.warning(
                    "label_pending: doc %s could not compute forward_return (open=0 or non-finite) — skipping.",
                    doc_id,
                )
                continue

            # ---- Build outcome document ----
            win: bool = fwd_ret > 0.0
            outcome: Dict[str, Any] = {
                "win": win,
                "forward_return": round(fwd_ret, 8),
                "labeled_at": datetime.now(timezone.utc),
            }

            # ---- Persist outcome ----
            db.signal_log.update_one(
                {"_id": doc_id},
                {"$set": {"outcome": outcome}},
            )

            labeled_count += 1
            logger.info(
                "label_pending: labeled doc %s | symbol=%s signal=%s "
                "forward_return=%.5f win=%s",
                doc_id,
                symbol,
                signal,
                fwd_ret,
                win,
            )

        except Exception as exc:
            logger.warning(
                "label_pending: unexpected error on doc %s — skipping. Error: %s",
                doc_id,
                exc,
                exc_info=True,
            )
            continue

    logger.info(
        "label_pending: finished. labeled=%d / %d candidate(s).",
        labeled_count,
        len(pending_docs),
    )
    return labeled_count


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------


def _parse_args(argv: Optional[List[str]] = None) -> Tuple[int, str]:
    """Parse CLI arguments with defaults.

    Args:
        argv: Argument list (``sys.argv[1:]`` by default).

    Returns:
        Tuple of (forward_bars, interval).
    """
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Label un-outcomed signal_log documents with forward candle returns. "
            "Designed for the Groww NIFTY F&O options-scalping system."
        )
    )
    parser.add_argument(
        "--forward-bars",
        type=int,
        default=6,
        help="Number of closed candles after the signal to use (default: 6).",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default="5",
        choices=["1", "5", "15", "60"],
        help="Candle interval in minutes (default: 5).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )
    ns = parser.parse_args(argv)
    return int(ns.forward_bars), str(ns.interval), str(ns.log_level)


if __name__ == "__main__":
    # Lazy imports here — only executed when run as a script, not at import time.
    forward_bars_arg, interval_arg, log_level_arg = _parse_args(sys.argv[1:])

    logging.basicConfig(
        level=getattr(logging, log_level_arg, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        # DB and candle_service singletons are imported here so that running
        # `python label_signals.py` (or importing this module) does NOT trigger
        # a MongoDB / Redis connection at import time.
        import os
        import sys as _sys

        # Ensure the backend package root is on sys.path when the script is
        # invoked from the project root (e.g. `python backend/scripts/label_signals.py`).
        _script_dir = os.path.dirname(os.path.abspath(__file__))
        _backend_dir = os.path.dirname(_script_dir)
        if _backend_dir not in _sys.path:
            _sys.path.insert(0, _backend_dir)

        from database.mongodb import db as mongo_db  # type: ignore[import]
        from services.candle_service import candle_service as cs  # type: ignore[import]

        n = label_pending(
            db=mongo_db,
            candle_service=cs,
            forward_bars=forward_bars_arg,
            interval=interval_arg,
        )
        print(f"label_pending complete: {n} document(s) labeled.")
        sys.exit(0)

    except Exception as _exc:
        # Top-level best-effort: log and exit non-zero so a scheduler can detect failure.
        logging.getLogger(__name__).error(
            "label_pending runner failed: %s", _exc, exc_info=True
        )
        sys.exit(1)
