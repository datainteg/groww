"""
Event-driven, BAR-CLOSE backtester for the Groww index-options scalping system.

This module runs a single-position, long-premium scalping strategy over a list
of OHLC candles, calling a user-supplied ``decision_fn`` once per *closed* bar.
It is deliberately small, pure, and free of look-ahead so that tuning done here
is trustworthy and matches the LIVE bar-close rule used by the production
schedulers.

Core design principles
----------------------
**1. No look-ahead (the bar-close rule).**
The live engine only ever acts on *closed* candles -- the still-forming last bar
is dropped before any signal math runs. This backtester reproduces that rule
exactly: when evaluating bar ``i`` we pass ``candles[: i + 1]`` to
``decision_fn``, i.e. only bars whose close is already known. Crucially, an
entry triggered by the close of bar ``i`` is filled at the **open of bar
``i + 1``** (the next bar that has not happened yet at decision time), never at
bar ``i``'s own close. This guarantees that no future information leaks into the
fill price.

**2. Single position at a time.**
A new entry is only considered when flat. This mirrors the scalper's
one-position-per-symbol behaviour and keeps position sizing and P&L unambiguous.

**3. Intrabar SL/target priority is conservative.**
While a position is open, each subsequent bar is checked for stop-loss and
target hits using that bar's high/low. When a single bar's range straddles both
the stop and the target we assume the **stop is hit first** (the pessimistic
assumption), since with only OHLC data we cannot know the true intrabar path.

INDEX-POINTS PROXY LIMITATION (read this)
-----------------------------------------
This backtester is fed *index* candles (NIFTY / BANKNIFTY / SENSEX / FINNIFTY
spot or future OHLC), **not** option-premium candles. We therefore use an
**index-points proxy** for the option leg: the per-unit "premium" P&L of a long
option position is approximated by the **index points moved in the trade's
direction**.

Concretely:

* For a BULLISH trade we go long a call proxy: profit per unit is
  ``exit_index - entry_index`` (index points).
* For a BEARISH trade we go long a put proxy: profit per unit is
  ``entry_index - exit_index`` (index points).
* ``sl_points`` / ``target_points`` are interpreted as **index points** of
  adverse / favourable spot movement.

This proxy assumes an option delta of ~1.0 and **ignores** option-specific
effects that dominate real scalping P&L: delta < 1, gamma, theta decay,
implied-vol changes, and the bid/ask spread of the specific strike. It will
systematically **overstate** the favourable moves of out-of-the-money options
and understate theta bleed. The cost model (:mod:`backend.backtest.cost_model`)
is still applied on these proxy premiums, but the gross leg is an index-points
approximation.

**TODO / wiring note:** once per-strike option-premium candles are available,
replace the ``_entry_premium`` / ``_exit_premium`` proxy computation below with
the real option OHLC for the chosen strike/expiry. The trade dicts already carry
``entry_index`` / ``exit_index`` so the index path is preserved for that
upgrade. Until then, treat absolute P&L magnitudes as directional/relative
indicators only -- the *shape* of the equity curve and relative comparisons
between parameterisations are meaningful; the rupee totals are not LIVE-accurate.

Purity
------
No DB, no network, no global mutable state. Importing this module has no side
effects. ``run_backtest`` is deterministic given the same inputs and
``decision_fn``.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# Sibling modules in the ``backtest`` package use relative imports; the
# cross-package position-sizing helper is imported by its top-level module path
# (the codebase is rooted at ``backend/`` on ``sys.path``) and *directly* from
# the submodule so we do not trigger ``utils/__init__`` -- which eagerly imports
# ``encryption`` -> ``config`` and is therefore not import-safe in isolation.
from . import cost_model
from . import metrics
from utils.position_sizing import position_size

__all__ = ["run_backtest", "run_option_premium_backtest", "DecisionFn"]

# A decision function receives the closed-candle history (oldest -> newest, the
# last element being the most recently *closed* bar) and returns at least a
# ``signal`` and a ``confidence``. Any extra keys are preserved onto the trade
# record for downstream analysis (e.g. ``regime``).
DecisionFn = Callable[[List[Dict[str, Any]]], Dict[str, Any]]

# Recognised long/flat signal tokens. Anything else (HOLD, NEUTRAL, None, ...)
# is treated as "no entry".
_BULLISH_TOKENS = frozenset({"BULLISH", "BUY", "LONG", "CE", "CALL"})
_BEARISH_TOKENS = frozenset({"BEARISH", "SELL", "SHORT", "PE", "PUT"})


def _candle_field(candle: Dict[str, Any], *names: str) -> Optional[float]:
    """Return the first present, finite numeric field from ``names``.

    Candle dicts in this codebase use the standard OHLC keys
    (``open``/``high``/``low``/``close``); this helper accepts a few common
    aliases (e.g. single-letter ``o``/``h``/``l``/``c``) so the backtester is
    robust to the exact source of the candle stream.

    Args:
        candle: A single OHLC candle dict.
        *names: Candidate key names, tried in order.

    Returns:
        The first matching value as a ``float``, or ``None`` if no candidate
        key holds a finite number.
    """
    for name in names:
        if name in candle:
            value = candle[name]
            try:
                scalar = float(value)
            except (TypeError, ValueError):
                continue
            # Reject NaN / inf so a single bad bar cannot corrupt fills.
            if scalar == scalar and scalar not in (float("inf"), float("-inf")):
                return scalar
    return None


def _bar_open(candle: Dict[str, Any]) -> Optional[float]:
    """Open price of a candle (``open`` or ``o``)."""
    return _candle_field(candle, "open", "o")


def _bar_high(candle: Dict[str, Any]) -> Optional[float]:
    """High price of a candle (``high`` or ``h``)."""
    return _candle_field(candle, "high", "h")


def _bar_low(candle: Dict[str, Any]) -> Optional[float]:
    """Low price of a candle (``low`` or ``l``)."""
    return _candle_field(candle, "low", "l")


def _bar_close(candle: Dict[str, Any]) -> Optional[float]:
    """Close price of a candle (``close`` or ``c``)."""
    return _candle_field(candle, "close", "c")


def _bar_time(candle: Dict[str, Any]) -> Any:
    """Best-effort timestamp of a candle for trade annotation (may be ``None``)."""
    for name in ("timestamp", "time", "t", "dt", "datetime"):
        if name in candle and candle[name] is not None:
            return candle[name]
    return None


def _normalise_signal(raw: Any) -> Optional[str]:
    """Map an arbitrary signal token to ``"BULLISH"``, ``"BEARISH"`` or ``None``.

    Args:
        raw: The ``signal`` value returned by ``decision_fn`` (any type).

    Returns:
        ``"BULLISH"`` for a long-call intent, ``"BEARISH"`` for a long-put
        intent, or ``None`` for hold / unknown / non-actionable signals.
    """
    if not isinstance(raw, str):
        return None
    token = raw.strip().upper()
    if token in _BULLISH_TOKENS:
        return "BULLISH"
    if token in _BEARISH_TOKENS:
        return "BEARISH"
    return None


def _normalise_confidence(raw: Any) -> float:
    """Coerce a confidence to a ``[0, 1]`` fraction.

    Engine confidence is a 0--1 fraction, but some callers store values on a
    0--100 percent scale; per project convention any value ``> 1`` is divided by
    100. Non-numeric / non-finite inputs collapse to ``0.0``.

    Args:
        raw: The ``confidence`` value from ``decision_fn``.

    Returns:
        A confidence clamped to ``[0.0, 1.0]``.
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if value != value:  # NaN
        return 0.0
    if value > 1.0:
        value /= 100.0
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _resolve_exit(
    direction: str,
    bar: Dict[str, Any],
    stop_price: float,
    target_price: float,
) -> Optional[Dict[str, Any]]:
    """Determine whether a bar triggers the stop-loss or target for an open trade.

    Uses the bar's high/low range. When the range straddles both levels the
    **stop is assumed to fill first** (pessimistic), because the true intrabar
    path is unknown from OHLC data alone.

    Args:
        direction: ``"BULLISH"`` (long-call proxy) or ``"BEARISH"`` (long-put
            proxy).
        bar: The candle being checked while the position is open.
        stop_price: Index-points stop level for the underlying.
        target_price: Index-points target level for the underlying.

    Returns:
        A dict ``{"exit_index": float, "reason": str}`` when an exit is
        triggered, otherwise ``None``. ``reason`` is one of ``"SL"`` / ``"TARGET"``.
    """
    high = _bar_high(bar)
    low = _bar_low(bar)
    if high is None or low is None:
        return None

    if direction == "BULLISH":
        hit_stop = low <= stop_price
        hit_target = high >= target_price
    else:  # BEARISH: stop is above entry, target is below entry
        hit_stop = high >= stop_price
        hit_target = low <= target_price

    # Pessimistic tie-break: stop wins if both are touched in the same bar.
    if hit_stop:
        return {"exit_index": stop_price, "reason": "SL"}
    if hit_target:
        return {"exit_index": target_price, "reason": "TARGET"}
    return None


