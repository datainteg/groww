"""
Position Sizing Utilities
=========================

Fixed-fractional position sizing for index F&O options scalping on Groww.

The core idea (fixed-fractional / "fixed-risk" sizing) is to risk a constant
fraction of capital on every trade. Given a stop-loss distance expressed in
*points* and the instrument's *lot size*, the per-lot rupee risk is::

    per_lot_risk = sl_points * lot_size

and the number of affordable lots is::

    lots = floor(capital * risk_pct / per_lot_risk)

The result is then clamped by an optional hard cap on lots (``max_lots``) and,
when broker margin information is available, by the number of lots the
available margin can actually fund (``floor(available_margin / margin_per_lot)``).

This module is intentionally dependency-free (pure ``math``) and contains no
DB/network access, so it is safe to import anywhere and trivial to unit-test.

All monetary values are in INR. ``sl_points`` is the stop distance in the
option's premium points (e.g. an entry at 120.0 with a stop at 105.0 is
``sl_points = 15.0``).
"""

from __future__ import annotations

import math
from typing import Optional, TypedDict


class PositionSizeResult(TypedDict):
    """Structured result returned by :func:`position_size`.

    Attributes:
        lots: Number of whole lots to trade (always ``>= 0``).
        quantity: Total quantity (``lots * lot_size``, always ``>= 0``).
        risk_amount: Rupee risk budget for the trade (``capital * risk_pct``,
            clamped to ``>= 0``). This is the *budgeted* risk, not the risk of
            the final clamped position.
        reason: Human-readable explanation. ``"OK"`` on success; a descriptive
            message whenever ``lots == 0`` (invalid input or a binding
            constraint).
    """

    lots: int
    quantity: int
    risk_amount: float
    reason: str


def _zero_result(reason: str, risk_amount: float = 0.0) -> PositionSizeResult:
    """Build a zero-lot result with a given reason and (sanitised) risk amount."""
    safe_risk = risk_amount if (risk_amount is not None and risk_amount > 0) else 0.0
    return PositionSizeResult(
        lots=0,
        quantity=0,
        risk_amount=float(safe_risk),
        reason=reason,
    )


