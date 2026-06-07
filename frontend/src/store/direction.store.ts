/**
 * Direction Store - Market Direction Engine state management
 */
import { create } from 'zustand'
import { directionApi } from '../api'
import type { MarketDirection } from '../types'

interface DirectionState {
  // Data
  directions: Record<string, MarketDirection>
  selectedSymbol: string
  
  // Status
  isLoading: boolean
  error: string | null
  lastUpdate: string | null
  schedulerRunning: boolean
  
  // Actions
  // FIX: Added isBackground param to prevent UI flashing during polling
  fetchAllDirections: (isBackground?: boolean) => Promise<void>
  // Force a fresh recompute for all indices (used by real-time polling) — same as
  // clicking a card, but silent (no spinner flash).
  refreshAllForce: (silent?: boolean) => Promise<void>
  fetchDirection: (symbol: string, forceRefresh?: boolean) => Promise<MarketDirection | null>
  setSelectedSymbol: (symbol: string) => void
  getDirection: (symbol: string) => MarketDirection | null
  
  // Scheduler
  fetchSchedulerStatus: () => Promise<void>
  startScheduler: () => Promise<void>
  stopScheduler: () => Promise<void>
  
  // Helpers
  clearError: () => void
}

export const useDirectionStore = create<DirectionState>((set, get) => ({
  // Initial state
  directions: {},
  selectedSymbol: 'NIFTY',
  isLoading: false,
  error: null,
  lastUpdate: null,
  schedulerRunning: false,

  // FIX: Handle silent background refreshes
  fetchAllDirections: async (isBackground = false) => {
    // Only show loading state if NOT in background mode
    if (!isBackground) {
      set({ isLoading: true, error: null })
    }

    try {
      const response = await directionApi.getAll()
      set({
        directions: response.directions || {},
        lastUpdate: response.timestamp,
        isLoading: false
      })
    } catch (err: any) {
      set({
        isLoading: false,
        error: err.response?.data?.error || err.message || 'Failed to fetch directions'
      })
    }
  },

  refreshAllForce: async (silent = true) => {
    if (!silent) set({ isLoading: true, error: null })
    const syms = ['NIFTY', 'BANKNIFTY', 'SENSEX']
    try {
      const results = await Promise.allSettled(syms.map((s) => directionApi.getBySymbol(s, true)))
      const merged: Record<string, MarketDirection> = { ...get().directions }
      let ts = get().lastUpdate
      results.forEach((r, i) => {
        if (r.status === 'fulfilled') { merged[syms[i]] = r.value; ts = r.value.timestamp }
      })
      set({ directions: merged, lastUpdate: ts, isLoading: false })
    } catch {
      set({ isLoading: false })
    }
  },

  fetchDirection: async (symbol: string, forceRefresh = false): Promise<MarketDirection | null> => {
    // Single fetch usually triggered by user action, so we show loading
    set({ isLoading: true, error: null })
    try {
      const direction = await directionApi.getBySymbol(symbol, forceRefresh)
      set(state => ({
        directions: {
          ...state.directions,
          [symbol]: direction
        },
        lastUpdate: direction.timestamp,
        isLoading: false
      }))
      return direction
    } catch (err: any) {
      set({
        isLoading: false,
        error: err.response?.data?.error || err.message || 'Failed to fetch direction'
      })
      return null
    }
  },

  setSelectedSymbol: (symbol: string) => {
    set({ selectedSymbol: symbol })
  },

  getDirection: (symbol: string): MarketDirection | null => {
    return get().directions[symbol] || null
  },

  fetchSchedulerStatus: async () => {
    try {
      const status = await directionApi.getSchedulerStatus()
      set({ schedulerRunning: status.running })
    } catch (err) {
      console.error('Failed to fetch scheduler status:', err)
    }
  },

  startScheduler: async () => {
    try {
      await directionApi.startScheduler()
      set({ schedulerRunning: true })
    } catch (err: any) {
      set({ error: err.response?.data?.error || 'Failed to start scheduler' })
    }
  },

  stopScheduler: async () => {
    try {
      await directionApi.stopScheduler()
      set({ schedulerRunning: false })
    } catch (err: any) {
      set({ error: err.response?.data?.error || 'Failed to stop scheduler' })
    }
  },

  clearError: () => set({ error: null })
}))