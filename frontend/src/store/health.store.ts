import { create } from 'zustand'
import { healthApi } from '../api'

interface HealthState {
  health: any | null
  reconciliation: any | null
  isLoading: boolean
  fetchHealth: () => Promise<void>
}

export const useHealthStore = create<HealthState>((set) => ({
  health: null,
  reconciliation: null,
  isLoading: false,

  fetchHealth: async () => {
    set({ isLoading: true })
    // Health is public; reconciliation needs auth and may be empty — never let
    // one failing call blank the other.
    const [h, r] = await Promise.allSettled([healthApi.getHealth(), healthApi.getReconciliation()])
    set({
      health: h.status === 'fulfilled' ? h.value : null,
      reconciliation: r.status === 'fulfilled' ? r.value : null,
      isLoading: false,
    })
  },
}))
