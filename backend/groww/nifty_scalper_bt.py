"""
NIFTY Options Scalping Backtester v4.2 (Visual + Adaptive)
==========================================================
1. STRATEGY: 1m Entry + 5m Momentum + 15m Trend.
2. EXECUTION: Adaptive ATR Trigger + Trailing Stoploss.
3. VISUALIZER: Generates interactive .html chart with trades.

NEW IN v4.2:
  - Added 'Visualizer' class using Plotly.
  - Generates 'backtest_visual.html' with Entry/Exit markers.
  - Plots the ACTUAL Option Chart to show precise SL/Target hits.

Usage:
    pip install growwapi plotly pandas
    python nifty_scalper_v4_2.py
"""

import csv
import os
import sys
import pandas as pd
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

# --- DEPENDENCY CHECK ---
try:
    from growwapi import GrowwAPI
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except ImportError:
    print("\n[ERROR] Missing libraries.")
    print("Please run: pip install growwapi plotly pandas")
    sys.exit(1)

# IST Timezone
IST = timezone(timedelta(hours=5, minutes=30))

# ============================================================================
# 1. CONFIGURATION
# ============================================================================

@dataclass
class Config:
    access_token: str = ""
    ce_symbol: str = ""
    pe_symbol: str = ""
    trade_mode: str = "CE_ONLY"  
    dates: List[str] = field(default_factory=list)
    
    # Adaptive Settings
    atr_period: int = 14
    trigger_multiplier: float = 1.2
    
    # Filters
    rsi_min: float = 45.0
    rsi_max: float = 80.0
    
    # Management
    target_points: float = 10.0
    stoploss_points: float = 6.0
    trailing_trigger: float = 4.0
    trailing_sl_move: float = 0.5
    max_holding_candles: int = 15
    
    # Costs
    entry_slippage: float = 0.5
    exit_slippage: float = 0.5
    lot_size: int = 75
    brokerage_per_order: float = 20.0
    
    output_dir: str = "backtest_v4_2_results"

# ============================================================================
# 2. DATA MODELS
# ============================================================================

@dataclass
class Bar:
    ts: int
    dt: datetime
    time_str: str
    o: float
    h: float
    l: float
    c: float
    v: float
    ema: float = 0.0
    rsi: float = 0.0
    atr: float = 0.0
    vol_sma: float = 0.0

@dataclass
class Trade:
    id: int
    date: str
    direction: str
    entry_time: str
    entry_price: float
    target: float
    sl: float
    original_sl: float
    audit_atr: float
    exit_time: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    result: str = ""
    pnl_pts: float = 0.0
    pnl_rs: float = 0.0
    holding_candles: int = 0
    candle_log: List[Dict] = field(default_factory=list)

# ============================================================================
# 3. INDICATOR LIBRARY
# ============================================================================

class Indicators:
    @staticmethod
    def ema(values: List[float], period: int) -> List[float]:
        if len(values) < period: return [0.0] * len(values)
        ema = [0.0] * len(values)
        ema[period-1] = sum(values[:period]) / period
        k = 2 / (period + 1)
        for i in range(period, len(values)):
            ema[i] = (values[i] - ema[i-1]) * k + ema[i-1]
        return ema

    @staticmethod
    def rsi(prices: List[float], period: int = 14) -> List[float]:
        if len(prices) < period + 1: return [0.0] * len(prices)
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [max(0, d) for d in deltas]
        losses = [abs(min(0, d)) for d in deltas]
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        rsis = [0.0] * len(prices)
        if avg_loss == 0: rsis[period] = 100.0
        else: rsis[period] = 100.0 - (100.0 / (1.0 + avg_gain/avg_loss))
        for i in range(period + 1, len(prices)):
            avg_gain = (avg_gain * (period - 1) + gains[i-1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i-1]) / period
            if avg_loss == 0: rsis[i] = 100.0
            else: rsis[i] = 100.0 - (100.0 / (1.0 + avg_gain/avg_loss))
        return rsis

    @staticmethod
    def atr(bars: List[Bar], period: int = 14) -> List[float]:
        if len(bars) < period + 1: return [0.0] * len(bars)
        tr = [0.0] * len(bars)
        for i in range(1, len(bars)):
            hl = bars[i].h - bars[i].l
            h_pc = abs(bars[i].h - bars[i-1].c)
            l_pc = abs(bars[i].l - bars[i-1].c)
            tr[i] = max(hl, h_pc, l_pc)
        atr = [0.0] * len(bars)
        atr[period] = sum(tr[1:period+1]) / period
        for i in range(period + 1, len(bars)):
            atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
        return atr

    @staticmethod
    def sma_volume(volumes: List[float], period: int = 20) -> List[float]:
        if len(volumes) < period: return [0.0] * len(volumes)
        sma = [0.0] * len(volumes)
        for i in range(period, len(volumes)):
            sma[i] = sum(volumes[i-period:i]) / period
        return sma

