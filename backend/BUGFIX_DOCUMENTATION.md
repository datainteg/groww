# Trading System Bug Fixes Documentation

## Issues Found and Fixed

### 1. ❌ CRITICAL: Missing `get_positions` Method in GrowwClient
**File:** `services/groww_client.py`
**Issue:** The `scheduler.py` calls `client.get_positions()` but this method didn't exist.
**Fix:** Added `get_positions()`, `get_holdings()`, and `get_margins()` methods.

### 2. ❌ CRITICAL: Inconsistent `get_ltp` Method Signatures  
**Files:** `services/paper_broker.py`, `services/trading_engine.py`
**Issue:** 
- `PaperBroker.get_ltp()` expected a single string
- `GrowwClient.get_ltp()` expected a list of symbols
- `trading_engine.monitor_active_trades()` called `broker.get_ltp([trade['symbol']])` which broke for Paper mode

**Fix:** 
- Updated `PaperBroker.get_ltp()` to accept both single string AND list (for compatibility)
- Created unified `_get_option_ltp()` method in TradingEngine that handles both modes

### 3. ❌ CRITICAL: Wrong Parameter Name for LIVE Orders
**File:** `services/trading_engine.py` (line 244-250)
**Issue:** Used `product_type=` instead of `product=` for Groww API
```python
# WRONG:
result = broker.place_order(..., product_type=strategy.get('product', 'MIS'))
# CORRECT:
result = broker.place_order(..., product=strategy.get('product', 'MIS'))
```
**Fix:** Changed to use `product=` consistently.

### 4. ❌ CRITICAL: Execution Mode Not Fetched from User Database
**Files:** `services/trading_engine.py`, `routes/trade_routes.py`
**Issue:** Trading engine always used `config.EXECUTION_MODE` instead of user's actual preference.
**Fix:** 
- Added `_get_user_execution_mode()` method that checks:
  1. User settings first
  2. User record second  
  3. Config default as fallback

### 5. ❌ CRITICAL: SL/TL Monitoring Not Working
**File:** `services/trading_engine.py`
**Issue:** `monitor_active_trades()` failed due to LTP fetch issues
**Fix:** 
- Created unified `_get_option_ltp()` method
- Added better error handling and logging
- Fixed segment parameter (`FNO` instead of `CASH` for options)

### 6. ⚠️ Exchange Parameter Issue  
**Issue:** For FNO orders, exchange should be `NFO` not `NSE` in some cases.
**Fix:** Added proper segment handling in `_get_option_ltp()`

### 7. ⚠️ Missing Execution Price After Order
**Issue:** Groww's `place_order` doesn't return execution price immediately for MARKET orders.
**Fix:** Added `_get_order_fill_price()` method that fetches order details to get actual fill price.

### 8. ⚠️ Scheduler Heartbeat Error Handling
**File:** `services/scheduler.py`
**Issue:** Errors in heartbeat job were not properly logged.
**Fix:** Added better error handling with traceback printing.

---

## Files Modified

1. **`services/trading_engine.py`** - Major rewrite with all fixes
2. **`services/groww_client.py`** - Added missing methods
3. **`services/paper_broker.py`** - Fixed `get_ltp()` signature
4. **`routes/trade_routes.py`** - Fixed execution mode detection
5. **`services/scheduler.py`** - Fixed heartbeat job

---

## How to Apply Fixes

The fixes have already been applied to your codebase. The files are:

```
/home/claude/backend/backend/services/trading_engine.py      # FIXED
/home/claude/backend/backend/services/groww_client.py        # FIXED  
/home/claude/backend/backend/services/paper_broker.py        # FIXED
/home/claude/backend/backend/routes/trade_routes.py          # FIXED
/home/claude/backend/backend/services/scheduler.py           # FIXED
```

Backup of original trading_engine:
```
/home/claude/backend/backend/services/trading_engine_backup.py
```

---

## Testing Checklist

After deploying, verify:

### 1. Execution Mode
```bash
# Set execution mode via API
PUT /api/settings/mode
{
  "mode": "PAPER"  # or "LIVE"
}
```

### 2. SL/TL Monitoring
- Create a strategy with SL and Target set
- Execute a trade
- Monitor logs for "Exit triggered" or "Trailing SL updated" messages

### 3. LIVE Order Execution
- Ensure broker is connected (Groww access token valid)
- Set execution mode to LIVE
- Place a test order with small quantity
- Check order appears in Groww's order book

### 4. Scheduler Running
Check console output for:
```
[timestamp] 🟢 Scheduler Service Running...
[timestamp] 📊 Master Sync Job: 1min fetch + Aggregation (5m, 15m, 60m, 1D)
```

---

## Key Code Changes Explained

### Trading Engine - Unified LTP Method
```python
def _get_option_ltp(self, trading_symbol: str) -> float:
    """
    Unified LTP fetching that works for both PAPER and LIVE modes
    """
    if self.execution_mode == 'PAPER':
        return self.paper.get_ltp(trading_symbol, segment='FNO')
    else:
        exchange_symbol = f"NFO_{trading_symbol}"
        result = self.groww.get_ltp([exchange_symbol], segment='FNO')
        # ... handle response
```

### Paper Broker - Flexible get_ltp
```python
def get_ltp(self, trading_symbol_or_list, segment: str = 'FNO') -> float:
    # Handle list input for compatibility
    if isinstance(trading_symbol_or_list, list):
        trading_symbol = trading_symbol_or_list[0]
        if '_' in trading_symbol:
            trading_symbol = trading_symbol.split('_', 1)[1]
    else:
        trading_symbol = trading_symbol_or_list
    # ... rest of method
```

### Execution Mode Detection
```python
def _get_user_execution_mode(self) -> str:
    # 1. Check user settings first
    if self.settings and self.settings.get('execution_mode'):
        return self.settings.get('execution_mode')
    
    # 2. Check user record
    user = db.get_user_by_id(self.user_id)
    if user and user.get('execution_mode'):
        return user.get('execution_mode')
    
    # 3. Fallback to config
    return config.EXECUTION_MODE
```

---

## Environment Variables

Make sure these are set in your `.env`:

```env
EXECUTION_MODE=PAPER    # Default mode
GROWW_API_BASE_URL=https://api.groww.in
REDIS_HOST=localhost
REDIS_PORT=6379
MONGO_URI=mongodb://localhost:27017/
```

---

## Common Issues After Fix

### Issue: "Broker not connected"
**Solution:** User needs to complete Groww OAuth login first.

### Issue: "No instrument found for..."
**Solution:** Run instrument sync job or call `/api/instruments/sync`

### Issue: SL/TL still not triggering
**Check:**
1. Market must be open (9:15 AM - 3:30 PM IST)
2. Scheduler must be running
3. User must have `broker_connected: true`
4. Trade must have valid `stop_loss` and `target` values
