import { create } from 'zustand'
import { settingsApi } from '../api'
import type { Settings, ToastMessage, ToastType } from '../types'
import { generateId } from '../utils'

interface UIState {
  settings: Settings | null
  theme: 'dark' | 'light'
  sidebarOpen: boolean
  toasts: ToastMessage[]
  isLoading: boolean

  // Settings
  fetchSettings: () => Promise<void>
  updateSettings: (data: Partial<Settings>) => Promise<void>
  toggleKillSwitch: (enabled: boolean) => Promise<void>
  setExecutionMode: (mode: 'PAPER' | 'LIVE') => Promise<void>

  // UI
  setTheme: (theme: 'dark' | 'light') => void
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void

  // Toasts
  addToast: (type: ToastType, message: string, duration?: number) => void
  removeToast: (id: string) => void
  clearToasts: () => void
}

export const useUIStore = create<UIState>((set, get) => ({
  settings: null,
  theme: 'light',
  // Mobile-first: drawer starts closed. On desktop the sidebar is always shown
  // via `lg:translate-x-0`, so this only controls the mobile drawer.
  sidebarOpen: false,
  toasts: [],
  isLoading: false,

  fetchSettings: async () => {
    try {
      const settings = await settingsApi.get()
      set({ settings, theme: settings.theme || 'light' })
    } catch (err: any) {
      console.error('Settings error:', err)
    }
  },

  updateSettings: async (data: Partial<Settings>) => {
    set({ isLoading: true })
    try {
      const response = await settingsApi.update(data)
      set({ settings: response.settings, isLoading: false })
    } catch (err: any) {
      set({ isLoading: false })
      throw err
    }
  },

  toggleKillSwitch: async (enabled: boolean) => {
    try {
      const response = await settingsApi.toggleKillSwitch(enabled)
      set(state => ({
        settings: state.settings ? { ...state.settings, kill_switch: response.kill_switch } : null
      }))
      get().addToast(
        enabled ? 'warning' : 'success',
        enabled ? 'Kill switch activated - All trading halted' : 'Kill switch deactivated'
      )
    } catch (err: any) {
      get().addToast('error', err.error || 'Failed to toggle kill switch')
      throw err
    }
  },

  setExecutionMode: async (mode: 'PAPER' | 'LIVE') => {
    try {
      await settingsApi.setExecutionMode(mode)
      set(state => ({
        settings: state.settings ? { ...state.settings, execution_mode: mode } : null
      }))
      get().addToast(
        mode === 'LIVE' ? 'warning' : 'info',
        mode === 'LIVE' ? '⚠️ LIVE mode activated - Real money at risk!' : 'Paper mode activated'
      )
    } catch (err: any) {
      get().addToast('error', err.error || 'Failed to change mode')
      throw err
    }
  },

  setTheme: (theme: 'dark' | 'light') => {
    set({ theme })
    // Update on settings in backend
    settingsApi.updateTheme(theme).catch(console.error)
    localStorage.setItem('theme', theme)
  },

  toggleSidebar: () => set(state => ({ sidebarOpen: !state.sidebarOpen })),
  setSidebarOpen: (open: boolean) => set({ sidebarOpen: open }),

  addToast: (type: ToastType, message: string, duration = 4000) => {
    const id = generateId()
    const toast: ToastMessage = { id, type, message, duration }
    
    set(state => ({ toasts: [...state.toasts, toast] }))
    
    if (duration > 0) {
      setTimeout(() => get().removeToast(id), duration)
    }
  },

  removeToast: (id: string) => {
    set(state => ({ toasts: state.toasts.filter(t => t.id !== id) }))
  },

  clearToasts: () => set({ toasts: [] }),
}))