# ============================================================================
# 4. DATA FETCHER
# ============================================================================

class MTFDataFetcher:
    def __init__(self, access_token: str):
        self.api = GrowwAPI(access_token)
        print("  ✓ Groww API Connected")

    def fetch_smart(self, symbol: str, date: str, interval: int, days_back: int = 5) -> List[Bar]:
        target_dt = datetime.strptime(date, "%Y-%m-%d")
        start_dt = target_dt - timedelta(days=days_back)
        s_str = start_dt.strftime("%Y-%m-%d")
        segment = "CASH" if "NIFTY" in symbol and "CE" not in symbol and "PE" not in symbol else "FNO"
        seg_enum = self.api.SEGMENT_CASH if segment == "CASH" else self.api.SEGMENT_FNO
        
        print(f"    Fetching {interval}m data for {symbol} ({s_str} to {date})...")
        try:
            data = self.api.get_historical_candle_data(
                trading_symbol=symbol, exchange=self.api.EXCHANGE_NSE,
                segment=seg_enum, start_time=f"{s_str} 09:15:00",
                end_time=f"{date} 15:30:00", interval_in_minutes=interval
            )
        except Exception: return []

        raw = data.get("candles", [])
        if not raw: return []

        bars = []
        for c in raw:
            dt = datetime.fromtimestamp(c[0], tz=IST)
            b = Bar(ts=c[0], dt=dt, time_str=dt.strftime("%H:%M"),
                    o=c[1], h=c[2], l=c[3], c=c[4], v=c[5] if len(c)>5 else 0)
            bars.append(b)
        bars.sort(key=lambda x: x.ts)
        
        # Calc Indicators
        closes = [b.c for b in bars]
        volumes = [b.v for b in bars]
        if interval == 15:
            emas = Indicators.ema(closes, 20)
            for i, b in enumerate(bars): b.ema = emas[i]
        elif interval == 5:
            rsis = Indicators.rsi(closes, 14)
            for i, b in enumerate(bars): b.rsi = rsis[i]
        elif interval == 1:
            atrs = Indicators.atr(bars, 14)
            vol_smas = Indicators.sma_volume(volumes, 20)
            for i, b in enumerate(bars):
                b.atr = atrs[i]
                b.vol_sma = vol_smas[i]
        return bars

# ============================================================================
# 5. SIGNAL ENGINE
# ============================================================================

def get_last_completed_bar(bars: List[Bar], current_time_ts: int) -> Optional[Bar]:
    for i in range(len(bars)-1, -1, -1):
        if bars[i].ts < current_time_ts: return bars[i]
    return None

def generate_signals(bars_1m: List[Bar], bars_5m: List[Bar], bars_15m: List[Bar], cfg: Config) -> List[Tuple]:
    signals = []
    for i in range(20, len(bars_1m)):
        curr_1m = bars_1m[i]
        if curr_1m.time_str >= "15:15": continue
        
        last_15m = get_last_completed_bar(bars_15m, curr_1m.ts)
        if not last_15m or last_15m.ema == 0: continue
        is_uptrend = last_15m.c > last_15m.ema
        is_downtrend = last_15m.c < last_15m.ema
        
        last_5m = get_last_completed_bar(bars_5m, curr_1m.ts)
        if not last_5m or last_5m.rsi == 0: continue
        is_bullish_mom = (cfg.rsi_min < last_5m.rsi < cfg.rsi_max)
        is_bearish_mom = ((100-cfg.rsi_max) < last_5m.rsi < (100-cfg.rsi_min))
        
        dynamic_threshold = curr_1m.atr * cfg.trigger_multiplier
        if dynamic_threshold == 0: continue
        move_1m = curr_1m.c - curr_1m.o
        is_high_volume = curr_1m.v > curr_1m.vol_sma
        
        audit = {"atr": curr_1m.atr, "threshold": dynamic_threshold}

        if (cfg.trade_mode in ["CE_ONLY", "BOTH"] and is_uptrend and is_bullish_mom and is_high_volume):
            if move_1m > dynamic_threshold: signals.append((i, "BUY_CE", audit))
        elif (cfg.trade_mode in ["PE_ONLY", "BOTH"] and is_downtrend and is_bearish_mom and is_high_volume):
            if move_1m < -dynamic_threshold: signals.append((i, "BUY_PE", audit))
    return signals

