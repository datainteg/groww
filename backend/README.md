# AI Trading System - Backend API

A comprehensive Flask-based trading backend with Groww API integration, featuring 67 technical indicators, paper trading, and real-time market analysis.

## Features

- **User Authentication**: JWT-based authentication with secure credential storage
- **Paper Trading**: Simulate trades using live market prices without risking real money
- **Live Trading**: Direct integration with Groww API for real order execution
- **67 Technical Indicators**: Comprehensive market analysis including:
  - Momentum: RSI, MACD, Stochastic, ADX, Williams %R, CCI, ROC, MFI
  - Volatility: ATR, Bollinger Bands, Keltner Channels, Donchian Channels
  - Patterns: Candlestick patterns, Harmonic patterns, Chart patterns
  - Support/Resistance: Pivot Points, Fibonacci, VWAP, Ichimoku
- **AI Decision Engine**: Weighted analysis generating BULLISH/BEARISH signals with confidence scores
- **Risk Management**: Stop loss, trailing SL, break-even, partial exits, kill switch
- **Telegram Alerts**: Real-time trade notifications
- **Trade Journal**: Track and review your trades

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file:

```env
# Flask
SECRET_KEY=your-secret-key-here
FLASK_DEBUG=True

# JWT
JWT_SECRET_KEY=your-jwt-secret-key
JWT_ACCESS_TOKEN_EXPIRES=86400

# MongoDB
MONGO_URI=mongodb://localhost:27017/
MONGO_DB_NAME=ai_trading_system

# Redis (optional)
REDIS_HOST=localhost
REDIS_PORT=6379

# Encryption
ENCRYPTION_KEY=your-32-byte-encryption-key-here!

# Groww API
GROWW_API_BASE_URL=https://api.groww.in
GROWW_INSTRUMENTS_URL=https://growwapi-assets.groww.in/instruments/instrument.csv

# Execution Mode (PAPER or LIVE)
EXECUTION_MODE=PAPER

# Paper Trading Initial Capital
PAPER_INITIAL_CAPITAL=1000000

# Telegram (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

### 3. Start MongoDB

```bash
# Using Docker
docker run -d -p 27017:27017 --name mongodb mongo:latest
```

### 4. Run the Server

```bash
python app.py
```

Server starts at `http://localhost:5000`

---

## API Testing with Postman

Import the included `postman_collection.json` for complete API testing.

### Testing Flow

1. **Register/Login** to get access token
2. **Sync Instruments** to download F&O data
3. **Create Strategy** with your settings
4. **Get Decision** to see AI analysis
5. **Place Orders** to trade

---

## API Endpoints Reference

### Health Check (No Auth)
```http
GET /api/health
```
Response:
```json
{
  "status": "healthy",
  "execution_mode": "PAPER",
  "version": "4.0.0"
}
```

### Authentication

#### Register
```http
POST /api/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```

#### Login
```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```
Response:
```json
{
  "message": "Login successful",
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "user": {
    "id": "abc123",
    "email": "user@example.com",
    "broker_connected": false,
    "execution_mode": "PAPER"
  }
}
```

### Market Data

#### Get Market Status
```http
GET /api/market/status
Authorization: Bearer <token>
```
Response:
```json
{
  "is_open": true,
  "current_time": "10:30:45",
  "market_open_time": "09:15",
  "market_close_time": "15:30",
  "status": "OPEN",
  "day_of_week": "Monday"
}
```

#### Get Indices
```http
GET /api/market/indices
Authorization: Bearer <token>
```
Response:
```json
[
  {
    "symbol": "NIFTY",
    "price": 24150.50,
    "change": 50.50,
    "change_percent": 0.21,
    "prev_close": 24100.00
  }
]
```

### Strategy Management

#### Create Strategy
```http
POST /api/strategy/create
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "NIFTY Scalper",
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

#### Get AI Decision (67 Indicators)
```http
GET /api/strategy/decision?symbol=NIFTY&interval=5
Authorization: Bearer <token>
```
Response:
```json
{
  "symbol": "NIFTY",
  "signal": "BULLISH",
  "confidence": 0.78,
  "market_regime": "TRENDING",
  "pattern_count": 3,
  "bullish_score": 0.65,
  "bearish_score": 0.22,
  "momentum": {
    "score": 0.72,
    "signal": "BULLISH",
    "details": {
      "rsi": {"value": 58.5, "signal": "NEUTRAL"},
      "macd": {"value": 15.2, "signal": "BULLISH"}
    }
  },
  "volatility": {
    "score": 0.6,
    "regime": "NORMAL"
  },
  "current_price": 24150.50,
  "timestamp": "2025-01-09T10:30:00"
}
```

### Trading

#### Place Order
```http
POST /api/trade/place-order
Authorization: Bearer <token>
Content-Type: application/json