def run_backtest(
    candles: List[Dict[str, Any]],
    decision_fn: DecisionFn,
    *,
    lot_size: int,
    capital: float = 1_000_000.0,
    risk_pct: float = 0.01,
    sl_points: float,
    target_points: float,
    slippage_pct: float = 0.0005,
    brokerage_per_order: float = 20.0,
) -> Dict[str, Any]:
    """Run an event-driven, bar-close backtest of a long-premium scalping strategy.

    For each closed bar ``i`` the backtester calls ``decision_fn(candles[: i + 1])``
    so the decision function sees *only* already-closed candles -- no look-ahead.
    A fresh BULLISH/BEARISH signal taken while flat is filled at the **open of
    the next bar** (``i + 1``); stop-loss and target are then managed bar by bar
    against the underlying's high/low.

    P&L uses an **index-points proxy** for the option leg (see the module
    docstring): per-unit gross is the index points moved in the trade's
    direction, fed through :func:`backend.backtest.cost_model.net_pnl` for
    realistic charges and slippage. Position size is computed once per trade via
    :func:`backend.utils.position_sizing.position_size`.

    Args:
        candles: Chronologically ordered list (oldest first) of OHLC candle
            dicts. Each must expose ``open``/``high``/``low``/``close`` (single
            letter aliases ``o``/``h``/``l``/``c`` are also accepted). Optional
            ``timestamp`` is recorded on trades. Every candle in the list is
            treated as **closed**; if the caller is streaming live data it must
            drop the still-forming final bar *before* calling this function.
        decision_fn: Callable invoked once per bar as
            ``decision_fn(history) -> dict`` where ``history`` is
            ``candles[: i + 1]``. The returned dict must contain ``signal`` and
            ``confidence``; any additional keys (e.g. ``regime``) are copied onto
            the resulting trade record under ``signal_meta`` and, for ``regime``
            specifically, surfaced at the top level for
            :func:`compute_metrics` bucketing.
        lot_size: Contract lot size (units per lot). Must be a positive integer.
        capital: Total trading capital in INR. Defaults to ``1_000_000``.
        risk_pct: Fraction of capital risked per trade as a decimal in
            ``(0, 1]`` (e.g. ``0.01`` = 1%). Defaults to ``0.01``.
        sl_points: Stop-loss distance in **index points** of adverse movement.
            Must be ``> 0``. Also used as the per-lot risk basis for sizing.
        target_points: Take-profit distance in **index points** of favourable
            movement. Must be ``> 0``.
        slippage_pct: Per-leg slippage as a fraction of premium. Defaults to
            ``0.0005`` (0.05%).
        brokerage_per_order: Flat brokerage per executed order (applied to both
            entry and exit). Defaults to ``20.0``.

    Returns:
        The dict returned by :func:`backend.backtest.metrics.compute_metrics`
        for the collected trades, augmented with a ``"trades"`` key holding the
        chronological list of closed-trade records. Each trade record contains:

        * ``direction`` -- ``"BULLISH"`` / ``"BEARISH"``.
        * ``confidence`` -- normalised ``[0, 1]`` confidence at entry.
        * ``entry_index`` / ``exit_index`` -- underlying index points.
        * ``entry_premium`` / ``exit_premium`` -- index-points proxy premiums.
        * ``entry_bar`` / ``exit_bar`` -- integer bar indices into ``candles``.
        * ``entry_time`` / ``exit_time`` -- candle timestamps (or ``None``).
        * ``lots`` / ``qty`` -- position size.
        * ``exit_reason`` -- ``"SL"`` / ``"TARGET"`` / ``"EOD"``.
        * ``gross`` / ``charges`` / ``slippage`` / ``net`` -- INR P&L breakdown.
        * ``regime`` -- copied from the entry signal if provided (else absent).
        * ``signal_meta`` -- the full extra-key payload from the entry signal.

    Notes:
        * Never raises on degenerate input. An empty / single-element candle
          list, an always-HOLD ``decision_fn``, or sizing that yields zero lots
          all produce an empty book and a fully-zeroed metrics summary.
        * Any position still open at the final bar is force-closed at that bar's
          close with ``exit_reason == "EOD"`` so no P&L is silently dropped.
        * The intrabar tie-break favours the stop (pessimistic) -- see
          :func:`_resolve_exit`.
    """
    trades: List[Dict[str, Any]] = []

    n = len(candles)
    # Need at least two bars: one to decide on, one to fill the next-bar open.
    if n < 2 or not isinstance(lot_size, int) or lot_size <= 0:
        result = metrics.compute_metrics(trades)
        result["trades"] = trades
        return result

    open_trade: Optional[Dict[str, Any]] = None

    # Iterate over every bar that has a *next* bar available for the fill. The
    # decision at bar i sees candles[: i + 1] (closed bars only); a resulting
    # entry fills at the open of bar i + 1.
    for i in range(n - 1):
        current_bar = candles[i]

        # ----- Manage an open position on the current (already-entered) bar ---
        if open_trade is not None:
            # Skip the bar on which we entered; SL/target management starts on
            # the *next* bar after the fill to avoid checking the entry bar's
            # own range against a fill that happened at its open.
            if i > open_trade["entry_bar"]:
                exit_info = _resolve_exit(
                    open_trade["direction"],
                    current_bar,
                    open_trade["stop_price"],
                    open_trade["target_price"],
                )
                if exit_info is not None:
                    _close_trade(
                        trades,
                        open_trade,
                        exit_index=exit_info["exit_index"],
                        exit_reason=exit_info["reason"],
                        exit_bar=i,
                        exit_time=_bar_time(current_bar),
                        slippage_pct=slippage_pct,
                        brokerage_per_order=brokerage_per_order,
                    )
                    open_trade = None

        # ----- Decide on a new entry only when flat ---------------------------
        if open_trade is None:
            try:
                decision = decision_fn(candles[: i + 1])
            except Exception:
                # A decision_fn that raises is treated as "no signal" for this
                # bar; the backtest must remain robust to strategy bugs.
                decision = None

            if isinstance(decision, dict):
                direction = _normalise_signal(decision.get("signal"))
                if direction is not None:
                    fill_bar = candles[i + 1]
                    entry_index = _bar_open(fill_bar)
                    if entry_index is not None and entry_index > 0:
                        sized = position_size(
                            capital=capital,
                            risk_pct=risk_pct,
                            sl_points=sl_points,
                            lot_size=lot_size,
                        )
                        if sized["lots"] > 0:
                            open_trade = _open_trade(
                                direction=direction,
                                decision=decision,
                                entry_index=entry_index,
                                entry_bar=i + 1,
                                entry_time=_bar_time(fill_bar),
                                qty=sized["quantity"],
                                lots=sized["lots"],
                                sl_points=sl_points,
                                target_points=target_points,
                            )

    # ----- Force-close any position still open at the end of the data --------
    if open_trade is not None:
        last_bar = candles[n - 1]
        last_close = _bar_close(last_bar)
        if last_close is None:
            last_close = open_trade["entry_index"]
        _close_trade(
            trades,
            open_trade,
            exit_index=last_close,
            exit_reason="EOD",
            exit_bar=n - 1,
            exit_time=_bar_time(last_bar),
            slippage_pct=slippage_pct,
            brokerage_per_order=brokerage_per_order,
        )
        open_trade = None

    result = metrics.compute_metrics(trades)
    result["trades"] = trades
    return result


