/**
 * Market Direction Card Component
 * Displays market direction (UP/DOWN/NEUTRAL) with strength gauge
 */
import {
  TrendingUp, TrendingDown, Minus, Activity,
  BarChart3, Zap, Volume2, Target
} from 'lucide-react'
import type { MarketDirection } from '../../types'

interface MarketDirectionCardProps {
  direction: MarketDirection | null
  symbol: string
  compact?: boolean
  showComponents?: boolean
  onClick?: () => void
}

export default function MarketDirectionCard({
  direction,
  symbol,
  compact = false,
  showComponents = true,
  onClick
}: MarketDirectionCardProps) {
  if (!direction) {
    return (
      <div className={`bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 rounded-xl p-4 ${onClick ? 'cursor-pointer hover:border-blue-500/30' : ''}`} onClick={onClick}>
        <div className="flex items-center justify-center h-24">
          <Activity className="w-6 h-6 text-gray-400 animate-pulse" />
          <span className="ml-2 text-gray-500 dark:text-dark-400">Loading {symbol}...</span>
        </div>
      </div>
    )
  }

  const directionConfig = {
    UP: {
      icon: TrendingUp,
      color: 'text-emerald-500',
      bgColor: 'bg-emerald-100 dark:bg-emerald-500/10',
      borderColor: 'border-emerald-200 dark:border-emerald-500/30',
      barColor: 'bg-emerald-500',
      label: 'BULLISH'
    },
    DOWN: {
      icon: TrendingDown,
      color: 'text-red-500',
      bgColor: 'bg-red-100 dark:bg-red-500/10',
      borderColor: 'border-red-200 dark:border-red-500/30',
      barColor: 'bg-red-500',
      label: 'BEARISH'
    },
    NEUTRAL: {
      icon: Minus,
      color: 'text-yellow-500',
      bgColor: 'bg-yellow-100 dark:bg-yellow-500/10',
      borderColor: 'border-yellow-200 dark:border-yellow-500/30',
      barColor: 'bg-yellow-500',
      label: 'NEUTRAL'
    }
  }

  const config = directionConfig[direction.direction] || directionConfig.NEUTRAL
  const Icon = config.icon

  // Strength percentage
  const strengthPercent = Math.round(direction.strength)

  if (compact) {
    return (
      <div 
        className={`bg-white dark:bg-dark-900 border ${config.borderColor} rounded-xl p-4 transition-all ${onClick ? 'cursor-pointer hover:shadow-lg' : ''}`}
        onClick={onClick}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${config.bgColor}`}>
              <Icon className={`w-5 h-5 ${config.color}`} />
            </div>
            <div>
              <h3 className="font-bold text-gray-900 dark:text-white">{symbol}</h3>
              <p className={`text-sm font-semibold ${config.color}`}>{config.label}</p>
            </div>
          </div>
          <div className="text-right">
            <p className={`text-2xl font-bold ${config.color}`}>{strengthPercent}%</p>
            <p className="text-xs text-gray-500 dark:text-dark-400">Strength</p>
          </div>
        </div>
        
        {/* Strength Bar */}
        <div className="mt-3 h-2 bg-gray-200 dark:bg-dark-700 rounded-full overflow-hidden">
          <div 
            className={`h-full ${config.barColor} transition-all duration-500`}
            style={{ width: `${strengthPercent}%` }}
          />
        </div>
      </div>
    )
  }

  return (
    <div 
      className={`bg-white dark:bg-dark-900 border ${config.borderColor} rounded-xl overflow-hidden transition-all ${onClick ? 'cursor-pointer hover:shadow-lg' : ''}`}
      onClick={onClick}
    >
      {/* Header */}
      <div className="p-4 border-b border-gray-200 dark:border-dark-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-3 rounded-xl ${config.bgColor}`}>
              <Icon className={`w-6 h-6 ${config.color}`} />
            </div>
            <div>
              <h3 className="text-lg font-bold text-gray-900 dark:text-white">{symbol}</h3>
              <p className={`text-sm font-semibold ${config.color}`}>{config.label}</p>
            </div>
          </div>
          <div className="text-right">
            <p className={`text-3xl font-bold ${config.color}`}>{strengthPercent}%</p>
            <p className="text-xs text-gray-500 dark:text-dark-400">Strength</p>
          </div>
        </div>
        
        {/* Large Strength Bar */}
        <div className="mt-4 h-3 bg-gray-200 dark:bg-dark-700 rounded-full overflow-hidden">
          <div 
            className={`h-full ${config.barColor} transition-all duration-500`}
            style={{ width: `${strengthPercent}%` }}
          />
        </div>
      </div>

      {/* Components Breakdown */}
      {showComponents && direction.components && (
        <div className="p-4 space-y-3">
          {/* 15m Trend */}
          <ComponentRow
            icon={<BarChart3 className="w-4 h-4" />}
            label="15m Trend"
            score={direction.components.trend_15m?.score}
            direction={direction.components.trend_15m?.direction}
            weight={35}
          />
          
          {/* 5m Structure */}
          <ComponentRow
            icon={<Target className="w-4 h-4" />}
            label="5m Structure"
            score={direction.components.structure_5m?.score}
            direction={direction.components.structure_5m?.direction}
            weight={25}
          />
          
          {/* 1m Momentum */}
          <ComponentRow
            icon={<Zap className="w-4 h-4" />}
            label="1m Momentum"
            score={direction.components.momentum_1m?.score}
            direction={direction.components.momentum_1m?.direction}
            weight={20}
          />
          
          {/* Volume */}
          <ComponentRow
            icon={<Volume2 className="w-4 h-4" />}
            label="Volume"
            score={direction.components.volume?.score}
            confirmed={direction.components.volume?.confirmed}
            weight={10}
          />
          
          {/* VWAP */}
          <ComponentRow
            icon={<Activity className="w-4 h-4" />}
            label="VWAP"
            score={direction.components.vwap?.score}
            position={direction.components.vwap?.position}
            weight={10}
          />
        </div>
      )}

      {/* Footer - Price & Indicators */}
      {direction.current_price && (
        <div className="px-4 py-3 bg-gray-50 dark:bg-dark-800/50 border-t border-gray-200 dark:border-dark-700">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-500 dark:text-dark-400">LTP</span>
            <span className="font-mono font-bold text-gray-900 dark:text-white">
              ₹{direction.current_price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </span>
          </div>
          {direction.indicators?.rsi_14 && (
            <div className="flex items-center justify-between text-sm mt-1">
              <span className="text-gray-500 dark:text-dark-400">RSI (14)</span>
              <span className={`font-mono font-bold ${
                direction.indicators.rsi_14 > 70 ? 'text-red-500' :
                direction.indicators.rsi_14 < 30 ? 'text-emerald-500' :
                'text-gray-900 dark:text-white'
              }`}>
                {direction.indicators.rsi_14.toFixed(1)}
              </span>
            </div>
          )}
          {direction.structure?.type && (
            <div className="flex items-center justify-between text-sm mt-1">
              <span className="text-gray-500 dark:text-dark-400">Structure</span>
              <span className={`font-bold text-xs px-2 py-0.5 rounded ${
                direction.structure.type === 'HH_HL' ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' :
                direction.structure.type === 'LH_LL' ? 'bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-400' :
                'bg-yellow-100 dark:bg-yellow-500/10 text-yellow-600 dark:text-yellow-400'
              }`}>
                {direction.structure.type === 'HH_HL' ? 'HH/HL' : 
                 direction.structure.type === 'LH_LL' ? 'LH/LL' : 'RANGING'}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Component Row Helper
function ComponentRow({
  icon,
  label,
  score,
  direction,
  confirmed,
  position,
  weight
}: {
  icon: React.ReactNode
  label: string
  score?: number
  direction?: string
  confirmed?: boolean
  position?: string
  weight: number
}) {
  const scoreValue = score ?? 50
  const scoreColor = scoreValue > 60 ? 'text-emerald-500' : scoreValue < 40 ? 'text-red-500' : 'text-yellow-500'
  const barColor = scoreValue > 60 ? 'bg-emerald-500' : scoreValue < 40 ? 'bg-red-500' : 'bg-yellow-500'

  return (
    <div className="flex items-center gap-3">
      <div className="text-gray-400 dark:text-dark-500">{icon}</div>
      <div className="flex-1">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-gray-600 dark:text-dark-300">{label}</span>
          <div className="flex items-center gap-2">
            {direction && (
              <span className={`text-[10px] font-bold ${
                direction === 'UP' ? 'text-emerald-500' :
                direction === 'DOWN' ? 'text-red-500' :
                'text-yellow-500'
              }`}>
                {direction === 'UP' ? '▲' : direction === 'DOWN' ? '▼' : '●'}
              </span>
            )}
            {confirmed !== undefined && (
              <span className={`text-[10px] font-bold ${confirmed ? 'text-emerald-500' : 'text-gray-400'}`}>
                {confirmed ? '✓' : '○'}
              </span>
            )}
            {position && (
              <span className={`text-[10px] font-bold ${
                position === 'ABOVE' ? 'text-emerald-500' :
                position === 'BELOW' ? 'text-red-500' :
                'text-yellow-500'
              }`}>
                {position}
              </span>
            )}
            <span className={`text-xs font-bold ${scoreColor}`}>{Math.round(scoreValue)}</span>
          </div>
        </div>
        <div className="h-1.5 bg-gray-200 dark:bg-dark-700 rounded-full overflow-hidden">
          <div 
            className={`h-full ${barColor} transition-all duration-300`}
            style={{ width: `${scoreValue}%` }}
          />
        </div>
      </div>
      <span className="text-[10px] text-gray-400 dark:text-dark-500 w-6 text-right">{weight}%</span>
    </div>
  )
}
