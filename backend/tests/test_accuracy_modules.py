"""
Offline unit tests for six pure modules (no DB, no network, no filesystem I/O).

Modules under test
------------------
1. backtest.cost_model      - net_pnl, options_round_trip_charges
2. backtest.metrics         - compute_metrics
3. utils.position_sizing    - position_size
4. analysis.regime          - detect_regime
5. analysis.calibration     - Calibrator
6. analysis.data_quality    - validate_candles

All tests run purely on in-memory data. None of these modules touch the DB,
network, or scheduler, so import-time side-effects are absent.
"""

from __future__ import annotations

import calendar
import math

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Module imports
# ---------------------------------------------------------------------------
from backtest.cost_model import (
    DEFAULT_BROKERAGE_PER_ORDER,
    DEFAULT_SLIPPAGE_PCT,
    EXCHANGE_TXN_RATE_ON_TURNOVER,
    GST_RATE,
    SEBI_RATE_ON_TURNOVER,
    STAMP_RATE_ON_BUY,
    STT_RATE_ON_SELL,
    net_pnl,
    options_round_trip_charges,
    slippage,
)
from backtest.metrics import compute_metrics
from utils.position_sizing import position_size
from analysis.regime import (
    ADX_TREND_THRESHOLD,
    RANGING,
    TRENDING,
    VOLATILE,
    VOL_RATIO_THRESHOLD,
    compute_adx,
    compute_atr,
    detect_regime,
)
from analysis.calibration import Calibrator
from analysis.data_quality import (
    MAX_ZERO_VOLUME_FRACTION,
    _IST_OFFSET_SEC,
    _MARKET_OPEN_SOD,
    validate_candles,
)


# ===========================================================================
# Helpers / Fixtures
# ===========================================================================

# A known Monday IST market session: 2024-01-15 09:15:00 IST
# Computed as: UTC-midnight of that date minus the IST offset plus the
# market-open seconds-of-day.
_IST_MON_JAN15_MARKET_OPEN_UTC: int = (
    calendar.timegm((2024, 1, 15, 0, 0, 0)) - _IST_OFFSET_SEC + _MARKET_OPEN_SOD
)  # 1705290300


def _make_intraday_candles(
    n: int,
    interval_sec: int = 300,
    base_ts: int = _IST_MON_JAN15_MARKET_OPEN_UTC,
    start_price: float = 100.0,
    volume: int = 1000,
) -> list[dict]:
    """Build a minimal valid OHLCV candle list for a single trading session."""
    candles = []
    for i in range(n):
        p = start_price + i
        candles.append(
            {
                "timestamp": base_ts + i * interval_sec,
                "open": p,
                "high": p + 2.0,
                "low": p - 1.0,
                "close": p + 1.0,
                "volume": volume,
            }
        )
    return candles


def _make_trending_ohlc_df(n: int = 100, seed: int = 42) -> "import pandas as pd; pd.DataFrame":
    """Return a DataFrame with a strong uptrend so ADX > ADX_TREND_THRESHOLD."""
    import pandas as pd  # noqa: PLC0415 – lazy import to match module pattern

    rng = np.random.default_rng(seed)
    close = 1000.0 + np.arange(n) * 5.0 + rng.normal(0, 0.5, n)
    high = close + np.abs(rng.normal(2, 0.5, n))
    low = close - np.abs(rng.normal(2, 0.5, n))
    opens = close - rng.normal(0, 0.5, n)
    return pd.DataFrame({"open": opens, "high": high, "low": low, "close": close})


def _make_ranging_ohlc_df(n: int = 60, seed: int = 7) -> "import pandas as pd; pd.DataFrame":
    """Return a DataFrame with a pure sine oscillation (low ADX, low vol ratio)."""
    import pandas as pd  # noqa: PLC0415

    # Very narrow range to keep ATR small and stable
    t = np.linspace(0, 2 * np.pi, n)
    close = 1000.0 + 3.0 * np.sin(t)
    high = close + 0.5
    low = close - 0.5
    opens = close - 0.1
    return pd.DataFrame({"open": opens, "high": high, "low": low, "close": close})


# ===========================================================================
# 1. cost_model.net_pnl
# ===========================================================================

