import { create } from 'zustand'
import { backtestApi } from '../api'
import type { BacktestConfig, BacktestRun, BacktestTrade, BacktestEquity } from '../types'

export type BacktestTab = 'run' | 'results' | 'runs' | 'compare' | 'walkforward' | 'calibration'

interface BacktestState {
  runs: BacktestRun[]
  selectedRun: BacktestRun | null
  trades: BacktestTrade[]
  equity: BacktestEquity | null
  report: any | null
  activeTab: BacktestTab
  isRunning: boolean
  isLoading: boolean
  error: string | null

  setTab: (t: BacktestTab) => void
  clearError: () => void
  fetchRuns: () => Promise<void>
  runBacktest: (cfg: BacktestConfig) => Promise<string | null>
  selectRun: (runId: string) => Promise<void>
}

export const useBacktestStore = create<BacktestState>((set, get) => ({
  runs: [],
  selectedRun: null,
  trades: [],
  equity: null,
  report: null,
  activeTab: 'run',
  isRunning: false,
  isLoading: false,
  error: null,

  setTab: (t) => set({ activeTab: t }),
  clearError: () => set({ error: null }),

  fetchRuns: async () => {
    set({ isLoading: true })
    try {
      const runs = await backtestApi.listRuns()
      set({ runs, isLoading: false })
    } catch (err: any) {
      set({ isLoading: false, error: err.response?.data?.error || err.message })
    }
  },

  runBacktest: async (cfg) => {
    set({ isRunning: true, error: null })
    try {
      const res = await backtestApi.createRun(cfg)
      set({ isRunning: false })
      get().fetchRuns()
      if (res.status === 'COMPLETED' && res.run_id) {
        await get().selectRun(res.run_id)
        set({ activeTab: 'results' })
        return res.run_id
      }
      set({ error: res.error || 'Backtest failed' })
      return null
    } catch (err: any) {
      set({ isRunning: false, error: err.response?.data?.error || err.message })
      return null
    }
  },

  selectRun: async (runId) => {
    set({ isLoading: true, error: null })
    try {
      const [report, equity, trades] = await Promise.all([
        backtestApi.getReport(runId),
        backtestApi.getEquity(runId),
        backtestApi.getTrades(runId),
      ])
      set({
        selectedRun: report.run,
        report: report.report,
        equity,
        trades: trades.trades || [],
        isLoading: false,
      })
    } catch (err: any) {
      set({ isLoading: false, error: err.response?.data?.error || err.message })
    }
  },
}))
