# AI Trading API - Postman Testing Guide

## Quick Setup

### 1. Import Collection
1. Open Postman
2. Click **Import** → Select `postman_collection.json`
3. The collection will appear with all endpoints organized by category

### 2. Set Variables
The collection uses variables for easy testing:
- `{{base_url}}` - Server URL (default: `http://localhost:5000/api`)
- `{{access_token}}` - JWT token (auto-saved on login)
- `{{strategy_id}}` - Strategy ID (auto-saved on create)
- `{{order_id}}` - Order ID (auto-saved on place order)

---

## Testing Workflow

### Step 1: Health Check (Verify Server Running)
```
GET {{base_url}}/health
```
**Expected Response:**
```json
{
  "status": "healthy",
  "execution_mode": "PAPER",
  "version": "4.0.0"
}
```

### Step 2: Register New User
```
POST {{base_url}}/auth/register
Body:
{
  "email": "trader@example.com",
  "password": "SecurePass123"
}
```
**Expected Response (201):**
```json
{
  "message": "User registered successfully",
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "user": {
    "id": "678abc123def456",
    "email": "trader@example.com",
    "broker_connected": false,
    "execution_mode": "PAPER"
  }
}
```
**Note:** The access_token is automatically saved to collection variables.

### Step 3: Login (If Already Registered)
```
POST {{base_url}}/auth/login
Body:
{
  "email": "trader@example.com",
  "password": "SecurePass123"
}
```

### Step 4: Check Market Status
```
GET {{base_url}}/market/status
Headers: Authorization: Bearer {{access_token}}
```
**Expected Response:**
```json
{
  "is_open": false,
  "current_time": "20:30:45",
  "market_open_time": "09:15",
  "market_close_time": "15:30",
  "status": "CLOSED",
  "day_of_week": "Thursday",
  "next_open": "2025-01-10 09:15:00"
}
```

### Step 5: Get Indices Data
```
GET {{base_url}}/market/indices
Headers: Authorization: Bearer {{access_token}}
```
**Expected Response:**
```json
[
  {
    "symbol": "NIFTY",
    "price": 24150.50,
    "change": 50.50,
    "change_percent": 0.21,
    "prev_close": 24100.00
  },
  {
    "symbol": "BANKNIFTY",
    "price": 51250.75,
    "change": 100.75,
    "change_percent": 0.20,
    "prev_close": 51150.00
  }
]
```

### Step 6: Get AI Decision (67 Indicators)
```
GET {{base_url}}/strategy/decision?symbol=NIFTY&interval=5
Headers: Authorization: Bearer {{access_token}}
```
**Expected Response:**
```json
{
  "symbol": "NIFTY",
  "signal": "BULLISH",
  "confidence": 0.78,
  "market_regime": "TRENDING",
  "pattern_count": 3,
  "patterns": [
    {"name": "Bullish Engulfing", "direction": "BULLISH", "confidence": 0.85}
  ],
  "bullish_score": 0.65,
  "bearish_score": 0.22,
  "momentum": {
    "score": 0.72,
    "signal": "BULLISH",
    "details": {
      "rsi": {"value": 58.5, "signal": "NEUTRAL"},
      "macd": {"value": 15.2, "signal": "BULLISH"},
      "stochastic": {"value": 72.3, "signal": "BULLISH"},
      "adx": {"value": 28.5, "signal": "TRENDING"}
    }
  },
  "volatility": {
    "score": 0.6,
    "regime": "NORMAL",
    "details": {
      "atr": {"value": 125.5, "regime": "NORMAL"},
      "bollinger": {"width_percentile": 45}
    }
  },
  "support_resistance": {
    "score": 0.7,
    "signal": "BULLISH",
    "levels": {
      "pivot": 24100,
      "r1": 24200,
      "r2": 24300,
      "s1": 24000,
      "s2": 23900,
      "vwap": 24080
    }
  },
  "volume": {
    "score": 0.65,
    "confirmed": true
  },
  "current_price": 24150.50,
  "timestamp": "2025-01-09T10:30:00"
}
```

### Step 7: Create a Strategy
```
POST {{base_url}}/strategy/create
Headers: Authorization: Bearer {{access_token}}
Body:
{
  "name": "NIFTY Momentum Scalper",
  "index": "NIFTY",
  "ce_symbol": "NIFTY25JAN23000CE",
  "pe_symbol": "NIFTY25JAN23000PE",
  "quantity": 50,
  "stop_loss": 50,
  "target": 100,
  "trailing_sl_enabled": true,
  "trailing_sl_value": 20,
  "break_even_enabled": true,
  "break_even_trigger": 50,
  "max_orders_per_day": 2,
  "max_profit_limit": 5000,
  "max_loss_limit": 2000
}
```
**Expected Response (201):**
```json
{
  "message": "Strategy created",
  "strategy_id": "678def456ghi789"
}
```