class TestNetPnl:
    """Verify round-trip cost decomposition and net P&L arithmetic."""

    # --- Charges are always positive (even on a losing trade) ---------------

    def test_charges_positive_winning_trade(self):
        r = net_pnl(entry_premium=100.0, exit_premium=150.0, qty=75)
        assert r["charges"] > 0, "Round-trip charges must be positive"

    def test_charges_positive_losing_trade(self):
        r = net_pnl(entry_premium=150.0, exit_premium=100.0, qty=75)
        assert r["charges"] > 0, "Charges remain positive even when the trade loses"

    def test_slippage_positive_always(self):
        r = net_pnl(entry_premium=100.0, exit_premium=90.0, qty=50)
        assert r["slippage"] > 0

    # --- Core formula: net = gross - charges - slippage ---------------------

    def test_net_equals_gross_minus_costs(self):
        r = net_pnl(entry_premium=100.0, exit_premium=150.0, qty=75)
        expected_net = r["gross"] - r["charges"] - r["slippage"]
        assert abs(r["net"] - expected_net) < 1e-9

    def test_gross_formula(self):
        r = net_pnl(entry_premium=100.0, exit_premium=150.0, qty=75)
        expected_gross = (150.0 - 100.0) * 75
        assert abs(r["gross"] - expected_gross) < 1e-9

    # --- STT is charged on SELL side only -----------------------------------

    def test_stt_charged_on_sell_premium_only(self):
        qty = 75
        entry, exit_ = 100.0, 150.0
        charges = options_round_trip_charges(entry, exit_, qty)
        expected_stt = exit_ * qty * STT_RATE_ON_SELL
        assert abs(charges["stt"] - expected_stt) < 1e-9, (
            f"STT must be sell_turnover * STT_RATE_ON_SELL; "
            f"expected {expected_stt}, got {charges['stt']}"
        )

    def test_stt_changes_with_exit_premium_not_entry(self):
        """A higher exit premium should increase STT; changing entry should not."""
        qty = 50
        charges_low_exit = options_round_trip_charges(100.0, 120.0, qty)
        charges_high_exit = options_round_trip_charges(100.0, 200.0, qty)
        charges_high_entry = options_round_trip_charges(200.0, 120.0, qty)

        # Higher exit -> more STT
        assert charges_high_exit["stt"] > charges_low_exit["stt"]
        # Changing entry at same exit -> STT unchanged
        assert abs(charges_high_entry["stt"] - charges_low_exit["stt"]) < 1e-9

    # --- Stamp duty on BUY side only ----------------------------------------

    def test_stamp_charged_on_buy_premium_only(self):
        qty = 75
        entry, exit_ = 100.0, 150.0
        charges = options_round_trip_charges(entry, exit_, qty)
        expected_stamp = entry * qty * STAMP_RATE_ON_BUY
        assert abs(charges["stamp"] - expected_stamp) < 1e-9

    # --- Brokerage is 2x flat fee -------------------------------------------

    def test_brokerage_is_double_flat_fee(self):
        charges = options_round_trip_charges(100.0, 150.0, 75)
        assert abs(charges["brokerage"] - DEFAULT_BROKERAGE_PER_ORDER * 2) < 1e-9

    # --- total = sum of components ------------------------------------------

    def test_total_charges_equals_sum_of_components(self):
        charges = options_round_trip_charges(100.0, 150.0, 75)
        component_sum = (
            charges["brokerage"]
            + charges["stt"]
            + charges["exchange_txn"]
            + charges["sebi"]
            + charges["gst"]
            + charges["stamp"]
        )
        assert abs(charges["total"] - component_sum) < 1e-9

    # --- GST base is correct -------------------------------------------------

    def test_gst_applied_to_correct_base(self):
        """GST = 18% of (brokerage + exchange_txn + sebi), not on STT/stamp."""
        charges = options_round_trip_charges(100.0, 150.0, 75)
        expected_gst = (
            charges["brokerage"] + charges["exchange_txn"] + charges["sebi"]
        ) * GST_RATE
        assert abs(charges["gst"] - expected_gst) < 1e-9

    # --- Exchange and SEBI on combined turnover ------------------------------

    def test_exchange_txn_on_total_turnover(self):
        qty = 75
        entry, exit_ = 100.0, 150.0
        charges = options_round_trip_charges(entry, exit_, qty)
        total_turnover = (entry + exit_) * qty
        expected_exchange = total_turnover * EXCHANGE_TXN_RATE_ON_TURNOVER
        assert abs(charges["exchange_txn"] - expected_exchange) < 1e-9

    # --- Net is less than gross for a winning trade (costs bite) ------------

    def test_profitable_trade_net_less_than_gross(self):
        r = net_pnl(entry_premium=100.0, exit_premium=300.0, qty=50)
        assert r["net"] < r["gross"]

    # --- Large loss trade: net is more negative than gross ------------------

    def test_loss_trade_net_more_negative_than_gross(self):
        r = net_pnl(entry_premium=150.0, exit_premium=80.0, qty=75)
        assert r["net"] < r["gross"]

    # --- qty is treated as absolute value -----------------------------------

    def test_qty_sign_ignored(self):
        pos = net_pnl(100.0, 150.0, 75)
        neg = net_pnl(100.0, 150.0, -75)
        assert abs(pos["net"] - neg["net"]) < 1e-9

    # --- Custom brokerage overrides default ----------------------------------

    def test_custom_brokerage_applied(self):
        default_r = net_pnl(100.0, 150.0, 50)
        custom_r = net_pnl(100.0, 150.0, 50, brokerage_per_order=0.0)
        # No brokerage -> lower charges -> higher net
        assert custom_r["net"] > default_r["net"]

    # --- slippage() helper --------------------------------------------------

    def test_slippage_helper_proportional_to_premium(self):
        s1 = slippage(100.0)
        s2 = slippage(200.0)
        assert abs(s2 - 2 * s1) < 1e-9

    def test_slippage_helper_direction_agnostic(self):
        assert slippage(-100.0) == slippage(100.0)


# ===========================================================================
# 2. backtest.metrics.compute_metrics
# ===========================================================================

