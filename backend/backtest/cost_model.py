"""
Indian NSE F&O OPTIONS cost model for backtesting and paper-fill realism.

This module computes the round-trip transaction costs (statutory charges +
brokerage) and slippage for a single options leg traded on NSE, and combines
them into a net P&L figure.

IMPORTANT - RATES ARE APPROXIMATIONS
====================================
Every statutory rate hard-coded below is an *approximation* of the published
NSE / SEBI / government schedule as understood at the time of writing. Rates
change with budget cycles and exchange circulars, and brokers may round or
batch charges differently. Before relying on these numbers for LIVE P&L or
reconciliation you MUST verify each rate against:

  * the actual Groww contract note / brokerage statement, and
  * the current NSE transaction-charge circular, SEBI turnover-fee schedule,
    and the prevailing STT / stamp-duty / GST rates.

The constants are therefore exposed as module-level names (suffixed with the
basis they apply to) so they can be overridden or audited in one place.

Scope and simplifying assumptions
----------------------------------
* This models ONE options leg, round-trip = one BUY + one SELL.
* ``qty`` is the total number of option units (i.e. lots * lot_size), NOT lots.
* Premium turnover = premium * qty (premium is the per-unit option price).
* STT on options is charged on the SELL side only (on premium turnover).
* Stamp duty is charged on the BUY side only.
* Exchange transaction charge, SEBI turnover fee and GST are charged on the
  total (buy + sell) premium turnover where applicable.
* All amounts are in INR. No rounding is applied internally except where noted;
  callers should round for display only.

Pure functions: no DB, no network, no global state mutation at import time.
"""

from __future__ import annotations

from typing import Dict, TypedDict

# ---------------------------------------------------------------------------
# Rate constants (ALL APPROXIMATE - verify against live broker / NSE circular)
# ---------------------------------------------------------------------------

# Securities Transaction Tax on options: SELL premium turnover.
# Raised 0.0625% -> 0.1% effective 2024-10-01 (Finance Act 2024).
# APPROXIMATION - confirm against your Groww contract note.
STT_RATE_ON_SELL: float = 0.001  # 0.1% of sell premium turnover

# Exchange transaction charge: ~0.03503% of total premium turnover (buy+sell).
# APPROXIMATION - NSE option transaction charge slab, verify current value.
EXCHANGE_TXN_RATE_ON_TURNOVER: float = 0.0003503  # 0.03503%

# SEBI turnover fee: ~0.0001% of total turnover (buy+sell).
# APPROXIMATION - SEBI fee is quoted as Rs.10 per crore = 0.000001 of turnover.
SEBI_RATE_ON_TURNOVER: float = 0.000001  # 0.0001%

# Stamp duty on options: ~0.003% of the BUY premium turnover.
# APPROXIMATION - stamp duty is levied on the buy side only.
STAMP_RATE_ON_BUY: float = 0.00003  # 0.003%

# GST: 18% applied on (brokerage + exchange transaction charge + SEBI fee).
# APPROXIMATION - confirm GST base components with the broker's contract note.
GST_RATE: float = 0.18  # 18%

# Default flat brokerage per executed order (entry and exit are separate orders).
# APPROXIMATION - Groww discount-brokerage style flat fee; verify the plan.
DEFAULT_BROKERAGE_PER_ORDER: float = 20.0

# Default per-leg slippage as a fraction of premium (one-way price give-up).
# APPROXIMATION - depends on liquidity / spread of the specific strike.
DEFAULT_SLIPPAGE_PCT: float = 0.0005  # 0.05%


class ChargesBreakdown(TypedDict):
    """Itemised round-trip charges, all in INR."""

    brokerage: float
    stt: float
    exchange_txn: float
    sebi: float
    gst: float
    stamp: float
    total: float


class NetPnlBreakdown(TypedDict):
    """Net P&L decomposition for a round-trip options trade, all in INR."""

    gross: float
    charges: float
    slippage: float
    net: float


