"""
Instrument Sync Service
Downloads and syncs F&O instruments from Groww daily
"""
from typing import List, Dict, Optional
from datetime import datetime
import pandas as pd
from database import db
from config import config

class InstrumentSync:
    """Service to sync F&O instruments from Groww"""
    
    def __init__(self):
        self.supported_underlyings = config.SUPPORTED_UNDERLYINGS if hasattr(config, 'SUPPORTED_UNDERLYINGS') else ['NIFTY', 'BANKNIFTY', 'SENSEX', 'FINNIFTY', 'MIDCPNIFTY']
    
    def sync_instruments(self) -> Dict:
        """Download and sync instruments from Groww"""
        # Lazy import to prevent circular dependency
        from services.groww_client import GrowwClient
        
        try:
            print("Downloading instruments from Groww...")
            df = GrowwClient.download_instruments()
            
            if df.empty:
                return {'success': False, 'error': 'Failed to download instruments CSV'}
            
            print(f"Downloaded {len(df)} total instruments")
            
            fno_df = GrowwClient.filter_fno_instruments(df, self.supported_underlyings)
            
            # Get current expiry instruments (limit to nearest 3 expiries to keep DB clean)
            current_df = GrowwClient.get_current_expiry_instruments(fno_df, max_expiries=3)
            
            if current_df.empty:
                return {'success': False, 'error': 'No current expiry instruments found'}
            
            instruments = self._prepare_instruments(current_df)

            # Atomic staging swap (no empty-collection window for live lookups);
            # indexes are rebuilt on staging before the rename.
            db.swap_instruments(instruments)

            summary = self._get_sync_summary(current_df)
            
            return {
                'success': True,
                'total_instruments': len(instruments),
                'summary': summary,
                'synced_at': datetime.utcnow().isoformat()
            }
        except Exception as e:
            print(f"Sync Error: {e}")
            return {'success': False, 'error': str(e)}
    
    def _prepare_instruments(self, df: pd.DataFrame) -> List[Dict]:
        """Convert DataFrame to list of instrument dicts"""
        instruments = []
        for _, row in df.iterrows():
            instrument = {
                'exchange': row.get('exchange', 'NSE'),
                'exchange_token': row.get('exchange_token'),
                'trading_symbol': row.get('trading_symbol'),
                'groww_symbol': row.get('symbol_name') or row.get('groww_symbol'),
                'instrument_type': row.get('instrument_type'),
                'segment': 'FNO',
                'underlying_symbol': row.get('underlying_symbol'),
                'expiry_date': row.get('expiry_date').strftime('%Y-%m-%d') if pd.notna(row.get('expiry_date')) else None,
                'strike_price': float(row.get('strike_price', 0)),
                'lot_size': int(row.get('lot_size', 1)),
                'tick_size': float(row.get('tick_size', 0.05)),
                'buy_allowed': True,
                'sell_allowed': True,
                'synced_at': datetime.utcnow()
            }
            instruments.append(instrument)
        return instruments
    
    def _get_sync_summary(self, df: pd.DataFrame) -> Dict:
        """Get summary of synced instruments"""
        summary = {}
        for underlying in self.supported_underlyings:
            underlying_df = df[df['underlying_symbol'] == underlying]
            if not underlying_df.empty:
                expiries = underlying_df['expiry_date'].unique()
                summary[underlying] = {
                    'total': len(underlying_df),
                    'expiries': [e.strftime('%Y-%m-%d') for e in sorted(expiries)]
                }
        return summary
    
    def get_atm_options(self, underlying: str, expiry: str, spot_price: float) -> Dict:
        """Get ATM CE and PE options"""
        query = {'underlying_symbol': underlying, 'expiry_date': expiry}
        instruments = list(db.instruments.find(query))
        
        if not instruments:
            return {}
        
        strikes = sorted(set(i['strike_price'] for i in instruments))
        if not strikes:
             return {}

        atm_strike = min(strikes, key=lambda x: abs(x - spot_price))
        
        return {
            'spot_price': spot_price,
            'atm_strike': atm_strike,
            'strikes': strikes
        }
    
    def search_instruments(self, query: str = "", underlying: str = None, expiry: str = None, limit: int = 20) -> List[Dict]:
        """Search instruments with filters"""
        mongo_query = {}
        if query:
            mongo_query['trading_symbol'] = {'$regex': query, '$options': 'i'}
        if underlying:
            mongo_query['underlying_symbol'] = underlying
        if expiry:
            mongo_query['expiry_date'] = expiry

        cursor = db.instruments.find(mongo_query).limit(limit)
        
        results = []
        for i in cursor:
            i['_id'] = str(i['_id'])
            if 'synced_at' in i and isinstance(i['synced_at'], datetime):
                i['synced_at'] = i['synced_at'].isoformat()
            results.append(i)
        return results

    def get_instrument_by_symbol(self, trading_symbol: str) -> Optional[Dict]:
        """Get full details of a single instrument"""
        instrument = db.instruments.find_one({'trading_symbol': trading_symbol})
        if instrument:
            instrument['_id'] = str(instrument['_id'])
            if 'synced_at' in instrument and isinstance(instrument['synced_at'], datetime):
                instrument['synced_at'] = instrument['synced_at'].isoformat()
            return instrument
        return None

    def get_count(self):
        """Get summary counts"""
        pipeline = [{"$group": {"_id": "$underlying_symbol", "count": {"$sum": 1}}}]
        aggs = list(db.instruments.aggregate(pipeline))
        summary = {item['_id']: item['count'] for item in aggs if item['_id']}
        return {'total': sum(summary.values()), 'by_underlying': summary}

instrument_sync = InstrumentSync()