def _close_option_trade(trades, ot, exit_premium, reason, exit_bar, exit_time,
                        slippage_pct, brokerage_per_order):
    """Finalize a long-option trade using REAL option premiums (OPTION_PREMIUM mode)."""
    entry_premium = ot["entry_premium"]
    pnl = cost_model.net_pnl(
        entry_premium=entry_premium, exit_premium=float(exit_premium),
        qty=ot["qty"], slippage_pct=slippage_pct, brokerage_per_order=brokerage_per_order,
    )
    rec = {
        "direction": ot["direction"], "option_type": ot.get("option_type"),
        "confidence": ot["confidence"],
        "entry_premium": entry_premium, "exit_premium": float(exit_premium),
        "entry_bar": ot["entry_bar"], "exit_bar": int(exit_bar),
        "entry_time": ot["entry_time"], "exit_time": exit_time,
        "lots": ot["lots"], "qty": ot["qty"], "exit_reason": reason,
        "gross": pnl["gross"], "charges": pnl["charges"],
        "slippage": pnl["slippage"], "net": pnl["net"],
        "signal_meta": ot["signal_meta"],
    }
    regime = ot["signal_meta"].get("regime")
    if isinstance(regime, str) and regime.strip():
        rec["regime"] = regime
    trades.append(rec)