class TestComputeMetrics:
    """Verify summary statistics against manually-derived expected values."""

    # Fixture trades chosen for easy manual verification.
    # net P&L: +100, -50, +200, -30, +150
    # wins: [100, 200, 150], losses: [-50, -30]
    _TRADES = [
        {"net": 100.0, "regime": "TRENDING"},
        {"net": -50.0, "regime": "RANGING"},
        {"net": 200.0, "regime": "TRENDING"},
        {"net": -30.0, "regime": "RANGING"},
        {"net": 150.0, "regime": "TRENDING"},
    ]

    def _result(self):
        return compute_metrics(self._TRADES)

    # --- empty list -----------------------------------------------------------

    def test_empty_list_returns_zeroed_dict(self):
        r = compute_metrics([])
        assert r["count"] == 0
        assert r["total_net"] == 0.0
        assert r["win_rate"] == 0.0
        assert r["avg_win"] == 0.0
        assert r["avg_loss"] == 0.0
        assert r["expectancy"] == 0.0
        assert r["profit_factor"] == 0.0
        assert r["max_drawdown"] == 0.0
        assert r["sharpe"] == 0.0
        assert r["by_regime"] == {}

    def test_empty_list_does_not_raise(self):
        compute_metrics([])  # must not raise

    # --- count ----------------------------------------------------------------

    def test_count(self):
        assert self._result()["count"] == 5

    # --- total_net ------------------------------------------------------------

    def test_total_net(self):
        assert abs(self._result()["total_net"] - 370.0) < 1e-9

    # --- win_rate -------------------------------------------------------------

    def test_win_rate(self):
        # 3 wins / 5 trades = 0.6
        assert abs(self._result()["win_rate"] - 0.6) < 1e-9

    # --- avg_win / avg_loss ---------------------------------------------------

    def test_avg_win(self):
        # (100 + 200 + 150) / 3 = 150.0
        assert abs(self._result()["avg_win"] - 150.0) < 1e-9

    def test_avg_loss(self):
        # (-50 + -30) / 2 = -40.0
        assert abs(self._result()["avg_loss"] - (-40.0)) < 1e-9

    # --- expectancy -----------------------------------------------------------

    def test_expectancy(self):
        # 370 / 5 = 74.0
        assert abs(self._result()["expectancy"] - 74.0) < 1e-9

    # --- profit_factor --------------------------------------------------------

    def test_profit_factor(self):
        # gross_profit = 100+200+150 = 450; gross_loss = 50+30 = 80
        # profit_factor = 450/80 = 5.625
        assert abs(self._result()["profit_factor"] - 5.625) < 1e-9

    def test_profit_factor_all_wins_is_inf(self):
        trades = [{"net": 100}, {"net": 200}]
        r = compute_metrics(trades)
        assert r["profit_factor"] == float("inf")

    def test_profit_factor_all_losses_is_zero(self):
        trades = [{"net": -100}, {"net": -50}]
        r = compute_metrics(trades)
        assert r["profit_factor"] == 0.0

    def test_profit_factor_all_flat_is_zero(self):
        trades = [{"net": 0.0}, {"net": 0.0}]
        r = compute_metrics(trades)
        assert r["profit_factor"] == 0.0

    # --- max_drawdown ---------------------------------------------------------

    def test_max_drawdown(self):
        # Cumulative: 100, 50, 250, 220, 370
        # Peak:       100, 100, 250, 250, 370
        # Drawdown:     0,  50,   0,  30,   0
        # Max drawdown = 50
        assert abs(self._result()["max_drawdown"] - 50.0) < 1e-9

    def test_max_drawdown_monotone_ascending_is_zero(self):
        trades = [{"net": i * 10.0} for i in range(1, 6)]
        r = compute_metrics(trades)
        assert r["max_drawdown"] == 0.0

    def test_max_drawdown_all_losses(self):
        # -100, -50 -> cumulative equity: [-100, -150]
        # running_peak = [-100, -100]  (np.maximum.accumulate over negatives)
        # drawdown     = [  0,   50]
        # max_drawdown = 50  (not 150 -- _max_drawdown measures peak-to-trough
        #                     of the cumulative curve, not absolute loss from zero)
        trades = [{"net": -100.0}, {"net": -50.0}]
        r = compute_metrics(trades)
        assert abs(r["max_drawdown"] - 50.0) < 1e-9

    # --- by_regime breakdown -------------------------------------------------

    def test_by_regime_keys_present(self):
        r = self._result()
        assert "TRENDING" in r["by_regime"]
        assert "RANGING" in r["by_regime"]

    def test_by_regime_trending_all_wins(self):
        trending = self._result()["by_regime"]["TRENDING"]
        assert trending["count"] == 3
        assert trending["win_rate"] == 1.0
        assert abs(trending["expectancy"] - 150.0) < 1e-9

    def test_by_regime_ranging_all_losses(self):
        ranging = self._result()["by_regime"]["RANGING"]
        assert ranging["count"] == 2
        assert ranging["win_rate"] == 0.0
        assert abs(ranging["expectancy"] - (-40.0)) < 1e-9

    def test_missing_regime_field_bucketed_as_unknown(self):
        trades = [{"net": 50.0}, {"net": -20.0}]  # no regime field
        r = compute_metrics(trades)
        assert "unknown" in r["by_regime"]

    # --- resilience to malformed net values ----------------------------------

    def test_malformed_net_treated_as_zero(self):
        trades = [{"net": "bad"}, {"net": None}, {"net": float("inf")}]
        r = compute_metrics(trades)
        # All coerced to 0.0 -> total_net == 0, no exception
        assert r["total_net"] == 0.0

    def test_single_trade_no_raise(self):
        r = compute_metrics([{"net": 100.0}])
        assert r["count"] == 1
        assert r["total_net"] == 100.0

    # --- sharpe guard --------------------------------------------------------

    def test_sharpe_zero_for_constant_pnl(self):
        # std == 0 for all-identical net values -> guarded to 0.0
        trades = [{"net": 50.0}, {"net": 50.0}, {"net": 50.0}]
        r = compute_metrics(trades)
        assert r["sharpe"] == 0.0


