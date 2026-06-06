import api from './axios'
import type { AuthResponse, User, Settings } from '../types'

export const authApi = {
  register: async (email: string, password: string, name?: string): Promise<AuthResponse> => {
    const response = await api.post<AuthResponse>('/auth/register', { email, password, name })
    return response.data
  },

  login: async (email: string, password: string): Promise<AuthResponse> => {
    const response = await api.post<AuthResponse>('/auth/login', { email, password })
    return response.data
  },

  logout: async (): Promise<{ message: string }> => {
    const response = await api.post('/auth/logout')
    return response.data
  },

  getMe: async (): Promise<User> => {
    const response = await api.get<User>('/auth/me')
    return response.data
  },

  getProfile: async (): Promise<User> => {
    const response = await api.get<User>('/auth/profile')
    return response.data
  },

  updateProfile: async (data: Partial<User>): Promise<{ message: string; profile: User }> => {
    const response = await api.put('/auth/profile', data)
    return response.data
  },

  updateGrowwCredentials: async (apiKey: string, apiSecret: string): Promise<{ message: string; broker_connected: boolean }> => {
    const response = await api.post('/auth/update-groww-credentials', {
      groww_api_key: apiKey,
      groww_api_secret: apiSecret,
    })
    return response.data
  },

  refreshToken: async (): Promise<{ access_token: string }> => {
    const response = await api.post('/auth/refresh-token')
    return response.data
  },
}
