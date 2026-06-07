"""
Options Engine — option-aware entry decisions for index F&O scalping.

This module turns a raw option chain (as returned by the Groww broker, or any
normalised equivalent) into concrete, contract-level entry decisions for the
scalping system.  Where the directional `decision_engine` answers *"which way is
the underlying going?"*, this module answers the follow-up questions that
actually decide whether a trade is worth placing:

  1. **Which strike** should we buy for a given directional bias?  We prefer the
     contract whose ``abs(delta)`` is closest to a target (default 0.40 — a
     slightly-OTM strike that balances premium decay against responsiveness),
     falling back to the nearest-ATM strike when greeks are unavailable.
  2. **Is the contract liquid enough** to scalp without getting chewed up by the
     bid/ask spread or stuck in an empty book?
  3. **Will the expected premium move clear our costs** (slippage + brokerage +
     STT + exchange fees), i.e. is there a positive edge after friction?

Design notes
------------
- Pure functions only.  No I/O, no DB, no network, no global mutable state.
  Safe to import and call from hot scheduler loops or request handlers.
- Pure ``numpy`` for any numeric work; no ``sklearn`` / ``scipy`` dependency.
- **Defensive by construction.**  Real option-chain payloads are messy: greeks
  may be missing, ``oi`` may be ``None``, bid/ask may be absent on illiquid
  strikes, and numeric fields may arrive as strings.  Every accessor tolerates
  missing / malformed fields and never raises on a single bad contract.
- Field-name agnostic.  Broker payloads vary, so each value is read through a
  small alias list (e.g. ``strike`` / ``strike_price``, ``oi`` /
  ``open_interest``, ``last_price`` / ``ltp`` / ``premium``).

Convention reminders for this codebase
--------------------------------------
- Greek ``delta`` is signed: CE deltas are positive (0..1), PE deltas are
  negative (-1..0).  We always compare on ``abs(delta)``.
- ``theta`` is per-day decay and is (almost always) negative for long options.
  ``expected_premium_move`` prorates it across the intraday holding window using
  the IST session length (6.25h = 6.25 * 60 minutes).
- All monetary values (premiums, costs) are in INR per unit (per share of the
  option), consistent with how Groww quotes option LTPs.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

#: Length of one IST trading session in minutes (09:15 -> 15:30 = 6h15m).
#: Used to prorate per-day theta down to the intraday holding horizon.
SESSION_MINUTES: float = 6.25 * 60.0  # 375.0

#: Field-name aliases for robustly reading heterogeneous chain payloads.
_STRIKE_KEYS: tuple[str, ...] = ("strike", "strike_price", "strikePrice")
_DELTA_KEYS: tuple[str, ...] = ("delta",)
_THETA_KEYS: tuple[str, ...] = ("theta",)
_OI_KEYS: tuple[str, ...] = ("oi", "open_interest", "openInterest")
_BID_KEYS: tuple[str, ...] = ("bid", "bid_price", "bidPrice", "best_bid")
_ASK_KEYS: tuple[str, ...] = ("ask", "ask_price", "askPrice", "best_ask", "offer")
_PRICE_KEYS: tuple[str, ...] = ("last_price", "ltp", "premium", "price", "close")
_GREEKS_KEYS: tuple[str, ...] = ("greeks", "greek")


# ---------------------------------------------------------------------------
# Private helpers — all defensive, never raise on a single bad field
# ---------------------------------------------------------------------------


def _to_float(value: object) -> Optional[float]:
    """Coerce an arbitrary value to a finite float, or return ``None``.

    Tolerates ``None``, numeric strings (possibly with surrounding
    whitespace), numpy scalars, ``bool``, and rejects NaN / inf.

    Args:
        value: Any object pulled from a chain payload.

    Returns:
        A finite ``float`` when coercion succeeds and the result is finite;
        otherwise ``None``.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _first(contract: dict, keys: tuple[str, ...]) -> Optional[float]:
    """Return the first coercible-to-float value among ``keys`` in ``contract``.

    Args:
        contract: A single option-chain entry (dict-like).
        keys: Ordered alias keys to try.

    Returns:
        The first finite float found, or ``None`` if none of the keys hold a
        usable numeric value.  Non-dict ``contract`` inputs yield ``None``.
    """
    if not isinstance(contract, dict):
        return None
    for key in keys:
        if key in contract:
            out = _to_float(contract[key])
            if out is not None:
                return out
    return None


