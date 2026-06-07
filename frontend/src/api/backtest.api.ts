import api from './axios'
import type {
  BacktestConfig, BacktestRun, BacktestTrade, BacktestEquity, CalibrationStatus,
} from '../types'

export const backtestApi = {
  createRun: async (cfg: BacktestConfig): Promise<{ run_id: string; status: string; summary?: any; error?: string }> => {
    const res = await api.post('/backtest/runs', cfg)
    return res.data
  },

  listRuns: async (limit = 50): Promise<BacktestRun[]> => {
    const res = await api.get(`/backtest/runs?limit=${limit}`)
    return res.data.runs || []
  },

  getRun: async (runId: string): Promise<BacktestRun> => {
    const res = await api.get(`/backtest/runs/${runId}`)
    return res.data
  },

  getTrades: async (runId: string, skip = 0, limit = 200): Promise<{ trades: BacktestTrade[]; total: number }> => {
    const res = await api.get(`/backtest/runs/${runId}/trades?skip=${skip}&limit=${limit}`)
    return res.data
  },

  getEquity: async (runId: string): Promise<BacktestEquity> => {
    const res = await api.get(`/backtest/runs/${runId}/equity`)
    return res.data
  },

  getReport: async (runId: string): Promise<{ run: BacktestRun; report: any }> => {
    const res = await api.get(`/backtest/runs/${runId}/report`)
    return res.data
  },

  cancelRun: async (runId: string): Promise<any> => {
    const res = await api.post(`/backtest/runs/${runId}/cancel`)
    return res.data
  },

  walkForward: async (cfg: any): Promise<any> => {
    const res = await api.post('/backtest/walk-forward', cfg)
    return res.data
  },

  compareRuns: async (runIds: string[]): Promise<{ runs: any[] }> => {
    const res = await api.post('/backtest/compare', { run_ids: runIds })
    return res.data
  },

  calibrate: async (minSamples = 50): Promise<any> => {
    const res = await api.post('/backtest/calibrate', { min_samples: minSamples })
    return res.data
  },

  calibrationStatus: async (): Promise<CalibrationStatus> => {
    const res = await api.get('/backtest/calibration/status')
    return res.data
  },
}