# ===========================================================================
# 3. utils.position_sizing.position_size
# ===========================================================================

class TestPositionSize:
    """Verify fixed-fractional sizing arithmetic, clamping, and zero-guards."""

    # --- Basic risk math ----------------------------------------------------

    def test_basic_lot_count(self):
        # risk_amount = 100_000 * 0.01 = 1000
        # per_lot_risk = 15 * 50 = 750
        # lots = floor(1000 / 750) = 1
        r = position_size(capital=100_000, risk_pct=0.01, sl_points=15.0, lot_size=50)
        assert r["lots"] == 1
        assert r["quantity"] == 50
        assert abs(r["risk_amount"] - 1000.0) < 1e-9
        assert r["reason"] == "OK"

    def test_quantity_equals_lots_times_lot_size(self):
        r = position_size(capital=500_000, risk_pct=0.02, sl_points=10.0, lot_size=25)
        assert r["quantity"] == r["lots"] * 25

    def test_floor_division_applied(self):
        # risk_amount = 50_000 * 0.01 = 500
        # per_lot_risk = 100 * 3 = 300
        # lots = floor(500 / 300) = 1  (not 1.67)
        r = position_size(capital=50_000, risk_pct=0.01, sl_points=100.0, lot_size=3)
        assert r["lots"] == 1

    def test_higher_capital_yields_more_lots(self):
        small = position_size(capital=100_000, risk_pct=0.01, sl_points=5.0, lot_size=50)
        large = position_size(capital=1_000_000, risk_pct=0.01, sl_points=5.0, lot_size=50)
        assert large["lots"] > small["lots"]

    # --- max_lots clamp ------------------------------------------------------

    def test_max_lots_clamps_result(self):
        r = position_size(
            capital=1_000_000, risk_pct=0.05, sl_points=5.0, lot_size=50, max_lots=3
        )
        assert r["lots"] == 3
        assert "max_lots" in r["reason"]

    def test_max_lots_zero_forces_zero_lots(self):
        r = position_size(capital=1_000_000, risk_pct=0.01, sl_points=5.0, lot_size=50, max_lots=0)
        assert r["lots"] == 0
        assert r["quantity"] == 0

    def test_max_lots_negative_is_invalid(self):
        r = position_size(capital=1_000_000, risk_pct=0.01, sl_points=5.0, lot_size=50, max_lots=-1)
        assert r["lots"] == 0

    def test_max_lots_larger_than_raw_does_not_clamp(self):
        r = position_size(
            capital=100_000, risk_pct=0.01, sl_points=15.0, lot_size=50, max_lots=100
        )
        # Raw lots = 1, max_lots=100 -> no clamp applied
        assert r["lots"] == 1
        assert r["reason"] == "OK"

    # --- margin clamp --------------------------------------------------------

    def test_margin_clamp_limits_lots(self):
        # Risk-based lots would be large, but margin only covers 1
        r = position_size(
            capital=500_000,
            risk_pct=0.05,
            sl_points=5.0,
            lot_size=50,
            available_margin=15_000,
            margin_per_lot=10_000,
        )
        assert r["lots"] == 1
        assert "margin" in r["reason"].lower()

    def test_zero_margin_yields_zero_lots(self):
        r = position_size(
            capital=500_000,
            risk_pct=0.01,
            sl_points=10.0,
            lot_size=50,
            available_margin=0.0,
            margin_per_lot=10_000,
        )
        assert r["lots"] == 0

    # --- zero / invalid input guards ----------------------------------------

    def test_zero_capital_returns_zero_lots(self):
        r = position_size(capital=0, risk_pct=0.01, sl_points=15.0, lot_size=50)
        assert r["lots"] == 0
        assert "capital" in r["reason"].lower()

    def test_negative_capital_returns_zero_lots(self):
        r = position_size(capital=-100_000, risk_pct=0.01, sl_points=15.0, lot_size=50)
        assert r["lots"] == 0

    def test_zero_sl_points_returns_zero_lots(self):
        r = position_size(capital=100_000, risk_pct=0.01, sl_points=0.0, lot_size=50)
        assert r["lots"] == 0
        assert "sl_points" in r["reason"].lower()

    def test_negative_sl_points_returns_zero_lots(self):
        r = position_size(capital=100_000, risk_pct=0.01, sl_points=-5.0, lot_size=50)
        assert r["lots"] == 0

    def test_zero_risk_pct_returns_zero_lots(self):
        r = position_size(capital=100_000, risk_pct=0.0, sl_points=15.0, lot_size=50)
        assert r["lots"] == 0

    def test_zero_lot_size_returns_zero_lots(self):
        r = position_size(capital=100_000, risk_pct=0.01, sl_points=15.0, lot_size=0)
        assert r["lots"] == 0

    def test_budget_too_small_returns_zero_lots(self):
        # risk = 100 * 0.01 = 1.0; per_lot_risk = 15 * 50 = 750 -> 0 lots
        r = position_size(capital=100, risk_pct=0.01, sl_points=15.0, lot_size=50)
        assert r["lots"] == 0

    def test_risk_amount_preserved_in_zero_result(self):
        """risk_amount field in zero-lot result reflects computed budget."""
        r = position_size(capital=100_000, risk_pct=0.02, sl_points=15.0, lot_size=50, max_lots=0)
        # risk_amount = 100_000 * 0.02 = 2000
        assert abs(r["risk_amount"] - 2_000.0) < 1e-9

    # --- lots is never negative ----------------------------------------------

    def test_lots_never_negative(self):
        for cap in [0, -1, 1]:
            r = position_size(capital=cap, risk_pct=0.01, sl_points=5.0, lot_size=50)
            assert r["lots"] >= 0

    # --- bool inputs rejected (Python bool is a subclass of int) ------------

    def test_bool_capital_rejected(self):
        r = position_size(capital=True, risk_pct=0.01, sl_points=5.0, lot_size=50)
        assert r["lots"] == 0

    def test_bool_lot_size_rejected(self):
        r = position_size(capital=100_000, risk_pct=0.01, sl_points=5.0, lot_size=True)
        assert r["lots"] == 0


