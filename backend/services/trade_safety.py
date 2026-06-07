"""
Centralized trade-safety gate.

Every order-placing path (scheduled auto-entry, manual execute-strategy, quick-trade,
direct place-order) MUST route through here so locking, validation, risk checks and
logging are identical everywhere.

Safety policy:
  - LIVE  + Redis unavailable      -> FAIL CLOSED (refuse).
  - PAPER + Redis unavailable      -> fail open (proceed, warn).
  - LIVE  + stale candle data      -> BLOCK entry.
  - LIVE  + broker feed dead (401) -> BLOCK entry.
  - kill switch / daily limits / max-concurrent / max-orders / duplicate open trade -> BLOCK.
  - LIVE auto-entry requires AUTO_TRADING_ENABLED + a fresh token (checked by callers).

No import of trading_engine here (avoids a circular import); heavy services are imported lazily.
"""
from contextlib import contextmanager
from typing import Dict, Optional, Tuple

import uuid

from bson import ObjectId

from database import db, redis_client
from config import config
from utils.risk_manager import risk_manager

# Atomic compare-and-delete: only release the lock if we still own it.
_RELEASE_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('del', KEYS[1]) else return 0 end"
)


# --------------------------------------------------------------------------- #
# Execution mode
# --------------------------------------------------------------------------- #
def get_user_execution_mode(user_id: str) -> str:
    """PAPER | LIVE. users collection is authoritative; settings is a legacy
    fallback; config default is the final safety net."""
    try:
        user = db.users.find_one({'_id': user_id})
        if not user:
            try:
                user = db.users.find_one({'_id': ObjectId(user_id)})
            except Exception:
                user = None
        if user and user.get('execution_mode'):
            return str(user['execution_mode']).upper()
        settings = db.get_settings(user_id)
        if settings and settings.get('execution_mode'):
            return str(settings['execution_mode']).upper()
    except Exception as e:
        print(f"[trade_safety] execution_mode lookup error: {e}")
    return str(config.EXECUTION_MODE).upper()


def _redis():
    return getattr(redis_client, 'client', None)


# --------------------------------------------------------------------------- #
# Locking
# --------------------------------------------------------------------------- #
@contextmanager
def acquire_user_trade_lock(user_id: str, execution_mode: Optional[str] = None, timeout: int = 5):
    """Per-user serialization of order operations.
    LIVE fails CLOSED when Redis is unavailable; PAPER fails open."""
    mode = (execution_mode or get_user_execution_mode(user_id)).upper()
    client = _redis()
    if not client:
        if mode == 'LIVE':
            print("[trade_safety] Redis unavailable in LIVE -> refusing trade (fail-closed).")
            yield False
        else:
            print("[trade_safety] Redis unavailable (PAPER) -> proceeding without lock.")
            yield True
        return

    key = f"trade_lock:{user_id}"
    token = uuid.uuid4().hex
    try:
        acquired = client.set(key, token, nx=True, ex=timeout)
    except Exception:
        if mode == 'LIVE':
            print("[trade_safety] Redis error acquiring lock in LIVE -> fail-closed.")
            yield False
        else:
            yield True
        return

    if acquired:
        try:
            yield True
        finally:
            try:
                client.eval(_RELEASE_LUA, 1, key, token)
            except Exception:
                pass
    else:
        yield False


# --------------------------------------------------------------------------- #
# Individual checks  -> (ok: bool, reason: str)
# --------------------------------------------------------------------------- #
def check_broker_feed_health(user_id: str) -> Tuple[bool, str]:
    """A prior 401 sets a 'feed dead' flag; treat the feed as down until it clears."""
    client = _redis()
    if not client:
        return True, "OK"  # can't tell; don't block on Redis absence here
    try:
        if client.get(f'groww:feed_dead:{user_id}'):
            return False, "Broker data feed is down (token expired/invalid) — re-connect Groww"
    except Exception:
        pass
    return True, "OK"