### Step 8: Place a Paper Trade
```
POST {{base_url}}/trade/place-order
Headers: Authorization: Bearer {{access_token}}
Body:
{
  "trading_symbol": "NIFTY25JAN23000CE",
  "quantity": 50,
  "transaction_type": "BUY",
  "order_type": "MARKET",
  "segment": "FNO"
}
```
**Expected Response:**
```json
{
  "success": true,
  "order_id": "PAPER_20250109153045123456",
  "status": "COMPLETE",
  "trading_symbol": "NIFTY25JAN23000CE",
  "quantity": 50,
  "transaction_type": "BUY",
  "execution_price": 152.50,
  "execution_time": "2025-01-09T15:30:45+05:30",
  "is_paper": true
}
```

### Step 9: Check Positions
```
GET {{base_url}}/trade/positions
Headers: Authorization: Bearer {{access_token}}
```
**Expected Response:**
```json
{
  "positions": [
    {
      "trading_symbol": "NIFTY25JAN23000CE",
      "quantity": 50,
      "entry_price": 152.50,
      "entry_time": "2025-01-09T15:30:45",
      "ltp": 155.00,
      "unrealized_pnl": 125.00
    }
  ]
}
```

### Step 10: Get Paper Account Limits
```
GET {{base_url}}/trade/limits
Headers: Authorization: Bearer {{access_token}}
```
**Expected Response:**
```json
{
  "available_balance": 998475.00,
  "used_margin": 1525.00,
  "total_balance": 1000000.00
}
```

### Step 11: Get Daily P&L
```
GET {{base_url}}/trade/daily-pnl
Headers: Authorization: Bearer {{access_token}}
```
**Expected Response:**
```json
{
  "total_pnl": 125.00,
  "realized_pnl": 0,
  "unrealized_pnl": 125.00,
  "trades_today": 1,
  "winning": 0,
  "losing": 0,
  "win_rate": 0
}
```

### Step 12: Close Position (Sell)
```
POST {{base_url}}/trade/place-order
Headers: Authorization: Bearer {{access_token}}
Body:
{
  "trading_symbol": "NIFTY25JAN23000CE",
  "quantity": 50,
  "transaction_type": "SELL",
  "order_type": "MARKET",
  "segment": "FNO"
}
```

---

## Error Responses

### 401 Unauthorized - Missing Token
```json
{
  "error": "Missing Authorization Header",
  "message": "Please login first"
}
```

### 401 Unauthorized - Invalid Token
```json
{
  "error": "Invalid token",
  "message": "Please login again"
}
```

### 400 Bad Request - Missing Field
```json
{
  "error": "trading_symbol is required"
}
```

### 404 Not Found
```json
{
  "error": "Strategy not found"
}
```

---

## Tips for Testing

1. **Auto-save Tokens**: The collection includes test scripts that automatically save `access_token`, `strategy_id`, and `order_id` to variables.

2. **Test in Order**: Follow the workflow above for best results - register/login first, then test other endpoints.

3. **Paper Mode**: By default, the system runs in PAPER mode. All trades are simulated.

4. **Mock Data**: If MongoDB has no candle data, the system generates mock candles for testing.

5. **Check Health First**: Always verify the server is running with `/api/health` before testing.

---

## Collection Structure

```
AI Trading System API
├── Health
│   └── Health Check (No Auth)
├── Auth
│   ├── Register User
│   ├── Login
│   ├── Get Current User
│   ├── Get Profile
│   ├── Update Profile
│   ├── Update Groww Credentials
│   ├── Refresh Token
│   └── Logout
├── Market
│   ├── Get Market Status
│   ├── Get Indices
│   ├── Get LTP
│   ├── Get Quote
│   ├── Sync Instruments
│   ├── Get Expiries
│   └── Search Instruments
├── Instruments
│   ├── Sync Instruments
│   ├── Get CE Symbols
│   ├── Get PE Symbols
│   ├── Get Underlying Info
│   ├── Get Expiries
│   ├── Get Instruments Count
│   └── Get Last Sync Info
├── Strategy
│   ├── Create Strategy
│   ├── List Strategies
│   ├── Get Strategy
│   ├── Update Strategy
│   ├── Delete Strategy
│   ├── Start Strategy
│   ├── Stop Strategy
│   ├── Stop All Strategies
│   ├── Get Engine Status
│   ├── Get Decision (67 Indicators)
│   ├── Get All Indicators
│   ├── Get Candles
│   ├── Sync Candles
│   └── Analyze Strategy
├── Trade
│   ├── Place Order - BUY
│   ├── Place Order - SELL
│   ├── Get Orders
│   ├── Get Order Status
│   ├── Get Positions
│   ├── Get Trades
│   ├── Get Active Trades
│   ├── Exit Trade
│   ├── Get Daily P&L
│   ├── Get Limits
│   ├── Get Statistics
│   ├── Reset Paper Account
│   ├── Get Journal
│   └── Add Journal Entry
└── Settings
    ├── Get Settings
    ├── Update Settings
    ├── Update Execution Mode
    ├── Update Theme
    ├── Toggle Kill Switch
    ├── Configure Telegram
    ├── Test Telegram
    ├── Disconnect Telegram
    └── Reset Daily Counters
```