# ===========================================================================
# 4. analysis.regime.detect_regime
# ===========================================================================

class TestDetectRegime:
    """Verify regime classification using both injected values and real data."""

    # --- Decision logic with injected ADX / vol_ratio ----------------------

    def test_volatile_when_vol_ratio_above_threshold(self):
        r = detect_regime(None, adx_value=30.0, vol_ratio=VOL_RATIO_THRESHOLD)
        assert r == VOLATILE

    def test_volatile_takes_priority_over_trending_adx(self):
        """VOLATILE must be returned even when ADX signals TRENDING."""
        r = detect_regime(None, adx_value=40.0, vol_ratio=2.0)
        assert r == VOLATILE

    def test_trending_when_adx_at_threshold_and_vol_ok(self):
        r = detect_regime(None, adx_value=ADX_TREND_THRESHOLD, vol_ratio=1.0)
        assert r == TRENDING

    def test_ranging_when_below_both_thresholds(self):
        r = detect_regime(None, adx_value=ADX_TREND_THRESHOLD - 0.1, vol_ratio=VOL_RATIO_THRESHOLD - 0.1)
        assert r == RANGING

    def test_ranging_fallback_when_no_data_available(self):
        """NaN ADX and NaN vol_ratio -> conservative RANGING fallback."""
        r = detect_regime(None, adx_value=float("nan"), vol_ratio=float("nan"))
        assert r == RANGING

    def test_ranging_fallback_when_both_none(self):
        import pandas as pd  # noqa: PLC0415
        # Short frame: not enough bars for ADX or long ATR -> NaN -> RANGING
        df = pd.DataFrame(
            {"open": [100.0], "high": [105.0], "low": [98.0], "close": [103.0]}
        )
        r = detect_regime(df)
        assert r == RANGING

    # --- Real trending data -------------------------------------------------

    def test_trending_fixture_returns_trending(self):
        df = _make_trending_ohlc_df(n=100)
        adx_val = compute_adx(df)
        # confirm our fixture really does produce a trending ADX
        assert not math.isnan(adx_val), "Fixture should produce a valid ADX"
        assert adx_val >= ADX_TREND_THRESHOLD, (
            f"Trending fixture ADX {adx_val:.1f} should be >= {ADX_TREND_THRESHOLD}"
        )
        # now detect regime from the df directly (vol_ratio stays < threshold)
        r = detect_regime(df, vol_ratio=0.9)
        assert r == TRENDING

    def test_volatile_override_via_injected_vol_ratio(self):
        """Even a trending frame is classified VOLATILE when vol_ratio is injected."""
        df = _make_trending_ohlc_df(n=100)
        r = detect_regime(df, vol_ratio=2.0)
        assert r == VOLATILE

    # --- Boundary conditions ------------------------------------------------

    def test_adx_just_below_threshold_is_ranging(self):
        r = detect_regime(None, adx_value=ADX_TREND_THRESHOLD - 0.001, vol_ratio=0.8)
        assert r == RANGING

    def test_vol_ratio_just_below_threshold_does_not_trigger_volatile(self):
        r = detect_regime(None, adx_value=30.0, vol_ratio=VOL_RATIO_THRESHOLD - 0.001)
        # ADX >= threshold and vol_ratio < threshold -> TRENDING
        assert r == TRENDING

    # --- Return values are the canonical constants --------------------------

    def test_return_value_is_canonical_string_constant(self):
        for adx, vr, expected in [
            (30.0, 1.0, TRENDING),
            (10.0, 1.0, RANGING),
            (30.0, 2.0, VOLATILE),
        ]:
            assert detect_regime(None, adx_value=adx, vol_ratio=vr) == expected