def options_round_trip_charges(
    entry_premium: float,
    exit_premium: float,
    qty: int,
    brokerage_per_order: float = DEFAULT_BROKERAGE_PER_ORDER,
) -> ChargesBreakdown:
    """Compute the full round-trip statutory + brokerage charges for one option leg.

    A "round trip" is one BUY (entry) followed by one SELL (exit). ``qty`` is the
    total number of option units (lots * lot_size).

    Args:
        entry_premium: Per-unit option premium paid on the BUY leg (INR).
        exit_premium: Per-unit option premium received on the SELL leg (INR).
        qty: Total number of option units traded (lots * lot_size). Treated as
            its absolute value.
        brokerage_per_order: Flat brokerage charged per executed order. Applied
            twice (entry + exit). Defaults to ``DEFAULT_BROKERAGE_PER_ORDER``.

    Returns:
        ChargesBreakdown dict with keys ``brokerage``, ``stt``, ``exchange_txn``,
        ``sebi``, ``gst``, ``stamp`` and ``total`` (all INR floats).

    Notes:
        * STT is charged on the SELL premium turnover only.
        * Stamp duty is charged on the BUY premium turnover only.
        * Exchange transaction charge and SEBI fee are charged on the combined
          (buy + sell) premium turnover.
        * GST is 18% of (brokerage + exchange_txn + sebi).
        * All rates are APPROXIMATIONS - see module docstring.
    """
    qty_abs = abs(int(qty))

    buy_turnover = float(entry_premium) * qty_abs
    sell_turnover = float(exit_premium) * qty_abs
    total_turnover = buy_turnover + sell_turnover

    # Flat brokerage on both legs (entry order + exit order).
    brokerage = float(brokerage_per_order) * 2

    # STT: sell side only.
    stt = sell_turnover * STT_RATE_ON_SELL

    # Exchange transaction charge: combined turnover.
    exchange_txn = total_turnover * EXCHANGE_TXN_RATE_ON_TURNOVER

    # SEBI turnover fee: combined turnover.
    sebi = total_turnover * SEBI_RATE_ON_TURNOVER

    # Stamp duty: buy side only.
    stamp = buy_turnover * STAMP_RATE_ON_BUY

    # GST: 18% on (brokerage + exchange txn charge + SEBI fee).
    gst = (brokerage + exchange_txn + sebi) * GST_RATE

    total = brokerage + stt + exchange_txn + sebi + gst + stamp

    return ChargesBreakdown(
        brokerage=brokerage,
        stt=stt,
        exchange_txn=exchange_txn,
        sebi=sebi,
        gst=gst,
        stamp=stamp,
        total=total,
    )


def slippage(premium: float, pct: float = DEFAULT_SLIPPAGE_PCT) -> float:
    """Return the one-way slippage amount (INR per unit) for a given premium.

    Slippage models the adverse price give-up versus the quoted/last price when
    crossing the spread on a market order. It is expressed as a fraction of the
    premium and is direction-agnostic (always non-negative).

    Args:
        premium: Per-unit option premium the slippage is computed against (INR).
        pct: Slippage as a fraction of premium (e.g. ``0.0005`` = 0.05%).
            Defaults to ``DEFAULT_SLIPPAGE_PCT``. APPROXIMATION - tune per
            instrument liquidity.

    Returns:
        Non-negative slippage amount per unit, in INR.
    """
    return abs(float(premium)) * abs(float(pct))


def net_pnl(
    entry_premium: float,
    exit_premium: float,
    qty: int,
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
    brokerage_per_order: float = DEFAULT_BROKERAGE_PER_ORDER,
) -> NetPnlBreakdown:
    """Compute net P&L for a round-trip options trade after charges and slippage.

    Models a long-option round trip: BUY at ``entry_premium`` then SELL at
    ``exit_premium``, for ``qty`` total units. Gross P&L is
    ``(exit_premium - entry_premium) * qty``. Slippage is applied on BOTH legs
    (entry and exit) as a per-unit give-up, and statutory + brokerage charges
    are subtracted via :func:`options_round_trip_charges`.

    Args:
        entry_premium: Per-unit option premium paid on the BUY leg (INR).
        exit_premium: Per-unit option premium received on the SELL leg (INR).
        qty: Total number of option units traded (lots * lot_size). Treated as
            its absolute value.
        slippage_pct: Per-leg slippage as a fraction of the leg premium.
            Defaults to ``DEFAULT_SLIPPAGE_PCT``.
        brokerage_per_order: Flat brokerage per order, applied to both legs.
            Defaults to ``DEFAULT_BROKERAGE_PER_ORDER``.

    Returns:
        NetPnlBreakdown dict with keys ``gross``, ``charges``, ``slippage`` and
        ``net`` (all INR floats). ``net = gross - charges - slippage``.

    Notes:
        Charges and slippage are always cost (positive) values that reduce the
        gross P&L. All underlying rates are APPROXIMATIONS - see module
        docstring and verify against the live broker.
    """
    qty_abs = abs(int(qty))

    gross = (float(exit_premium) - float(entry_premium)) * qty_abs

    charges_breakdown = options_round_trip_charges(
        entry_premium=entry_premium,
        exit_premium=exit_premium,
        qty=qty_abs,
        brokerage_per_order=brokerage_per_order,
    )
    charges = charges_breakdown["total"]

    # Slippage applied per unit on both the entry and exit legs.
    slippage_per_unit = slippage(entry_premium, slippage_pct) + slippage(
        exit_premium, slippage_pct
    )
    slippage_total = slippage_per_unit * qty_abs

    net = gross - charges - slippage_total

    return NetPnlBreakdown(
        gross=gross,
        charges=charges,
        slippage=slippage_total,
        net=net,
    )
