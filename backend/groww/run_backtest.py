"""
Quick Run Script — Call Backtester Programmatically
=====================================================
Edit the parameters below and run:
    python run_backtest.py

No interactive prompts — just edit and run.
"""

from nifty_scalper_bt import Config, Backtester, get_trading_dates


# ============================================================================
# ✏️ EDIT YOUR PARAMETERS HERE
# ============================================================================

ACCESS_TOKEN = "eyJraWQiOiJaTUtjVXciLCJhbGciOiJFUzI1NiJ9.eyJleHAiOjE3NzA0MjQyMDAsImlhdCI6MTc3MDQwMzQxOCwibmJmIjoxNzcwNDAzNDE4LCJzdWIiOiJ7XCJ0b2tlblJlZklkXCI6XCI5MDhhMDBiNS0zZjAwLTQ5NmMtYmE2Ni03YWFmMjc4Nzc3N2VcIixcInZlbmRvckludGVncmF0aW9uS2V5XCI6XCJlMzFmZjIzYjA4NmI0MDZjODg3NGIyZjZkODQ5NTMxM1wiLFwidXNlckFjY291bnRJZFwiOlwiNWZiNzBmZmQtN2M0NS00OTM4LWE4NDUtNmM3MWFhNWI2MmZlXCIsXCJkZXZpY2VJZFwiOlwiZTIyN2NjMmUtOGQwZS01NzVkLWFiMGYtZjgyMGEyYjQ3MzA0XCIsXCJzZXNzaW9uSWRcIjpcImFiZGNlNjAwLTc4ZmMtNDI5Yy05ODZkLWZhYjdkOThiY2I5YlwiLFwiYWRkaXRpb25hbERhdGFcIjpcIno1NC9NZzltdjE2WXdmb0gvS0EwYktUcStWVXpEM1F2aFJ5Mk9OMnYxdVZSTkczdTlLa2pWZDNoWjU1ZStNZERhWXBOVi9UOUxIRmtQejFFQisybTdRPT1cIixcInJvbGVcIjpcIm9yZGVyLWJhc2ljLGxpdmVfZGF0YS1iYXNpYyxub25fdHJhZGluZy1iYXNpYyxvcmRlcl9yZWFkX29ubHktYmFzaWNcIixcInNvdXJjZUlwQWRkcmVzc1wiOm51bGwsXCJ0d29GYUV4cGlyeVRzXCI6MTc3MDQyNDIwMDAwMH0iLCJpc3MiOiJhcGV4LWF1dGgtcHJvZC1hcHAifQ.RDLZu-srzpPLB22KB_FdKy9EhELXnldxQQdlNenDgfPXsv88iYqaH0nDk85UaTEMBECyLNAqCLlOoCEmPELwLg"

# --- Option symbols ---
CE_SYMBOL = "NIFTY2621025850CE"    # Change to your ATM CE
PE_SYMBOL = "NIFTY2621025450PE"    # Change to your ATM PE (needed for PE_ONLY/BOTH)

# --- Mode ---
# "CE_ONLY"  → Buy CE when index moves UP
# "PE_ONLY"  → Buy PE when index moves DOWN
# "BOTH"     → Both CE and PE trades
TRADE_MODE = "BOTH"

# --- Dates ---
# Option 1: Explicit dates
DATES = ["2026-02-06"]

# Option 2: Last N trading days (uncomment to use)
# DATES = get_trading_dates(5, end_date="2026-02-06")

# --- Timeframe ---
INTERVAL = 5                # 1 or 5 (minutes)

# --- Strategy Parameters ---
TARGET_POINTS = 5.0         # Target profit per trade (pts)
STOPLOSS_POINTS = 10.0       # Stoploss per trade (pts)
INDEX_THRESHOLD = 20.0      # Min index move to trigger entry (pts)
MAX_HOLDING = 6           # Max candles to hold before timeout

# --- Costs ---
LOT_SIZE = 650               # NIFTY lot size
ENTRY_SLIPPAGE = 0.5        # Added to buy price
EXIT_SLIPPAGE = 0.3         # Subtracted from sell price
BROKERAGE = 20.0            # ₹ per order

# --- Output ---
OUTPUT_DIR = "backtest_output"


# ============================================================================
# RUN
# ============================================================================

if __name__ == "__main__":

    cfg = Config(
        access_token=ACCESS_TOKEN,
        ce_symbol=CE_SYMBOL,
        pe_symbol=PE_SYMBOL,
        trade_mode=TRADE_MODE,
        interval=INTERVAL,
        dates=DATES,
        target_points=TARGET_POINTS,
        stoploss_points=STOPLOSS_POINTS,
        index_move_threshold=INDEX_THRESHOLD,
        max_holding_candles=MAX_HOLDING,
        lot_size=LOT_SIZE,
        entry_slippage=ENTRY_SLIPPAGE,
        exit_slippage=EXIT_SLIPPAGE,
        brokerage_per_order=BROKERAGE,
        output_dir=OUTPUT_DIR,
    )

    bt = Backtester(cfg)
    results = bt.run()


# ============================================================================
# UTILITY: Parameter Sweep
# ============================================================================

def run_parameter_sweep():
    """Test multiple target/SL combinations"""
    combos = [
        (3, 3), (3, 5), (5, 3), (5, 5), (5, 7),
        (7, 5), (7, 7), (10, 5), (10, 10),
    ]
    results = []
    for target, sl in combos:
        cfg = Config(
            access_token=ACCESS_TOKEN,
            ce_symbol=CE_SYMBOL,
            trade_mode="CE_ONLY",
            interval=1,
            dates=DATES,
            target_points=target,
            stoploss_points=sl,
            index_move_threshold=INDEX_THRESHOLD,
            max_holding_candles=MAX_HOLDING,
            output_dir=f"sweep_T{target}_SL{sl}",
        )
        bt = Backtester(cfg)
        stats = bt.run()
        results.append({"target": target, "sl": sl, **stats})

    print("\n" + "=" * 60)
    print("PARAMETER SWEEP RESULTS")
    print(f"{'T':>4} {'SL':>4} {'Trades':>7} {'WR%':>6} {'PnL':>8} {'PF':>6}")
    for r in results:
        print(f"{r['target']:>4} {r['sl']:>4} {r.get('total_trades',0):>7} "
              f"{r.get('win_rate',0):>6.1f} {r.get('total_pnl_pts',0):>+8.2f} "
              f"{r.get('profit_factor',0):>6.2f}")

# Uncomment to run sweep:
run_parameter_sweep()