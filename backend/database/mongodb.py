"""
MongoDB Database Operations
"""
from pymongo import MongoClient, ASCENDING, DESCENDING, UpdateOne
from pymongo.errors import DuplicateKeyError
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from bson import ObjectId
from config import config


class MongoDB:
    """MongoDB database handler"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize MongoDB connection and create indexes"""
        self.client = MongoClient(config.MONGO_URI)
        self.db = self.client[config.MONGO_DB_NAME]
        
        # Collections
        self.users = self.db['users']
        self.strategies = self.db['strategies']
        self.trades = self.db['trades']
        self.signals = self.db['signals']
        self.settings = self.db['settings']
        self.instruments = self.db['instruments']
        self.candles = self.db['candles']  # Candle data for charts
        self.paper_account = self.db['paper_account']
        self.trade_journal = self.db['trade_journal']
        self.daily_summary = self.db['daily_summary']
        self.signal_log = self.db['signal_log']  # decision snapshots for calibration
        # Backtesting Machine collections.
        self.backtest_runs = self.db['backtest_runs']
        self.backtest_trades = self.db['backtest_trades']
        self.backtest_reports = self.db['backtest_reports']
        self.backtest_datasets = self.db['backtest_datasets']
        self.backtest_presets = self.db['backtest_presets']

        self._create_indexes()
    
    def _create_indexes(self):
        """Create database indexes for performance"""
        try:
            # Users
            self.users.create_index('email', unique=True)
            # broker_connected is queried by the scheduler/reconcile every cycle.
            self.users.create_index('broker_connected')
            self.users.create_index([('execution_mode', ASCENDING), ('broker_connected', ASCENDING)])
            
            # Strategies
            self.strategies.create_index([('user_id', ASCENDING)])
            self.strategies.create_index([('is_active', ASCENDING)])
            
            # Trades
            self.trades.create_index([('user_id', ASCENDING), ('created_at', DESCENDING)])
            self.trades.create_index([('strategy_id', ASCENDING)])
            self.trades.create_index([('status', ASCENDING)])
            
            # Signals
            self.signals.create_index([('created_at', DESCENDING)])
            self.signals.create_index([('symbol', ASCENDING)])
            
            # Instruments
            self.instruments.create_index([('underlying_symbol', ASCENDING)])
            self.instruments.create_index([('trading_symbol', ASCENDING)])
            self.instruments.create_index([('expiry_date', ASCENDING)])
            self.instruments.create_index([('strike_price', ASCENDING)])
            
            # Signal log (calibration dataset)
            self.signal_log.create_index([('created_at', DESCENDING)])
            self.signal_log.create_index([('strategy_id', ASCENDING), ('created_at', DESCENDING)])

            # Backtesting Machine
            self.backtest_runs.create_index([('user_id', ASCENDING), ('started_at', DESCENDING)])
            self.backtest_runs.create_index('run_id', unique=True)
            self.backtest_trades.create_index([('run_id', ASCENDING), ('entry_bar', ASCENDING)])
            self.backtest_reports.create_index('run_id', unique=True)
            self.backtest_presets.create_index([('user_id', ASCENDING)])

            # Candles - Compound index for fast retrieval
            self.candles.create_index([('symbol', ASCENDING), ('interval', ASCENDING)])
            # Unique index to prevent duplicates at the DB level
            self.candles.create_index([('symbol', ASCENDING), ('interval', ASCENDING), ('timestamp', DESCENDING)], unique=True)
        except Exception as e:
            print(f"Index creation warning: {e}")
    
    # ==================== CANDLE OPERATIONS ====================
    
    def upsert_candles(self, symbol: str, interval: str, candles: List[Dict]):
        """
        Upsert candles (Update if exists, Insert if new).
        Preserves history and prevents Duplicate Key Errors.
        """
        if not candles:
            return

        # 1. Deduplicate Input List (Safety check)
        unique_candles_map = {c['timestamp']: c for c in candles}
        unique_candles = list(unique_candles_map.values())

        operations = []
        for candle in unique_candles:
            # Prepare filter
            filter_query = {
                'symbol': symbol,
                'interval': str(interval),
                'timestamp': candle['timestamp']
            }
            
            # Ensure metadata matches
            candle['symbol'] = symbol
            candle['interval'] = str(interval)
            
            # Remove _id if present to avoid immutable field error during update
            if '_id' in candle:
                del candle['_id']
            
            # Create Upsert Operation
            operations.append(
                UpdateOne(filter_query, {'$set': candle}, upsert=True)
            )
        
        if operations:
            try:
                # Ordered=False allows successful writes even if one fails
                self.candles.bulk_write(operations, ordered=False)
            except Exception as e:
                # Log but don't crash on bulk write errors (e.g. slight race conditions)
                if "E11000" not in str(e):
                    print(f"Bulk write error: {e}")

    def save_candles(self, symbol: str, interval: str, candles: List[Dict]) -> int:
        """
        Legacy Save: Redirects to upsert_candles to prevent data wiping.
        """
        self.upsert_candles(symbol, interval, candles)
        return len(candles)
    
    def get_candles(self, symbol: str, interval: str = '5', limit: int = 100) -> List[Dict]:
        """Get candles for a symbol"""
        candles = list(self.candles.find(
            {'symbol': symbol, 'interval': str(interval)}
        ).sort('timestamp', DESCENDING).limit(limit))
        
        for c in candles:
            c['_id'] = str(c['_id'])
        
        return list(reversed(candles))  # Return in chronological order

    # ==================== USER OPERATIONS ====================
    def create_user(self, user_data: Dict) -> str:
        user_data['created_at'] = datetime.utcnow()
        user_data['updated_at'] = datetime.utcnow()
        result = self.users.insert_one(user_data)
        return str(result.inserted_id)
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        return self.users.find_one({'email': email})
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        try: return self.users.find_one({'_id': ObjectId(user_id)})
        except: return None
    
    def update_user(self, user_id: str, update_data: Dict) -> bool:
        update_data['updated_at'] = datetime.utcnow()
        result = self.users.update_one({'_id': ObjectId(user_id)}, {'$set': update_data})
        return result.modified_count > 0

    def update_user_token(self, user_id: str, token_data: Dict) -> bool:
        return self.update_user(user_id, {
            'groww_access_token': token_data['token'],
            'groww_token_expiry': token_data['expiry'],
            'groww_token_ref_id': token_data.get('tokenRefId'),
            'broker_connected': True
        })

    # ==================== STRATEGY OPERATIONS ====================
    def create_strategy(self, strategy_data: Dict) -> str:
        strategy_data['created_at'] = datetime.utcnow()
        strategy_data['updated_at'] = datetime.utcnow()
        strategy_data['today_orders'] = 0
        strategy_data['today_pnl'] = 0.0
        result = self.strategies.insert_one(strategy_data)
        return str(result.inserted_id)
    
    def get_strategies_by_user(self, user_id: str) -> List[Dict]:
        strategies = list(self.strategies.find({'user_id': user_id}))
        for s in strategies: s['_id'] = str(s['_id'])
        return strategies
    
    def get_strategy_by_id(self, strategy_id: str) -> Optional[Dict]:
        try:
            strategy = self.strategies.find_one({'_id': ObjectId(strategy_id)})
            if strategy: strategy['_id'] = str(strategy['_id'])
            return strategy
        except: return None
    
    def update_strategy(self, strategy_id: str, update_data: Dict) -> bool:
        update_data['updated_at'] = datetime.utcnow()
        result = self.strategies.update_one({'_id': ObjectId(strategy_id)}, {'$set': update_data})
        return result.modified_count > 0
    
    def delete_strategy(self, strategy_id: str) -> bool:
        result = self.strategies.delete_one({'_id': ObjectId(strategy_id)})
        return result.deleted_count > 0
    
    def get_active_strategies(self, user_id: str = None) -> List[Dict]:
        query = {'is_active': True}
        if user_id: query['user_id'] = user_id
        strategies = list(self.strategies.find(query))
        for s in strategies: s['_id'] = str(s['_id'])
        return strategies
    
    def increment_strategy_orders(self, strategy_id: str) -> bool:
        result = self.strategies.update_one({'_id': ObjectId(strategy_id)}, {'$inc': {'today_orders': 1}})
        return result.modified_count > 0
    
    def update_strategy_pnl(self, strategy_id: str, pnl: float) -> bool:
        result = self.strategies.update_one({'_id': ObjectId(strategy_id)}, {'$inc': {'today_pnl': pnl}})
        return result.modified_count > 0
    
    def reset_daily_strategy_counters(self):
        self.strategies.update_many({}, {'$set': {'today_orders': 0, 'today_pnl': 0.0}})

    # ==================== TRADE OPERATIONS ====================
    def create_trade(self, trade_data: Dict) -> str:
        trade_data['created_at'] = datetime.utcnow()
        trade_data['updated_at'] = datetime.utcnow()
        result = self.trades.insert_one(trade_data)
        return str(result.inserted_id)
    
    def get_trade_by_id(self, trade_id: str) -> Optional[Dict]:
        try:
            trade = self.trades.find_one({'_id': ObjectId(trade_id)})
            if trade: trade['_id'] = str(trade['_id'])
            return trade
        except: return None
    
    def get_trades_by_user(self, user_id: str, limit: int = 50, status: str = None) -> List[Dict]:
        query = {'user_id': user_id}
        if status: query['status'] = status
        trades = list(self.trades.find(query).sort('created_at', DESCENDING).limit(limit))
        for t in trades: t['_id'] = str(t['_id'])
        return trades
    
    def get_active_trades(self, user_id: str = None) -> List[Dict]:
        query = {'status': 'OPEN'}
        if user_id: query['user_id'] = user_id
        trades = list(self.trades.find(query))
        for t in trades: t['_id'] = str(t['_id'])
        return trades
    
    def update_trade(self, trade_id: str, update_data: Dict) -> bool:
        update_data['updated_at'] = datetime.utcnow()
        result = self.trades.update_one({'_id': ObjectId(trade_id)}, {'$set': update_data})
        return result.modified_count > 0
    
    def close_trade(self, trade_id: str, exit_data: Dict) -> bool:
        exit_data['status'] = 'CLOSED'
        exit_data['exit_time'] = datetime.utcnow()
        return self.update_trade(trade_id, exit_data)
    
    def get_trades_by_strategy(self, strategy_id: str, limit: int = 50) -> List[Dict]:
        trades = list(self.trades.find({'strategy_id': strategy_id}).sort('created_at', DESCENDING).limit(limit))
        for t in trades: t['_id'] = str(t['_id'])
        return trades
    
    def get_today_trades(self, user_id: str) -> List[Dict]:
        # "Today" = the IST trading day. created_at is stored as naive UTC
        # (datetime.utcnow()), so compute IST midnight then express it in naive
        # UTC for the comparison. Using UTC midnight here would start the day at
        # 05:30 IST and mis-bucket early-session trades.
        import pytz
        from utils.time_utils import get_ist_now
        ist_midnight = get_ist_now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_start = ist_midnight.astimezone(pytz.utc).replace(tzinfo=None)
        trades = list(self.trades.find({'user_id': user_id, 'created_at': {'$gte': today_start}}))
        for t in trades: t['_id'] = str(t['_id'])
        return trades

    # ==================== SIGNAL LOG (calibration) ====================
    def log_signal(self, doc: Dict) -> bool:
        """Append a decision-engine signal snapshot for later P(win) calibration."""
        try:
            doc = dict(doc)
            doc.setdefault('created_at', datetime.utcnow())
            self.signal_log.insert_one(doc)
            return True
        except Exception as e:
            print(f"log_signal error: {e}")
            return False

    # ==================== SETTINGS OPERATIONS ====================
    def get_settings(self, user_id: str) -> Optional[Dict]:
        settings = self.settings.find_one({'user_id': user_id})
        if settings: settings['_id'] = str(settings['_id'])
        return settings
    
    def upsert_settings(self, user_id: str, settings_data: Dict) -> bool:
        settings_data['user_id'] = user_id
        settings_data['updated_at'] = datetime.utcnow()
        result = self.settings.update_one({'user_id': user_id}, {'$set': settings_data}, upsert=True)
        return result.acknowledged

    # ==================== INSTRUMENT OPERATIONS ====================
    def swap_instruments(self, instruments: List[Dict]) -> bool:
        """Atomically replace the instruments collection via a staging swap.

        Avoids the empty-collection window of delete_many + insert_many, during
        which ATM/strike resolution for live trades would find no instruments.
        Indexes are built on staging BEFORE the rename so the live collection is
        never index-less.
        """
        if not instruments:
            return False
        staging = self.db['instruments_staging']
        staging.delete_many({})
        for inst in instruments:
            inst['synced_at'] = datetime.utcnow()
        staging.insert_many(instruments)
        staging.create_index([('underlying_symbol', ASCENDING)])
        staging.create_index([('trading_symbol', ASCENDING)])
        staging.create_index([('expiry_date', ASCENDING)])
        staging.create_index([('strike_price', ASCENDING)])
        staging.create_index([('underlying_symbol', ASCENDING), ('expiry_date', ASCENDING)])
        # Atomic server-side rename onto the live collection.
        staging.rename('instruments', dropTarget=True)
        return True

    def bulk_upsert_instruments(self, instruments: List[Dict]):
        # Delegate to the atomic staging swap (no empty-collection window).
        return self.swap_instruments(instruments)
    
    def get_instruments_by_underlying(self, underlying: str, expiry: str = None, option_type: str = None) -> List[Dict]:
        query = {'underlying_symbol': underlying}
        if expiry: query['expiry_date'] = expiry
        if option_type: query['instrument_type'] = option_type
        instruments = list(self.instruments.find(query).sort('strike_price', ASCENDING))
        for i in instruments: i['_id'] = str(i['_id'])
        return instruments

    def get_available_expiries(self, underlying: str) -> List[str]:
        expiries = self.instruments.distinct('expiry_date', {'underlying_symbol': underlying})
        return sorted(expiries)
    
    def get_instrument_by_symbol(self, trading_symbol: str) -> Optional[Dict]:
        instrument = self.instruments.find_one({'trading_symbol': trading_symbol})
        if instrument: instrument['_id'] = str(instrument['_id'])
        return instrument
    
    def find_instrument_by_strike(self, underlying: str, strike: float, option_type: str) -> Optional[Dict]:
        instrument = self.instruments.find_one({
            'underlying_symbol': underlying, 'strike_price': strike, 'instrument_type': option_type
        }, sort=[('expiry_date', ASCENDING)])
        if instrument: instrument['_id'] = str(instrument['_id'])
        return instrument
    
    def get_atm_strikes(self, underlying: str, expiry: str, spot_price: float) -> Dict:
        instruments = self.get_instruments_by_underlying(underlying, expiry)
        ce_options = [i for i in instruments if i.get('instrument_type') == 'CE']
        if not ce_options: return {}
        strikes = sorted(set(i['strike_price'] for i in ce_options))
        if not strikes: return {}
        atm_strike = min(strikes, key=lambda x: abs(x - spot_price))
        return {'atm_strike': atm_strike, 'spot_price': spot_price, 'strikes': strikes}
    
    # ==================== PAPER ACCOUNT ====================
    def reset_paper_account(self, user_id: str, initial_capital: float) -> bool:
        return self.upsert_paper_account(user_id, {
            'balance': initial_capital, 'initial_capital': initial_capital,
            'realized_pnl': 0.0, 'unrealized_pnl': 0.0, 'positions': [], 'reset_at': datetime.utcnow()
        })

    def upsert_paper_account(self, user_id: str, account_data: Dict) -> bool:
        account_data['user_id'] = user_id
        account_data['updated_at'] = datetime.utcnow()
        result = self.paper_account.update_one({'user_id': user_id}, {'$set': account_data}, upsert=True)
        return result.acknowledged
    
    def get_paper_account(self, user_id: str) -> Optional[Dict]:
        account = self.paper_account.find_one({'user_id': user_id})
        if account: account['_id'] = str(account['_id'])
        return account

    # ==================== JOURNAL & SUMMARY ====================
    def save_daily_summary(self, user_id: str, date: str, summary_data: Dict):
        summary_data['user_id'] = user_id
        summary_data['date'] = date
        summary_data['created_at'] = datetime.utcnow()
        self.daily_summary.update_one({'user_id': user_id, 'date': date}, {'$set': summary_data}, upsert=True)
    
    def get_daily_summaries(self, user_id: str, days: int = 30) -> List[Dict]:
        summaries = list(self.daily_summary.find({'user_id': user_id}).sort('date', DESCENDING).limit(days))
        for s in summaries: s['_id'] = str(s['_id'])
        return summaries

    def add_journal_entry(self, trade_id: str, user_id: str, entry_data: Dict) -> str:
        entry_data['trade_id'] = trade_id
        entry_data['user_id'] = user_id
        entry_data['created_at'] = datetime.utcnow()
        result = self.trade_journal.insert_one(entry_data)
        return str(result.inserted_id)

    def get_user_journal(self, user_id: str, limit: int = 50) -> List[Dict]:
        entries = list(self.trade_journal.find({'user_id': user_id}).sort('created_at', DESCENDING).limit(limit))
        for e in entries: e['_id'] = str(e['_id'])
        return entries
    
    # ==================== SIGNALS ====================
    def create_signal(self, signal_data: Dict) -> str:
        signal_data['created_at'] = datetime.utcnow()
        result = self.signals.insert_one(signal_data)
        return str(result.inserted_id)
    
    def get_recent_signals(self, symbol: str = None, limit: int = 20) -> List[Dict]:
        query = {}
        if symbol: query['symbol'] = symbol
        signals = list(self.signals.find(query).sort('created_at', DESCENDING).limit(limit))
        for s in signals: s['_id'] = str(s['_id'])
        return signals

    # ==================== BACKTEST OPERATIONS ====================
    def create_backtest_run(self, run_doc: Dict) -> str:
        run_doc.setdefault('created_at', datetime.utcnow())
        self.backtest_runs.insert_one(run_doc)
        return run_doc['run_id']

    def update_backtest_run(self, run_id: str, updates: Dict) -> bool:
        updates['updated_at'] = datetime.utcnow()
        r = self.backtest_runs.update_one({'run_id': run_id}, {'$set': updates})
        return r.modified_count > 0

    def get_backtest_run(self, run_id: str, user_id: str = None) -> Optional[Dict]:
        q = {'run_id': run_id}
        if user_id:
            q['user_id'] = user_id
        doc = self.backtest_runs.find_one(q, {'_id': 0})
        return doc

    def list_backtest_runs(self, user_id: str, limit: int = 50) -> List[Dict]:
        return list(self.backtest_runs.find(
            {'user_id': user_id}, {'_id': 0}
        ).sort('started_at', DESCENDING).limit(limit))

    def save_backtest_trades(self, run_id: str, trades: List[Dict]) -> int:
        if not trades:
            return 0
        self.backtest_trades.delete_many({'run_id': run_id})
        docs = []
        for i, t in enumerate(trades):
            d = dict(t)
            d['run_id'] = run_id
            d.setdefault('entry_bar', i)
            docs.append(d)
        self.backtest_trades.insert_many(docs)
        return len(docs)

    def get_backtest_trades(self, run_id: str, skip: int = 0, limit: int = 100) -> List[Dict]:
        return list(self.backtest_trades.find(
            {'run_id': run_id}, {'_id': 0}
        ).sort('entry_bar', ASCENDING).skip(skip).limit(limit))

    def count_backtest_trades(self, run_id: str) -> int:
        return self.backtest_trades.count_documents({'run_id': run_id})

    def save_backtest_report(self, run_id: str, report: Dict) -> bool:
        report['run_id'] = run_id
        report['saved_at'] = datetime.utcnow()
        r = self.backtest_reports.update_one({'run_id': run_id}, {'$set': report}, upsert=True)
        return r.acknowledged

    def get_backtest_report(self, run_id: str) -> Optional[Dict]:
        return self.backtest_reports.find_one({'run_id': run_id}, {'_id': 0})


# Singleton instance
db = MongoDB()
mongo_client = db.client