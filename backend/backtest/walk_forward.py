"""Walk-forward (rolling out-of-sample) evaluation harness.

This module provides a single pure-orchestration entry point,
:func:`walk_forward`, that rolls a contiguous train / test window across an
ordered list of candles, fitting on the in-sample slice and evaluating on the
immediately following out-of-sample slice. It exists to make strategy / model
tuning *trustworthy*: every trade metric it reports is computed only on data the
fitter never saw, which is the whole point of walk-forward analysis and the
defence against the overfitting that plagues single-shot backtests.

Design constraints
------------------
* **Pure orchestration.** This module owns none of the trading logic. The caller
  supplies ``fit_fn`` (e.g. fit a logistic / Platt confidence calibrator on the
  training candles) and ``run_fn`` (e.g. run the scalper backtest on the test
  candles using the fitted object and emit closed-trade dicts). We only slice,
  loop, collect, and aggregate.
* **No side effects at import.** No DB, no network, no global mutation. The
  function is deterministic given deterministic ``fit_fn`` / ``run_fn``.
* **Defensive by construction.** Insufficient data, a zero step, a fitter or
  runner that returns ``None``, and an empty out-of-sample book must never
  raise -- they collapse to clearly-flagged, type-stable results.
* **Pure numpy / stdlib.** No pandas, scipy, or sklearn dependency. Metric
  aggregation reuses :func:`backtest.metrics.compute_metrics` so the win /
  expectancy / drawdown definitions match the rest of the backtester exactly.

Bar-close discipline (caller's responsibility)
-----------------------------------------------
The candles handed in are assumed to already be **closed** bars in chronological
order. This module performs no resampling and drops no bars; honouring the
"closed candles only" rule and any IST timeframe bucketing happens upstream in
``fit_fn`` / ``run_fn``. We simply preserve the ordering and contiguity of the
slices we cut.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from backtest.metrics import compute_metrics

__all__ = ["walk_forward"]


# Type aliases for the caller-supplied hooks. ``fit_fn`` consumes the training
# slice and returns an opaque fitted object (anything: a calibrator, a params
# dict, a tuned strategy). ``run_fn`` consumes the test slice plus that fitted
# object and returns the closed out-of-sample trades for that window.
Candle = Dict[str, Any]
Trade = Dict[str, Any]
FitFn = Callable[[List[Candle]], Any]
RunFn = Callable[[List[Candle], Any], Optional[Sequence[Trade]]]


# --------------------------------------------------------------------------- #
# Internal helpers (pure)                                                      #
# --------------------------------------------------------------------------- #
def _empty_result(reason: str) -> Dict[str, Any]:
    """Build a fully type-stable result for a run that produced no windows.

    Args:
        reason: Human-readable explanation (e.g. why no window could be cut).

    Returns:
        A result dict with the same shape :func:`walk_forward` always returns,
        but with zero windows, an empty pooled trade book, and ``ok=False``.
    """
    return {
        "ok": False,
        "reason": reason,
        "n_windows": 0,
        "n_trades": 0,
        "windows": [],
        "pooled": compute_metrics([]),
    }


def _coerce_trades(raw: Optional[Sequence[Trade]]) -> List[Trade]:
    """Normalize a runner's output into a flat list of trade dicts.

    A ``run_fn`` may legitimately return ``None`` (it ran but opened no trades),
    an empty sequence, or any sequence of dict-like trades. Anything that is not
    a mapping is dropped defensively so a single malformed row cannot break
    aggregation.

    Args:
        raw: Whatever ``run_fn`` returned for one test window.

    Returns:
        A list of dict trades (possibly empty). Never ``None``.
    """
    if not raw:
        return []
    return [t for t in raw if isinstance(t, dict)]


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #
def walk_forward(
    candles: List[Candle],
    fit_fn: FitFn,
    run_fn: RunFn,
    *,
    train_bars: int,
    test_bars: int,
    step_bars: Optional[int] = None,
) -> Dict[str, Any]:
    """Roll a train / test window across ``candles`` and aggregate OOS metrics.

    On each window the function fits on the in-sample (training) slice via
    ``fit_fn`` and then evaluates on the *immediately following*, non-overlapping
    out-of-sample (test) slice via ``run_fn``. The closed trades returned by
    ``run_fn`` for every window are collected, summarized per window with
    :func:`backtest.metrics.compute_metrics`, and finally pooled across all
    windows and summarized once more so the report carries both a per-window
    and a single pooled out-of-sample view.

    Window layout (``step_bars`` defaults to ``test_bars`` -> contiguous,
    non-overlapping test segments, i.e. a classic rolling walk-forward)::

        |<-- train_bars -->|<-- test_bars -->|
                           ^ fit boundary    ^ next window starts step_bars on

    Args:
        candles: Chronologically ordered list of **closed** candle dicts. Their
            internal shape is opaque to this function; it is only sliced and
            handed to ``fit_fn`` / ``run_fn``.
        fit_fn: Callable invoked once per window as ``fit_fn(train_slice)``;
            returns an opaque fitted object (calibrator, params, tuned strategy)
            that is forwarded to ``run_fn``. Must not mutate ``candles``.
        run_fn: Callable invoked once per window as
            ``run_fn(test_slice, fitted)``; returns the closed out-of-sample
            trades for that window (a sequence of dicts, each exposing at least
            a ``net`` field, as required by ``compute_metrics``), or ``None`` if
            no trades were opened.
        train_bars: Number of bars in each training slice. Must be ``>= 1``.
        test_bars: Number of bars in each test slice. Must be ``>= 1``.
        step_bars: How many bars to advance the window start between iterations.
            Defaults to ``test_bars`` (non-overlapping test segments). Must be
            ``>= 1`` when provided.

    Returns:
        A result dict with keys:

        * ``ok`` (bool): ``True`` when at least one window was evaluated.
        * ``reason`` (str): empty on success; otherwise why no window ran.
        * ``n_windows`` (int): number of train/test windows evaluated.
        * ``n_trades`` (int): total pooled out-of-sample trade count.
        * ``windows`` (list): one entry per window, each a dict with
          ``index``, ``train_start``, ``train_end``, ``test_start``,
          ``test_end`` (all integer bar offsets, end-exclusive), ``n_trades``
          (int), and ``metrics`` (the per-window
          :func:`compute_metrics` output over that window's OOS trades).
        * ``pooled`` (dict): :func:`compute_metrics` over the OOS trades of all
          windows concatenated in chronological window order.

        On insufficient data (fewer than ``train_bars + test_bars`` candles) or
        invalid window parameters, returns the same shape with ``ok=False``, a
        populated ``reason``, zero windows, and a zeroed pooled summary.

    Raises:
        Never raises on data shortfalls or empty results. ``fit_fn`` / ``run_fn``
        exceptions are intentionally **not** suppressed -- a broken fitter or
        runner should surface loudly rather than be silently dropped.
    """
    # ----- Validate window parameters (degrade gracefully, never raise). ----- #
    if not isinstance(train_bars, int) or train_bars < 1:
        return _empty_result(f"train_bars must be a positive int, got {train_bars!r}")
    if not isinstance(test_bars, int) or test_bars < 1:
        return _empty_result(f"test_bars must be a positive int, got {test_bars!r}")

    step = test_bars if step_bars is None else step_bars
    if not isinstance(step, int) or step < 1:
        return _empty_result(f"step_bars must be a positive int, got {step_bars!r}")

    total = len(candles)
    window_span = train_bars + test_bars
    if total < window_span:
        return _empty_result(
            f"insufficient data: need >= {window_span} candles "
            f"(train_bars={train_bars} + test_bars={test_bars}), got {total}"
        )

    # ----- Roll the window. --------------------------------------------------- #
    windows: List[Dict[str, Any]] = []
    pooled_trades: List[Trade] = []

    train_start = 0
    while train_start + window_span <= total:
        train_end = train_start + train_bars  # end-exclusive
        test_start = train_end
        test_end = test_start + test_bars  # end-exclusive

        train_slice = candles[train_start:train_end]
        test_slice = candles[test_start:test_end]

        fitted = fit_fn(train_slice)
        oos_trades = _coerce_trades(run_fn(test_slice, fitted))
        pooled_trades.extend(oos_trades)

        windows.append(
            {
                "index": len(windows),
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
                "n_trades": len(oos_trades),
                "metrics": compute_metrics(oos_trades),
            }
        )

        train_start += step

    # Window span fits but step never produced a window (shouldn't happen given
    # the validations above, but guard for total-stability of the contract).
    if not windows:
        return _empty_result(
            "no windows produced: check train_bars / test_bars / step_bars vs data length"
        )

    return {
        "ok": True,
        "reason": "",
        "n_windows": len(windows),
        "n_trades": len(pooled_trades),
        "windows": windows,
        "pooled": compute_metrics(pooled_trades),
    }
