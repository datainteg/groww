import api from './axios'
import type { Settings } from '../types'

export const settingsApi = {
  // Get all settings
  get: async (): Promise<Settings> => {
    const response = await api.get<Settings>('/settings/')
    return response.data
  },

  // Update settings
  update: async (data: Partial<Settings>): Promise<{ message: string; settings: Settings }> => {
    const response = await api.put('/settings/', data)
    return response.data
  },

  // Toggle kill switch
  toggleKillSwitch: async (enabled: boolean): Promise<{ message: string; kill_switch: boolean; strategies_stopped?: number }> => {
    const response = await api.post('/settings/kill-switch', { enabled })
    return response.data
  },

  // Set execution mode
  setExecutionMode: async (mode: 'PAPER' | 'LIVE'): Promise<{ message: string; execution_mode: string; warning?: string }> => {
    const response = await api.put('/settings/mode', { mode })
    return response.data
  },

  // Configure Telegram
  configureTelegram: async (botToken: string, chatId: string): Promise<{ message: string; telegram_configured: boolean }> => {
    const response = await api.post('/settings/telegram', { bot_token: botToken, chat_id: chatId })
    return response.data
  },

  // Test Telegram (Connection Check)
  testTelegram: async (): Promise<{ success: boolean; message: string }> => {
    const response = await api.post('/settings/telegram/test')
    return response.data
  },

  // Send Custom Message (New)
  sendMessage: async (message: string): Promise<{ success: boolean; message: string }> => {
    const response = await api.post('/settings/telegram/send', { message })
    return response.data
  },

  // Disconnect Telegram
  disconnectTelegram: async (): Promise<{ message: string; telegram_configured: boolean }> => {
    const response = await api.delete('/settings/telegram')
    return response.data
  },

  // Reset daily counters
  resetDaily: async (): Promise<{ message: string; strategies_reset: number }> => {
    const response = await api.post('/settings/reset-daily')
    return response.data
  },

  // Update theme
  updateTheme: async (theme: 'dark' | 'light'): Promise<{ message: string; theme: string }> => {
    const response = await api.put('/settings/theme', { theme })
    return response.data
  },
}