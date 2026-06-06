import api from './axios'
import type { Trade, Position, Order, DailyPnl, TradeStatistics } from '../types'

export const tradeApi = {
  // Place manual order
  placeOrder: async (data: {
    trading_symbol: string
    quantity: number
    transaction_type: 'BUY' | 'SELL'
    order_type: 'MARKET' | 'LIMIT' | 'SL' | 'SL-M'
    product?: 'MIS' | 'NRML'
    price?: number
    trigger_price?: number
    stop_loss?: number
    target?: number
  }): Promise<{ success: boolean; trade_id: string; order_id: string; entry_price: number }> => {
    const response = await api.post('/trade/place-order', data)
    return response.data
  },

  // Execute strategy trade instantly (ATM strike auto-resolved)
  executeStrategy: async (data: {
    strategy_id: string
    option_type: 'CE' | 'PE'
  }): Promise<{ success: boolean; message: string; trade_id: string; option_type: string }> => {
    const response = await api.post('/trade/execute-strategy', data)
    return response.data
  },

  // Quick trade with strategy context (manual order using strategy rules)
  quickTrade: async (data: {
    strategy_id: string
    option_type: 'CE' | 'PE'
    transaction_type: 'BUY' | 'SELL'
    quantity?: number
  }): Promise<{ 
    success: boolean
    message: string
    trade_id: string
    order_id: string
    trading_symbol: string
    entry_price: number
    quantity: number
  }> => {
    const response = await api.post('/trade/quick-trade', data)
    return response.data
  },

  // Get all orders
  getOrders: async (segment: string = 'FNO'): Promise<{ success: boolean; data: Order[] }> => {
    const response = await api.get('/trade/orders', { params: { segment } })
    return response.data
  },

  // Get order status
  getOrderStatus: async (orderId: string): Promise<{ success: boolean; data: Order }> => {
    const response = await api.get(`/trade/order/${orderId}`)
    return response.data
  },

  // Get positions
  getPositions: async (): Promise<{ positions: Position[] }> => {
    const response = await api.get('/trade/positions')
    return response.data
  },

  // Get trade history
  getTrades: async (limit: number = 50): Promise<Trade[]> => {
    const response = await api.get('/trade/trades', { params: { limit } })
    return response.data
  },

  // Get active/open trades
  getActiveTrades: async (): Promise<Trade[]> => {
    const response = await api.get('/trade/active-trades')
    return response.data
  },

  // Get single trade
  getTrade: async (tradeId: string): Promise<Trade> => {
    const response = await api.get<Trade>(`/trade/${tradeId}`)
    return response.data
  },

  // Exit single trade
  exitTrade: async (tradeId: string): Promise<{ success: boolean; message: string; pnl: number; exit_price?: number }> => {
    const response = await api.post(`/trade/${tradeId}/exit`)
    return response.data
  },

  // Modify open trade (SL/Target)
  modifyTrade: async (tradeId: string, data: {
    stop_loss?: number
    target?: number
    trailing_sl_enabled?: boolean
    trailing_sl_value?: number
  }): Promise<{ success: boolean; message: string; trade: Trade }> => {
    const response = await api.put(`/trade/${tradeId}/modify`, data)
    return response.data
  },

  // Exit all trades
  exitAll: async (): Promise<{ success: boolean; exited_count: number; total_pnl: number; errors?: string[] }> => {
    const response = await api.post('/trade/exit-all')
    return response.data
  },

  // Get daily P&L
  getDailyPnl: async (): Promise<DailyPnl> => {
    const response = await api.get<DailyPnl>('/trade/daily-pnl')
    return response.data
  },

  // Get margin/limits
  getLimits: async (): Promise<{
    available_balance: number
    used_margin: number
    total_balance?: number
    equity?: number
  }> => {
    const response = await api.get('/trade/limits')
    return response.data
  },

  // Get trading statistics
  getStatistics: async (days: number = 30): Promise<TradeStatistics> => {
    const response = await api.get<TradeStatistics>('/trade/statistics', { params: { days } })
    return response.data
  },

  // Reset paper account
  resetPaperAccount: async (): Promise<{ success: boolean; message: string }> => {
    const response = await api.post('/trade/paper/reset')
    return response.data
  },

  // Get trade journal
  getJournal: async (limit: number = 50): Promise<any[]> => {
    const response = await api.get('/trade/journal', { params: { limit } })
    return response.data
  },

  // Add journal entry
  addJournalEntry: async (tradeId: string, data: {
    notes: string
    tags?: string[]
    rating?: number
    lessons?: string
  }): Promise<{ message: string; entry_id: string }> => {
    const response = await api.post(`/trade/journal/${tradeId}`, data)
    return response.data
  },
}