# ===========================================================================
# 5. analysis.calibration.Calibrator
# ===========================================================================

class TestCalibrator:
    """Verify logistic calibrator fit/predict on separable data and degenerate inputs."""

    # --- Separable data fixture --------------------------------------------

    @staticmethod
    def _make_separable_data(n_per_class: int = 60, seed: int = 1):
        """Two Gaussian blobs separated by 4 std-devs -> reliably separable."""
        rng = np.random.default_rng(seed)
        X_pos = rng.normal(2.0, 0.5, (n_per_class, 2))
        X_neg = rng.normal(-2.0, 0.5, (n_per_class, 2))
        X = np.vstack([X_pos, X_neg])
        y = np.array([1.0] * n_per_class + [0.0] * n_per_class)
        return X, y, X_pos, X_neg

    # --- Unfitted state returns 0.5 -----------------------------------------

    def test_unfitted_predict_proba_returns_half(self):
        c = Calibrator()
        X = np.array([[0.8, 0.2], [0.3, 0.9], [1.5, -0.5]])
        probs = c.predict_proba(X)
        assert np.allclose(probs, 0.5)

    def test_unfitted_is_fitted_is_false(self):
        assert not Calibrator().is_fitted

    # --- After fit on separable data ----------------------------------------

    def test_fit_marks_is_fitted(self):
        X, y, _, _ = self._make_separable_data()
        c = Calibrator()
        c.fit(X, y)
        assert c.is_fitted

    def test_positive_class_proba_above_half(self):
        X, y, X_pos, _ = self._make_separable_data()
        c = Calibrator().fit(X, y)
        probs = c.predict_proba(X_pos[:10])
        assert np.all(probs > 0.5), (
            f"All positive-class samples must have P > 0.5; got min={probs.min():.4f}"
        )

    def test_negative_class_proba_below_half(self):
        X, y, _, X_neg = self._make_separable_data()
        c = Calibrator().fit(X, y)
        probs = c.predict_proba(X_neg[:10])
        assert np.all(probs < 0.5), (
            f"All negative-class samples must have P < 0.5; got max={probs.max():.4f}"
        )

    def test_predict_proba_strictly_between_zero_and_one(self):
        """Probabilities must be clipped to the open interval (0, 1)."""
        X, y, _, _ = self._make_separable_data()
        c = Calibrator().fit(X, y)
        probs = c.predict_proba(X)
        assert np.all(probs > 0.0)
        assert np.all(probs < 1.0)

    def test_output_length_matches_input_rows(self):
        X, y, _, _ = self._make_separable_data()
        c = Calibrator().fit(X, y)
        assert c.predict_proba(X).shape[0] == len(X)

    # --- 1-D feature input ---------------------------------------------------

    def test_fit_and_predict_1d_feature(self):
        """Calibrator must accept 1-D inputs (treated as single feature)."""
        rng = np.random.default_rng(5)
        X = rng.normal(0, 1, 100)
        y = (X > 0).astype(float)
        c = Calibrator().fit(X, y)
        assert c.is_fitted
        p = c.predict_proba(np.array([3.0]))
        assert p[0] > 0.5

    # --- Degenerate inputs leave model unfitted -----------------------------

    def test_empty_X_stays_unfitted(self):
        c = Calibrator().fit(np.array([]), np.array([]))
        assert not c.is_fitted

    def test_single_sample_stays_unfitted(self):
        c = Calibrator().fit(np.array([[1.0, 2.0]]), np.array([1.0]))
        assert not c.is_fitted

    def test_single_class_only_stays_unfitted(self):
        X = np.array([[1.0], [2.0], [3.0]])
        y = np.array([1.0, 1.0, 1.0])
        c = Calibrator().fit(X, y)
        assert not c.is_fitted

    def test_single_class_unfitted_predict_returns_half(self):
        X = np.array([[1.0], [2.0], [3.0]])
        y = np.array([0.0, 0.0, 0.0])
        c = Calibrator().fit(X, y)
        probs = c.predict_proba(np.array([[1.5]]))
        assert np.allclose(probs, 0.5)

    def test_feature_count_mismatch_returns_half(self):
        """predict_proba must return 0.5 when feature count differs from training."""
        X, y, _, _ = self._make_separable_data()
        c = Calibrator().fit(X, y)
        # Training used 2 features; predict with 3
        probs = c.predict_proba(np.array([[1.0, 2.0, 3.0]]))
        assert np.allclose(probs, 0.5)

    def test_nonfinite_row_returns_half(self):
        """Rows with NaN or inf must fall back to 0.5, not raise."""
        X, y, _, _ = self._make_separable_data()
        c = Calibrator().fit(X, y)
        X_with_nan = np.array([[2.0, 2.0], [float("nan"), 1.0], [-2.0, -2.0]])
        probs = c.predict_proba(X_with_nan)
        assert probs[1] == pytest.approx(0.5)  # the nan row
        assert probs[0] > 0.5   # normal positive row
        assert probs[2] < 0.5   # normal negative row

    # --- fit() returns self (fluent interface) --------------------------------

    def test_fit_returns_self(self):
        X, y, _, _ = self._make_separable_data()
        c = Calibrator()
        result = c.fit(X, y)
        assert result is c

    # --- re-fit resets model -------------------------------------------------

    def test_refit_resets_to_fresh_model(self):
        """Calling fit() twice should overwrite, not accumulate, parameters."""
        X, y, X_pos, _ = self._make_separable_data(seed=1)
        c = Calibrator().fit(X, y)
        first_coef = c.coef_.copy()

        X2, y2, _, _ = self._make_separable_data(seed=99)
        c.fit(X2, y2)
        assert not np.allclose(c.coef_, first_coef), "Re-fit should change coef_"


