import api from './axios'
import type { Strategy, StrategyFormData, EngineStatus, Decision, Candle } from '../types'

export const strategyApi = {
  // Create new strategy
  create: async (data: StrategyFormData): Promise<{ message: string; strategy_id: string; strategy: Strategy }> => {
    const response = await api.post('/strategy/create', data)
    return response.data
  },

  // List all strategies
  list: async (): Promise<Strategy[]> => {
    const response = await api.get<Strategy[]>('/strategy/list')
    return response.data
  },

  // Get single strategy
  get: async (id: string): Promise<Strategy> => {
    const response = await api.get<Strategy>(`/strategy/${id}`)
    return response.data
  },

  // Update strategy
  update: async (id: string, data: Partial<StrategyFormData>): Promise<{ message: string; strategy: Strategy }> => {
    const response = await api.put(`/strategy/${id}`, data)
    return response.data
  },

  // Delete strategy
  delete: async (id: string): Promise<{ message: string }> => {
    const response = await api.delete(`/strategy/${id}`)
    return response.data
  },

  // Start strategy
  start: async (id: string): Promise<{ message: string; strategy_id: string; is_active: boolean }> => {
    const response = await api.post(`/strategy/${id}/start`)
    return response.data
  },

  // Stop strategy
  stop: async (id: string, reason?: string): Promise<{ message: string; strategy_id: string; is_active: boolean }> => {
    const response = await api.post(`/strategy/${id}/stop`, { reason })
    return response.data
  },

  // Stop all strategies
  stopAll: async (): Promise<{ message: string; stopped_count: number }> => {
    const response = await api.post('/strategy/stop-all')
    return response.data
  },

  // Get engine status
  getStatus: async (): Promise<EngineStatus> => {
    const response = await api.get<EngineStatus>('/strategy/status')
    return response.data
  },

  // Get AI decision/signal (67 indicators)
  getDecision: async (symbol: string = 'NIFTY', interval: number = 5): Promise<Decision> => {
    const response = await api.get<Decision>('/strategy/decision', { params: { symbol, interval } })
    return response.data
  },

  // Analyze specific strategy
  analyzeStrategy: async (id: string): Promise<Decision> => {
    const response = await api.get<Decision>(`/strategy/${id}/analyze`)
    return response.data
  },

  // Get candles for charting
  getCandles: async (symbol: string, interval: string = '5', limit: number = 100): Promise<{ symbol: string; interval: string; candles: Candle[]; count: number }> => {
    const response = await api.get(`/strategy/candles/${symbol}`, { params: { interval, limit } })
    return response.data
  },

  // Sync candles from broker
  syncCandles: async (symbol: string, interval: string = '5'): Promise<{ message: string; symbol: string; count: number }> => {
    const response = await api.post(`/strategy/candles/${symbol}/sync`, null, { params: { interval } })
    return response.data
  },

  // Get technical indicators
  getIndicators: async (symbol: string): Promise<any> => {
    const response = await api.get(`/strategy/indicators/${symbol}`)
    return response.data
  },
}
