import { useEffect, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore, useUIStore } from './store'
import Layout from './components/layout/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Strategy from './pages/Strategy'
import Trades from './pages/Trades'
import Signals from './pages/Signals'
import SafetyCenter from './pages/SafetyCenter'
import Settings from './pages/Settings'
import Profile from './pages/Profile'
import NotFound from './pages/NotFound'

// Heavy chart pages are code-split (pull in lightweight-charts on demand).
const Charts = lazy(() => import('./pages/Charts'))
const Backtest = lazy(() => import('./pages/Backtest'))

// Fallback while a lazy (code-split) page loads.
function PageFallback() {
  return (
    <div className="space-y-3">
      <div className="h-8 w-48 rounded-lg bg-gray-100 dark:bg-dark-800 animate-pulse" />
      <div className="h-64 rounded-xl bg-gray-100 dark:bg-dark-800 animate-pulse" />
    </div>
  )
}

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
          <Route path="/charts" element={<Suspense fallback={<PageFallback />}><Charts /></Suspense>} />
          <Route path="/signals" element={<Signals />} />
          <Route path="/backtest" element={<Suspense fallback={<PageFallback />}><Backtest /></Suspense>} />
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