# ============================================================================
# 6. EXECUTION ENGINE
# ============================================================================

def execute_trades(bars_1m: List[Bar], opt_bars: List[Bar], signals: List[Tuple], cfg: Config, date: str) -> List[Trade]:
    trades = []
    trade_id = 1
    last_exit_idx = -1
    opt_map = {b.ts: b for b in opt_bars}
    
    for sig in signals:
        idx_1m, direction, audit = sig
        if idx_1m <= last_exit_idx: continue
        
        entry_idx = idx_1m + 1
        if entry_idx >= len(opt_bars): continue
        ts_entry = bars_1m[entry_idx].ts
        if ts_entry not in opt_map: continue
            
        opt_entry_bar = opt_map[ts_entry]
        ep = opt_entry_bar.o + cfg.entry_slippage
        tp = ep + cfg.target_points
        sl = ep - cfg.stoploss_points
        
        t = Trade(
            id=trade_id, date=date, direction=direction,
            entry_time=opt_entry_bar.time_str, entry_price=ep,
            target=tp, sl=sl, original_sl=sl, audit_atr=audit["atr"]
        )
        
        exited = False
        try: opt_idx_start = opt_bars.index(opt_entry_bar)
        except ValueError: continue
        max_idx = min(opt_idx_start + cfg.max_holding_candles, len(opt_bars))
        
        for k in range(opt_idx_start, max_idx):
            ob = opt_bars[k]
            t.candle_log.append({"t": ob.time_str, "o": ob.o, "h": ob.h, "l": ob.l, "c": ob.c})
            
            # Trailing
            if (ob.h - ep) >= cfg.trailing_trigger:
                if (ep + cfg.trailing_sl_move) > t.sl: t.sl = ep + cfg.trailing_sl_move
            
            # Exit
            hit_tp = ob.h >= tp
            hit_sl = ob.l <= t.sl
            if hit_tp and hit_sl:
                t.exit_price, t.result, t.exit_reason = t.sl, "STOPLOSS", "Choppy"
                exited = True
            elif hit_tp:
                t.exit_price, t.result, t.exit_reason = tp, "TARGET", "Target Hit"
                exited = True
            elif hit_sl:
                t.exit_price, t.result, t.exit_reason = t.sl, "STOPLOSS", "SL Hit"
                exited = True
            
            if exited:
                t.exit_time, t.pnl_pts = ob.time_str, t.exit_price - ep - cfg.exit_slippage
                t.holding_candles = k - opt_idx_start + 1
                last_exit_idx = idx_1m + t.holding_candles
                break
        
        if not exited:
            last_bar = opt_bars[max_idx-1]
            t.exit_price, t.result, t.exit_reason = last_bar.c - cfg.exit_slippage, "TIMEOUT", "Time Exit"
            t.pnl_pts = t.exit_price - ep
            t.exit_time = last_bar.time_str
            t.holding_candles = cfg.max_holding_candles
            last_exit_idx = idx_1m + cfg.max_holding_candles

        t.pnl_rs = (t.pnl_pts * cfg.lot_size) - cfg.brokerage_per_order
        trades.append(t)
        trade_id += 1
    return trades

# ============================================================================
# 7. VISUALIZER CLASS (NEW)
# ============================================================================

