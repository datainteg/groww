/**
 * Direction Panel Component
 * Shows market direction for all indices in a grid
 */
import { useEffect } from 'react'
import { RefreshCw, Zap, Activity } from 'lucide-react'
import { useDirectionStore } from '../../store'
import MarketDirectionCard from './MarketDirectionCard'

interface DirectionPanelProps {
  indices?: string[]
  compact?: boolean
  showTitle?: boolean
  refreshInterval?: number
  onSymbolClick?: (symbol: string) => void
}

export default function DirectionPanel({
  indices = ['NIFTY', 'BANKNIFTY', 'SENSEX'],
  compact = false,
  showTitle = true,
  refreshInterval = 5000,
  onSymbolClick
}: DirectionPanelProps) {
  const { 
    directions, 
    isLoading, 
    lastUpdate, 
    fetchAllDirections 
  } = useDirectionStore()

  // Initial fetch
  useEffect(() => {
    fetchAllDirections()
  }, [])

  // Auto-refresh
  useEffect(() => {
    if (refreshInterval > 0) {
      const timer = setInterval(fetchAllDirections, refreshInterval)
      return () => clearInterval(timer)
    }
  }, [refreshInterval])

  const handleRefresh = () => {
    fetchAllDirections()
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      {showTitle && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-purple-500" />
            <h3 className="font-bold text-gray-900 dark:text-white">Market Direction Engine</h3>
            <span className="text-[10px] px-2 py-0.5 bg-purple-100 dark:bg-purple-500/10 text-purple-600 dark:text-purple-400 rounded-full font-bold">
              LIVE
            </span>
          </div>
          <div className="flex items-center gap-2">
            {lastUpdate && (
              <span className="text-xs text-gray-500 dark:text-dark-400">
                {new Date(lastUpdate).toLocaleTimeString('en-IN', { 
                  hour: '2-digit', 
                  minute: '2-digit', 
                  second: '2-digit' 
                })}
              </span>
            )}
            <button 
              onClick={handleRefresh}
              disabled={isLoading}
              className="p-1.5 rounded-lg text-gray-500 dark:text-dark-400 hover:bg-gray-100 dark:hover:bg-dark-800 transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      )}

      {/* Direction Cards Grid */}
      <div className={`grid gap-4 ${compact ? 'grid-cols-1 md:grid-cols-3' : 'grid-cols-1 lg:grid-cols-3'}`}>
        {indices.map(symbol => (
          <MarketDirectionCard
            key={symbol}
            symbol={symbol}
            direction={directions[symbol] || null}
            compact={compact}
            showComponents={!compact}
            onClick={onSymbolClick ? () => onSymbolClick(symbol) : undefined}
          />
        ))}
      </div>

      {/* Loading overlay */}
      {isLoading && Object.keys(directions).length === 0 && (
        <div className="flex items-center justify-center py-8">
          <Activity className="w-6 h-6 text-purple-500 animate-pulse mr-2" />
          <span className="text-gray-500 dark:text-dark-400">Analyzing market direction...</span>
        </div>
      )}
    </div>
  )
}
