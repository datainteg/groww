"""
Scheduler Service
Handles scheduled jobs: Market Heartbeat, Candle Sync (1m + Aggregation), and Maintenance
"""
import sys
import os
import time
import uuid
import pandas as pd
import numpy as np
from datetime import datetime

# Ensure parent directory is visible
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from database.mongodb import db
from database.redis_client import redis_client
from config import config
from utils.time_utils import get_ist_now, is_market_open
from utils import encryption

# Services & Analysis
from services.candle_service import candle_service
from analysis.timeframe_aggregator import timeframe_aggregator

class SchedulerService:
    """Background scheduler for automated trading tasks"""

    # Leader election so only ONE process drives the jobs even when the web app
    # runs under a multi-worker WSGI server (gunicorn/uwsgi).
    LEADER_KEY = 'scheduler:leader'
    LEADER_TTL = 30  # seconds; renewed every heartbeat tick
    HEARTBEAT_KEY = 'scheduler:last_heartbeat'

    # Atomic compare-and-set renewal: only the current owner may extend the TTL.
    # Prevents a delayed-then-revived instance from stealing leadership back after
    # its key already expired and another instance took over.
    _RENEW_LUA = (
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end"
    )

    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone='Asia/Kolkata')
        self._setup_jobs()
        self.active_user_id = None
        self.instance_id = uuid.uuid4().hex
        self.is_leader = False
        # Cached trading context so the 5s heartbeat doesn't hit Mongo + decrypt
        # the token on every tick.
        self._ctx_user_id = None
        self._ctx_client = None
        self._ctx_engine = None
        self._ctx_checked_at = 0.0

    def _redis(self):
        """Return the raw redis client or None if unavailable."""
        return getattr(redis_client, 'client', None)

    def _has_leadership(self) -> bool:
        return self.is_leader

    def _acquire_leadership(self) -> bool:
        """Try to become the single scheduler leader. If Redis is unavailable
        (e.g. local single-process dev), allow startup."""
        client = self._redis()
        if not client:
            self.is_leader = True
            return True
        try:
            won = bool(client.set(self.LEADER_KEY, self.instance_id,
                                  nx=True, ex=self.LEADER_TTL))
            self.is_leader = won
            return won
        except Exception:
            # Redis error: fail open in dev so the single process still runs.
            self.is_leader = True
            return True

    def _renew_leadership(self) -> bool:
        """Extend the lock ONLY if we still own it (atomic CAS). If ownership was
        lost (key expired and taken by another instance), stand down and stop."""
        client = self._redis()
        if not client:
            return True  # single-process dev
        try:
            renewed = client.eval(self._RENEW_LUA, 1, self.LEADER_KEY,
                                  self.instance_id, self.LEADER_TTL)
            if not renewed:
                if self.is_leader:
                    print(f"[{get_ist_now()}] Lost scheduler leadership; standing down.")
                self.is_leader = False
                if self.scheduler.running:
                    self.scheduler.shutdown(wait=False)
                return False
            self.is_leader = True
            return True
        except Exception:
            # Don't tear down on a transient Redis error.
            return self.is_leader

    def _mark_heartbeat(self):
        """Publish liveness so the API process can report scheduler health."""
        client = self._redis()
        if not client:
            return
        try:
            client.set(self.HEARTBEAT_KEY, str(int(time.time())), ex=120)
        except Exception:
            pass

    def _get_trading_context(self):
        """Return (user_id, client, engine), cached. Re-resolves the active user
        at most every 30s and rebuilds client/engine only when the user changes.
        Avoids a Mongo lookup + token decrypt on every 5s heartbeat tick."""
        now = time.time()
        if self._ctx_client is not None and (now - self._ctx_checked_at) < 30:
            return self._ctx_user_id, self._ctx_client, self._ctx_engine

        self._ctx_checked_at = now
        user = self._get_active_user()
        if not user:
            self._ctx_user_id = self._ctx_client = self._ctx_engine = None
            return None, None, None

        user_id = str(user['_id'])
        if user_id != self._ctx_user_id or self._ctx_client is None:
            from services.groww_client import get_groww_client
            from services.trading_engine import get_trading_engine
            self._ctx_user_id = user_id
            self._ctx_client = get_groww_client(user_id)
            self._ctx_engine = get_trading_engine(user_id)
        return self._ctx_user_id, self._ctx_client, self._ctx_engine

    def _get_active_user(self):
        """
        Helper to fetch the currently active/logged-in user.
        Prioritizes user with broker connected.
        """
        # Find user who has completed broker login
        user = db.users.find_one({'broker_connected': True})
        if user:
            return user
        return None

    def _setup_jobs(self):
        """Setup scheduled jobs"""
        
        # 1. MARKET HEARTBEAT (Every 5 Seconds) - Live Prices
        self.scheduler.add_job(
            self.market_heartbeat_job,
            IntervalTrigger(seconds=5),
            id='market_heartbeat',
            replace_existing=True,
            max_instances=1
        )
        
        # 2. MASTER SYNC & AGGREGATE (Every 1 Minute)
        # Fetches 1-min data and aggregates to 5m, 15m, 60m, 1D
        self.scheduler.add_job(
            self.sync_and_aggregate_job,
            CronTrigger(minute='*/1'),  # Runs every minute
            id='sync_and_aggregate',
            replace_existing=True,
            max_instances=1
        )

        # 3. SAFETY NET / RECONCILIATION (Every 1 Minute)
        self.scheduler.add_job(
            self.reconcile_orders_job,
            IntervalTrigger(minutes=1),
            id='reconcile_orders',
            replace_existing=True,
            max_instances=1
        )

        # 4. MAINTENANCE JOBS
        self.scheduler.add_job(
            self.sync_instruments_job,
            CronTrigger(hour=8, minute=0),
            id='instrument_sync',
            replace_existing=True
        )
        
        self.scheduler.add_job(
            self.daily_reset_job,
            CronTrigger(hour=6, minute=5),
            id='daily_reset',
            replace_existing=True
        )
        
        self.scheduler.add_job(
            self.daily_summary_job,
            CronTrigger(hour=15, minute=35, day_of_week='mon-fri'),
            id='daily_summary',
            replace_existing=True
        )

        # 5. SIGNAL LABELLING (Every hour, Mon-Fri) — labels pending signal_log
        #    docs with forward returns so the calibration model can be retrained.
        #    Guarded by _has_leadership() inside the job body; never raises.
        self.scheduler.add_job(
            self.label_signals_job,
            CronTrigger(minute=50, day_of_week='mon-fri'),
            id='label_signals',
            replace_existing=True
        )

    def start(self):
        """Start the scheduler safely with user check + single-instance guard."""
        if self.scheduler.running:
            return

        # Only one process may drive the jobs.
        if not self._acquire_leadership():
            print(f"[{get_ist_now()}] Scheduler NOT started: another instance is leader.")
            return

        user = self._get_active_user()
        if user:
            self.active_user_id = user['_id']
            print(f"[{get_ist_now()}] Scheduler Initialized for User: {user.get('name', 'Trader')} ({user.get('email')})")
        else:
            print(f"[{get_ist_now()}] Scheduler Started (Waiting for user login...)")

        if not self.scheduler.running:
            self.scheduler.start()
            print(f"[{get_ist_now()}] 🟢 Scheduler Service Running...")
            print(f"[{get_ist_now()}] 📊 Master Sync Job: 1min fetch + Aggregation (5m, 15m, 60m, 1D)")
    
    def stop(self):
        """Stop the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            print(f"[{get_ist_now()}] 🔴 Scheduler Service Stopped")

    def market_heartbeat_job(self):
        """Market heartbeat - runs every 5 seconds"""
        # Keep leadership; if we lost it (key expired + taken over), stand down.
        if not self._renew_leadership():
            return
        self._mark_heartbeat()

        if not is_market_open():
            return

        try:
            user_id, client, engine = self._get_trading_context()
            if not client:
                return

            # FIX: Use correct exchange prefixes
            indices = ['NSE_NIFTY', 'NSE_BANKNIFTY', 'BSE_SENSEX']
            ltp_result = client.get_ltp(indices, segment='CASH')  # Indices are in CASH segment

            if ltp_result.get('success') and ltp_result.get('data'):
                # Feed is alive: clear any 'dead feed' flag set by a prior 401.
                fd = self._redis()
                if fd:
                    try:
                        fd.delete(f'groww:feed_dead:{user_id}')
                    except Exception:
                        pass
                for exchange_symbol, price in ltp_result['data'].items():
                    # Extract symbol name from exchange_symbol
                    symbol = exchange_symbol.replace('NSE_', '').replace('BSE_', '')
                    
                    # Handle special cases
                    symbol_map = {
                        'NIFTY 50': 'NIFTY',
                        'NIFTY BANK': 'BANKNIFTY'
                    }
                    symbol = symbol_map.get(symbol, symbol)
                    
                    # Ensure price is valid
                    try:
                        price = float(price)
                    except (TypeError, ValueError):
                        continue
                    
                    if price > 0:
                        redis_client.cache_ltp(symbol, price, expiry=10)
                        engine.evaluate_strategies(symbol, price)
                        engine.monitor_active_trades(symbol, price)
            else:
                print(f"LTP fetch failed: {ltp_result.get('error', 'Unknown error')}")

        except Exception as e:
            print(f"Heartbeat Error: {e}")
            import traceback
            traceback.print_exc()

    def sync_and_aggregate_job(self):
        """
        Master Sync Job:
        1. Fetch ONLY 1-minute candles from Broker (Source of Truth).
        2. Aggregate 1m -> 5m, 15m, 60m, 1D.
        3. Save all to DB.
        """
        # Only the leader drives this job (guards multi-worker double-run).
        if not self._has_leadership():
            return
        # Ensure market is open to avoid empty API calls
        if not is_market_open():
            return

        try:
            active_user = self._get_active_user()
            if not active_user or not active_user.get('groww_access_token'):
                return
            
            token = encryption.decrypt(active_user['groww_access_token'])
            indices = ['NIFTY', 'BANKNIFTY', 'SENSEX']
            
            # Use fixed limit for fetching from DB for aggregation
            # We need enough 1-min candles to build at least a few 60-min candles
            fetch_limit = 50000
            
            for symbol in indices:
                # --- STEP 1: Sync 1-Minute Data (Base) ---
                # Upsert (not delete+insert) so there is no window where the
                # candles collection is empty for a concurrent reader.
                candle_service.sync_realtime(
                    db, symbol, interval='1', access_token=token
                )
                
                # --- STEP 2: Fetch 1-Minute Data from DB for Aggregation ---
                # We fetch what we just synced to ensure we have a continuous dataframe
                candles_1m = candle_service.get_candles(db, symbol, '1', fetch_limit)
                
                if not candles_1m or len(candles_1m) < 2:
                    continue
                
                # Convert to DataFrame
                df_1m = pd.DataFrame(candles_1m)
                
                # --- CRITICAL FIX: Ensure datetime is Object, not String ---
                # Aggregation keys off the epoch 'timestamp' column; this datetime
                # column is only a convenience. Parse defensively (utc=True avoids
                # a raise on any mixed-offset strings).
                if 'timestamp' in df_1m.columns:
                    df_1m['datetime'] = pd.to_datetime(df_1m['timestamp'], unit='s', utc=True)
                elif 'datetime' in df_1m.columns:
                    df_1m['datetime'] = pd.to_datetime(df_1m['datetime'], utc=True, errors='coerce')
                else:
                    continue # Skip if no valid time column
                
                # --- STEP 3: Aggregate Standard Timeframes (5, 15, 30, 60) ---
                # Uses the TimeframeAggregator utility
                aggregated_data = timeframe_aggregator.aggregate_all(df_1m, symbol)
                
                # --- STEP 4: Aggregate Daily (1D) Manually ---
                # TimeframeAggregator handles minutes; we handle Day here
                try:
                    df_day = df_1m.copy()
                    # Build an IST-aware index straight from epoch so the daily
                    # bucket is the IST trading session, not UTC midnight.
                    df_day['datetime'] = pd.to_datetime(
                        df_day['timestamp'], unit='s', utc=True
                    ).dt.tz_convert('Asia/Kolkata')
                    df_day.set_index('datetime', inplace=True)

                    # Anchor the daily bar to the 09:15 IST session open
                    # (offset shifts the 1D bin edges from midnight to 09:15).
                    df_1d = df_day.resample('1D', offset='9h15min').agg({
                        'open': 'first',
                        'high': 'max',
                        'low': 'min',
                        'close': 'last',
                        'volume': 'sum'
                    }).dropna()

                    # Reset index
                    df_1d.reset_index(inplace=True)
                    df_1d['timestamp'] = df_1d['datetime'].astype(np.int64) // 10**9
                    
                    # Add to aggregation results
                    aggregated_data['1D'] = df_1d
                except Exception as agg_err:
                    print(f"Daily aggregation failed for {symbol}: {agg_err}")

                # --- STEP 5: Save All Timeframes to DB ---
                for interval, df in aggregated_data.items():
                    if interval == '1': continue # Already saved in Step 1

                    if not df.empty:
                        # Convert DataFrame to list of dicts
                        records = df.to_dict('records')

                        # Persist 'datetime' as an IST-aware ISO string, matching
                        # how 1m candles are stored (uniform across all intervals;
                        # epoch 'timestamp' remains the single source of truth).
                        for r in records:
                            dt = r.get('datetime')
                            if hasattr(dt, 'isoformat'):
                                r['datetime'] = dt.isoformat()

                        # Save using new upsert_candles helper
                        db.upsert_candles(symbol, interval, records)
            
            print(f"[{get_ist_now()}] ✅ Live Aggregation Sync Complete")
                
        except Exception as e:
            print(f"Sync & Aggregate Error: {e}")

    def reconcile_orders_job(self):
        """Reconcile orders - safety net to sync Broker <-> DB"""
        # Only the leader runs this; only during market hours (an empty broker
        # position list off-hours must not be read as 'all trades closed').
        if not self._has_leadership():
            return
        if not is_market_open():
            return
        try:
            from services.groww_client import get_groww_client
            from services.trading_engine import get_trading_engine

            # execution_mode is authoritative in the users collection (Sprint 1).
            active_users = db.users.find({'execution_mode': 'LIVE',
                                          'broker_connected': True})

            for user in active_users:
                user_id = str(user['_id'])

                client = get_groww_client(user_id)
                broker_pos = client.get_positions()

                if broker_pos.get('success'):
                    engine = get_trading_engine(user_id)
                    engine.reconcile_positions(broker_pos['data'])

        except Exception as e:
            print(f"Reconciliation Error: {e}")

    def sync_instruments_job(self):
        """Sync instruments daily at 8 AM"""
        try:
            from services.instrument_sync import instrument_sync
            print(f"[{get_ist_now()}] 🔄 Running instrument sync...")
            instrument_sync.sync_instruments()
        except Exception as e:
            print(f"Instrument sync error: {e}")
    
    def daily_reset_job(self):
        """Daily reset at 6:05 AM"""
        try:
            print(f"[{get_ist_now()}] 🧹 Running daily reset...")
            db.reset_daily_strategy_counters()
            db.settings.update_many({}, {'$set': {'overall_pnl_today': 0}})
        except Exception as e:
            print(f"Daily reset error: {e}")
    
    def daily_summary_job(self):
        """Daily summary at 3:35 PM via Telegram"""
        try:
            from services.telegram_alert import get_telegram_alert

            print(f"[{get_ist_now()}] 📊 Generating daily summaries...")
            users = list(db.settings.find({'telegram_configured': True}))

            for user_settings in users:
                user_id = user_settings['user_id']
                today_trades = db.get_today_trades(user_id)

                total_pnl = sum(t.get('pnl', 0) for t in today_trades if t.get('status') == 'CLOSED')
                winning = len([t for t in today_trades if t.get('pnl', 0) > 0])
                total_trades = len(today_trades)

                summary = {
                    'total_pnl': total_pnl,
                    'total_trades': total_trades,
                    'winning': winning,
                    'win_rate': (winning / total_trades * 100) if total_trades > 0 else 0,
                    'execution_mode': config.EXECUTION_MODE
                }

                db.save_daily_summary(user_id, get_ist_now().strftime('%Y-%m-%d'), summary)

                if user_settings.get('telegram_bot_token'):
                    telegram = get_telegram_alert(
                        user_settings.get('telegram_bot_token'),
                        user_settings.get('telegram_chat_id')
                    )
                    telegram.send_daily_summary(summary)
        except Exception as e:
            print(f"Daily summary error: {e}")

    def label_signals_job(self):
        """Hourly job: label pending signal_log docs with forward returns.

        Delegates to scripts.label_signals.label_pending.  Guarded by
        _has_leadership() so only the leader process runs it in a multi-worker
        deployment.  The entire body is wrapped in try/except so a failure here
        never propagates to the scheduler and never affects live trading.
        """
        # Only the leader process drives this job.
        if not self._has_leadership():
            return
        try:
            from scripts.label_signals import label_pending  # lazy import
            n = label_pending(db, candle_service)
            if n:
                print(f"[{get_ist_now()}] label_signals_job: labeled {n} signal(s).")
        except Exception as e:
            print(f"label_signals_job error: {e}")


# Global instance
scheduler_service = SchedulerService()

if __name__ == "__main__":
    print("--- AI TRADING SCHEDULER ---")
    scheduler_service.start()
    
    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nStopping Scheduler...")
        scheduler_service.stop()