# 📁 Complete Project Folder Structure

## Backend (Flask/Python)

```
backend/
├── analysis/                           # Technical Analysis Module
│   ├── __init__.py                     # Module exports
│   ├── decision_engine.py              # Original 67-indicator analysis (kept)
│   ├── market_direction_engine.py      # ✨ NEW: Simplified 12-indicator system
│   ├── timeframe_aggregator.py         # ✨ NEW: 1m → 5m/15m/30m conversion
│   ├── momentum/
│   │   ├── __init__.py
│   │   └── indicators.py               # RSI, MACD, Stochastic, etc.
│   ├── patterns/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── candlestick/
│   │   │   ├── __init__.py
│   │   │   └── patterns.py             # Candlestick patterns
│   │   ├── harmonic/
│   │   │   ├── __init__.py
│   │   │   └── patterns.py             # Harmonic patterns
│   │   └── primary/
│   │       ├── __init__.py
│   │       └── patterns.py             # Primary patterns
│   ├── support_resistance/
│   │   ├── __init__.py
│   │   └── indicators.py               # Pivot, Fibonacci, VWAP, etc.
│   └── volatility/
│       ├── __init__.py
│       └── indicators.py               # ATR, Bollinger, Keltner, etc.
│
├── database/
│   ├── __init__.py
│   ├── mongodb.py                      # MongoDB operations
│   └── redis_client.py                 # Redis caching
│
├── docs/
│   ├── api_mapping.mermaid
│   ├── indicators_breakdown.mermaid
│   ├── system_flowchart.mermaid
│   ├── system_flowcharts.html
│   └── trading_flow.mermaid
│
├── models/
│   ├── __init__.py
│   └── models.py                       # ✨ UPDATED: Strategy with confidence fields
│
├── routes/
│   ├── __init__.py
│   ├── auth_routes.py                  # Authentication endpoints
│   ├── instruments_routes.py           # Instrument management
│   ├── market_routes.py                # ✨ UPDATED: Added direction endpoints
│   ├── settings_routes.py              # User settings
│   ├── strategy_routes.py              # ✨ UPDATED: Confidence config support
│   └── trade_routes.py                 # Trade management
│
├── services/
│   ├── __init__.py                     # ✨ UPDATED: Added direction exports
│   ├── candle_service.py               # Candle data management
│   ├── direction_scheduler.py          # ✨ NEW: 1-second direction updates
│   ├── groww_client.py                 # Groww broker API
│   ├── instrument_sync.py              # Instrument synchronization
│   ├── paper_broker.py                 # Paper trading simulation
│   ├── scheduler.py                    # Main scheduler (5s heartbeat)
│   ├── telegram_alert.py               # Telegram notifications
│   └── trading_engine.py               # Trade execution
│
├── utils/
│   ├── __init__.py
│   ├── checksum.py                     # API checksum utilities
│   ├── encryption.py                   # Credential encryption
│   ├── risk_manager.py                 # Risk management
│   └── time_utils.py                   # IST time utilities
│
├── app.py                              # Flask application entry
├── config.py                           # Configuration
├── requirements.txt                    # Python dependencies
├── postman_collection.json             # API testing collection
├── POSTMAN_TESTING_GUIDE.md
└── README.md
```

## Frontend (React/TypeScript/Vite)

