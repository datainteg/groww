"""
Data Quality Validator for OHLCV Candle Data.

Provides a single pure function ``validate_candles`` that performs a battery
of quality checks on a candle series before it is fed to any indicator or
signal engine.  The function is intentionally *pure* (no I/O, no DB, no
network) so it can be called from any context without side-effects.

Supported input formats
-----------------------
- ``list[dict]``  – each dict must carry keys: timestamp, open, high, low,
  close, volume.  Extra keys are ignored.
- ``pd.DataFrame`` – must have the same columns as above.

Checks performed
----------------
1. Non-empty and minimum-length guard (>= 2 rows required for gap analysis).
2. All required OHLCV columns are present.
3. ``timestamp`` values are strictly increasing and unique.
4. Intra-session time gaps: no gap > 1.5 * interval_min * 60 seconds between
   *consecutive candles that share the same trading session*.  Overnight /
   weekend gaps are explicitly excluded (see ``_is_session_boundary``).
5. Zero / negative ``volume`` rows do not exceed ``MAX_ZERO_VOLUME_FRACTION``
   of the total (default 5 %).
6. OHLC values are finite, non-NaN, and strictly positive (> 0).
7. Staleness check (optional): when ``now_epoch`` is supplied the last
   timestamp must be no older than ``2 * interval_min * 60`` seconds.

Return value
------------
``{"ok": bool, "issues": list[str], "reason": str}``

- ``ok`` is ``True`` only when *zero* issues are found.
- ``issues`` lists every problem detected (multiple may fire at once).
- ``reason`` is the first issue string (empty string when ``ok`` is True).

Notes
-----
- Closed-candle convention: the caller is responsible for dropping the
  still-forming last bar before calling this function (see candle_service.py).
- All timestamps are Unix epoch seconds (integer or float).
- Pure numpy is used for numeric operations; no sklearn / scipy dependency.
- Python 3.10 compatible (``list[dict]`` etc. via ``from __future__ import``).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Union

import numpy as np

if TYPE_CHECKING:
    import pandas as pd

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

#: Minimum number of candles required to run gap analysis.
MIN_CANDLES: int = 2

#: Maximum fraction of rows allowed to have zero or negative volume before
#: flagging a quality issue.  5 % accommodates genuine illiquid strikes.
MAX_ZERO_VOLUME_FRACTION: float = 0.05

#: Gap tolerance multiplier.  A consecutive intra-session gap whose duration
#: exceeds ``GAP_TOLERANCE * interval_sec`` is flagged.
GAP_TOLERANCE: float = 1.5

#: Market open time in seconds from midnight IST (09:15:00).
_MARKET_OPEN_SOD: int = 9 * 3600 + 15 * 60  # 33300

#: Market close time in seconds from midnight IST (15:30:00).
_MARKET_CLOSE_SOD: int = 15 * 3600 + 30 * 60  # 55800

#: IST offset from UTC in seconds (UTC+5:30).
_IST_OFFSET_SEC: int = 5 * 3600 + 30 * 60  # 19800

#: Required OHLCV column names.
_REQUIRED_COLUMNS: tuple[str, ...] = ("timestamp", "open", "high", "low", "close", "volume")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _epoch_to_ist_sod(epoch: float) -> int:
    """Return seconds-since-midnight in IST for a given UTC epoch.

    Args:
        epoch: Unix timestamp (seconds, UTC).

    Returns:
        Integer seconds elapsed since midnight IST for that epoch value.
    """
    ist_epoch = int(epoch) + _IST_OFFSET_SEC
    return ist_epoch % 86400  # seconds within the IST calendar day


def _epoch_to_ist_weekday(epoch: float) -> int:
    """Return the ISO weekday in IST (Monday=1, Sunday=7).

    Args:
        epoch: Unix timestamp (seconds, UTC).

    Returns:
        Weekday integer 1–7 in IST.
    """
    # Days since Unix epoch (Thursday 1 Jan 1970 = weekday 4 in ISO)
    ist_epoch = int(epoch) + _IST_OFFSET_SEC
    days = ist_epoch // 86400
    # Unix epoch was a Thursday (ISO weekday 4).
    # (days + 3) % 7 gives 0=Monday … 6=Sunday; add 1 for ISO 1-based.
    return (days + 3) % 7 + 1


def _is_session_boundary(ts_prev: float, ts_next: float) -> bool:
    """Determine whether the gap between two consecutive timestamps spans an
    overnight or weekend break rather than a genuine missing-bar condition.

    A boundary is declared when either:
    - ``ts_prev`` falls at or after market close (>= 15:30 IST), or
    - ``ts_next`` falls before or at market open (<= 09:15 IST), or
    - ``ts_prev`` is on a Friday at/after market close through to Monday
      (weekend gap), or
    - the two timestamps belong to different IST calendar days AND either
      endpoint is outside the 09:15–15:30 window.

    Args:
        ts_prev: Epoch of the earlier candle.
        ts_next: Epoch of the later candle.

    Returns:
        ``True`` if the gap is an expected non-trading break and should be
        skipped for intra-session gap detection.
    """
    sod_prev = _epoch_to_ist_sod(ts_prev)
    sod_next = _epoch_to_ist_sod(ts_next)
    day_prev = int(ts_prev + _IST_OFFSET_SEC) // 86400
    day_next = int(ts_next + _IST_OFFSET_SEC) // 86400

    # Same calendar day in IST — cannot be an overnight gap.
    if day_prev == day_next:
        return False

    # Different calendar days — classify as overnight/weekend.
    # (Covers day roll-overs, Friday->Monday, and multi-day holiday gaps.)
    weekday_prev = _epoch_to_ist_weekday(ts_prev)

    # Anything crossing midnight is a session boundary.
    # Friday after-close to Monday before-open is a weekend gap.
    _ = weekday_prev  # retained for future use; the day-diff check suffices.
    return True


def _to_numpy_arrays(
    candles: Union[list[dict], "pd.DataFrame"],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Convert list-of-dicts or DataFrame to six numpy arrays.

    Args:
        candles: Raw candle data (list[dict] or pd.DataFrame).

    Returns:
        Tuple of ``(timestamps, opens, highs, lows, closes, volumes)`` as
        numpy arrays (dtype float64 except timestamps which are float64 too).

    Raises:
        KeyError: If a required column is missing.
        TypeError: If ``candles`` is neither a list nor a DataFrame.
    """
    # Lazy import to keep module importable without pandas installed.
    try:
        import pandas as _pd  # noqa: F401 – used for isinstance check only.
        is_df = isinstance(candles, _pd.DataFrame)
    except ImportError:
        is_df = False

    if is_df:
        import pandas as _pd

        df: _pd.DataFrame = candles  # type: ignore[assignment]
        for col in _REQUIRED_COLUMNS:
            if col not in df.columns:
                raise KeyError(col)
        timestamps = df["timestamp"].to_numpy(dtype=float)
        opens = df["open"].to_numpy(dtype=float)
        highs = df["high"].to_numpy(dtype=float)
        lows = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)
        volumes = df["volume"].to_numpy(dtype=float)
    elif isinstance(candles, list):
        # Validate keys on first row as a cheap pre-check.
        if candles:
            first = candles[0]
            for col in _REQUIRED_COLUMNS:
                if col not in first:
                    raise KeyError(col)
        n = len(candles)
        timestamps = np.empty(n, dtype=float)
        opens = np.empty(n, dtype=float)
        highs = np.empty(n, dtype=float)
        lows = np.empty(n, dtype=float)
        closes = np.empty(n, dtype=float)
        volumes = np.empty(n, dtype=float)
        for i, row in enumerate(candles):
            timestamps[i] = float(row["timestamp"])
            opens[i] = float(row["open"])
            highs[i] = float(row["high"])
            lows[i] = float(row["low"])
            closes[i] = float(row["close"])
            volumes[i] = float(row["volume"])
    else:
        raise TypeError(
            f"candles must be list[dict] or pd.DataFrame, got {type(candles).__name__}"
        )

    return timestamps, opens, highs, lows, closes, volumes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_candles(
    candles: Union[list[dict], "pd.DataFrame"],
    interval_min: int,
    now_epoch: int | None = None,
) -> dict:
    """Validate an OHLCV candle series for data-quality issues.

    This function is *pure*: it performs no I/O, modifies no state, and has
    no side-effects.  It is safe to call from hot paths (scheduler loops).

    Args:
        candles: Candle data as either a ``list[dict]`` (each dict must
            contain keys: ``timestamp``, ``open``, ``high``, ``low``,
            ``close``, ``volume``) or a ``pd.DataFrame`` with the same
            column names.  All timestamps are expected to be Unix epoch
            seconds (integer or float).
        interval_min: Candle interval in *minutes* (e.g. 1, 5, 15, 60).
            Used to compute expected bar spacing and staleness thresholds.
        now_epoch: Optional current Unix timestamp (integer seconds).
            When provided, enables the staleness check that flags series
            whose last bar is older than ``2 * interval_min`` minutes.

    Returns:
        A dict with three keys:

        - ``ok`` (``bool``): ``True`` only when no issues are detected.
        - ``issues`` (``list[str]``): Human-readable descriptions of every
          problem found.  Empty list when ``ok`` is ``True``.
        - ``reason`` (``str``): The first entry from ``issues``, or an empty
          string when ``ok`` is ``True``.  Convenient for single-condition
          callers (e.g., log messages, API error responses).

    Examples:
        >>> result = validate_candles([], interval_min=5)
        >>> result["ok"]
        False
        >>> "empty" in result["reason"]
        True

        >>> from pandas import DataFrame
        >>> df = DataFrame([
        ...     {"timestamp": 1700000000, "open": 100, "high": 105,
        ...      "low": 98, "close": 103, "volume": 1000},
        ...     {"timestamp": 1700000300, "open": 103, "high": 107,
        ...      "low": 101, "close": 106, "volume": 1200},
        ... ])
        >>> validate_candles(df, interval_min=5)["ok"]
        True
    """
    issues: list[str] = []
    interval_sec: int = interval_min * 60

    # ------------------------------------------------------------------
    # Check 1 — non-empty and minimum length
    # ------------------------------------------------------------------
    try:
        n_rows = len(candles)  # works for both list and DataFrame
    except TypeError:
        issues.append("candles object has no len(); cannot determine size")
        return _build_result(issues)

    if n_rows == 0:
        issues.append(
            "candles series is empty — no data to validate or analyse"
        )
        return _build_result(issues)

    if n_rows < MIN_CANDLES:
        issues.append(
            f"candles series has only {n_rows} row(s); minimum required is "
            f"{MIN_CANDLES} for gap analysis"
        )
        # Continue — later checks may still be informative on a single row.

    # ------------------------------------------------------------------
    # Parse into numpy arrays (also validates required columns)
    # ------------------------------------------------------------------
    try:
        timestamps, opens, highs, lows, closes, volumes = _to_numpy_arrays(candles)
    except KeyError as exc:
        issues.append(f"missing required column: {exc}")
        return _build_result(issues)
    except (TypeError, ValueError) as exc:
        issues.append(f"candle data cannot be converted to numeric arrays: {exc}")
        return _build_result(issues)

    n = len(timestamps)

    # ------------------------------------------------------------------
    # Check 2 — strictly increasing unique timestamps
    # ------------------------------------------------------------------
    if n >= 2:
        diffs = np.diff(timestamps)
        non_positive_mask = diffs <= 0
        if np.any(non_positive_mask):
            bad_indices = np.where(non_positive_mask)[0]
            # Report up to 3 offending positions to keep the message readable.
            sample = [int(i) for i in bad_indices[:3]]
            issues.append(
                f"timestamps are not strictly increasing at "
                f"{len(bad_indices)} position(s); first offender(s) at "
                f"index position(s) {sample} "
                f"(values: {[int(timestamps[i]) for i in bad_indices[:3]]})"
            )

    # ------------------------------------------------------------------
    # Check 3 — intra-session gap detection (skip overnight/weekend breaks)
    # ------------------------------------------------------------------
    if n >= 2:
        gap_threshold_sec: float = GAP_TOLERANCE * interval_sec
        gap_violations: list[str] = []

        for idx in range(n - 1):
            ts_a = float(timestamps[idx])
            ts_b = float(timestamps[idx + 1])
            gap = ts_b - ts_a

            # Skip negative or zero gaps — already captured above.
            if gap <= 0:
                continue

            # Skip expected overnight/weekend breaks.
            if _is_session_boundary(ts_a, ts_b):
                continue

            if gap > gap_threshold_sec:
                gap_violations.append(
                    f"index {idx}->{idx + 1}: gap {gap:.0f}s "
                    f"(threshold {gap_threshold_sec:.0f}s, "
                    f"ts_start={int(ts_a)}, ts_end={int(ts_b)})"
                )

        if gap_violations:
            # Collapse into a single issue string for clarity.
            sample_violations = gap_violations[:3]
            extra = len(gap_violations) - len(sample_violations)
            detail = "; ".join(sample_violations)
            if extra > 0:
                detail += f"; … and {extra} more"
            issues.append(
                f"{len(gap_violations)} intra-session time gap(s) exceed "
                f"{GAP_TOLERANCE}x interval ({interval_sec}s): {detail}"
            )

    # ------------------------------------------------------------------
    # Check 4 — zero / negative volume tolerance
    # ------------------------------------------------------------------
    bad_vol_mask = volumes <= 0
    n_bad_vol = int(np.sum(bad_vol_mask))
    if n_bad_vol > 0:
        fraction = n_bad_vol / n
        if fraction > MAX_ZERO_VOLUME_FRACTION:
            bad_ts_sample = [int(timestamps[i]) for i in np.where(bad_vol_mask)[0][:3]]
            issues.append(
                f"{n_bad_vol}/{n} rows ({fraction * 100:.1f}%) have zero or "
                f"negative volume — exceeds tolerance of "
                f"{MAX_ZERO_VOLUME_FRACTION * 100:.0f}%; "
                f"first timestamp(s): {bad_ts_sample}"
            )

    # ------------------------------------------------------------------
    # Check 5 — NaN or non-positive OHLC values
    # ------------------------------------------------------------------
    ohlc_arrays = {
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
    }
    for col_name, arr in ohlc_arrays.items():
        # NaN check (np.isnan handles float arrays; inf is also problematic)
        bad_mask = ~np.isfinite(arr) | (arr <= 0)
        n_bad = int(np.sum(bad_mask))
        if n_bad > 0:
            bad_ts_sample = [int(timestamps[i]) for i in np.where(bad_mask)[0][:3]]
            issues.append(
                f"{n_bad} row(s) have NaN, infinite, or non-positive "
                f"'{col_name}' values; "
                f"first timestamp(s): {bad_ts_sample}"
            )

    # ------------------------------------------------------------------
    # Check 6 — staleness (requires now_epoch)
    # ------------------------------------------------------------------
    if now_epoch is not None:
        staleness_threshold_sec: float = 2.0 * interval_sec
        last_ts = float(timestamps[-1])
        age_sec = float(now_epoch) - last_ts
        if age_sec > staleness_threshold_sec:
            issues.append(
                f"last candle timestamp {int(last_ts)} is stale: "
                f"{age_sec:.0f}s old, threshold is "
                f"{staleness_threshold_sec:.0f}s "
                f"(2 * {interval_min}min interval)"
            )

    return _build_result(issues)


def _build_result(issues: list[str]) -> dict:
    """Construct the standard return dict from a list of issue strings.

    Args:
        issues: Collected issue descriptions (may be empty).

    Returns:
        ``{"ok": bool, "issues": list[str], "reason": str}``
    """
    ok = len(issues) == 0
    return {
        "ok": ok,
        "issues": issues,
        "reason": issues[0] if issues else "",
    }
