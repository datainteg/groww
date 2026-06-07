// ==================== AUTH TYPES ====================
export interface User {
  id: string
  email: string
  name?: string
  broker_connected: boolean
  execution_mode: ExecutionMode
  groww_api_key_masked?: string
  token_expiry?: string
  token_valid?: boolean
  needs_groww_refresh?: boolean
  must_change_password?: boolean
  created_at?: string
}

export interface AuthResponse {
  message: string
  access_token: string
  user: User
}

export type ExecutionMode = 'PAPER' | 'LIVE'

// ==================== MARKET TYPES ====================
export interface MarketStatus {
  is_open: boolean
  current_time: string
  session: 'PRE_MARKET' | 'TRADING' | 'POST_MARKET' | 'CLOSED'
  next_open?: string
  next_close?: string
}

export interface IndexData {
  symbol: string
  price: number
  change: number
  change_percent: number
  prev_close?: number
}

export interface Instrument {
  _id: string
  trading_symbol: string
  underlying_symbol: string
  strike_price: number
  instrument_type: 'CE' | 'PE'
  expiry_date: string
  lot_size: number
  exchange: string
  tick_size?: number
}

export interface Quote {
  symbol: string
  ltp: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  change?: number
  change_percent?: number
  timestamp?: number
}

export interface OptionChainItem {
  strike_price: number
  ce?: {
    symbol: string
    ltp: number
    oi: number
    volume: number
    iv?: number
  }
  pe?: {
    symbol: string
    ltp: number
    oi: number
    volume: number
    iv?: number
  }
}

export interface Candle {
  timestamp: number
  datetime: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

// ==================== MARKET DIRECTION TYPES ====================
export type DirectionType = 'UP' | 'DOWN' | 'NEUTRAL'

export interface DirectionComponent {
  score: number
  direction?: string
  weight: number
  confirmed?: boolean
  position?: string
}

export interface MarketDirection {
  direction: DirectionType
  strength: number
  components: {
    trend_15m: DirectionComponent
    structure_5m: DirectionComponent
    momentum_1m: DirectionComponent
    volume: DirectionComponent
    vwap: DirectionComponent
  }
  indicators: {
    ema_9?: number
    ema_21?: number
    ema_50?: number
    ema_100?: number
    rsi_14?: number
    rsi_slope?: number
    vwap?: number
  }
  structure: {
    type: string  // HH_HL, LH_LL, RANGING
    recent_high?: number
    recent_low?: number
    swing_high?: number
    swing_low?: number
  }
  volume_data: {
    current?: number
    average?: number
    ratio?: number
  }
  current_price?: number
  symbol: string
  timestamp: string
  error?: string
}

export interface AllDirectionsResponse {
  directions: Record<string, MarketDirection>
  timestamp: string
}

// ==================== STRATEGY TYPES ====================
export type SelectionMode = 'DYNAMIC' | 'MANUAL'
export type ConfidencePreset = 'conservative' | 'balanced' | 'aggressive' | 'custom'
export type AllowedSignals = 'BOTH' | 'BULLISH' | 'BEARISH'

export interface Strategy {
  _id: string
  user_id: string
  name: string
  index: string
  selection_mode: SelectionMode
  atm_offset: number
  exchange_segment: string
  product: 'MIS' | 'NRML'
  expiry: string
  strike_price?: string
  ce_symbol?: string
  pe_symbol?: string
  quantity: number
  stop_loss: number
  target: number
  trailing_sl_enabled: boolean
  trailing_sl_value: number
  break_even_enabled: boolean
  break_even_trigger: number
  partial_exit_enabled: boolean
  partial_exit_percent: number
  time_exit_enabled: boolean
  max_orders_per_day: number
  max_profit_limit: number
  max_loss_limit: number
  is_active: boolean
  today_pnl: number
  today_orders: number
  total_pnl?: number
  win_rate?: number
  created_at: string
  updated_at: string
  // NEW: Confidence Configuration
  confidence_preset: ConfidencePreset
  min_confidence: number
  volume_confirmation: boolean
  volatility_filter: boolean
  trend_alignment: boolean
  allowed_signals: AllowedSignals
  time_filter_enabled: boolean
  time_filter_start: string
  time_filter_end: string
  use_direction_engine: boolean
  direction_min_strength: number
}

export interface StrategyFormData {
  name: string
  index: string
  selection_mode: SelectionMode
  atm_offset: number
  exchange_segment: string
  product: 'MIS' | 'NRML'
  expiry: string
  strike_price?: string
  ce_symbol?: string
  pe_symbol?: string
  quantity: number
  stop_loss: number
  target: number
  trailing_sl_enabled: boolean
  trailing_sl_value: number
  break_even_enabled: boolean
  break_even_trigger: number
  partial_exit_enabled: boolean
  partial_exit_percent: number
  time_exit_enabled: boolean
  max_orders_per_day: number
  max_profit_limit: number
  max_loss_limit: number
  // NEW: Confidence Configuration
  confidence_preset: ConfidencePreset
  min_confidence: number
  volume_confirmation: boolean
  volatility_filter: boolean
  trend_alignment: boolean
  allowed_signals: AllowedSignals
  time_filter_enabled: boolean
  time_filter_start: string
  time_filter_end: string
  use_direction_engine: boolean
  direction_min_strength: number
}

export interface EngineStatus {
  is_running: boolean
  active_strategies: number
  market_open: boolean
  execution_mode: ExecutionMode
  kill_switch: boolean
}

// ==================== SIGNAL/DECISION TYPES ====================
export type SignalType = 'BULLISH' | 'BEARISH' | 'NEUTRAL' | null

export interface Decision {
  symbol: string
  signal: SignalType
  confidence: number
  strength?: 'STRONG' | 'MODERATE' | 'WEAK'
  market_regime: string
  recommendation?: string
  