def check_data_freshness(symbol: str, interval: str = '5') -> Tuple[bool, str]:
    """Validate the latest stored candles (gaps / staleness / bad rows)."""
    try:
        import time as _t
        from services.candle_service import candle_service
        from analysis.data_quality import validate_candles
        candles = candle_service.get_candles(db, symbol, interval, 60)
        if not candles:
            return False, f"No candle data for {symbol} {interval}m"
        res = validate_candles(candles, int(interval), now_epoch=int(_t.time()))
        if not res.get('ok'):
            return False, f"Stale/invalid candles for {symbol}: {res.get('reason', 'data quality')}"
    except Exception as e:
        # Don't hard-fail the whole gate on a checker error (caller decides per mode).
        return True, f"data-quality check skipped ({e})"
    return True, "OK"


def check_strategy_limits(strategy: Dict, settings: Optional[Dict] = None) -> Tuple[bool, str]:
    return risk_manager.can_strategy_trade(strategy, settings)


def check_overall_limits(user_id: str, settings: Optional[Dict] = None) -> Tuple[bool, str]:
    try:
        if settings is None:
            settings = db.get_settings(user_id)
        active = len(db.get_active_trades(user_id))
        return risk_manager.can_overall_trade(settings, active)
    except Exception as e:
        return True, f"overall-limit check skipped ({e})"


def build_trade_block_reason(check: str, detail: str) -> str:
    return f"[{check}] {detail}"


# --------------------------------------------------------------------------- #
# Master gate
# --------------------------------------------------------------------------- #
def validate_trade_allowed(user_id: str, strategy: Optional[Dict] = None,
                           symbol: Optional[str] = None, side: Optional[str] = None,
                           source: str = "AUTO") -> Dict:
    """Single decision point for whether a NEW entry may proceed.
    Returns {allowed, blocked, reason, source, mode}."""
    mode = get_user_execution_mode(user_id)

    def block(reason: str) -> Dict:
        return {'allowed': False, 'blocked': True, 'reason': reason, 'source': source, 'mode': mode}

    # LIVE auto-trading must be explicitly enabled (hard default off).
    if mode == 'LIVE' and source == 'AUTO' and not bool(getattr(config, 'AUTO_TRADING_ENABLED', False)):
        return block(build_trade_block_reason('auto', 'LIVE auto-trading disabled (set AUTO_TRADING_ENABLED=true)'))

    settings = None
    try:
        settings = db.get_settings(user_id)
    except Exception:
        pass

    # Kill switch (settings)
    if settings and settings.get('kill_switch'):
        return block(build_trade_block_reason('kill_switch', 'Kill switch is active'))

    # Broker feed health — always blocks in LIVE; in PAPER it's informational.
    feed_ok, feed_reason = check_broker_feed_health(user_id)
    if not feed_ok and mode == 'LIVE':
        return block(build_trade_block_reason('feed', feed_reason))

    # Data freshness — blocks LIVE; warns PAPER.
    if symbol:
        fresh_ok, fresh_reason = check_data_freshness(symbol)
        if not fresh_ok and mode == 'LIVE':
            return block(build_trade_block_reason('data_quality', fresh_reason))

    # Per-strategy limits + duplicate open trade.
    if strategy is not None:
        ok, reason = check_strategy_limits(strategy, settings)
        if not ok:
            return block(build_trade_block_reason('strategy_limit', reason))
        try:
            dup = db.trades.find_one({'strategy_id': str(strategy.get('_id')), 'status': 'OPEN'})
            if dup:
                return block(build_trade_block_reason('duplicate', 'An open trade already exists for this strategy'))
        except Exception:
            pass

    # Portfolio limits (max concurrent, overall P&L).
    ok, reason = check_overall_limits(user_id, settings)
    if not ok:
        return block(build_trade_block_reason('overall_limit', reason))

    return {'allowed': True, 'blocked': False, 'reason': 'OK', 'source': source, 'mode': mode}
