"""
Time utilities for trading operations
"""
from datetime import datetime, timedelta, time
import pytz
from config import config

IST = pytz.timezone('Asia/Kolkata')


def get_ist_now() -> datetime:
    """Get current time in IST"""
    return datetime.now(IST)


def is_market_open() -> bool:
    """Check if market is currently open"""
    now = get_ist_now()
    
    # Weekend check
    if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    
    market_open = time(config.MARKET_OPEN_HOUR, config.MARKET_OPEN_MINUTE)
    market_close = time(config.MARKET_CLOSE_HOUR, config.MARKET_CLOSE_MINUTE)
    current_time = now.time()

    # Strict upper bound: the 15:30 closing minute is NOT a tradable window.
    return market_open <= current_time < market_close


def is_auto_exit_time() -> bool:
    """Check if it's time for auto-exit (force-close before the close)."""
    now = get_ist_now()
    # Defensive defaults in case AUTO_EXIT_* is absent from an older config.
    auto_exit = time(getattr(config, 'AUTO_EXIT_HOUR', 15),
                     getattr(config, 'AUTO_EXIT_MINUTE', 15))
    market_close = time(config.MARKET_CLOSE_HOUR, config.MARKET_CLOSE_MINUTE)
    current_time = now.time()

    return auto_exit <= current_time <= market_close


def get_market_status() -> dict:
    """Get detailed market status"""
    now = get_ist_now()
    is_open = is_market_open()
    
    market_open_time = now.replace(
        hour=config.MARKET_OPEN_HOUR, 
        minute=config.MARKET_OPEN_MINUTE, 
        second=0, 
        microsecond=0
    )
    market_close_time = now.replace(
        hour=config.MARKET_CLOSE_HOUR, 
        minute=config.MARKET_CLOSE_MINUTE, 
        second=0, 
        microsecond=0
    )
    
    status = {
        'is_open': is_open,
        'current_time': now.strftime('%H:%M:%S'),
        'market_open_time': f"{config.MARKET_OPEN_HOUR:02d}:{config.MARKET_OPEN_MINUTE:02d}",
        'market_close_time': f"{config.MARKET_CLOSE_HOUR:02d}:{config.MARKET_CLOSE_MINUTE:02d}",
        'day_of_week': now.strftime('%A'),
        'is_weekend': now.weekday() >= 5
    }
    
    if is_open:
        time_to_close = market_close_time - now
        status['time_to_close'] = str(time_to_close).split('.')[0]
        status['status'] = 'OPEN'
    else:
        if now.weekday() >= 5:
            # Weekend - next open is Monday
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7
            next_open = now + timedelta(days=days_until_monday)
            next_open = next_open.replace(
                hour=config.MARKET_OPEN_HOUR,
                minute=config.MARKET_OPEN_MINUTE,
                second=0,
                microsecond=0
            )
        elif now.time() < market_open_time.time():
            # Before market open today
            next_open = market_open_time
        else:
            # After market close - next day
            next_open = now + timedelta(days=1)
            next_open = next_open.replace(
                hour=config.MARKET_OPEN_HOUR,
                minute=config.MARKET_OPEN_MINUTE,
                second=0,
                microsecond=0
            )
            # Skip weekend
            while next_open.weekday() >= 5:
                next_open += timedelta(days=1)
        
        status['next_open'] = next_open.strftime('%Y-%m-%d %H:%M:%S')
        status['status'] = 'CLOSED'
    
    return status


def get_token_expiry_time() -> datetime:
    """Get Groww token expiry time (6 AM next day IST)"""
    now = get_ist_now()
    
    # Token expires at 6 AM IST
    expiry = now.replace(hour=6, minute=0, second=0, microsecond=0)
    
    # If current time is after 6 AM, expiry is tomorrow 6 AM
    if now.hour >= 6:
        expiry += timedelta(days=1)
    
    return expiry


def is_token_expired(expiry_time: datetime) -> bool:
    """Check if Groww token is expired"""
    if not expiry_time:
        return True
    
    now = get_ist_now()
    
    # If expiry_time is naive (no timezone), assume IST
    if expiry_time.tzinfo is None:
        expiry_time = IST.localize(expiry_time)
    
    return now >= expiry_time


def get_current_expiry_dates() -> list:
    """Get current week and month expiry dates for F&O"""
    now = get_ist_now()
    
    expiries = []
    
    # Weekly expiry (Thursday)
    days_until_thursday = (3 - now.weekday()) % 7
    if days_until_thursday == 0 and now.hour >= 15:
        days_until_thursday = 7
    weekly_expiry = now + timedelta(days=days_until_thursday)
    expiries.append(weekly_expiry.strftime('%Y-%m-%d'))
    
    # Next week expiry
    next_weekly = weekly_expiry + timedelta(days=7)
    expiries.append(next_weekly.strftime('%Y-%m-%d'))
    
    # Monthly expiry (last Thursday of month)
    # Find last day of current month
    if now.month == 12:
        next_month = now.replace(year=now.year + 1, month=1, day=1)
    else:
        next_month = now.replace(month=now.month + 1, day=1)
    last_day = next_month - timedelta(days=1)
    
    # Find last Thursday
    days_since_thursday = (last_day.weekday() - 3) % 7
    monthly_expiry = last_day - timedelta(days=days_since_thursday)
    expiries.append(monthly_expiry.strftime('%Y-%m-%d'))
    
    return list(set(expiries))


def format_datetime(dt: datetime) -> str:
    """Format datetime for display"""
    if dt is None:
        return ''
    return dt.strftime('%Y-%m-%d %H:%M:%S')