  // Scores
  bullish_score: number
  bearish_score: number
  
  // Component scores
  scores?: {
    pattern_score: number
    momentum_score: number
    volatility_score: number
    support_resistance_score: number
    volume_score: number
  }
  
  // Indicators
  indicators?: {
    rsi?: number
    macd?: { macd: number; signal: number; histogram: number }
    adx?: number
    stochastic?: { k: number; d: number }
    atr?: number
    bollinger?: { upper: number; middle: number; lower: number }
  }
  
  // Patterns
  patterns: PatternInfo[]
  pattern_count: number
  
  // Support/Resistance (backend sends score/signal/levels; legacy flat fields optional)
  support_resistance?: {
    score?: number
    signal?: string
    levels?: Record<string, number>
    support_1?: number
    support_2?: number
    resistance_1?: number
    resistance_2?: number
    pivot?: number
  }
  net_score?: number
  
  // Price info
  current_price: number
  timestamp: string
  
  // Detailed components (from 67 indicators)
  momentum?: {
    score: number
    signal: string
    details: Record<string, { value: number; signal: string }>
  }
  volatility?: {
    score: number
    regime: string
    details: Record<string, { value: number; regime: string }>
  }
  volume?: {
    score: number
    confirmed: boolean
  }
  
  error?: string
}

export interface PatternInfo {
  name?: string
  type?: string
  direction: 'BULLISH' | 'BEARISH'
  strength?: number
}

// ==================== TRADE TYPES ====================
export type TradeStatus = 'OPEN' | 'CLOSED' | 'CANCELLED' | 'PENDING'
export type TradeSide = 'BUY' | 'SELL'
export type OrderType = 'MARKET' | 'LIMIT' | 'SL' | 'SL-M'
export type ExitReason = 'TARGET' | 'SL' | 'TRAILING_SL' | 'MANUAL' | 'TIME_EXIT' | 'BREAK_EVEN'

export interface Trade {
  _id: string
  user_id: string
  strategy_id?: string
  strategy_name?: string
  trading_symbol: string
  underlying?: string
  option_type?: 'CE' | 'PE'
  order_type: OrderType
  side: TradeSide
  transaction_type?: TradeSide  // Backend sends this, mapping to side for display
  quantity: number
  entry_price: number
  exit_price?: number
  stop_loss: number
  current_sl?: number
  target: number
  trailing_sl_enabled?: boolean
  trailing_sl_value?: number
  ltp?: number
  status: TradeStatus
  pnl: number
  pnl_percent?: number
  entry_time: string
  exit_time?: string
  exit_reason?: ExitReason
  execution_mode: ExecutionMode
  order_id?: string
  symbol?: string  // Backend sometimes sends this instead of trading_symbol
}

export interface Position {
  _id?: string
  trading_symbol: string
  quantity: number
  avg_price: number
  ltp: number
  pnl: number
  pnl_percent: number
  side: 'LONG' | 'SHORT'
  product?: string
}

export interface Order {
  order_id: string
  trading_symbol: string
  transaction_type: TradeSide
  quantity: number
  price: number
  trigger_price?: number
  order_type: OrderType
  status: 'PENDING' | 'COMPLETE' | 'REJECTED' | 'CANCELLED'
  timestamp: string
  message?: string
}

export interface DailyPnl {
  date?: string
  total_pnl: number
  realized_pnl: number
  unrealized_pnl: number
  trades_today: number
  winning: number
  losing: number
  win_rate: number
  best_trade?: number
  worst_trade?: number
}

export interface TradeStatistics {
  period_days: number
  total_pnl: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  avg_win: number
  avg_loss: number
  best_trade: number
  worst_trade: number
  profit_factor: number
  max_drawdown: number
  sharpe_ratio?: number
  equity_curve?: { date: string; equity: number }[]
}

// ==================== SETTINGS TYPES ====================
export interface Settings {
  execution_mode: ExecutionMode
  theme: 'dark' | 'light'
  alerts_enabled: boolean
  kill_switch: boolean
  overall_max_profit: number
  overall_max_loss: number
  max_concurrent_trades: number
  auto_square_off?: boolean
  square_off_time?: string
  telegram_configured: boolean
  telegram_chat_id?: string
  telegram_bot_token?: string
}

// ==================== UI TYPES ====================
export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface ToastMessage {
  id: string
  type: ToastType
  message: string
  duration?: number
}

// ==================== API RESPONSE TYPES ====================
export interface ApiResponse<T = any> {
  success: boolean
  data?: T
  message?: string
  error?: string
}

export interface PaginatedResponse<T> {
  data: T[]
  total: number
  page: number
  limit: number
  hasMore: boolean
}