def run_option_premium_backtest(
    index_candles: List[Dict[str, Any]],
    option_candles: List[Dict[str, Any]],
    decision_fn: DecisionFn,
    option_type: str,
    *,
    lot_size: int,
    capital: float = 1_000_000.0,
    risk_pct: float = 0.01,
    sl_points: float,
    target_points: float,
    slippage_pct: float = 0.0005,
    brokerage_per_order: float = 20.0,
) -> Dict[str, Any]:
    """Dual-series OPTION_PREMIUM backtest.

    Decisions are made on the **index** candle history (identical to live), but
    fills, SL/target and P&L use the **chosen option's REAL premium candles**
    (aligned by timestamp). The position is always LONG the option (a CE for a
    BULLISH index signal, a PE for a BEARISH one); ``sl_points`` / ``target_points``
    are interpreted as **premium points**. No look-ahead: an entry decided on the
    close of index bar ``i`` fills at the option's bar-``i+1`` open. Pessimistic
    intrabar tie-break (stop first)."""
    trades: List[Dict[str, Any]] = []
    want = "BULLISH" if str(option_type).upper().startswith("C") else "BEARISH"
    opt_by_ts = {}
    for c in option_candles:
        ts = _bar_time(c)
        if ts is not None:
            opt_by_ts[ts] = c

    n = len(index_candles)
    if n < 2 or not isinstance(lot_size, int) or lot_size <= 0:
        result = metrics.compute_metrics(trades)
        result["trades"] = trades
        return result

    open_trade: Optional[Dict[str, Any]] = None
    for i in range(n - 1):
        cur_ts = _bar_time(index_candles[i])

        if open_trade is not None and i > open_trade["entry_bar"]:
            ob = opt_by_ts.get(cur_ts)
            if ob is not None:
                hi, lo = _bar_high(ob), _bar_low(ob)
                if hi is not None and lo is not None:
                    stop, tgt = open_trade["stop_price"], open_trade["target_price"]
                    if lo <= stop:  # pessimistic: stop first
                        _close_option_trade(trades, open_trade, stop, "SL", i, cur_ts,
                                            slippage_pct, brokerage_per_order)
                        open_trade = None
                    elif hi >= tgt:
                        _close_option_trade(trades, open_trade, tgt, "TARGET", i, cur_ts,
                                            slippage_pct, brokerage_per_order)
                        open_trade = None

        if open_trade is None:
            try:
                decision = decision_fn(index_candles[: i + 1])
            except Exception:
                decision = None
            if isinstance(decision, dict) and _normalise_signal(decision.get("signal")) == want:
                fill_ts = _bar_time(index_candles[i + 1])
                ob = opt_by_ts.get(fill_ts)
                entry_prem = _bar_open(ob) if ob is not None else None
                if entry_prem is not None and entry_prem > 0:
                    sized = position_size(capital=capital, risk_pct=risk_pct,
                                          sl_points=sl_points, lot_size=lot_size)
                    if sized["lots"] > 0:
                        open_trade = {
                            "direction": want, "option_type": option_type,
                            "confidence": _normalise_confidence(decision.get("confidence")),
                            "entry_premium": float(entry_prem),
                            "entry_bar": i + 1, "entry_time": fill_ts,
                            "qty": sized["quantity"], "lots": sized["lots"],
                            "stop_price": float(entry_prem - sl_points),
                            "target_price": float(entry_prem + target_points),
                            "signal_meta": {k: v for k, v in decision.items()
                                            if k not in ("signal", "confidence")},
                        }

    if open_trade is not None:
        last_ts = _bar_time(index_candles[n - 1])
        ob = opt_by_ts.get(last_ts)
        exit_prem = _bar_close(ob) if ob is not None else open_trade["entry_premium"]
        if exit_prem is None:
            exit_prem = open_trade["entry_premium"]
        _close_option_trade(trades, open_trade, exit_prem, "EOD", n - 1, last_ts,
                            slippage_pct, brokerage_per_order)

    result = metrics.compute_metrics(trades)
    result["trades"] = trades
    return result


