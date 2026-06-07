import { create } from 'zustand'
import { marketApi, instrumentsApi } from '../api'
import type { MarketStatus, IndexData, Instrument } from '../types'

interface MarketState {
  marketStatus: MarketStatus | null
  indices: IndexData[]
  instruments: Instrument[]
  expiries: Record<string, string[]>
  syncInfo: { total: number; by_underlying: Record<string, number> } | null
  isLoading: boolean
  error: string | null

  fetchMarketStatus: () => Promise<void>
  fetchIndices: () => Promise<void>
  fetchInstruments: (underlying?: string, expiry?: string, optionType?: string) => Promise<void>
  fetchExpiries: (underlying: string) => Promise<void>
  syncInstruments: () => Promise<void>
  fetchSyncInfo: () => Promise<void>
  getLtp: (symbol: string) => Promise<number>
}

export const useMarketStore = create<MarketState>((set, get) => ({
  marketStatus: null,
  indices: [],
  instruments: [],
  expiries: {},
  syncInfo: null,
  isLoading: false,
  error: null,

  fetchMarketStatus: async () => {
    try {
      const marketStatus = await marketApi.getStatus()
      set({ marketStatus })
    } catch (err: any) {
      console.error('Market status error:', err)
    }
  },

  fetchIndices: async () => {
    try {
      const indices = await marketApi.getIndices()
      set({ indices: Array.isArray(indices) ? indices : [] })
    } catch (err: any) {
      console.error('Indices error:', err)
      set({ indices: [] })
    }
  },

  fetchInstruments: async (underlying?: string, expiry?: string, optionType?: string) => {
    set({ isLoading: true })
    try {
      const instruments = await instrumentsApi.getInstruments(underlying, expiry, optionType)
      set({ instruments, isLoading: false })
    } catch (err: any) {
      set({ isLoading: false, error: err.error })
    }
  },

  fetchExpiries: async (underlying: string) => {
    try {
      const response = await instrumentsApi.getExpiries(underlying)
      set(state => ({
        expiries: { ...state.expiries, [underlying]: Array.isArray(response) ? response : [] }
      }))
    } catch (err: any) {
      console.error('Expiries error:', err)
    }
  },

  syncInstruments: async () => {
    set({ isLoading: true })
    try {
      await instrumentsApi.syncInstruments()
      await get().fetchSyncInfo()
      set({ isLoading: false })
    } catch (err: any) {
      set({ isLoading: false, error: err.error })
      throw err
    }
  },

  fetchSyncInfo: async () => {
    try {
      const syncInfo = await instrumentsApi.getCount()
      set({ syncInfo })
    } catch (err: any) {
      console.error('Sync info error:', err)
    }
  },

  getLtp: async (symbol: string): Promise<number> => {
    try {
      const response = await marketApi.getLtp(symbol)
      return response.ltp || 0
    } catch {
      return 0
    }
  },
}))