{
  "trading_symbol": "NIFTY25JAN23000CE",
  "quantity": 50,
  "transaction_type": "BUY",
  "order_type": "MARKET",
  "segment": "FNO"
}
```
Response:
```json
{
  "success": true,
  "order_id": "PAPER_20250109103045123456",
  "status": "COMPLETE",
  "trading_symbol": "NIFTY25JAN23000CE",
  "quantity": 50,
  "transaction_type": "BUY",
  "execution_price": 150.50,
  "is_paper": true
}
```

#### Get Positions
```http
GET /api/trade/positions
Authorization: Bearer <token>
```

#### Get Daily P&L
```http
GET /api/trade/daily-pnl
Authorization: Bearer <token>
```
Response:
```json
{
  "total_pnl": 1500.00,
  "realized_pnl": 1500.00,
  "unrealized_pnl": 0,
  "trades_today": 5,
  "winning": 3,
  "losing": 2,
  "win_rate": 60.0
}
```

### Settings

#### Get Settings
```http
GET /api/settings/
Authorization: Bearer <token>
```

#### Toggle Kill Switch
```http
POST /api/settings/kill-switch
Authorization: Bearer <token>
Content-Type: application/json

{"enabled": true}
```

---

## Curl Testing Examples

### 1. Health Check
```bash
curl http://localhost:5000/api/health
```

### 2. Register
```bash
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}'
```

### 3. Login
```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}'
```

### 4. Get Market Status (with token)
```bash
TOKEN="your_jwt_token_here"
curl http://localhost:5000/api/market/status \
  -H "Authorization: Bearer $TOKEN"
```

### 5. Get AI Decision
```bash
curl "http://localhost:5000/api/strategy/decision?symbol=NIFTY&interval=5" \
  -H "Authorization: Bearer $TOKEN"
```

### 6. Place Order
```bash
curl -X POST http://localhost:5000/api/trade/place-order \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"trading_symbol":"NIFTY25JAN23000CE","quantity":50,"transaction_type":"BUY","order_type":"MARKET","segment":"FNO"}'
```

---

## Project Structure

```
ai_trading_backend/
├── app.py                 # Main Flask application
├── config.py              # Configuration settings
├── requirements.txt       # Python dependencies
├── postman_collection.json # Postman API collection
│
├── routes/                # API route handlers
│   ├── auth_routes.py     # Authentication
│   ├── market_routes.py   # Market data
│   ├── strategy_routes.py # Strategy & AI decision
│   ├── trade_routes.py    # Order execution
│   ├── settings_routes.py # User settings
│   └── instruments_routes.py # F&O instruments
│
├── services/              # Business logic
│   ├── groww_client.py    # Groww API client
│   ├── paper_broker.py    # Paper trading simulator
│   ├── trading_engine.py  # Trading engine
│   ├── candle_service.py  # Candlestick data
│   ├── instrument_sync.py # Instrument sync
│   ├── telegram_alert.py  # Notifications
│   └── scheduler.py       # Background tasks
│
├── analysis/              # Technical analysis
│   ├── decision_engine.py # AI decision engine
│   ├── momentum/          # RSI, MACD, etc.
│   ├── volatility/        # ATR, BB, etc.
│   ├── patterns/          # Chart patterns
│   └── support_resistance/ # S/R levels
│
├── database/              # Database layer
│   └── mongodb.py         # MongoDB operations
│
└── utils/                 # Utilities
    ├── encryption.py      # Credential encryption
    ├── risk_manager.py    # Risk management
    └── time_utils.py      # Market hours, IST
```

---

## Risk Management Features

- **Stop Loss**: Automatic exit at specified price
- **Trailing Stop Loss**: Move SL as profit increases
- **Break-Even**: Move SL to entry when target % reached
- **Partial Exit**: Exit portion of position at first target
- **Daily Limits**: Max profit/loss per day
- **Kill Switch**: Emergency stop all trading

---

## Support

For issues or feature requests, please check the documentation or raise an issue.

## License

MIT License