class Visualizer:
    @staticmethod
    def generate_html(opt_bars: List[Bar], trades: List[Trade], symbol: str, output_path: str):
        if not opt_bars: return
        
        # Filter data to trading hours only
        df = pd.DataFrame([vars(b) for b in opt_bars])
        df['dt'] = pd.to_datetime(df['dt'])
        
        # Create Figure
        fig = make_subplots(rows=1, cols=1, shared_xaxes=True)
        
        # 1. Candlestick Chart
        fig.add_trace(go.Candlestick(
            x=df['dt'], open=df['o'], high=df['h'], low=df['l'], close=df['c'],
            name=symbol
        ))
        
        # 2. Add Trade Markers
        buy_x, buy_y = [], []
        sell_x, sell_y = [], []
        colors = []
        
        for t in trades:
            # We use the Entry Time for the Buy Marker
            # We map string time to datetime object roughly
            # (Note: Exact alignment relies on the day being correct)
            try:
                # Find matching datetime in df
                entry_dt = df.loc[df['time_str'] == t.entry_time, 'dt'].values[0]
                exit_dt = df.loc[df['time_str'] == t.exit_time, 'dt'].values[0]
                
                # Plot Entry
                fig.add_trace(go.Scatter(
                    x=[entry_dt], y=[t.entry_price], mode='markers',
                    marker=dict(symbol='triangle-up', size=12, color='blue'),
                    name=f'Entry #{t.id}', showlegend=False
                ))
                
                # Plot Exit
                color = 'green' if t.pnl_pts > 0 else 'red'
                fig.add_trace(go.Scatter(
                    x=[exit_dt], y=[t.exit_price], mode='markers',
                    marker=dict(symbol='triangle-down', size=12, color=color),
                    name=f'Exit #{t.id} ({t.result})', showlegend=False
                ))
                
                # Draw Line
                fig.add_trace(go.Scatter(
                    x=[entry_dt, exit_dt], y=[t.entry_price, t.exit_price],
                    mode='lines', line=dict(color=color, width=1, dash='dot'),
                    showlegend=False
                ))
                
            except IndexError: continue

        fig.update_layout(
            title=f"Trade Execution Visualizer: {symbol}",
            yaxis_title="Option Price",
            xaxis_rangeslider_visible=False,
            height=600,
            template="plotly_dark"
        )
        
        fig.write_html(output_path)
        print(f"  📊 Visual Chart Saved: {output_path}")

# ============================================================================
# 8. MAIN RUNNER
# ============================================================================

def run():
    print("\n" + "="*60)
    print(" NIFTY SCALPER v4.2 (Adaptive + Visual)")
    print("="*60)
    
    token = input("  Groww Access Token: ").strip()
    if not token: return
    
    ce_sym = input("  CE Symbol: ").strip()
    pe_sym = input("  PE Symbol: ").strip()
    date_str = input("  Test Date (YYYY-MM-DD): ").strip()
    
    cfg = Config(
        access_token=token, ce_symbol=ce_sym, pe_symbol=pe_sym,
        dates=[date_str], trade_mode="BOTH", trigger_multiplier=1.2
    )
    
    fetcher = MTFDataFetcher(token)
    
    print("\n  [1/4] Fetching Context...")
    bars_15m = fetcher.fetch_smart("NIFTY", date_str, interval=15, days_back=7)
    bars_5m = fetcher.fetch_smart("NIFTY", date_str, interval=5, days_back=7)
    print("  [2/4] Fetching Trigger Data...")
    bars_1m = fetcher.fetch_smart("NIFTY", date_str, interval=1, days_back=0)
    
    if not bars_1m: return
    print("  [3/4] Generating Signals...")
    signals = generate_signals(bars_1m, bars_5m, bars_15m, cfg)
    print(f"       -> Signals: {len(signals)}")
    
    print("  [4/4] Executing & Visualizing...")
    all_trades = []
    
    # CE
    if ce_sym:
        opt_bars = fetcher.fetch_smart(ce_sym, date_str, interval=1, days_back=0)
        ce_trades = execute_trades(bars_1m, opt_bars, [s for s in signals if s[1]=="BUY_CE"], cfg, date_str)
        all_trades.extend(ce_trades)
        # VISUALIZE CE
        if ce_trades:
            Visualizer.generate_html(opt_bars, ce_trades, ce_sym, f"{cfg.output_dir}/chart_{ce_sym}.html")
            
    # PE
    if pe_sym:
        opt_bars = fetcher.fetch_smart(pe_sym, date_str, interval=1, days_back=0)
        pe_trades = execute_trades(bars_1m, opt_bars, [s for s in signals if s[1]=="BUY_PE"], cfg, date_str)
        all_trades.extend(pe_trades)
        # VISUALIZE PE
        if pe_trades:
            Visualizer.generate_html(opt_bars, pe_trades, pe_sym, f"{cfg.output_dir}/chart_{pe_sym}.html")

    # CSV Report
    os.makedirs(cfg.output_dir, exist_ok=True)
    ts = datetime.now().strftime("%H%M%S")
    csv_path = f"{cfg.output_dir}/trades_{ts}.csv"
    
    all_trades.sort(key=lambda x: x.entry_time)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Dir", "Entry", "Exit", "Reason", "PnL", "ATR"])
        for t in all_trades:
            w.writerow([t.id, t.direction, t.entry_time, t.exit_time, t.exit_reason, round(t.pnl_pts,2), round(t.audit_atr,2)])
            
    print(f"\n  ✅ Complete. Check '{cfg.output_dir}' for HTML charts.")
    print(f"  Total PnL: {sum(t.pnl_pts for t in all_trades):.2f} pts")

if __name__ == "__main__":
    run()