# ===========================================================================
# 6. analysis.data_quality.validate_candles
# ===========================================================================

class TestValidateCandles:
    """Verify data quality checks for good, gappy, stale, and bad-OHLCV candles."""

    # Canonical IST Monday 09:15 base timestamp
    BASE_TS: int = _IST_MON_JAN15_MARKET_OPEN_UTC  # 1705290300

    # --- Good data ----------------------------------------------------------

    def test_good_candles_list_is_ok(self):
        candles = _make_intraday_candles(5, interval_sec=300, base_ts=self.BASE_TS)
        r = validate_candles(candles, interval_min=5)
        assert r["ok"] is True
        assert r["issues"] == []
        assert r["reason"] == ""

    def test_good_candles_dataframe_is_ok(self):
        import pandas as pd  # noqa: PLC0415
        candles = _make_intraday_candles(5, interval_sec=300, base_ts=self.BASE_TS)
        df = pd.DataFrame(candles)
        r = validate_candles(df, interval_min=5)
        assert r["ok"] is True

    # --- Empty / too-short series -------------------------------------------

    def test_empty_list_not_ok(self):
        r = validate_candles([], interval_min=5)
        assert r["ok"] is False
        assert "empty" in r["reason"].lower()

    def test_single_candle_reports_issue(self):
        candles = _make_intraday_candles(1, base_ts=self.BASE_TS)
        r = validate_candles(candles, interval_min=5)
        assert r["ok"] is False  # single row < MIN_CANDLES (2)

    # --- Intra-session gap detection ----------------------------------------

    def test_intra_session_gap_detected(self):
        # Two candles 300 s apart, then a 1800 s gap (30 min) within same session.
        candles = [
            {"timestamp": self.BASE_TS,        "open": 100, "high": 102, "low": 99,  "close": 101, "volume": 1000},
            {"timestamp": self.BASE_TS + 300,   "open": 101, "high": 103, "low": 100, "close": 102, "volume": 1000},
            # 1800 s gap -- threshold for 5-min bars is 1.5 * 300 = 450 s
            {"timestamp": self.BASE_TS + 2100,  "open": 102, "high": 104, "low": 101, "close": 103, "volume": 1000},
        ]
        r = validate_candles(candles, interval_min=5)
        assert r["ok"] is False
        assert any("gap" in issue.lower() for issue in r["issues"])

    def test_overnight_gap_not_flagged_as_issue(self):
        """A gap spanning two different IST calendar days must not raise an issue.

        The fixture places two candles on IST Monday 2024-01-15 and two on
        IST Tuesday 2024-01-16 (each at 09:15 + 0/300 s).  The multi-hour
        overnight gap must be recognised as a session boundary and skipped
        by the intra-session gap detector.
        """
        # 2024-01-16 IST market open (Tuesday), calculated the same way as
        # BASE_TS but for the next calendar date.
        day2_open_utc: int = (
            calendar.timegm((2024, 1, 16, 0, 0, 0)) - _IST_OFFSET_SEC + _MARKET_OPEN_SOD
        )  # 1705376700

        candles = [
            {"timestamp": self.BASE_TS,          "open": 100, "high": 102, "low": 99,  "close": 101, "volume": 500},
            {"timestamp": self.BASE_TS + 300,     "open": 101, "high": 103, "low": 100, "close": 102, "volume": 600},
            # ~18-hour overnight gap to the next trading session
            {"timestamp": day2_open_utc,           "open": 102, "high": 104, "low": 101, "close": 103, "volume": 700},
            {"timestamp": day2_open_utc + 300,     "open": 103, "high": 105, "low": 102, "close": 104, "volume": 800},
        ]
        r = validate_candles(candles, interval_min=5)
        gap_issues = [i for i in r["issues"] if "gap" in i.lower()]
        assert gap_issues == [], f"Overnight gap was incorrectly flagged: {gap_issues}"

    # --- Zero / negative volume ---------------------------------------------

    def test_majority_zero_volume_not_ok(self):
        """More than MAX_ZERO_VOLUME_FRACTION zero-volume rows must fail."""
        n = 10
        candles = _make_intraday_candles(n, volume=0, base_ts=self.BASE_TS)
        r = validate_candles(candles, interval_min=5)
        assert r["ok"] is False
        assert any("volume" in i.lower() for i in r["issues"])

    def test_few_zero_volume_rows_still_ok(self):
        """Up to MAX_ZERO_VOLUME_FRACTION zero-volume rows are tolerated."""
        candles = _make_intraday_candles(20, volume=1000, base_ts=self.BASE_TS)
        # zero out just 1 of 20 (5% = at the boundary, not exceeding)
        candles[0]["volume"] = 0
        r = validate_candles(candles, interval_min=5)
        # 1/20 = 5% which equals the limit; implementation uses > not >= so this is ok
        assert r["ok"] is True

    def test_zero_volume_fraction_threshold(self):
        """Fraction exactly at MAX_ZERO_VOLUME_FRACTION boundary should not raise issue."""
        # MAX_ZERO_VOLUME_FRACTION = 0.05 -> 5%
        # With 20 candles, 1 zero-vol = 5%, which is == not > -> tolerated
        candles = _make_intraday_candles(20, volume=1000, base_ts=self.BASE_TS)
        candles[5]["volume"] = 0
        r = validate_candles(candles, interval_min=5)
        assert r["ok"] is True

    # --- Non-positive / NaN OHLC values -------------------------------------

    def test_zero_open_price_not_ok(self):
        candles = _make_intraday_candles(3, base_ts=self.BASE_TS)
        candles[0]["open"] = 0.0
        r = validate_candles(candles, interval_min=5)
        assert r["ok"] is False
        assert any("open" in i for i in r["issues"])

    def test_negative_close_price_not_ok(self):
        candles = _make_intraday_candles(3, base_ts=self.BASE_TS)
        candles[1]["close"] = -5.0
        r = validate_candles(candles, interval_min=5)
        assert r["ok"] is False

    def test_nan_high_price_not_ok(self):
        candles = _make_intraday_candles(3, base_ts=self.BASE_TS)
        candles[2]["high"] = float("nan")
        r = validate_candles(candles, interval_min=5)
        assert r["ok"] is False
        assert any("high" in i for i in r["issues"])

    # --- Staleness check -----------------------------------------------------

    def test_stale_last_candle_flagged(self):
        candles = _make_intraday_candles(3, interval_sec=300, base_ts=self.BASE_TS)
        last_ts = candles[-1]["timestamp"]
        # now is 1000 s after last candle; threshold is 2 * 5min = 600 s -> stale
        now_epoch = last_ts + 1000
        r = validate_candles(candles, interval_min=5, now_epoch=now_epoch)
        assert r["ok"] is False
        assert any("stale" in i.lower() for i in r["issues"])

    def test_fresh_last_candle_not_stale(self):
        candles = _make_intraday_candles(3, interval_sec=300, base_ts=self.BASE_TS)
        last_ts = candles[-1]["timestamp"]
        # now is 100 s after last candle; threshold is 600 s -> not stale
        now_epoch = last_ts + 100
        r = validate_candles(candles, interval_min=5, now_epoch=now_epoch)
        # Staleness alone must be ok; check specifically
        stale_issues = [i for i in r["issues"] if "stale" in i.lower()]
        assert stale_issues == []

    def test_no_now_epoch_skips_staleness_check(self):
        candles = _make_intraday_candles(3, base_ts=self.BASE_TS)
        # Simulate very old candles (1970) without supplying now_epoch
        candles[-1]["timestamp"] = 0
        candles[0]["timestamp"] = -600   # this will also break timestamp ordering
        # Only check that no staleness issue fires (ordering issue may fire instead)
        r = validate_candles(candles, interval_min=5, now_epoch=None)
        stale_issues = [i for i in r["issues"] if "stale" in i.lower()]
        assert stale_issues == []

    # --- Missing required column --------------------------------------------

    def test_missing_volume_column_not_ok(self):
        candles = [
            {"timestamp": self.BASE_TS,       "open": 100, "high": 102, "low": 99, "close": 101},
            {"timestamp": self.BASE_TS + 300,  "open": 101, "high": 103, "low": 100, "close": 102},
        ]
        r = validate_candles(candles, interval_min=5)
        assert r["ok"] is False
        assert any("volume" in i.lower() or "missing" in i.lower() for i in r["issues"])

    # --- Non-strictly-increasing timestamps ---------------------------------

    def test_non_increasing_timestamps_not_ok(self):
        candles = _make_intraday_candles(3, base_ts=self.BASE_TS)
        # Swap second and third candle timestamps to create a duplicate/reversal
        candles[2]["timestamp"] = candles[1]["timestamp"]
        r = validate_candles(candles, interval_min=5)
        assert r["ok"] is False
        assert any("timestamp" in i.lower() for i in r["issues"])

    # --- Return structure is always well-formed -----------------------------

    def test_return_has_ok_issues_reason_keys(self):
        r = validate_candles([], interval_min=1)
        assert "ok" in r
        assert "issues" in r
        assert "reason" in r
        assert isinstance(r["ok"], bool)
        assert isinstance(r["issues"], list)
        assert isinstance(r["reason"], str)

    def test_reason_is_first_issue(self):
        candles = _make_intraday_candles(3, base_ts=self.BASE_TS)
        candles[0]["open"] = 0.0
        r = validate_candles(candles, interval_min=5)
        if r["issues"]:
            assert r["reason"] == r["issues"][0]
