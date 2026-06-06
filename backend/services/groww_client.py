"""
Groww API Client
Complete implementation for Groww Trading API.
Handles Authentication, Order Management, Live Data, Historical Data, and Instruments.
"""
import requests
import json
import logging
import re
import time
import random
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime, date
import pandas as pd
from io import StringIO

from config import config
from utils import generate_checksum, get_current_timestamp, encryption
from database import db

# Configure logging
logger = logging.getLogger(__name__)

class GrowwClient:
    """
    Groww API Client for market data and order execution.
    
    Attributes:
        user_id (str): The database ID of the user (for token retrieval).
        access_token (str): The active Bearer token for API calls.
        base_url (str): The base URL for Groww API.
    """
    
    BASE_URL = config.GROWW_API_BASE_URL
    API_VERSION = "1.0"
    
    def __init__(self, user_id: str = None):
        """
        Initialize the Groww Client.
        
        Args:
            user_id: Optional user_id to auto-load token from DB.
        """
        self.user_id = user_id
        self.access_token = None
        self.session = requests.Session()
        
        # Load token if user_id is provided
        if self.user_id:
            self._load_token()
    
    def _load_token(self):
        """Load access token from database and decrypt it."""
        if self.user_id:
            try:
                user = db.get_user_by_id(self.user_id)
                if user and user.get('groww_access_token'):
                    self.access_token = encryption.decrypt(user['groww_access_token'])
                    # logger.debug(f"Token loaded successfully for user {self.user_id}")
                else:
                    logger.warning(f"No access token found in DB for user {self.user_id}")
            except Exception as e:
                logger.error(f"Failed to load token for user {self.user_id}: {e}")

    def _get_headers(self) -> Dict[str, str]:
        """
        Construct request headers with authentication.
        
        Returns:
            Dictionary of headers.
        """
        # Double check if token is missing and try to reload
        if not self.access_token and self.user_id:
             self._load_token()

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-API-VERSION': self.API_VERSION
        }
        
        if self.access_token:
            headers['Authorization'] = f'Bearer {self.access_token}'
            
        return headers
    
    @staticmethod
    def _backoff_seconds(attempt: int) -> float:
        """Exponential backoff with jitter: ~0.5s, 1s, 2s (capped 8s)."""
        return min(0.5 * (2 ** attempt), 8.0) + random.uniform(0, 0.3)

    @staticmethod
    def _retry_after_seconds(response, attempt: int) -> float:
        """Honor a 429 Retry-After header, else exponential (capped 60s)."""
        ra = response.headers.get('Retry-After')
        if ra:
            try:
                return min(float(ra), 60.0)
            except (ValueError, TypeError):
                pass
        return min(2 ** attempt, 60.0)

    def _on_auth_failure(self):
        """A 401 means the Groww token is dead. Drop it, flag the feed as down so
        the scheduler stops trading on stale data, and alert (kill-switch level)."""
        self.access_token = None
        try:
            from database.redis_client import redis_client
            client = getattr(redis_client, 'client', None)
            if client:
                # 1h TTL so the flag self-clears after a re-login + restart.
                client.set(f'groww:feed_dead:{self.user_id}', '1', ex=3600)
        except Exception:
            pass
        try:
            from services.telegram_alert import telegram_alert
            telegram_alert.send_kill_switch_alert(
                "Groww token expired/invalid (401). Live data + order feed is DOWN. "
                "Re-login required; automated trading is halted."
            )
        except Exception:
            pass

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Dict = None,
        data: Dict = None,
        headers: Dict = None,
        timeout: int = 15,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Centralized HTTP request to Groww API with retry/backoff.

        Retries are SAFE-ONLY: network/5xx errors are retried for idempotent
        methods (GET/HEAD/OPTIONS) only — a POST (order placement) is never
        retried on an ambiguous failure, to avoid duplicate real-money orders.
        A 429 is always retryable (the request was rejected, not executed).

        Returns:
            Dictionary with 'status' (SUCCESS/FAILURE) and data/error.
        """
        url = f"{self.BASE_URL}{endpoint}"
        req_headers = headers or self._get_headers()
        idempotent = method.upper() in ('GET', 'HEAD', 'OPTIONS')
        # 429 is normally pre-execution (safe to retry), but cap order POSTs to a
        # single retry as defense-in-depth against duplicate real-money orders.
        max_429 = max_retries if idempotent else 1

        attempt = 0
        while True:
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    headers=req_headers,
                    params=params,
                    json=data,
                    timeout=timeout
                )

                # Rate limited: retry (request was rejected, not executed).
                if response.status_code == 429 and attempt < max_429:
                    wait = self._retry_after_seconds(response, attempt)
                    logger.warning(f"429 rate limited for {endpoint}; retry in {wait:.1f}s")
                    time.sleep(wait)
                    attempt += 1
                    continue

                # Token dead: stop, flag the feed, alert. Do not retry.
                if response.status_code == 401:
                    logger.critical(f"401 Unauthorized for {endpoint}. Token expired.")
                    self._on_auth_failure()
                    return {
                        'status': 'FAILURE',
                        'error': {'code': '401',
                                  'message': 'Unauthorized or Token Expired. Please re-login.'}
                    }

                # Transient server errors: retry idempotent reads only.
                if 500 <= response.status_code < 600 and idempotent and attempt < max_retries:
                    wait = self._backoff_seconds(attempt)
                    logger.warning(f"HTTP {response.status_code} for {endpoint}; retry in {wait:.1f}s")
                    time.sleep(wait)
                    attempt += 1
                    continue

                # Parse JSON response
                try:
                    result = response.json()
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON response from {url}: {response.text}")
                    return {'status': 'FAILURE',
                            'error': {'message': f'Invalid JSON response: {response.text}'}}

                if response.status_code in (200, 201):
                    return result

                return {
                    'status': 'FAILURE',
                    'error': result.get('error', {'message': f'HTTP {response.status_code}: {response.text}'})
                }

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                # Network failure. For a POST the order MAY have reached the broker,
                # so never retry — surface the failure and let reconciliation sort it.
                if idempotent and attempt < max_retries:
                    wait = self._backoff_seconds(attempt)
                    logger.warning(f"{type(e).__name__} for {url}; retry in {wait:.1f}s")
                    time.sleep(wait)
                    attempt += 1
                    continue
                logger.error(f"{type(e).__name__} for {url} (no retry)")
                return {'status': 'FAILURE', 'error': {'message': f'{type(e).__name__}: network error'}}

            except requests.exceptions.RequestException as e:
                logger.error(f"Request exception for {url}: {e}")
                return {'status': 'FAILURE', 'error': {'message': str(e)}}

            except Exception as e:
                logger.error(f"Unexpected error for {url}: {e}")
                return {'status': 'FAILURE', 'error': {'message': str(e)}}

    def _parse_ohlc_string(self, ohlc_str: str) -> Dict[str, float]:
        """
        Helper to parse Groww's non-standard OHLC string format.
        Format: "{open: 149.50,high: 150.50,low: 148.50,close: 149.50}"
        """
        try:
            if not isinstance(ohlc_str, str):
                return {'open': 0.0, 'high': 0.0, 'low': 0.0, 'close': 0.0}
                
            # Remove braces and whitespace
            clean_str = ohlc_str.strip('{} ')
            # Split by comma
            parts = clean_str.split(',')
            result = {}
            for part in parts:
                if ':' in part:
                    # maxsplit=1 so values containing ':' don't raise ValueError.
                    k, v = part.split(':', 1)
                    try:
                        result[k.strip()] = float(v.strip())
                    except ValueError:
                        continue
            return result
        except Exception as e:
            logger.warning(f"Failed to parse OHLC string '{ohlc_str}': {e}")
            return {'open': 0.0, 'high': 0.0, 'low': 0.0, 'close': 0.0}

    # =========================================================================
    #                               AUTHENTICATION
    # =========================================================================
    
    def generate_access_token(self, api_key: str, api_secret: str) -> Dict:
        """
        Generate access token using API Key and Secret (Step 1).
        Usually requires a subsequent Step 2 with TOTP or PIN if 2FA is enabled.
        """
        timestamp = get_current_timestamp()
        checksum, _ = generate_checksum(api_secret, timestamp)
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        data = {
            'key_type': 'approval',
            'checksum': checksum,
            'timestamp': timestamp
        }
        
        result = self._make_request('POST', '/v1/token/api/access', data=data, headers=headers)
        
        if result.get('status') == 'SUCCESS' or result.get('token'):
            # Some flows return token immediately
            if result.get('token'):
                self.access_token = result.get('token')
                
            return {
                'success': True,
                'token': result.get('token'),
                'expiry': result.get('expiry'),
                'tokenRefId': result.get('tokenRefId'),
                'sessionName': result.get('sessionName'),
                'isActive': result.get('isActive', True)
            }
        
        return {
            'success': False,
            'error': result.get('error', {}).get('message', 'Failed to generate token')
        }
    
    def generate_token_with_totp(self, api_key: str, totp: str) -> Dict:
        """
        Generate access token using TOTP (Step 2).
        Use this if 'generate_access_token' returns a requirement for TOTP.
        """
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        data = {
            'key_type': 'totp',
            'totp': totp
        }
        
        result = self._make_request('POST', '/v1/token/api/access', data=data, headers=headers)
        
        if result.get('status') == 'SUCCESS' or result.get('token'):
            self.access_token = result.get('token')
            return {
                'success': True,
                'token': result.get('token'),
                'expiry': result.get('expiry'),
                'tokenRefId': result.get('tokenRefId')
            }
        
        return {
            'success': False,
            'error': result.get('error', {}).get('message', 'Failed to generate token')
        }

    # =========================================================================
    #                               LIVE DATA
    # =========================================================================

    def get_quote(self, trading_symbol: str, exchange: str = 'NSE', segment: str = 'CASH') -> Dict:
        """
        Get complete live data snapshot for an instrument.
        Includes LTP, Depth, OHLC, Volume, OI, etc.
        """
        params = {
            'exchange': exchange,
            'segment': segment,
            'trading_symbol': trading_symbol
        }
        
        result = self._make_request('GET', '/v1/live-data/quote', params=params)
        
        if result.get('status') == 'SUCCESS':
            payload = result.get('payload', {})
            # Fix: Parse OHLC string if it exists
            if 'ohlc' in payload and isinstance(payload['ohlc'], str):
                payload['parsed_ohlc'] = self._parse_ohlc_string(payload['ohlc'])
            return {'success': True, 'data': payload}
        
        return {'success': False, 'error': result.get('error', {}).get('message', 'Failed to get quote')}

    def get_ltp(self, exchange_symbols: List[str], segment: str = 'CASH') -> Dict:
        """
        Get latest price for multiple instruments (Max 50).
        Args:
            exchange_symbols: List of symbols like ['NSE_RELIANCE', 'BSE_SENSEX']
        """
        params = {
            'segment': segment,
            'exchange_symbols': ','.join(exchange_symbols)
        }
        
        result = self._make_request('GET', '/v1/live-data/ltp', params=params)
        
        if result.get('status') == 'SUCCESS':
            return {'success': True, 'data': result.get('payload', {})}
        
        return {'success': False, 'error': result.get('error', {}).get('message', 'Failed to get LTP')}

    def get_ohlc(self, exchange_symbols: List[str], segment: str = 'CASH') -> Dict:
        """
        Get OHLC data for multiple instruments.
        Returns data with parsed OHLC values.
        """
        params = {
            'segment': segment,
            'exchange_symbols': ','.join(exchange_symbols)
        }
        
        result = self._make_request('GET', '/v1/live-data/ohlc', params=params)
        
        if result.get('status') == 'SUCCESS':
            raw_data = result.get('payload', {})
            parsed_data = {}
            
            # Parse the custom string format for each symbol
            for sym, ohlc_str in raw_data.items():
                parsed_data[sym] = self._parse_ohlc_string(ohlc_str)
                
            return {'success': True, 'data': parsed_data}
        
        return {'success': False, 'error': result.get('error', {}).get('message', 'Failed to get OHLC')}

    def get_option_chain(self, underlying: str, expiry_date: str, exchange: str = 'NSE') -> Dict:
        """
        Get complete option chain including Greeks for FNO contracts.
        """
        endpoint = f'/v1/option-chain/exchange/{exchange}/underlying/{underlying}'
        params = {'expiry_date': expiry_date}
        
        result = self._make_request('GET', endpoint, params=params)
        
        if result.get('status') == 'SUCCESS':
            return {'success': True, 'data': result.get('payload', {})}
        
        return {'success': False, 'error': result.get('error', {}).get('message', 'Failed to get option chain')}

    def get_greeks(self, underlying: str, trading_symbol: str, expiry: str, exchange: str = 'NSE') -> Dict:
        """
        Get specific Greeks for a contract.
        """
        endpoint = f'/v1/live-data/greeks/exchange/{exchange}/underlying/{underlying}/trading_symbol/{trading_symbol}/expiry/{expiry}'
        
        result = self._make_request('GET', endpoint)
        
        if result.get('status') == 'SUCCESS':
            return {'success': True, 'data': result.get('payload', {})}
        
        return {'success': False, 'error': result.get('error', {}).get('message', 'Failed to get Greeks')}

    # =========================================================================
    #                            HISTORICAL DATA
    # =========================================================================
    
    def get_historical_candles(
            self,
            trading_symbol: str,
            start_time: str,
            end_time: str,
            interval: int = 5,
            exchange: str = 'NSE',
            segment: str = 'CASH'
        ) -> Dict:
            """
            Get historical candle data.
            Handles symbol mapping for Indices automatically.
            """
            
            # Map generic Index names to Groww's internal format
            symbol_map = {
                'NIFTY': 'NIFTY 50',
                'BANKNIFTY': 'NIFTY BANK',
                'FINNIFTY': 'NIFTY FIN SERVICE',
                'SENSEX': 'SENSEX'
            }
            
            final_symbol = symbol_map.get(trading_symbol, trading_symbol)
            final_exchange = 'BSE' if trading_symbol == 'SENSEX' else exchange
            
            params = {
                'exchange': final_exchange,
                'segment': segment,
                'trading_symbol': final_symbol,
                'start_time': start_time,
                'end_time': end_time,
                # Groww REST expects snake_case 'interval_in_minutes' (camelCase
                # was silently ignored -> wrong-timeframe candles).
                'interval_in_minutes': interval
            }

            result = self._make_request('GET', '/v1/historical/candle/range', params=params)
            
            if result.get('status') == 'SUCCESS':
                payload = result.get('payload', {})
                candles = payload.get('candles', [])
                
                formatted = []
                for c in candles:
                    if len(c) >= 6:
                        formatted.append({
                            'time': c[0],
                            'open': c[1],
                            'high': c[2],
                            'low': c[3],
                            'close': c[4],
                            'volume': c[5]
                        })
                
                return {'success': True, 'data': formatted}
            
            return {'success': False, 'error': result.get('error', {}).get('message', 'Failed to get candles')}
        
    def get_expiries(self, underlying: str, year: int, month: int, exchange: str = 'NSE') -> Dict:
        """Get available expiries for backtesting or historical analysis."""
        params = {
            'exchange': exchange,
            'underlying_symbol': underlying,
            'year': year,
            'month': month
        }
        
        result = self._make_request('GET', '/v1/historical/expiries', params=params)
        
        if result.get('status') == 'SUCCESS':
            return {'success': True, 'data': result.get('payload', {}).get('expiries', [])}
        
        return {'success': False, 'error': result.get('error', {}).get('message', 'Failed to get expiries')}
    
    # =========================================================================
    #                            ORDER MANAGEMENT
    # =========================================================================
    
    def place_order(
        self,
        trading_symbol: str,
        quantity: int,
        transaction_type: str,
        order_type: str = 'MARKET',
        price: float = 0,
        trigger_price: float = None,
        product: str = 'MIS',
        exchange: str = 'NSE',
        segment: str = 'FNO',
        validity: str = 'DAY',
        order_reference_id: str = None
    ) -> Dict:
        """
        Place a new order.
        
        Args:
            trading_symbol: e.g., 'NIFTY23OCT19000CE'
            quantity: Number of units
            transaction_type: 'BUY' or 'SELL'
            order_type: 'MARKET', 'LIMIT', 'SL', 'SL_M'
            price: Required for LIMIT/SL
            trigger_price: Required for SL/SL_M
            product: 'MIS' (Intraday) or 'NRML' (Delivery/Carryforward)
        """
        data = {
            'trading_symbol': trading_symbol,
            'quantity': quantity,
            'transaction_type': transaction_type,
            'order_type': order_type,
            'price': price,
            'product': product,
            'exchange': exchange,
            'segment': segment,
            'validity': validity
        }
        
        if trigger_price:
            data['trigger_price'] = trigger_price
        
        if order_reference_id:
            data['order_reference_id'] = order_reference_id
        
        result = self._make_request('POST', '/v1/order/create', data=data)
        
        if result.get('status') == 'SUCCESS':
            payload = result.get('payload', {})
            return {
                'success': True,
                'order_id': payload.get('groww_order_id'),
                'status': payload.get('order_status'),
                'reference_id': payload.get('order_reference_id'),
                'remark': payload.get('remark')
            }
        
        return {
            'success': False, 
            'error': result.get('error', {}).get('message', 'Failed to place order')
        }
    
    def modify_order(
        self,
        groww_order_id: str,
        segment: str,
        quantity: int = None,
        price: float = None,
        trigger_price: float = None,
        order_type: str = None
    ) -> Dict:
        """Modify an open pending order."""
        data = {
            'groww_order_id': groww_order_id,
            'segment': segment
        }
        
        if quantity is not None:
            data['quantity'] = quantity
        if price is not None:
            data['price'] = price
        if trigger_price is not None:
            data['trigger_price'] = trigger_price
        if order_type is not None:
            data['order_type'] = order_type
        
        result = self._make_request('POST', '/v1/order/modify', data=data)
        
        if result.get('status') == 'SUCCESS':
            payload = result.get('payload', {})
            return {
                'success': True,
                'order_id': payload.get('groww_order_id'),
                'status': payload.get('order_status')
            }
        
        return {
            'success': False,
            'error': result.get('error', {}).get('message', 'Failed to modify order')
        }
    
    def cancel_order(self, groww_order_id: str, segment: str) -> Dict:
        """Cancel an open pending order."""
        data = {
            'groww_order_id': groww_order_id,
            'segment': segment
        }
        
        result = self._make_request('POST', '/v1/order/cancel', data=data)
        
        if result.get('status') == 'SUCCESS':
            payload = result.get('payload', {})
            return {
                'success': True,
                'order_id': payload.get('groww_order_id'),
                'status': payload.get('order_status')
            }
        
        return {
            'success': False,
            'error': result.get('error', {}).get('message', 'Failed to cancel order')
        }
    
    def get_order_status(self, groww_order_id: str, segment: str) -> Dict:
        """Get current status of a specific order."""
        params = {'segment': segment}
        result = self._make_request('GET', f'/v1/order/status/{groww_order_id}', params=params)
        
        if result.get('status') == 'SUCCESS':
            return {'success': True, 'data': result.get('payload', {})}
        
        return {'success': False, 'error': result.get('error', {}).get('message', 'Failed to get order status')}
    
    def get_order_details(self, groww_order_id: str, segment: str) -> Dict:
        """Get full details of a specific order."""
        params = {'segment': segment}
        result = self._make_request('GET', f'/v1/order/detail/{groww_order_id}', params=params)
        
        if result.get('status') == 'SUCCESS':
            return {'success': True, 'data': result.get('payload', {})}
        
        return {'success': False, 'error': result.get('error', {}).get('message', 'Failed to get order details')}
    
    def get_order_list(self, segment: str, page: int = 0, page_size: int = 100) -> Dict:
        """Get list of orders (paginated)."""
        params = {
            'segment': segment,
            'page': page,
            'page_size': page_size
        }
        
        result = self._make_request('GET', '/v1/order/list', params=params)
        
        if result.get('status') == 'SUCCESS':
            return {'success': True, 'data': result.get('payload', {}).get('order_list', [])}
        
        return {'success': False, 'error': result.get('error', {}).get('message', 'Failed to get order list')}
    
    def get_trades_for_order(self, groww_order_id: str, segment: str) -> Dict:
        """Get list of trades (fills) associated with an order."""
        params = {'segment': segment}
        result = self._make_request('GET', f'/v1/order/trades/{groww_order_id}', params=params)
        
        if result.get('status') == 'SUCCESS':
            return {'success': True, 'data': result.get('payload', {}).get('trade_list', [])}
        
        return {'success': False, 'error': result.get('error', {}).get('message', 'Failed to get trades')}

    # =========================================================================
    #                            POSITIONS - ADDED MISSING METHOD
    # =========================================================================
    
    def get_positions(self, segment: str = 'FNO') -> Dict:
        """
        Get current positions from broker.
        This method was MISSING - now added!
        
        Args:
            segment: 'FNO' for F&O or 'CASH' for equity
            
        Returns:
            Dict with success status and position data
        """
        # Per Groww docs: GET /v1/positions/user (current-day positions).
        params = {'segment': segment}
        result = self._make_request('GET', '/v1/positions/user', params=params)

        if result.get('status') == 'SUCCESS':
            payload = result.get('payload', {})
            # Be tolerant of the wrapper key across API versions.
            positions = (payload.get('positions') or payload.get('position_list')
                         or (payload if isinstance(payload, list) else []))
            return {'success': True, 'data': positions}

        return {
            'success': False,
            'error': result.get('error', {}).get('message', 'Failed to get positions'),
            'data': []
        }
    
    def get_holdings(self) -> Dict:
        """
        Get holdings (for equity segment).
        
        Returns:
            Dict with success status and holdings data
        """
        # Per Groww docs: GET /v1/holdings/user.
        result = self._make_request('GET', '/v1/holdings/user')

        if result.get('status') == 'SUCCESS':
            payload = result.get('payload', {})
            holdings = (payload.get('holdings') or payload.get('holding_list')
                        or (payload if isinstance(payload, list) else []))
            return {'success': True, 'data': holdings}

        return {
            'success': False,
            'error': result.get('error', {}).get('message', 'Failed to get holdings'),
            'data': []
        }
    
    def get_margins(self, segment: str = 'FNO') -> Dict:
        """
        Get available user margin / funds.

        Per Groww docs this is a user-level endpoint (GET /v1/margins/detail/user)
        with no segment parameter; `segment` is accepted for backward-compat but
        not sent. Response includes clear_cash, net_margin_used, collateral, etc.
        """
        result = self._make_request('GET', '/v1/margins/detail/user')

        if result.get('status') == 'SUCCESS':
            return {'success': True, 'data': result.get('payload', {})}
        
        return {
            'success': False, 
            'error': result.get('error', {}).get('message', 'Failed to get margins'),
            'data': {}
        }

    # =========================================================================
    #                            INSTRUMENTS / UTILS
    # =========================================================================
    
    @staticmethod
    def download_instruments() -> pd.DataFrame:
        """Download instrument master CSV from Groww."""
        try:
            response = requests.get(config.GROWW_INSTRUMENTS_URL, timeout=60)
            response.raise_for_status()
            
            df = pd.read_csv(StringIO(response.text))
            return df
        
        except Exception as e:
            logger.error(f"Error downloading instruments: {e}")
            return pd.DataFrame()
    
    @staticmethod
    def filter_fno_instruments(df: pd.DataFrame, underlyings: List[str] = None) -> pd.DataFrame:
        """
        Filter instruments DataFrame for F&O segment and specific underlyings.
        
        Args:
            df: The full instruments dataframe.
            underlyings: List of underlying symbols (e.g. ['NIFTY', 'BANKNIFTY']).
        """
        if df.empty:
            return df
        
        if underlyings is None:
            underlyings = config.SUPPORTED_UNDERLYINGS
        
        fno_df = df[
            (df['segment'] == 'FNO') &
            (df['underlying_symbol'].isin(underlyings))
        ].copy()
        
        return fno_df
    
    @staticmethod
    def get_current_expiry_instruments(df: pd.DataFrame, max_expiries: int = 3) -> pd.DataFrame:
        """
        Filter instruments to keep only the nearest 'max_expiries' expiry dates per underlying.
        Useful to keep the database size manageable.
        """
        if df.empty:
            return df
        
        # Ensure expiry is datetime
        if 'expiry_date' in df.columns:
            df['expiry_date'] = pd.to_datetime(df['expiry_date'])
        
        today = datetime.now().date()
        
        # Remove expired instruments
        df = df[df['expiry_date'].dt.date >= today].copy()
        
        result_frames = []
        
        # Process each underlying separately
        for underlying in df['underlying_symbol'].unique():
            underlying_df = df[df['underlying_symbol'] == underlying]
            
            # Get sorted unique expiries
            expiries = sorted(underlying_df['expiry_date'].unique())[:max_expiries]
            
            # Keep only instruments belonging to these expiries
            filtered = underlying_df[underlying_df['expiry_date'].isin(expiries)]
            result_frames.append(filtered)
        
        if result_frames:
            return pd.concat(result_frames, ignore_index=True)
        
        return pd.DataFrame()


# Helper factory function
def get_groww_client(user_id: str = None) -> GrowwClient:
    """Factory to get Groww client instance for a user"""
    return GrowwClient(user_id)