def position_size(
    capital: float,
    risk_pct: float,
    sl_points: float,
    lot_size: int,
    max_lots: Optional[int] = None,
    available_margin: Optional[float] = None,
    margin_per_lot: Optional[float] = None,
) -> PositionSizeResult:
    """Compute a fixed-fractional position size in whole lots.

    The risk budget is ``risk_amount = capital * risk_pct``. The raw lot count
    is ``floor(risk_amount / (sl_points * lot_size))``. The raw count is then
    clamped, in order, by:

    1. ``max_lots`` (hard cap on lots), when provided and ``>= 0``.
    2. ``floor(available_margin / margin_per_lot)`` (margin affordability),
       when both margin inputs are provided and valid.

    The returned ``lots`` is never negative. When the result is zero, ``reason``
    explains why (invalid input or a binding constraint).

    Args:
        capital: Total trading capital in INR. Must be ``> 0``.
        risk_pct: Fraction of capital to risk per trade, expressed as a
            decimal in ``(0, 1]`` (e.g. ``0.01`` for 1%). Must be ``> 0``.
        sl_points: Stop-loss distance in premium points. Must be ``> 0``.
        lot_size: Contract lot size (units per lot). Must be ``> 0``.
        max_lots: Optional hard cap on the number of lots. ``None`` disables
            the cap. A value of ``0`` forces zero lots.
        available_margin: Optional free margin in INR usable for this trade.
            When provided together with ``margin_per_lot``, lots are clamped to
            what the margin can fund.
        margin_per_lot: Optional margin requirement per lot in INR. Must be
            ``> 0`` to be applied. Ignored (with a no-op) when ``available_margin``
            is not also provided.

    Returns:
        A :class:`PositionSizeResult` dict with keys ``lots``, ``quantity``,
        ``risk_amount`` and ``reason``.

    Notes:
        * ``risk_pct`` is expected as a decimal fraction; callers that store it
          as a percent (e.g. ``1`` meaning 1%) must normalise before calling.
        * This function never raises on bad numeric input; instead it returns a
          zero-lot result with an explanatory ``reason``.
    """
    # --- Validate the always-required inputs ---------------------------------
    if not _is_positive_number(capital):
        return _zero_result("Invalid capital: must be a positive number")

    if not _is_positive_number(risk_pct):
        return _zero_result("Invalid risk_pct: must be a positive number")

    if not _is_positive_number(sl_points):
        return _zero_result("Invalid sl_points: must be a positive number")

    if not _is_positive_int(lot_size):
        return _zero_result("Invalid lot_size: must be a positive integer")

    capital = float(capital)
    risk_pct = float(risk_pct)
    sl_points = float(sl_points)
    lot_size = int(lot_size)

    # --- Risk budget ---------------------------------------------------------
    risk_amount = capital * risk_pct

    per_lot_risk = sl_points * lot_size
    if per_lot_risk <= 0:
        # Defensive: cannot happen given the validation above, but guards
        # against any float edge case before dividing.
        return _zero_result("Invalid stop risk: sl_points * lot_size must be > 0", risk_amount)

    # --- Raw fixed-fractional lot count --------------------------------------
    raw_lots = math.floor(risk_amount / per_lot_risk)
    if raw_lots <= 0:
        return _zero_result(
            f"Risk budget too small: ₹{risk_amount:,.2f} < per-lot risk "
            f"₹{per_lot_risk:,.2f}",
            risk_amount,
        )

    lots = raw_lots
    reason = "OK"

    # --- Clamp 1: hard cap on lots -------------------------------------------
    if max_lots is not None:
        try:
            max_lots_int = int(max_lots)
        except (TypeError, ValueError):
            return _zero_result("Invalid max_lots: must be an integer", risk_amount)

        if max_lots_int < 0:
            return _zero_result("Invalid max_lots: must be >= 0", risk_amount)

        if max_lots_int == 0:
            return _zero_result("Capped at max_lots=0", risk_amount)

        if lots > max_lots_int:
            lots = max_lots_int
            reason = f"Capped at max_lots={max_lots_int}"

    # --- Clamp 2: margin affordability ---------------------------------------
    if available_margin is not None and margin_per_lot is not None:
        if not _is_non_negative_number(available_margin):
            return _zero_result("Invalid available_margin: must be a number >= 0", risk_amount)

        if not _is_positive_number(margin_per_lot):
            return _zero_result("Invalid margin_per_lot: must be a positive number", risk_amount)

        affordable_lots = math.floor(float(available_margin) / float(margin_per_lot))
        if affordable_lots <= 0:
            return _zero_result(
                f"Insufficient margin: ₹{float(available_margin):,.2f} cannot fund "
                f"one lot (₹{float(margin_per_lot):,.2f}/lot)",
                risk_amount,
            )

        if lots > affordable_lots:
            lots = affordable_lots
            reason = (
                f"Capped by available margin to {affordable_lots} lot(s) "
                f"(₹{float(margin_per_lot):,.2f}/lot)"
            )

    # --- Final safety net: never negative ------------------------------------
    if lots <= 0:
        return _zero_result("No lots affordable after constraints", risk_amount)

    quantity = lots * lot_size

    return PositionSizeResult(
        lots=int(lots),
        quantity=int(quantity),
        risk_amount=float(risk_amount),
        reason=reason,
    )


def _is_positive_number(value: object) -> bool:
    """Return True for a real, finite, strictly-positive numeric value."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value) and value > 0


def _is_non_negative_number(value: object) -> bool:
    """Return True for a real, finite numeric value >= 0."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value) and value >= 0


def _is_positive_int(value: object) -> bool:
    """Return True for a strictly-positive integer (rejects bool and floats)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return value > 0
