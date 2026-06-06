import { create } from 'zustand'
import { strategyApi } from '../api'
import type { Strategy, StrategyFormData, EngineStatus, Decision } from '../types'

interface StrategyState {
  strategies: Strategy[]
  engineStatus: EngineStatus | null
  decision: Decision | null
  decisions: Record<string, Decision>  // Store decisions per symbol
  selectedStrategyId: string | null
  isLoading: boolean
  isAnalyzing: boolean
  error: string | null

  fetchStrategies: () => Promise<void>
  fetchEngineStatus: () => Promise<void>
  fetchDecision: (symbol?: string, interval?: number) => Promise<Decision | null>
  analyzeStrategy: (id: string) => Promise<void>
  createStrategy: (data: StrategyFormData) => Promise<string>
  updateStrategy: (id: string, data: Partial<StrategyFormData>) => Promise<void>
  deleteStrategy: (id: string) => Promise<void>
  startStrategy: (id: string) => Promise<void>
  stopStrategy: (id: string, reason?: string) => Promise<void>
  stopAllStrategies: () => Promise<void>
  setSelectedStrategy: (id: string | null) => void
  refresh: () => Promise<void>
  clearError: () => void
}

export const useStrategyStore = create<StrategyState>((set, get) => ({
  strategies: [],
  engineStatus: null,
  decision: null,
  decisions: {},
  selectedStrategyId: null,
  isLoading: false,
  isAnalyzing: false,
  error: null,

  fetchStrategies: async () => {
    set({ isLoading: true, error: null })
    try {
      const response = await strategyApi.list()
      
      // FIX: Robust response handling (Array directly or nested in .strategies/.data)
      let strategies: Strategy[] = []
      if (Array.isArray(response)) {
        strategies = response
      } else if (Array.isArray((response as any).strategies)) {
        strategies = (response as any).strategies
      } else if (Array.isArray((response as any).data)) {
        strategies = (response as any).data
      }

      set({ strategies, isLoading: false })
    } catch (err: any) {
      set({ isLoading: false, error: err.response?.data?.error || err.message })
      console.error('Strategies error:', err)
    }
  },

  fetchEngineStatus: async () => {
    try {
      const result = await strategyApi.getStatus()
      // FIX: Handle wrapped response { status: {...} } vs direct {...}
      const engineStatus = result.status || result
      set({ engineStatus })
    } catch (err: any) {
      console.error('Engine status error:', err)
    }
  },

  fetchDecision: async (symbol = 'NIFTY', interval = 5): Promise<Decision | null> => {
    set({ isAnalyzing: true, error: null })
    try {
      const result = await strategyApi.getDecision(symbol, interval)
      // FIX: Handle wrapped response
      const decision = result.decision || result.data || result

      set(state => ({
        decision,
        decisions: { ...state.decisions, [symbol]: decision },
        isAnalyzing: false
      }))
      return decision
    } catch (err: any) {
      set({ isAnalyzing: false, error: err.response?.data?.error || 'Analysis failed' })
      console.error('Decision error:', err)
      return null
    }
  },

  analyzeStrategy: async (id: string) => {
    set({ isAnalyzing: true, error: null })
    try {
      const result = await strategyApi.analyzeStrategy(id)
      const decision = result.decision || result.data || result
      set({ decision, isAnalyzing: false })
    } catch (err: any) {
      set({ isAnalyzing: false, error: err.response?.data?.error || err.message })
    }
  },

  createStrategy: async (data: StrategyFormData): Promise<string> => {
    set({ isLoading: true, error: null })
    try {
      const result = await strategyApi.create(data)
      await get().fetchStrategies()
      set({ isLoading: false })
      
      // FIX: Handle various ID field names from backend
      return result.strategy_id || result.id || result._id || ''
    } catch (err: any) {
      set({ isLoading: false, error: err.response?.data?.error || err.message })
      throw err
    }
  },

  updateStrategy: async (id: string, data: Partial<StrategyFormData>) => {
    set({ isLoading: true, error: null })
    try {
      await strategyApi.update(id, data)
      await get().fetchStrategies()
      set({ isLoading: false })
    } catch (err: any) {
      set({ isLoading: false, error: err.response?.data?.error || err.message })
      throw err
    }
  },

  deleteStrategy: async (id: string) => {
    set({ isLoading: true, error: null })
    try {
      await strategyApi.delete(id)
      await get().fetchStrategies()
      set({ isLoading: false })
    } catch (err: any) {
      set({ isLoading: false, error: err.response?.data?.error || err.message })
      throw err
    }
  },

  startStrategy: async (id: string) => {
    set({ error: null })
    try {
      await strategyApi.start(id)
      // Refresh both list (for active status) and engine status
      await Promise.all([
        get().fetchStrategies(),
        get().fetchEngineStatus()
      ])
    } catch (err: any) {
      const msg = err.response?.data?.error || err.message
      set({ error: msg })
      throw err
    }
  },

  stopStrategy: async (id: string, reason?: string) => {
    set({ error: null })
    try {
      await strategyApi.stop(id, reason)
      await Promise.all([
        get().fetchStrategies(),
        get().fetchEngineStatus()
      ])
    } catch (err: any) {
      const msg = err.response?.data?.error || err.message
      set({ error: msg })
      throw err
    }
  },

  stopAllStrategies: async () => {
    set({ error: null })
    try {
      await strategyApi.stopAll()
      await Promise.all([
        get().fetchStrategies(),
        get().fetchEngineStatus()
      ])
    } catch (err: any) {
      const msg = err.response?.data?.error || err.message
      set({ error: msg })
      throw err
    }
  },

  setSelectedStrategy: (id: string | null) => set({ selectedStrategyId: id }),

  refresh: async () => {
    await Promise.all([
      get().fetchStrategies(),
      get().fetchEngineStatus()
    ])
  },

  clearError: () => set({ error: null }),
}))