def _open_trade(
    *,
    direction: str,
    decision: Dict[str, Any],
    entry_index: float,
    entry_bar: int,
    entry_time: Any,
    qty: int,
    lots: int,
    sl_points: float,
    target_points: float,
) -> Dict[str, Any]:
    """Build the in-flight open-trade state for a freshly filled entry.

    Stop and target levels are placed in **index points** relative to the entry,
    oriented by ``direction`` (a BULLISH long-call proxy stops below and targets
    above; a BEARISH long-put proxy is mirrored). The entry "premium" is the
    index-points proxy (the entry index level itself), per the module docstring.

    Args:
        direction: ``"BULLISH"`` or ``"BEARISH"``.
        decision: The raw ``decision_fn`` payload for the entry bar.
        entry_index: Underlying index level at the next-bar-open fill.
        entry_bar: Index into ``candles`` of the fill bar.
        entry_time: Timestamp of the fill bar (or ``None``).
        qty: Total option units (lots * lot_size).
        lots: Number of lots.
        sl_points: Stop distance in index points.
        target_points: Target distance in index points.

    Returns:
        A mutable open-trade dict consumed by :func:`_resolve_exit` and
        :func:`_close_trade`.
    """
    if direction == "BULLISH":
        stop_price = entry_index - sl_points
        target_price = entry_index + target_points
    else:  # BEARISH
        stop_price = entry_index + sl_points
        target_price = entry_index - target_points

    return {
        "direction": direction,
        "confidence": _normalise_confidence(decision.get("confidence")),
        "entry_index": float(entry_index),
        # Index-points proxy: the long-option entry "premium" is the entry index
        # level. Replace with real option OHLC once premium data is wired.
        "entry_premium": float(entry_index),
        "entry_bar": int(entry_bar),
        "entry_time": entry_time,
        "qty": int(qty),
        "lots": int(lots),
        "stop_price": float(stop_price),
        "target_price": float(target_price),
        "signal_meta": {
            k: v for k, v in decision.items() if k not in ("signal", "confidence")
        },
    }


