"""
NIFTY Options Scalping Opportunity Scanner
==========================================
Input: Your 1-min Index and CE data from Groww API
Output: Table of all scalping opportunities

Usage:
    scanner = OpportunityScanner(index_1min_data, ce_1min_data)
    scanner.find_opportunities()
    scanner.print_table()
"""

from datetime import datetime
from typing import List, Dict, Tuple
import json


class OpportunityScanner:
    """Scans for scalping opportunities from Index + Option data"""
    
    def __init__(self, index_data: dict, option_data: dict, option_type: str = "CE"):
        """
        Args:
            index_data: Groww API response for NIFTY index (1-min candles)
            option_data: Groww API response for CE/PE option (1-min candles)
            option_type: "CE" or "PE"
        """
        self.index_candles = index_data.get('candles', [])
        self.option_candles = option_data.get('candles', [])
        self.option_type = option_type
        
        # Create lookup for quick access
        self.option_lookup = {c[0]: c for c in self.option_candles}
        
        # Store opportunities
        self.opportunities = []
        
        # Converted timeframes
        self.index_5min = []
        self.index_15min = []
        self.option_5min = []
        self.option_15min = []
    
    def _ts_to_time(self, ts: int) -> str:
        """Convert timestamp to HH:MM format"""
        return datetime.fromtimestamp(ts).strftime("%H:%M")
    
    def _ts_to_datetime(self, ts: int) -> str:
        """Convert timestamp to full datetime"""
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    
    # =========================================================================
    # TIMEFRAME CONVERSION
    # =========================================================================
    
    def convert_to_higher_timeframe(self, candles_1min: List, minutes: int) -> List:
        """
        Convert 1-min candles to higher timeframe (5-min, 15-min)
        
        Args:
            candles_1min: List of [ts, open, high, low, close, volume] candles
            minutes: Target timeframe (5 or 15)
        
        Returns:
            List of converted candles
        """
        if not candles_1min:
            return []
        
        converted = []
        bucket = []
        
        for candle in candles_1min:
            ts = candle[0]
            dt = datetime.fromtimestamp(ts)
            
            # Calculate bucket start (align to timeframe)
            bucket_minute = (dt.minute // minutes) * minutes
            bucket_start = dt.replace(minute=bucket_minute, second=0, microsecond=0)
            bucket_ts = int(bucket_start.timestamp())
            
            if not bucket or bucket[0][0] != bucket_ts:
                # Save previous bucket
                if bucket:
                    converted.append(self._aggregate_candles(bucket))
                bucket = [(bucket_ts, candle)]
            else:
                bucket.append((bucket_ts, candle))
        
        # Don't forget last bucket
        if bucket:
            converted.append(self._aggregate_candles(bucket))
        
        return converted
    
    def _aggregate_candles(self, bucket: List[Tuple]) -> List:
        """Aggregate candles in a bucket into single OHLCV candle"""
        if not bucket:
            return None
        
        ts = bucket[0][0]  # Bucket timestamp
        candles = [b[1] for b in bucket]
        
        open_price = candles[0][1]
        high_price = max(c[2] for c in candles)
        low_price = min(c[3] for c in candles)
        close_price = candles[-1][4]
        
        # Volume: sum if available
        volume = None
        if len(candles[0]) > 5 and candles[0][5] is not None:
            volume = sum(c[5] for c in candles if c[5] is not None)
        
        return [ts, open_price, high_price, low_price, close_price, volume]
    
    def build_timeframes(self):
        """Build 5-min and 15-min data from 1-min"""
        print("📊 Converting timeframes...")
        
        self.index_5min = self.convert_to_higher_timeframe(self.index_candles, 5)
        self.index_15min = self.convert_to_higher_timeframe(self.index_candles, 15)
        self.option_5min = self.convert_to_higher_timeframe(self.option_candles, 5)
        self.option_15min = self.convert_to_higher_timeframe(self.option_candles, 15)
        
        print(f"   1-min candles: Index={len(self.index_candles)}, Option={len(self.option_candles)}")
        print(f"   5-min candles: Index={len(self.index_5min)}, Option={len(self.option_5min)}")
        print(f"   15-min candles: Index={len(self.index_15min)}, Option={len(self.option_15min)}")
    
    # =========================================================================
    # OPPORTUNITY SCANNING
    # =========================================================================
    
    def find_opportunities(self, 
                           index_threshold: float = 10.0,
                           min_profit: float = 5.0,
                           timeframe: str = "1min"):
        """
        Find all scalping opportunities
        
        Args:
            index_threshold: Minimum index move to trigger signal
            min_profit: Minimum potential profit in points
            timeframe: "1min", "5min", or "15min"
        """
        print(f"\n🔍 Scanning for opportunities (Timeframe: {timeframe})...")
        print(f"   Index threshold: {index_threshold} pts")
        print(f"   Min profit target: {min_profit} pts")
        
        # Select data based on timeframe
        if timeframe == "1min":
            index_data = self.index_candles
            option_data = self.option_candles
        elif timeframe == "5min":
            index_data = self.index_5min
            option_data = self.option_5min
        else:  # 15min
            index_data = self.index_15min
            option_data = self.option_15min
        
        # Create option lookup
        opt_lookup = {c[0]: c for c in option_data}
        
        self.opportunities = []
        
        for i in range(len(index_data) - 1):
            idx = index_data[i]
            idx_next = index_data[i + 1]
            
            ts = idx[0]
            time_str = self._ts_to_time(ts)
            
            # Skip first 5 min and last 5 min
            if time_str < "09:20" or time_str > "15:20":
                continue
            
            # Check if option data exists
            if ts not in opt_lookup or idx_next[0] not in opt_lookup:
                continue
            
            opt = opt_lookup[ts]
            opt_next = opt_lookup[idx_next[0]]
            
            # Calculate moves
            idx_open, idx_high, idx_low, idx_close = idx[1], idx[2], idx[3], idx[4]
            idx_move = idx_close - idx_open
            idx_range = idx_high - idx_low
            
            opt_open, opt_high, opt_low, opt_close = opt[1], opt[2], opt[3], opt[4]
            opt_next_open = opt_next[1]
            opt_next_high = opt_next[2]
            opt_next_low = opt_next[3]
            opt_next_close = opt_next[4]
            
            # Potential profit/loss on next candle
            potential_up = opt_next_high - opt_next_open  # If we go long
            potential_down = opt_next_open - opt_next_low  # If we go short (or PE long)
            
            # Determine opportunity
            opp = None
            
            # BULLISH signal: Index UP → CE LONG
            if idx_move >= index_threshold:
                if self.option_type == "CE" and potential_up >= min_profit:
                    opp = {
                        'signal_time': time_str,
                        'entry_time': self._ts_to_time(idx_next[0]),
                        'type': 'CE LONG ✅',
                        'index_move': f"+{idx_move:.1f}",
                        'entry': opt_next_open,
                        'target': opt_next_high,
                        'sl': opt_next_low,
                        'profit': potential_up,
                        'risk': potential_down,
                        'rr': round(potential_up / potential_down, 2) if potential_down > 0 else 999,
                        'result': '✅ WIN' if potential_up >= min_profit else '❌ LOSS'
                    }
                elif self.option_type == "PE" and potential_down >= min_profit:
                    opp = {
                        'signal_time': time_str,
                        'entry_time': self._ts_to_time(idx_next[0]),
                        'type': 'PE SHORT ⚠️',
                        'index_move': f"+{idx_move:.1f}",
                        'entry': opt_next_open,
                        'target': opt_next_low,
                        'sl': opt_next_high,
                        'profit': potential_down,
                        'risk': potential_up,
                        'rr': round(potential_down / potential_up, 2) if potential_up > 0 else 999,
                        'result': '✅ WIN' if potential_down >= min_profit else '❌ LOSS'
                    }
            
            # BEARISH signal: Index DOWN → PE LONG (or CE SHORT)
            elif idx_move <= -index_threshold:
                if self.option_type == "CE" and potential_down >= min_profit:
                    opp = {
                        'signal_time': time_str,
                        'entry_time': self._ts_to_time(idx_next[0]),
                        'type': 'CE SHORT (PE LONG) 📉',
                        'index_move': f"{idx_move:.1f}",
                        'entry': opt_next_open,
                        'target': opt_next_low,
                        'sl': opt_next_high,
                        'profit': potential_down,
                        'risk': potential_up,
                        'rr': round(potential_down / potential_up, 2) if potential_up > 0 else 999,
                        'result': '✅ WIN' if potential_down >= min_profit else '❌ LOSS'
                    }
                elif self.option_type == "PE" and potential_up >= min_profit:
                    opp = {
                        'signal_time': time_str,
                        'entry_time': self._ts_to_time(idx_next[0]),
                        'type': 'PE LONG ✅',
                        'index_move': f"{idx_move:.1f}",
                        'entry': opt_next_open,
                        'target': opt_next_high,
                        'sl': opt_next_low,
                        'profit': potential_up,
                        'risk': potential_down,
                        'rr': round(potential_up / potential_down, 2) if potential_down > 0 else 999,
                        'result': '✅ WIN' if potential_up >= min_profit else '❌ LOSS'
                    }
            
            if opp:
                self.opportunities.append(opp)
        
        print(f"   Found: {len(self.opportunities)} opportunities")
        return self.opportunities
    
    # =========================================================================
    # OUTPUT
    # =========================================================================
    
    def print_table(self):
        """Print opportunities as formatted table"""
        if not self.opportunities:
            print("\n⚠️ No opportunities found!")
            return
        
        print("\n" + "=" * 120)
        print("SCALPING OPPORTUNITIES - February 6, 2026")
        print("=" * 120)
        
        # Header
        header = f"{'Signal':<8} {'Entry':<8} {'Type':<22} {'Index':<10} {'Entry₹':<10} {'Target₹':<10} {'SL₹':<10} {'Profit':<8} {'Risk':<8} {'R:R':<6} {'Result'}"
        print(header)
        print("-" * 120)
        
        total_profit = 0
        wins = 0
        
        for opp in self.opportunities:
            row = f"{opp['signal_time']:<8} {opp['entry_time']:<8} {opp['type']:<22} {opp['index_move']:<10} {opp['entry']:<10.2f} {opp['target']:<10.2f} {opp['sl']:<10.2f} {opp['profit']:<8.2f} {opp['risk']:<8.2f} {opp['rr']:<6.2f} {opp['result']}"
            print(row)
            
            if '✅' in opp['result']:
                total_profit += opp['profit']
                wins += 1
            else:
                total_profit -= opp['risk']
        
        print("-" * 120)
        print(f"SUMMARY: {len(self.opportunities)} trades | {wins} wins | Win Rate: {wins/len(self.opportunities)*100:.1f}% | Net P&L: {total_profit:.2f} pts")
        print("=" * 120)
    
    def get_dataframe_dict(self) -> List[Dict]:
        """Return opportunities as list of dicts (for pandas/CSV)"""
        return self.opportunities
    
    def export_csv(self, filename: str = "opportunities.csv"):
        """Export opportunities to CSV"""
        if not self.opportunities:
            print("No opportunities to export!")
            return
        
        import csv
        
        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.opportunities[0].keys())
            writer.writeheader()
            writer.writerows(self.opportunities)
        
        print(f"📄 Exported to {filename}")


# =============================================================================
# USAGE EXAMPLE
# =============================================================================

if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║       NIFTY OPTIONS SCALPING OPPORTUNITY SCANNER              ║
    ╚═══════════════════════════════════════════════════════════════╝
    
    Usage:
    
    1. Load your Groww API data:
    
       index_data = groww.get_historical_candle_data(
           trading_symbol="NIFTY",
           segment=groww.SEGMENT_CASH,
           interval_in_minutes=1
       )
       
       ce_data = groww.get_historical_candle_data(
           trading_symbol="NIFTY2621025850CE",
           segment=groww.SEGMENT_FNO,
           interval_in_minutes=1
       )
    
    2. Create scanner and find opportunities:
    
       scanner = OpportunityScanner(index_data, ce_data, option_type="CE")
       scanner.build_timeframes()  # Creates 5-min and 15-min data
       
       # Scan different timeframes
       scanner.find_opportunities(index_threshold=10, min_profit=5, timeframe="1min")
       scanner.print_table()
       
       scanner.find_opportunities(index_threshold=15, min_profit=5, timeframe="5min")
       scanner.print_table()
    
    3. Export results:
       scanner.export_csv("opportunities.csv")
    """)
