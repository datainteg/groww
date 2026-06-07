import axios from 'axios'
import { config } from '../config'

const api = axios.create({
  baseURL: config.API_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor - attach the auth token
api.interceptors.request.use(
  (cfg) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      cfg.headers.Authorization = `Bearer ${token}`
    }
    return cfg
  },
  (error) => Promise.reject(error)
)

function forceLogout() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('user')
  if (!window.location.pathname.includes('/login')) {
    window.location.href = '/login'
  }
}

// Shared in-flight refresh so concurrent 401s trigger only ONE refresh call.
let refreshPromise: Promise<string | null> | null = null

function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    const token = localStorage.getItem('access_token')
    refreshPromise = (token
      ? axios
          // Raw axios (not `api`) so a 401 here doesn't re-enter this interceptor.
          .post(`${config.API_URL}/auth/refresh-token`, {}, { headers: { Authorization: `Bearer ${token}` } })
          .then((res) => res.data?.access_token ?? null)
          .catch(() => null)
      : Promise.resolve(null)
    ).finally(() => { refreshPromise = null })
  }
  return refreshPromise
}

// Response interceptor - try ONE token refresh before ejecting to /login.
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config || {}
    const status = error.response?.status
    const url = String(original.url || '')
    const isAuthCall = url.includes('/auth/refresh-token') || url.includes('/auth/login')

    if (status === 401 && !original._retry && !isAuthCall) {
      original._retry = true
      const newToken = await refreshAccessToken()
      if (newToken) {
        localStorage.setItem('access_token', newToken)
        original.headers = original.headers || {}
        original.headers.Authorization = `Bearer ${newToken}`
        return api(original) // replay the original request once
      }
      forceLogout()
    }

    const message =
      error.response?.data?.error ||
      error.response?.data?.message ||
      error.message ||
      'An error occurred'

    return Promise.reject({ error: message, status, data: error.response?.data })
  }
)

export default api
