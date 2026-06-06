# AI Trading Frontend - Folder Structure

```
ai_trading_frontend/
│
├── public/                          # Static assets
│   └── favicon.svg
│
├── src/
│   ├── api/                         # API Layer (Backend Communication)
│   │   ├── index.ts                 # Export all APIs
│   │   ├── axios.ts                 # Axios instance with interceptors
│   │   ├── auth.api.ts              # /api/auth/* endpoints
│   │   ├── market.api.ts            # /api/market/* endpoints  
│   │   ├── strategy.api.ts          # /api/strategy/* endpoints
│   │   ├── trade.api.ts             # /api/trade/* endpoints
│   │   ├── settings.api.ts          # /api/settings/* endpoints
│   │   └── instruments.api.ts       # /api/instruments/* endpoints
│   │
│   ├── components/                  # Reusable UI Components
│   │   ├── common/                  # Generic components
│   │   │   ├── Button.tsx           # Primary, Ghost, Danger buttons
│   │   │   ├── Card.tsx             # Card wrapper
│   │   │   ├── Modal.tsx            # Modal dialog
│   │   │   ├── Toast.tsx            # Toast notifications
│   │   │   ├── Loading.tsx          # Loading spinner
│   │   │   ├── Badge.tsx            # Status badges
│   │   │   └── Input.tsx            # Form inputs
│   │   │
│   │   ├── layout/                  # Layout components
│   │   │   ├── Layout.tsx           # Main layout wrapper
│   │   │   ├── Sidebar.tsx          # Navigation sidebar
│   │   │   └── Header.tsx           # Top header bar
│   │   │
│   │   ├── dashboard/               # Dashboard widgets
│   │   │   ├── MarketOverview.tsx   # NIFTY, BANKNIFTY, SENSEX cards
│   │   │   ├── SignalCard.tsx       # AI Signal display
│   │   │   ├── PnlSummary.tsx       # Today's P&L
│   │   │   └── QuickStats.tsx       # Active strategies, trades
│   │   │
│   │   ├── strategy/                # Strategy components
│   │   │   ├── StrategyCard.tsx     # Strategy item card
│   │   │   ├── StrategyForm.tsx     # Create/Edit form (ATM + Manual)
│   │   │   └── StrategyList.tsx     # List of strategies
│   │   │
│   │   ├── trade/                   # Trade components
│   │   │   ├── ActiveTrades.tsx     # Live positions
│   │   │   ├── TradeHistory.tsx     # Past trades table
│   │   │   ├── OrderBook.tsx        # Order list
│   │   │   └── QuickTrade.tsx       # Manual order panel
│   │   │
│   │   ├── charts/                  # Chart components
│   │   │   ├── PriceChart.tsx       # TradingView Lightweight Charts
│   │   │   ├── IndicatorPanel.tsx   # RSI, MACD, etc.
│   │   │   └── OptionChain.tsx      # Option chain view
│   │   │
│   │   └── signals/                 # Signal components
│   │       ├── SignalDashboard.tsx  # 67-indicator analysis
│   │       ├── PatternList.tsx      # Detected patterns
│   │       └── ScoreGauge.tsx       # Bull/Bear score gauge
│   │
│   ├── hooks/                       # Custom React Hooks
│   │   ├── useAuth.ts               # Authentication hook
│   │   ├── useMarket.ts             # Market data hook
│   │   ├── useStrategy.ts           # Strategy management hook
│   │   ├── useTrade.ts              # Trade management hook
│   │   ├── useInterval.ts           # Polling interval hook
│   │   └── useToast.ts              # Toast notification hook
│   │
│   ├── pages/                       # Route Pages
│   │   ├── Dashboard.tsx            # Main dashboard
│   │   ├── Strategy.tsx             # Strategy management
│   │   ├── Trades.tsx               # Trade history & positions
│   │   ├── Charts.tsx               # Advanced charts
│   │   ├── Signals.tsx              # AI Signal analysis
│   │   ├── Settings.tsx             # User settings
│   │   ├── Profile.tsx              # User profile
│   │   ├── Login.tsx                # Login page
│   │   └── NotFound.tsx             # 404 page
│   │
│   ├── store/                       # Zustand State Management
│   │   ├── index.ts                 # Export all stores
│   │   ├── auth.store.ts            # Auth state
│   │   ├── market.store.ts          # Market data state
│   │   ├── strategy.store.ts        # Strategy state
│   │   ├── trade.store.ts           # Trade state
│   │   └── ui.store.ts              # UI state (theme, toasts)
│   │
│   ├── types/                       # TypeScript Types
│   │   ├── index.ts                 # Export all types
│   │   ├── auth.types.ts            # User, AuthResponse
│   │   ├── market.types.ts          # Instrument, Quote, OptionChain
│   │   ├── strategy.types.ts        # Strategy, EngineStatus
│   │   ├── trade.types.ts           # Trade, Position, Order
│   │   └── signal.types.ts          # Decision, Indicator
│   │
│   ├── utils/                       # Utility Functions
│   │   ├── formatter.ts             # Currency, percentage formatting
│   │   ├── time.ts                  # Time utilities, IST conversion
│   │   ├── validation.ts            # Form validation
│   │   └── constants.ts             # App constants
│   │
│   ├── styles/                      # CSS Styles
│   │   ├── globals.css              # Global styles, Tailwind
│   │   └── theme.css                # Theme variables
│   │
│   ├── config/                      # Configuration
│   │   └── index.ts                 # API URL, intervals, etc.
│   │
│   ├── App.tsx                      # Main App component
│   └── main.tsx                     # Entry point
│
├── .env                             # Environment variables
├── .env.example                     # Env template
├── index.html                       # HTML entry
├── package.json                     # Dependencies
├── tailwind.config.js               # Tailwind configuration
├── tsconfig.json                    # TypeScript config
├── vite.config.ts                   # Vite bundler config
└── README.md                        # Documentation
```

## Key Design Principles

### 1. **API Layer** (`/api`)
- All API calls are centralized
- Axios interceptors for auth tokens
- Error handling middleware

### 2. **Components** (`/components`)
- Reusable, single-responsibility
- Props-driven, no internal API calls
- Styled with Tailwind CSS

### 3. **Pages** (`/pages`)
- Route-level components
- Data fetching with hooks
- Composition of smaller components

### 4. **Store** (`/store`)
- Zustand for state management
- Separate stores per domain
- Actions and selectors together

### 5. **Types** (`/types`)
- Strict TypeScript types
- Shared across components
- Backend contract alignment

### 6. **Data Flow**
```
User Action → Page → Store Action → API Call → Store Update → Re-render
```

### 7. **Real-time Updates**
- Polling every 5 seconds for market data
- WebSocket-ready architecture
- Optimistic updates for UX

## Color Scheme

| Element | Dark Theme | Purpose |
|---------|------------|---------|
| Background | `#0a0f1a` | Main background |
| Card | `#111827` | Card/Panel background |
| Border | `#1f2937` | Subtle borders |
| Text Primary | `#f3f4f6` | Main text |
| Text Secondary | `#9ca3af` | Muted text |
| Green/Bull | `#22c55e` | Profit, bullish |
| Red/Bear | `#ef4444` | Loss, bearish |
| Blue/Primary | `#3b82f6` | Primary actions |
| Amber/Warning | `#f59e0b` | Warnings |
| Purple/Accent | `#8b5cf6` | Accent highlights |
