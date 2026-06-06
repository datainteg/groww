import { create } from 'zustand'
import { tradeApi } from '../api'
import type { Trade, Position, DailyPnl, TradeStatistics } from '../types'

interface TradeState {
  trades: Trade[]
  activeTrades: Trade[]
  positions: Position[]
  dailyPnl: DailyPnl | null
  statistics: TradeStatistics | null
  limits: {
    available_balance: number
    used_margin: number
    total_balance?: number
    equity?: number
  } | null
  isLoading: boolean
  error: string | null

  fetchTrades: (limit?: number) => Promise<void>
  fetchActiveTrades: () => Promise<void>
  fetchPositions: () => Promise<void>
  fetchDailyPnl: () => Promise<void>
  fetchStatistics: (days?: number) => Promise<void>
  fetchLimits: () => Promise<void>
  placeOrder: (data: any) => Promise<any>
  executeStrategy: (strategyId: string, optionType: 'CE' | 'PE') => Promise<any>
  quickTrade: (strategyId: string, optionType: 'CE' | 'PE', transactionType: 'BUY' | 'SELL', quantity?: number) => Promise<any>
  exitTrade: (tradeId: string) => Promise<void>
  modifyTrade: (tradeId: string, data: { stop_loss?: number; target?: number; trailing_sl_enabled?: boolean; trailing_sl_value?: number }) => Promise<void>
  exitAllTrades: () => Promise<void>
  resetPaperAccount: () => Promise<void>
  refresh: () => Promise<void>
  clearError: () => void
}

export const useTradeStore = create<TradeState>((set, get) => ({
  trades: [],
  activeTrades: [],
  positions: [],
  dailyPnl: null,
  statistics: null,
  limits: null,
  isLoading: false,
  error: null,

  fetchTrades: async (limit = 50) => {
    set({ isLoading: true })
    try {
      const response = await tradeApi.getTrades(limit)
      // Handle both array response and wrapped response
      const trades = Array.isArray(response) ? response : (response as any).trades || []
      set({ trades, isLoading: false })
    } catch (err: any) {
      set({ isLoading: false, error: err.error })
    }
  },

  fetchActiveTrades: async () => {
    try {
      const response = await tradeApi.getActiveTrades()
      // Handle both array response and wrapped response
      const activeTrades = Array.isArray(response) ? response : (response as any).trades || []
      set({ activeTrades })
    } catch (err: any) {
      console.error('Active trades error:', err)
    }
  },

  fetchPositions: async () => {
    try {
      const response = await tradeApi.getPositions()
      set({ positions: response.positions || [] })
    } catch (err: any) {
      console.error('Positions error:', err)
    }
  },

  fetchDailyPnl: async () => {
    try {
      const dailyPnl = await tradeApi.getDailyPnl()
      set({ dailyPnl })
    } catch (err: any) {
      console.error('Daily PnL error:', err)
    }
  },

  fetchStatistics: async (days = 30) => {
    try {
      const statistics = await tradeApi.getStatistics(days)
      set({ statistics })
    } catch (err: any) {
      console.error('Statistics error:', err)
    }
  },

  fetchLimits: async () => {
    try {
      const limits = await tradeApi.getLimits()
      set({ limits })
    } catch (err: any) {
      console.error('Limits error:', err)
    }
  },

  placeOrder: async (data: any) => {
    set({ isLoading: true })
    try {
      const result = await tradeApi.placeOrder(data)
      await get().refresh()
      set({ isLoading: false })
      return result
    } catch (err: any) {
      set({ isLoading: false, error: err.error })
      throw err
    }
  },

  executeStrategy: async (strategyId: string, optionType: 'CE' | 'PE') => {
    set({ isLoading: true })
    try {
      const result = await tradeApi.executeStrategy({ strategy_id: strategyId, option_type: optionType })
      await get().refresh()
      set({ isLoading: false })
      return result
    } catch (err: any) {
      set({ isLoading: false, error: err.error || err.response?.data?.error })
      throw err
    }
  },

  quickTrade: async (strategyId: string, optionType: 'CE' | 'PE', transactionType: 'BUY' | 'SELL', quantity?: number) => {
    set({ isLoading: true })
    try {
      const result = await tradeApi.quickTrade({
        strategy_id: strategyId,
        option_type: optionType,
        transaction_type: transactionType,
        quantity
      })
      await get().refresh()
      set({ isLoading: false })
      return result
    } catch (err: any) {
      set({ isLoading: false, error: err.error || err.response?.data?.error })
      throw err
    }
  },

  exitTrade: async (tradeId: string) => {
    try {
      await tradeApi.exitTrade(tradeId)
      await get().refresh()
    } catch (err: any) {
      set({ error: err.response?.data?.error || err.error })
      throw err
    }
  },

  modifyTrade: async (tradeId: string, data: { stop_loss?: number; target?: number; trailing_sl_enabled?: boolean; trailing_sl_value?: number }) => {
    try {
      await tradeApi.modifyTrade(tradeId, data)
      await get().refresh()
    } catch (err: any) {
      set({ error: err.response?.data?.error || err.error })
      throw err
    }
  },

  exitAllTrades: async () => {
    try {
      await tradeApi.exitAll()
      await get().refresh()
    } catch (err: any) {
      set({ error: err.error })
      throw err
    }
  },

  resetPaperAccount: async () => {
    set({ isLoading: true })
    try {
      await tradeApi.resetPaperAccount()
      await get().refresh()
      set({ isLoading: false })
    } catch (err: any) {
      set({ isLoading: false, error: err.error })
      throw err
    }
  },

  refresh: async () => {
    await Promise.all([
      get().fetchActiveTrades(),
      get().fetchPositions(),
      get().fetchDailyPnl(),
      get().fetchLimits()
    ])
  },

  clearError: () => set({ error: null }),
}))
