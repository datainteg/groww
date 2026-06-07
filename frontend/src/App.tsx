import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore, useUIStore } from './store'
import Layout from './components/layout/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Strategy from './pages/Strategy'
import Trades from './pages/Trades'
import Charts from './pages/Charts'
import Signals from './pages/Signals'
import Backtest from './pages/Backtest'
import SafetyCenter from './pages/SafetyCenter'
import Settings from './pages/Settings'
import Profile from './pages/Profile'
import NotFound from './pages/NotFound'

// Protected Route wrapper
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  
  return <>{children}</>
}

export default function App() {
  const { initialize } = useAuthStore()
  const { theme } = useUIStore()

  // Initialize Auth
  useEffect(() => {
    initialize()
  }, [])

  // --- THEME SYNC ---
  // This effect listens to the 'theme' store and updates the HTML class
  // ensuring the entire app switches between light/dark modes instantly.
  useEffect(() => {
    const root = window.document.documentElement
    
    // 1. Remove previous classes
    root.classList.remove('light', 'dark')
    
    // 2. Add current theme class
    root.classList.add(theme)
    
    // 3. Persist to LocalStorage (optional if store persists, but safe to keep)
    localStorage.setItem('theme', theme)
  }, [theme])

  return (
    <BrowserRouter>
      <Routes>
        {/* Public Routes */}
        <Route path="/login" element={<Login />} />

        {/* Protected Routes (Wrapped in Layout) */}
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<Dashboard />} />
          <Route path="/strategy" element={<Strategy />} />
          <Route path="/trades" element={<Trades />} />
          <Route path="/charts" element={<Charts />} />
          <Route path="/signals" element={<Signals />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/safety" element={<SafetyCenter />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/profile" element={<Profile />} />
        </Route>

        {/* 404 Not Found */}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  )
}