def _greek(contract: dict, keys: tuple[str, ...]) -> Optional[float]:
    """Read a greek value, checking both the top level and a nested ``greeks`` dict.

    Some broker payloads inline greeks on the contract (``{"delta": 0.4, ...}``)
    while others nest them (``{"greeks": {"delta": 0.4, ...}}``).  This helper
    transparently handles both shapes.

    Args:
        contract: A single option-chain entry (dict-like).
        keys: Ordered alias keys for the desired greek (e.g. ``_DELTA_KEYS``).

    Returns:
        The greek as a finite float, or ``None`` when absent / malformed.
    """
    if not isinstance(contract, dict):
        return None
    # 1. Top level (most common for the Groww chain payload).
    top = _first(contract, keys)
    if top is not None:
        return top
    # 2. Nested greeks container.
    for gkey in _GREEKS_KEYS:
        nested = contract.get(gkey)
        if isinstance(nested, dict):
            inner = _first(nested, keys)
            if inner is not None:
                return inner
    return None


def _contract_side(contract: dict) -> Optional[str]:
    """Best-effort classification of a contract as ``'CE'`` or ``'PE'``.

    Tries explicit option-type fields first, then the sign of delta, then the
    trading symbol suffix.  Returns ``None`` when the side cannot be inferred.

    Args:
        contract: A single option-chain entry (dict-like).

    Returns:
        ``'CE'``, ``'PE'``, or ``None``.
    """
    if not isinstance(contract, dict):
        return None

    # Explicit option-type field, under a few common names.
    for key in ("option_type", "optionType", "instrument_type", "type", "side"):
        raw = contract.get(key)
        if isinstance(raw, str):
            up = raw.strip().upper()
            if up in ("CE", "CALL"):
                return "CE"
            if up in ("PE", "PUT"):
                return "PE"

    # Trading-symbol suffix (e.g. "NIFTY24...22000CE").
    for key in ("trading_symbol", "tradingSymbol", "symbol", "tradingsymbol"):
        raw = contract.get(key)
        if isinstance(raw, str):
            up = raw.strip().upper()
            if up.endswith("CE"):
                return "CE"
            if up.endswith("PE"):
                return "PE"

    # Fall back to delta sign: CE delta > 0, PE delta < 0.
    delta = _greek(contract, _DELTA_KEYS)
    if delta is not None:
        if delta > 0:
            return "CE"
        if delta < 0:
            return "PE"
    return None


