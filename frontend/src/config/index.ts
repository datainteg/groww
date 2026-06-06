// Configuration constants for the AI Trading Frontend

export const config = {
  // API Configuration
  API_URL: import.meta.env.VITE_API_URL || 'http://localhost:5000/api',
  
  // Polling Intervals (in milliseconds)
  MARKET_POLL_INTERVAL: 5000,      // 5 seconds for market data
  SIGNAL_POLL_INTERVAL: 10000,     // 10 seconds for AI signals
  TRADE_POLL_INTERVAL: 3000,       // 3 seconds for active trades
  POSITION_POLL_INTERVAL: 5000,    // 5 seconds for positions
  
  // Supported Indices
  INDICES: ['NIFTY', 'BANKNIFTY', 'SENSEX', 'FINNIFTY'] as const,
  
  // Default Strategy Settings
  DEFAULT_STRATEGY: {
    index: 'NIFTY',
    quantity: 50,
    stopLoss: 20,
    target: 40,
    maxOrdersPerDay: 3,
    maxProfitLimit: 10000,
    maxLossLimit: 5000,
    product: 'MIS',
    trailingSLEnabled: true,
    trailingSLValue: 15,
  },
  
  // ATM Offset Options
  ATM_OFFSETS: [
    { value: 0, label: 'ATM (0)' },
    { value: 50, label: 'ITM 1 (+50)' },
    { value: 100, label: 'ITM 2 (+100)' },
    { value: -50, label: 'OTM 1 (-50)' },
    { value: -100, label: 'OTM 2 (-100)' },
    { value: -150, label: 'OTM 3 (-150)' },
  ],
  
  // Lot Sizes (for reference)
  LOT_SIZES: {
    NIFTY: 50,
    BANKNIFTY: 15,
    SENSEX: 10,
    FINNIFTY: 25,
  } as Record<string, number>,
  
  // Chart Settings
  CHART_INTERVALS: [
    { value: '1', label: '1m' },
    { value: '5', label: '5m' },
    { value: '15', label: '15m' },
    { value: '60', label: '1h' },
    { value: '1D', label: '1D' },
  ],
  
  // Market Hours (IST)
  MARKET_HOURS: {
    open: '09:15',
    close: '15:30',
    preMarket: '09:00',
    postMarket: '15:35',
  },
  
  // Risk Limits
  RISK_LIMITS: {
    maxDailyProfit: 50000,
    maxDailyLoss: 25000,
    maxConcurrentTrades: 5,
    defaultCapital: 1000000,
  },
  
  // Signal Thresholds
  SIGNAL_THRESHOLDS: {
    strongBullish: 0.7,
    weakBullish: 0.55,
    neutral: 0.45,
    weakBearish: 0.45,
    strongBearish: 0.3,
  },
}

export type IndexType = typeof config.INDICES[number]
