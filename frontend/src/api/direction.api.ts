/**
 * Direction API - Market Direction Engine endpoints
 */
import axios from './axios'
import type { MarketDirection, AllDirectionsResponse } from '../types'

export const directionApi = {
  /**
   * Get market direction for all indices
   */
  getAll: async (): Promise<AllDirectionsResponse> => {
    const { data } = await axios.get('/market/direction')
    return data
  },

  /**
   * Get market direction for a specific symbol
   */
  getBySymbol: async (symbol: string, forceRefresh: boolean = false): Promise<MarketDirection> => {
    const { data } = await axios.get(`/market/direction/${symbol}`, {
      params: { force_refresh: forceRefresh }
    })
    return data
  },

  /**
   * Get direction scheduler status
   */
  getSchedulerStatus: async (): Promise<{
    running: boolean
    last_updates: Record<string, string>
    cached_symbols: string[]
  }> => {
    const { data } = await axios.get('/market/direction/scheduler/status')
    return data
  },

  /**
   * Start direction scheduler
   */
  startScheduler: async (): Promise<{ message: string; status: any }> => {
    const { data } = await axios.post('/market/direction/scheduler/start')
    return data
  },

  /**
   * Stop direction scheduler
   */
  stopScheduler: async (): Promise<{ message: string }> => {
    const { data } = await axios.post('/market/direction/scheduler/stop')
    return data
  }
}
