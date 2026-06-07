import { useEffect, useRef } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import BottomNav from './BottomNav'
import Header from './Header'
import Toast from '../common/Toast'
import { useUIStore, useMarketStore, useStrategyStore, useTradeStore } from '../../store'
import { config } from '../../config'

export default function Layout() {
  const { sidebarOpen, toggleSidebar, setSidebarOpen, fetchSettings } = useUIStore()
  const { fetchMarketStatus, fetchIndices } = useMarketStore()
  const { fetchStrategies, fetchEngineStatus, fetchDecision } = useStrategyStore()
  const { fetchDailyPnl, fetchActiveTrades, fetchPositions } = useTradeStore()

  const intervalsRef = useRef<NodeJS.Timeout[]>([])

  useEffect(() => {
    // Initial data fetch
    const initializeData = async () => {
      await Promise.all([
        fetchSettings(),
        fetchMarketStatus(),
        fetchIndices(),
        fetchStrategies(),
        fetchEngineStatus(),
        fetchDailyPnl(),
        fetchDecision('NIFTY', 5)
      ])
    }

    initializeData()

    // Set up polling intervals
    const marketInterval = setInterval(() => {
      fetchMarketStatus()
      fetchIndices()
    }, config.MARKET_POLL_INTERVAL || 5000)

    const signalInterval = setInterval(() => {
      fetchDecision('NIFTY', 5)
      fetchEngineStatus()
    }, config.SIGNAL_POLL_INTERVAL || 10000)

    const tradeInterval = setInterval(() => {
      fetchActiveTrades()
      fetchPositions()
      fetchDailyPnl()
    }, config.TRADE_POLL_INTERVAL || 5000)

    const strategyInterval = setInterval(() => {
      fetchStrategies()
    }, 10000)

    intervalsRef.current = [marketInterval, signalInterval, tradeInterval, strategyInterval]

    return () => {
      intervalsRef.current.forEach(clearInterval)
    }
  }, [])

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-dark-950 text-gray-900 dark:text-white transition-colors duration-200">

      {/* Sidebar: static on desktop, off-canvas drawer on mobile */}
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {/* Mobile drawer backdrop */}
      {sidebarOpen && (
        <div
          className="lg:hidden fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Main Content — left margin only on desktop where the sidebar is static */}
      <div className="lg:ml-64">

        {/* Header */}
        <Header onToggleSidebar={toggleSidebar} />

        {/* Page Content (bottom padding clears the mobile tab bar) */}
        <main className="p-4 sm:p-6 pb-24 lg:pb-6 min-h-[calc(100vh-4rem)]">
          <Outlet />
        </main>
      </div>

      {/* Mobile bottom tab bar */}
      <BottomNav />

      {/* Toast Notifications */}
      <Toast />
    </div>
  )
}