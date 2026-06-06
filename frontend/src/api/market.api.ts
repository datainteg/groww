import api from './axios'
import type { MarketStatus, IndexData, Quote, Instrument } from '../types'

const unwrapArray = <T>(res: any): T[] => {
  if (Array.isArray(res)) return res
  if (Array.isArray(res?.data)) return res.data
  if (Array.isArray(res?.results)) return res.results
  return []
}

const unwrapObject = <T>(res: any): T => {
  return res?.data ?? res
}

export const marketApi = {
  getStatus: async (): Promise<MarketStatus> => {
    const res = await api.get('/market/status')
    return unwrapObject(res.data)
  },

  getIndices: async (): Promise<IndexData[]> => {
    const res = await api.get('/market/indices')
    return unwrapArray(res.data)
  },

  getATMOptions: async (
    underlying: string,
    expiry: string
  ): Promise<{ atm_strike: number; spot_price: number; strikes: number[] }> => {
    const res = await api.get(`/market/atm/${underlying}/${expiry}`)
    const data = unwrapObject<any>(res.data)
    return {
      atm_strike: data?.atm_strike || 0,
      spot_price: data?.spot_price || 0,
      strikes: unwrapArray(data?.strikes),
    }
  }
}

export const instrumentsApi = {
  getInstruments: async (
    underlying?: string,
    expiry?: string,
    optionType?: string
  ): Promise<Instrument[]> => {
    const res = await api.get('/instruments/search', {
      params: { 
        underlying, 
        expiry, 
        q: optionType, 
        limit: 200 
      },
    })
    return unwrapArray(res.data)
  },

  // FIX: Mapped total_instruments to total
  syncInstruments: async (): Promise<{ success: boolean; total: number }> => {
    const res = await api.post('/instruments/sync')
    const data = unwrapObject<any>(res.data)
    return {
      success: data?.success,
      total: data?.total_instruments || data?.total || 0
    }
  },

  getIndexInfo: async (index: string): Promise<{ lot_size: number; expiry: string }> => {
    const res = await api.get(`/instruments/info/${index}`)
    return unwrapObject(res.data)
  },

  getExpiries: async (underlying: string): Promise<string[]> => {
    const res = await api.get(`/instruments/expiries/${underlying}`)
    const data = unwrapObject<any>(res.data)
    return Array.isArray(data) ? data : (data?.expiries || [])
  }
}