def _close_trade(
    trades: List[Dict[str, Any]],
    open_trade: Dict[str, Any],
    *,
    exit_index: float,
    exit_reason: str,
    exit_bar: int,
    exit_time: Any,
    slippage_pct: float,
    brokerage_per_order: float,
) -> None:
    """Finalise an open trade into a closed-trade record and append it to ``trades``.

    Converts the index path into the index-points proxy premiums for the long
    option leg, then runs them through
    :func:`backend.backtest.cost_model.net_pnl` to obtain a cost- and
    slippage-aware net P&L. The completed record is appended in place.

    Args:
        trades: The trade list to append the closed record to (mutated).
        open_trade: The in-flight open-trade dict from :func:`_open_trade`.
        exit_index: Underlying index level at exit.
        exit_reason: ``"SL"`` / ``"TARGET"`` / ``"EOD"``.
        exit_bar: Index into ``candles`` of the exit bar.
        exit_time: Timestamp of the exit bar (or ``None``).
        slippage_pct: Per-leg slippage fraction passed to the cost model.
        brokerage_per_order: Flat brokerage per order passed to the cost model.
    """
    direction = open_trade["direction"]
    entry_index = open_trade["entry_index"]

    # Index-points proxy for the long-option leg. For a long call the premium
    # rises with the index; for a long put it rises as the index falls. We build
    # synthetic entry/exit "premiums" whose difference equals the directional
    # index move, then hand them to the options cost model so charges/slippage
    # scale off a premium-like turnover.
    if direction == "BULLISH":
        directional_move = exit_index - entry_index
    else:  # BEARISH
        directional_move = entry_index - exit_index

    entry_premium = open_trade["entry_premium"]
    # Exit premium = entry premium + directional gain (long-option convention:
    # gross per unit = exit_premium - entry_premium = directional_move).
    exit_premium = entry_premium + directional_move

    pnl = cost_model.net_pnl(
        entry_premium=entry_premium,
        exit_premium=exit_premium,
        qty=open_trade["qty"],
        slippage_pct=slippage_pct,
        brokerage_per_order=brokerage_per_order,
    )

    record: Dict[str, Any] = {
        "direction": direction,
        "confidence": open_trade["confidence"],
        "entry_index": entry_index,
        "exit_index": float(exit_index),
        "entry_premium": entry_premium,
        "exit_premium": float(exit_premium),
        "entry_bar": open_trade["entry_bar"],
        "exit_bar": int(exit_bar),
        "entry_time": open_trade["entry_time"],
        "exit_time": exit_time,
        "lots": open_trade["lots"],
        "qty": open_trade["qty"],
        "exit_reason": exit_reason,
        "gross": pnl["gross"],
        "charges": pnl["charges"],
        "slippage": pnl["slippage"],
        "net": pnl["net"],
        "signal_meta": open_trade["signal_meta"],
    }

    # Surface a regime label at the top level for compute_metrics bucketing.
    regime = open_trade["signal_meta"].get("regime")
    if isinstance(regime, str) and regime.strip():
        record["regime"] = regime

    trades.append(record)
