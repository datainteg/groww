"""IST time helpers (Sprint 2)."""
from datetime import datetime, timedelta
from utils.time_utils import (
    is_token_expired, get_current_expiry_dates, is_market_open, get_ist_now,
)


def test_token_expired_none_is_true():
    assert is_token_expired(None) is True


def test_token_expired_past_and_future():
    assert is_token_expired(get_ist_now() - timedelta(hours=1)) is True
    assert is_token_expired(get_ist_now() + timedelta(hours=1)) is False


def test_token_expired_naive_assumed_ist():
    naive_future = (get_ist_now() + timedelta(hours=2)).replace(tzinfo=None)
    assert is_token_expired(naive_future) is False


def test_expiry_dates_parseable():
    e = get_current_expiry_dates()
    assert isinstance(e, list) and len(e) >= 1
    for d in e:
        datetime.strptime(d, '%Y-%m-%d')  # raises if malformed


def test_market_open_returns_bool():
    assert isinstance(is_market_open(), bool)