```
frontend/
├── src/
│   ├── api/
│   │   ├── index.ts                    # ✨ UPDATED: Added direction export
│   │   ├── auth.api.ts                 # Authentication API
│   │   ├── axios.ts                    # Axios configuration
│   │   ├── direction.api.ts            # ✨ NEW: Direction API client
│   │   ├── market.api.ts               # Market data API
│   │   ├── settings.api.ts             # Settings API
│   │   ├── strategy.api.ts             # Strategy API
│   │   └── trade.api.ts                # Trade API
│   │
│   ├── components/
│   │   ├── common/
│   │   │   ├── Loading.tsx             # Loading spinner
│   │   │   ├── Modal.tsx               # Modal component
│   │   │   └── Toast.tsx               # Toast notifications
│   │   │
│   │   ├── direction/                  # ✨ NEW FOLDER
│   │   │   ├── index.ts                # Exports
│   │   │   ├── DirectionPanel.tsx      # Grid of direction cards
│   │   │   └── MarketDirectionCard.tsx # Single direction display
│   │   │
│   │   ├── layout/
│   │   │   ├── Header.tsx              # App header
│   │   │   ├── Layout.tsx              # Main layout wrapper
│   │   │   └── Sidebar.tsx             # Navigation sidebar
│   │   │
│   │   └── strategy/                   # ✨ NEW FOLDER
│   │       ├── index.ts                # Exports
│   │       └── ConfidenceConfig.tsx    # Confidence configuration UI
│   │
│   ├── config/
│   │   └── index.ts                    # App configuration
│   │
│   ├── pages/
│   │   ├── Charts.tsx                  # ✨ UPDATED: Added direction panel
│   │   ├── Dashboard.tsx               # ✨ UPDATED: Added direction panel
│   │   ├── Login.tsx                   # Login page
│   │   ├── NotFound.tsx                # 404 page
│   │   ├── Profile.tsx                 # User profile
│   │   ├── Settings.tsx                # Settings page
│   │   ├── Signals.tsx                 # Signals log
│   │   ├── Strategy.tsx                # ✨ UPDATED: Added confidence tab
│   │   └── Trades.tsx                  # Trades history
│   │
│   ├── store/
│   │   ├── index.ts                    # ✨ UPDATED: Added direction export
│   │   ├── auth.store.ts               # Auth state
│   │   ├── direction.store.ts          # ✨ NEW: Direction state
│   │   ├── market.store.ts             # Market state
│   │   ├── strategy.store.ts           # Strategy state
│   │   ├── trade.store.ts              # Trade state
│   │   └── ui.store.ts                 # UI state
│   │
│   ├── styles/
│   │   ├── globals.css                 # Global styles
│   │   └── ui.plugin.js                # Tailwind plugin
│   │
│   ├── types/
│   │   └── index.ts                    # ✨ UPDATED: Added direction types
│   │
│   ├── utils/
│   │   ├── index.ts                    # Utility exports
│   │   ├── formatter.ts                # Formatting utilities
│   │   └── indicators.ts               # Chart indicators
│   │
│   ├── App.tsx                         # Main app component
│   └── main.tsx                        # Entry point
│
├── index.html                          # HTML entry
├── package.json                        # Dependencies
├── package-lock.json                   # Lock file
├── postcss.config.js                   # PostCSS config
├── tailwind.config.js                  # Tailwind config
├── tsconfig.json                       # TypeScript config
├── tsconfig.node.json                  # Node TypeScript config
├── vite.config.ts                      # Vite config
└── FOLDER_STRUCTURE.md                 # Structure documentation
```

## ✨ New/Updated Files Summary

### Backend (7 files changed/added)
| File | Status | Description |
|------|--------|-------------|
| `analysis/market_direction_engine.py` | NEW | Simplified 12-indicator direction engine |
| `analysis/timeframe_aggregator.py` | NEW | Candle timeframe conversion |
| `analysis/__init__.py` | UPDATED | Added new exports |
| `services/direction_scheduler.py` | NEW | 1-second direction updates |
| `services/__init__.py` | UPDATED | Added direction exports |
| `models/models.py` | UPDATED | Strategy confidence fields |
| `routes/market_routes.py` | UPDATED | Direction API endpoints |
| `routes/strategy_routes.py` | UPDATED | Confidence config support |

### Frontend (12 files changed/added)
| File | Status | Description |
|------|--------|-------------|
| `api/direction.api.ts` | NEW | Direction API client |
| `api/index.ts` | UPDATED | Added direction export |
| `store/direction.store.ts` | NEW | Direction state management |
| `store/index.ts` | UPDATED | Added direction export |
| `components/direction/index.ts` | NEW | Direction components export |
| `components/direction/MarketDirectionCard.tsx` | NEW | Direction card UI |
| `components/direction/DirectionPanel.tsx` | NEW | Direction grid panel |
| `components/strategy/index.ts` | NEW | Strategy components export |
| `components/strategy/ConfidenceConfig.tsx` | NEW | Confidence config UI |
| `types/index.ts` | UPDATED | Added direction types |
| `pages/Dashboard.tsx` | UPDATED | Added direction panel |
| `pages/Charts.tsx` | UPDATED | Added direction display |
| `pages/Strategy.tsx` | UPDATED | Added confidence tab |

## API Endpoints Added

```
GET  /api/market/direction              # Get all indices directions
GET  /api/market/direction/<symbol>     # Get specific symbol direction
GET  /api/market/direction/scheduler/status
POST /api/market/direction/scheduler/start
POST /api/market/direction/scheduler/stop
```

## Strategy Confidence Fields Added

```python
# New fields in Strategy model
confidence_preset: str       # 'conservative' | 'balanced' | 'aggressive' | 'custom'
min_confidence: int          # 50-95
volume_confirmation: bool    # Default: True
volatility_filter: bool      # Default: True
trend_alignment: bool        # Default: False
allowed_signals: str         # 'BOTH' | 'BULLISH' | 'BEARISH'
time_filter_enabled: bool    # Default: False
time_filter_start: str       # '09:30'
time_filter_end: str         # '15:00'
use_direction_engine: bool   # Default: True (use new engine)
direction_min_strength: int  # 40-90, Default: 60
```
