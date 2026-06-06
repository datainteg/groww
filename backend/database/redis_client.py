"""
Redis Client for caching and real-time data
"""
import redis
import json
from typing import Optional, Any, Dict
from config import config

class RedisClient:
    """Redis client for caching market data and session management"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize Redis connection with Auth/SSL support"""
        try:
            self.client = redis.Redis(
                host=config.REDIS_HOST,
                port=config.REDIS_PORT,
                db=config.REDIS_DB,
                password=config.REDIS_PASSWORD,
                ssl=config.REDIS_SSL,
                decode_responses=True,
                socket_timeout=5  # Fail fast if cloud is unreachable
            )
            self.client.ping()
            self.connected = True
            print(f"✅ Redis Connected: {config.REDIS_HOST}")
        except redis.ConnectionError as e:
            print(f"❌ Redis Connection Failed: {e}")
            self.client = None
            self.connected = False
    
    # ... (Rest of the methods: get, set, cache_ltp remain exactly the same) ...
    
    def get_cached_ltp(self, symbol: str) -> Optional[float]:
        if not self.connected: return None
        val = self.client.get(f"ltp:{symbol}")
        return float(val) if val else None

    def cache_ltp(self, symbol: str, price: float, expiry: int=10):
        if self.connected:
            self.client.setex(f"ltp:{symbol}", expiry, str(price))

    def get(self, key):
        return self.client.get(key) if self.connected else None

    def set(self, key, val, expiry=None):
        if not self.connected: return False
        if expiry: self.client.setex(key, expiry, val)
        else: self.client.set(key, val)
        return True

redis_client = RedisClient()