def _mid(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    """Return the bid/ask midpoint when both legs are present and positive."""
    if bid is None or ask is None:
        return None
    if bid <= 0 or ask <= 0:
        return None
    return (bid + ask) / 2.0


def _normalise_side(side: str) -> str:
    """Normalise a requested side string to ``'CE'`` or ``'PE'``.

    Args:
        side: Caller-supplied side; accepts ``CE``/``CALL`` and ``PE``/``PUT``
            in any case, with surrounding whitespace.

    Returns:
        ``'CE'`` or ``'PE'``.

    Raises:
        ValueError: If ``side`` does not denote a call or a put.
    """
    if not isinstance(side, str):
        raise ValueError(f"side must be a string, got {type(side).__name__}")
    up = side.strip().upper()
    if up in ("CE", "CALL", "C"):
        return "CE"
    if up in ("PE", "PUT", "P"):
        return "PE"
    raise ValueError(f"side must be 'CE' or 'PE', got {side!r}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def select_strike(
    option_chain: list[dict],
    spot: float,
    side: str,
    target_delta: float = 0.4,
) -> Optional[dict]:
    """Select the best contract for a directional bias from an option chain.

    Selection logic:
      1. Filter the chain to contracts matching ``side`` (CE for bullish, PE
         for bearish).  When a contract's side cannot be inferred it is *not*
         excluded by the side filter alone — it only participates in the
         delta-based ranking if it carries a delta whose sign matches ``side``;
         otherwise it remains eligible for the ATM fallback.
      2. **Delta path** (preferred): among side-matching contracts that expose a
         finite delta, pick the one whose ``abs(delta)`` is closest to
         ``target_delta``.  Ties break toward the strike nearest ``spot``.
      3. **ATM fallback**: when *no* side-matching contract exposes a delta,
         pick the contract whose strike is nearest to ``spot``.

    The function never mutates ``option_chain`` or its contracts.

    Args:
        option_chain: List of option-chain entries (dict-like).  Each entry may
            carry ``strike``/``strike_price``, ``delta`` (signed; or nested under
            ``greeks``), an option-type / trading-symbol field, etc.  Malformed
            or non-dict entries are skipped.
        spot: Current underlying spot price (must be a finite positive number;
            used for ATM distance and tie-breaking).
        side: ``'CE'`` (calls) or ``'PE'`` (puts); ``'CALL'``/``'PUT'`` also
            accepted.
        target_delta: Target absolute delta to aim for (default ``0.4``).
            Interpreted as a magnitude, so the sign is ignored.

    Returns:
        The selected contract dict (the original object from ``option_chain``,
        not a copy), or ``None`` when no usable contract exists.
    """
    side_norm = _normalise_side(side)
    target_abs = abs(_to_float(target_delta) or 0.0)
    spot_f = _to_float(spot)

    if not isinstance(option_chain, list) or not option_chain:
        return None

    # Build a working list of (contract, strike, abs_delta, side) tuples,
    # tolerating any malformed entries.
    delta_candidates: list[tuple[dict, Optional[float], float]] = []
    atm_candidates: list[tuple[dict, float]] = []

    for contract in option_chain:
        if not isinstance(contract, dict):
            continue

        inferred = _contract_side(contract)
        delta = _greek(contract, _DELTA_KEYS)
        strike = _first(contract, _STRIKE_KEYS)

        # Determine whether this contract belongs to the requested side.
        # If an explicit/inferred side exists it must match; otherwise we use
        # the delta sign as the side proxy for the delta path.
        side_matches: bool
        if inferred is not None:
            side_matches = inferred == side_norm
        elif delta is not None:
            side_matches = (delta >= 0) if side_norm == "CE" else (delta <= 0)
        else:
            # Side unknown and no delta: only usable via ATM fallback.
            side_matches = True

        if not side_matches:
            continue

        # Delta path eligibility: needs a finite delta whose sign matches side.
        if delta is not None:
            sign_ok = (delta >= 0) if side_norm == "CE" else (delta <= 0)
            if sign_ok:
                delta_candidates.append((contract, strike, abs(delta)))

        # ATM fallback eligibility: needs a finite strike.
        if strike is not None:
            atm_candidates.append((contract, strike))

    # ---- Delta path (preferred) -----------------------------------------
    if delta_candidates:
        def _delta_key(item: tuple[dict, Optional[float], float]) -> tuple[float, float]:
            _contract, strike, abs_delta = item
            delta_err = abs(abs_delta - target_abs)
            # Tie-break toward the strike nearest spot (smaller is better).
            if strike is not None and spot_f is not None:
                strike_dist = abs(strike - spot_f)
            else:
                strike_dist = math.inf
            return (delta_err, strike_dist)

        best = min(delta_candidates, key=_delta_key)
        return best[0]

    # ---- ATM fallback ----------------------------------------------------
    if atm_candidates and spot_f is not None:
        best_atm = min(atm_candidates, key=lambda item: abs(item[1] - spot_f))
        return best_atm[0]

    return None


def liquidity_ok(
    contract: dict,
    min_oi: int = 0,
    max_spread_pct: float = 0.05,
) -> bool:
    """Check whether a contract is liquid enough to scalp.

    Two independent gates, both of which must pass:

      - **Open interest**: ``oi >= min_oi``.  When ``oi`` is absent the gate is
        skipped *only if* ``min_oi <= 0`` (no requirement); a positive ``min_oi``
        against a missing ``oi`` fails closed.
      - **Bid/ask spread**: ``(ask - bid) / mid <= max_spread_pct`` where
        ``mid = (bid + ask) / 2``.  When *either* bid or ask is absent (common on
        illiquid strikes where the broker omits a side of the book) this spread
        check is skipped entirely, per the spec.

    Args:
        contract: A single option-chain entry (dict-like).  Reads ``oi`` /
            ``open_interest`` and ``bid`` / ``ask`` (with common aliases).
        min_oi: Minimum acceptable open interest (default ``0`` = no OI floor).
        max_spread_pct: Maximum acceptable relative spread as a fraction
            (default ``0.05`` = 5%).

    Returns:
        ``True`` when every applicable liquidity gate passes; ``False``
        otherwise.  Non-dict input returns ``False``.
    """
    if not isinstance(contract, dict):
        return False

    # --- Open-interest gate ---
    oi = _first(contract, _OI_KEYS)
    if min_oi > 0:
        # A real OI floor is requested: missing OI must fail closed.
        if oi is None or oi < min_oi:
            return False
    else:
        # No OI requirement; still reject an explicitly negative OI as garbage.
        if oi is not None and oi < 0:
            return False

    # --- Spread gate (skipped when bid or ask absent) ---
    bid = _first(contract, _BID_KEYS)
    ask = _first(contract, _ASK_KEYS)
    if bid is not None and ask is not None:
        mid = _mid(bid, ask)
        if mid is None or mid <= 0:
            # Non-positive book — not tradable.
            return False
        spread_pct = (ask - bid) / mid
        # A crossed/locked book (ask < bid) yields a negative spread_pct, which
        # passes the <= ceiling; treat any negative spread as unusable.
        if spread_pct < 0:
            return False
        if spread_pct > max_spread_pct:
            return False

    return True


def expected_premium_move(
    delta: float,
    d_spot: float,
    theta: float = 0.0,
    d_minutes: float = 0.0,
) -> float:
    """Estimate the option premium change over a short holding horizon.

    First-order (delta + theta) approximation of the premium move:

        premium_move = delta * d_spot + theta * (d_minutes / SESSION_MINUTES)

    where ``SESSION_MINUTES`` is one IST trading session (6.25h = 375 min), so
    ``theta`` (a *per-day* decay, normally negative for long options) is prorated
    across the actual intraday holding window.  Gamma and vega are intentionally
    omitted: over a scalping horizon of seconds-to-minutes the delta term
    dominates, and a deliberately conservative theta drag keeps the edge estimate
    honest.

    The directional sign is the caller's responsibility: pass a signed ``delta``
    (positive for CE, negative for PE) and a signed ``d_spot`` (the expected
    underlying move).  For a CE on a +d_spot move the delta term is positive; for
    a PE the negative delta and negative d_spot multiply to a positive premium
    move, as expected.

    Args:
        delta: Option delta (signed). Non-finite / missing values treated as 0.
        d_spot: Expected change in the underlying spot (signed, same units as
            spot). Non-finite / missing values treated as 0.
        theta: Per-day theta of the option (signed, normally negative for long
            positions). Defaults to ``0.0`` (no decay term). Non-finite treated
            as 0.
        d_minutes: Expected holding time in minutes used to prorate theta.
            Defaults to ``0.0`` (no decay applied). Non-finite / negative
            values are clamped to 0.

    Returns:
        Estimated premium move in the same monetary units as the premium
        (INR per option unit). Always a finite float.
    """
    d = _to_float(delta) or 0.0
    ds = _to_float(d_spot) or 0.0
    th = _to_float(theta) or 0.0
    dm = _to_float(d_minutes) or 0.0
    if dm < 0:
        dm = 0.0

    delta_term = d * ds
    theta_term = th * (dm / SESSION_MINUTES) if SESSION_MINUTES > 0 else 0.0
    return float(delta_term + theta_term)


def entry_ok(
    contract: dict,
    spot: float,
    side: str,
    expected_spot_move: float,
    costs: float,
    min_oi: int = 0,
    max_spread_pct: float = 0.05,
) -> dict:
    """Decide whether entering this option contract has positive expected edge.

    Gate (all must hold):
      1. The contract is **liquid** (see :func:`liquidity_ok`).
      2. The **expected premium move strictly exceeds costs**, i.e.
         ``expected_premium_move > costs`` where ``costs`` bundles slippage,
         brokerage, STT and exchange fees (INR per option unit).

    The expected premium move is computed from the contract's own greeks via
    :func:`expected_premium_move`, using a *side-correct* signed delta and a
    *side-correct* signed spot move:

      - For a **CE**, a bullish entry expects a positive spot move; delta is
        positive, so the delta term is positive.
      - For a **PE**, a bearish entry expects the underlying to fall, so we apply
        ``-abs(expected_spot_move)`` against the put's negative delta, again
        yielding a positive premium move.

    ``expected_spot_move`` is therefore supplied as a **magnitude** (the size of
    the anticipated favourable underlying move); this function applies the
    correct sign per ``side``.  Theta drag is excluded here (``d_minutes=0``)
    because the caller does not provide a holding horizon at the gate; the
    conservative comparison is purely directional edge vs. round-trip costs.

    Args:
        contract: The candidate option-chain entry (dict-like). Reads ``delta``
            (signed, possibly nested under ``greeks``) and liquidity fields.
        spot: Current underlying spot (accepted for interface symmetry; not
            required by the gate itself).
        side: ``'CE'`` or ``'PE'`` (``'CALL'``/``'PUT'`` also accepted).
        expected_spot_move: Magnitude of the expected favourable move in the
            underlying (same units as spot). Sign is applied per ``side``.
        costs: Total round-trip friction cost in INR per option unit (slippage +
            brokerage + STT + exchange fees). Compared against the premium move.
        min_oi: Minimum open interest for the liquidity gate (default ``0``).
        max_spread_pct: Maximum relative bid/ask spread for the liquidity gate
            (default ``0.05`` = 5%).

    Returns:
        A dict with keys:

        - ``ok`` (``bool``): ``True`` only when liquid *and* edge-positive.
        - ``reason`` (``str``): ``"ok"`` on success, else a short machine-friendly
          reason (``"not_a_dict"``, ``"illiquid"``, ``"missing_delta"``,
          ``"edge_below_costs"``, ``"bad_side"``).
        - ``expected_premium_move`` (``float`` | ``None``): The computed premium
          move (``None`` when it could not be computed, e.g. delta missing).
    """
    # --- Validate inputs defensively ---
    if not isinstance(contract, dict):
        return {"ok": False, "reason": "not_a_dict", "expected_premium_move": None}

    try:
        side_norm = _normalise_side(side)
    except ValueError:
        return {"ok": False, "reason": "bad_side", "expected_premium_move": None}

    costs_f = _to_float(costs)
    if costs_f is None:
        costs_f = 0.0

    # --- Gate 1: liquidity ---
    if not liquidity_ok(contract, min_oi=min_oi, max_spread_pct=max_spread_pct):
        return {"ok": False, "reason": "illiquid", "expected_premium_move": None}

    # --- Resolve a side-correct signed delta ---
    delta = _greek(contract, _DELTA_KEYS)
    if delta is None:
        return {"ok": False, "reason": "missing_delta", "expected_premium_move": None}

    # Normalise delta sign to the requested side so the edge computation is
    # robust even if the chain reports an unsigned magnitude.
    abs_delta = abs(delta)
    signed_delta = abs_delta if side_norm == "CE" else -abs_delta

    # Side-correct signed spot move: favourable for CE is up, for PE is down.
    move_mag = abs(_to_float(expected_spot_move) or 0.0)
    signed_move = move_mag if side_norm == "CE" else -move_mag

    epm = expected_premium_move(
        delta=signed_delta,
        d_spot=signed_move,
        theta=0.0,
        d_minutes=0.0,
    )

    # --- Gate 2: edge must strictly exceed costs ---
    if epm > costs_f:
        return {"ok": True, "reason": "ok", "expected_premium_move": epm}

    return {
        "ok": False,
        "reason": "edge_below_costs",
        "expected_premium_move": epm,
    }
