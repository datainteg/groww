import { create } from 'zustand'
import { authApi } from '../api'
import type { User } from '../types'

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null

  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, name?: string) => Promise<void>
  logout: () => Promise<void>
  fetchUser: () => Promise<void>
  updateProfile: (data: Partial<User>) => Promise<void>
  updateGrowwCredentials: (apiKey: string, apiSecret: string) => Promise<void>
  clearError: () => void
  initialize: () => void
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  initialize: () => {
    const token = localStorage.getItem('access_token')
    const userStr = localStorage.getItem('user')
    if (token && userStr) {
      try {
        const user = JSON.parse(userStr)
        set({ user, isAuthenticated: true })
      } catch {
        localStorage.removeItem('access_token')
        localStorage.removeItem('user')
      }
    }
  },

  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null })
    try {
      const response = await authApi.login(email, password)
      localStorage.setItem('access_token', response.access_token)
      localStorage.setItem('user', JSON.stringify(response.user))
      set({ user: response.user, isAuthenticated: true, isLoading: false })
    } catch (err: any) {
      set({ isLoading: false, error: err.error || 'Login failed' })
      throw err
    }
  },

  register: async (email: string, password: string, name?: string) => {
    set({ isLoading: true, error: null })
    try {
      const response = await authApi.register(email, password, name)
      localStorage.setItem('access_token', response.access_token)
      localStorage.setItem('user', JSON.stringify(response.user))
      set({ user: response.user, isAuthenticated: true, isLoading: false })
    } catch (err: any) {
      set({ isLoading: false, error: err.error || 'Registration failed' })
      throw err
    }
  },

  logout: async () => {
    try {
      await authApi.logout()
    } catch {
      // Ignore errors
    }
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
    set({ user: null, isAuthenticated: false })
  },

  fetchUser: async () => {
    try {
      const user = await authApi.getMe()
      localStorage.setItem('user', JSON.stringify(user))
      set({ user, isAuthenticated: true })
    } catch {
      set({ user: null, isAuthenticated: false })
    }
  },

  updateProfile: async (data: Partial<User>) => {
    set({ isLoading: true })
    try {
      const response = await authApi.updateProfile(data)
      const updatedUser = { ...get().user, ...response.profile } as User
      localStorage.setItem('user', JSON.stringify(updatedUser))
      set({ user: updatedUser, isLoading: false })
    } catch (err: any) {
      set({ isLoading: false, error: err.error })
      throw err
    }
  },

  updateGrowwCredentials: async (apiKey: string, apiSecret: string) => {
    set({ isLoading: true })
    try {
      const response = await authApi.updateGrowwCredentials(apiKey, apiSecret)
      const updatedUser = { ...get().user, broker_connected: response.broker_connected } as User
      localStorage.setItem('user', JSON.stringify(updatedUser))
      set({ user: updatedUser, isLoading: false })
    } catch (err: any) {
      set({ isLoading: false, error: err.error })
      throw err
    }
  },

  clearError: () => set({ error: null }),
}))
