import { useEffect, useRef } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Header from './Header'
import Toast from '../common/Toast'
import { useUIStore, useMarketStore, useStrategyStore, useTradeStore } from '../../store'
import { config } from '../../config'

export default function Layout() {
  const { sidebarOpen, toggleSidebar, fetchSettings } = useUIStore()
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
    // FIX: Added 'bg-gray-50 dark:bg-dark-950' and 'text-gray-900 dark:text-white'
    <div className="min-h-screen bg-gray-50 dark:bg-dark-950 text-gray-900 dark:text-white transition-colors duration-200">
      
      {/* Sidebar */}
      <Sidebar isOpen={sidebarOpen} />

      {/* Main Content */}
      <div className={`transition-all duration-300 ${sidebarOpen ? 'ml-64' : 'ml-20'}`}>
        
        {/* Header */}
        <Header onToggleSidebar={toggleSidebar} />

        {/* Page Content */}
        <main className="p-6 min-h-[calc(100vh-4rem)]">
          <Outlet />
        </main>
      </div>

      {/* Toast Notifications */}
      <Toast />
    </div>
  )
}