import { useEffect, useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { 
  Zap, TrendingUp, TrendingDown, Activity, RefreshCw, BarChart3, 
  Target, AlertTriangle, ArrowUpRight, ArrowDownRight, Clock,
  ChevronRight, Play, Pause, DollarSign, Layers, Minus,
  Volume2, Gauge, Eye, Info, FlaskConical, ShieldCheck
} from 'lucide-react'
import { useMarketStore, useStrategyStore, useTradeStore, useUIStore, useDirectionStore, useHealthStore, useAuthStore } from '../store'
import { formatCurrency, formatPercent, getISTString, getPnlClass } from '../utils/formatter'
import Modal from '../components/common/Modal'
import { Badge } from '../components/ui'
import type { MarketDirection, DirectionType } from '../types'

// ==================== HELPERS ====================

// Configuration map for direction styling
const getDirectionConfig = (direction: DirectionType | string = 'NEUTRAL') => {
  switch (direction) {
    case 'UP':
    case 'BULLISH':
      return { 
        icon: TrendingUp, 
        color: 'text-emerald-500', 
        bgColor: 'bg-emerald-50 dark:bg-emerald-500/10', 
        borderColor: 'border-emerald-200 dark:border-emerald-500/30', 
        barColor: 'bg-emerald-500', 
        label: 'BULLISH' 
      }
    case 'DOWN':
    case 'BEARISH':
      return { 
        icon: TrendingDown, 
        color: 'text-red-500', 
        bgColor: 'bg-red-50 dark:bg-red-500/10', 
        borderColor: 'border-red-200 dark:border-red-500/30', 
        barColor: 'bg-red-500', 
        label: 'BEARISH' 
      }
    default:
      return { 
        icon: Minus, 
        color: 'text-yellow-500', 
        bgColor: 'bg-yellow-50 dark:bg-yellow-500/10', 
        borderColor: 'border-yellow-200 dark:border-yellow-500/30', 
        barColor: 'bg-yellow-500', 
        label: 'NEUTRAL' 
      }
  }
}

// Component for rendering a progress bar within the direction analysis
const ComponentBar = ({ 
  label, 
  score, 
  direction, 
  confirmed, 
  position, 
  weight, 
  icon 
}: { 
  label: string; 
  score: number; 
  direction?: string; 
  confirmed?: boolean; 
  position?: string; 
  weight: number; 
  icon: React.ReactNode 
}) => {
  const scoreColor = score > 60 ? 'text-emerald-500' : score < 40 ? 'text-red-500' : 'text-yellow-500'
  const barColor = score > 60 ? 'bg-emerald-500' : score < 40 ? 'bg-red-500' : 'bg-yellow-500'
  
  return (
    <div className="flex items-center gap-3">
      <div className="text-gray-400 dark:text-dark-500 w-5">{icon}</div>
      <div className="flex-1">
        <div className="flex items-center justify-between mb-1">
          <span className="text-sm text-gray-700 dark:text-gray-300 font-medium">{label}</span>
          <div className="flex items-center gap-3">
            {direction && (
              <span className={`text-xs font-bold flex items-center gap-1 ${direction === 'UP' ? 'text-emerald-500' : direction === 'DOWN' ? 'text-red-500' : 'text-yellow-500'}`}>
                {direction === 'UP' ? <TrendingUp className="w-3 h-3" /> : direction === 'DOWN' ? <TrendingDown className="w-3 h-3" /> : <Minus className="w-3 h-3" />}
                {direction}
              </span>
            )}
            {confirmed !== undefined && (
              <span className={`text-xs font-bold ${confirmed ? 'text-emerald-500' : 'text-gray-400'}`}>
                {confirmed ? '✓ Confirmed' : '○ Not Confirmed'}
              </span>
            )}
            {position && (
              <span className={`text-xs font-bold ${position === 'ABOVE' ? 'text-emerald-500' : position === 'BELOW' ? 'text-red-500' : 'text-yellow-500'}`}>
                {position}
              </span>
            )}
            <span className={`text-sm font-bold ${scoreColor}`}>{Math.round(score)}</span>
          </div>
        </div>
        <div className="h-2 bg-gray-200 dark:bg-dark-700 rounded-full overflow-hidden">
          <div className={`h-full ${barColor} transition-all duration-300`} style={{ width: `${score}%` }} />
        </div>
      </div>
      <span className="text-xs text-gray-400 dark:text-dark-500 w-8 text-right">{weight}%</span>
    </div>
  )
}

// Modal Content for Detailed Analysis
const DirectionAnalysisContent = ({ 
  direction, 
  loading, 
  onRefresh 
}: { 
  direction: MarketDirection; 
  loading: boolean; 
  onRefresh: () => void 
}) => {
  const cfg = getDirectionConfig(direction.direction)
  const Icon = cfg.icon
  const strength = Math.round(direction.strength)

  return (
    <div className="space-y-6">
      {/* Header Card */}
      <div className={`p-5 rounded-xl ${cfg.bgColor} border ${cfg.borderColor} border-opacity-30`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="p-4 rounded-xl bg-white/50 dark:bg-black/20">
              <Icon className={`w-10 h-10 ${cfg.color}`} />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white">{direction.symbol}</h2>
              <p className={`text-lg font-bold ${cfg.color}`}>{cfg.label}</p>
            </div>
          </div>
          <div className="text-right">
            <p className={`text-4xl font-bold ${cfg.color}`}>{strength}%</p>
            <p className="text-sm text-gray-500 dark:text-dark-400">Strength Score</p>
          </div>
        </div>
        <div className="mt-4 h-4 bg-white/30 dark:bg-black/20 rounded-full overflow-hidden">
          <div className={`h-full ${cfg.barColor} transition-all duration-500`} style={{ width: `${strength}%` }} />
        </div>
        <div className="mt-4 flex items-center justify-between">
          <span className="text-gray-600 dark:text-dark-300">Current Price</span>
          <span className="text-2xl font-bold font-mono text-gray-900 dark:text-white">
            {formatCurrency(direction.current_price || 0)}
          </span>
        </div>
      </div>

      {/* Components Breakdown */}
      <div className="bg-gray-50 dark:bg-dark-800/50 rounded-xl border border-gray-200 dark:border-dark-700 p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Gauge className="w-5 h-5 text-purple-500" /> Component Analysis
          </h3>
          <button 
            onClick={onRefresh} 
            disabled={loading} 
            className="p-2 rounded-lg text-gray-500 hover:bg-gray-200 dark:hover:bg-dark-700 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
        <div className="space-y-4">
          <ComponentBar label="15m Trend" score={direction.components?.trend_15m?.score || 50} direction={direction.components?.trend_15m?.direction} weight={35} icon={<BarChart3 className="w-4 h-4" />} />
          <ComponentBar label="5m Structure" score={direction.components?.structure_5m?.score || 50} direction={direction.components?.structure_5m?.direction} weight={25} icon={<Target className="w-4 h-4" />} />
          <ComponentBar label="1m Momentum" score={direction.components?.momentum_1m?.score || 50} direction={direction.components?.momentum_1m?.direction} weight={20} icon={<Zap className="w-4 h-4" />} />
          <ComponentBar label="Volume" score={direction.components?.volume?.score || 50} confirmed={direction.components?.volume?.confirmed} weight={10} icon={<Volume2 className="w-4 h-4" />} />
          <ComponentBar label="VWAP" score={direction.components?.vwap?.score || 50} position={direction.components?.vwap?.position} weight={10} icon={<Activity className="w-4 h-4" />} />
        </div>
      </div>

      {/* Technical Indicators & Structure */}
      <div className="grid grid-cols-2 gap-4">
        {/* Indicators */}
        <div className="bg-gray-50 dark:bg-dark-800/50 rounded-xl border border-gray-200 dark:border-dark-700 p-4">
          <h4 className="font-bold text-gray-700 dark:text-gray-300 text-sm mb-3 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-blue-500" /> Indicators
          </h4>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-gray-500 dark:text-dark-400">EMA 9</span><span className="font-mono font-bold text-gray-900 dark:text-white">{direction.indicators?.ema_9?.toFixed(2) || '-'}</span></div>
            <div className="flex justify-between"><span className="text-gray-500 dark:text-dark-400">EMA 21</span><span className="font-mono font-bold text-gray-900 dark:text-white">{direction.indicators?.ema_21?.toFixed(2) || '-'}</span></div>
            <div className="flex justify-between"><span className="text-gray-500 dark:text-dark-400">EMA 50</span><span className="font-mono font-bold text-gray-900 dark:text-white">{direction.indicators?.ema_50?.toFixed(2) || '-'}</span></div>
            <div className="flex justify-between"><span className="text-gray-500 dark:text-dark-400">RSI (14)</span><span className={`font-mono font-bold ${(direction.indicators?.rsi_14 || 50) > 70 ? 'text-red-500' : (direction.indicators?.rsi_14 || 50) < 30 ? 'text-emerald-500' : 'text-gray-900 dark:text-white'}`}>{direction.indicators?.rsi_14?.toFixed(1) || '-'}</span></div>
            <div className="flex justify-between"><span className="text-gray-500 dark:text-dark-400">VWAP</span><span className="font-mono font-bold text-gray-900 dark:text-white">{direction.indicators?.vwap?.toFixed(2) || '-'}</span></div>
          </div>
        </div>
        
        {/* Structure */}
        <div className="bg-gray-50 dark:bg-dark-800/50 rounded-xl border border-gray-200 dark:border-dark-700 p-4">
          <h4 className="font-bold text-gray-700 dark:text-gray-300 text-sm mb-3 flex items-center gap-2">
            <Target className="w-4 h-4 text-purple-500" /> Price Structure
          </h4>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between items-center">
              <span className="text-gray-500 dark:text-dark-400">Pattern</span>
              <span className={`px-2 py-0.5 rounded text-xs font-bold ${direction.structure?.type === 'HH_HL' ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600' : direction.structure?.type === 'LH_LL' ? 'bg-red-100 dark:bg-red-500/10 text-red-600' : 'bg-yellow-100 dark:bg-yellow-500/10 text-yellow-600'}`}>
                {direction.structure?.type === 'HH_HL' ? 'Higher Highs' : direction.structure?.type === 'LH_LL' ? 'Lower Lows' : 'Ranging'}
              </span>
            </div>
            <div className="flex justify-between"><span className="text-gray-500 dark:text-dark-400">Recent High</span><span className="font-mono font-bold text-emerald-500">{direction.structure?.recent_high?.toFixed(2) || '-'}</span></div>
            <div className="flex justify-between"><span className="text-gray-500 dark:text-dark-400">Recent Low</span><span className="font-mono font-bold text-red-500">{direction.structure?.recent_low?.toFixed(2) || '-'}</span></div>
          </div>
        </div>
      </div>

      {/* Timestamp */}
      <div className="flex items-center justify-between text-xs text-gray-500 dark:text-dark-400 pt-2 border-t border-gray-200 dark:border-dark-700">
        <span className="flex items-center gap-1"><Info className="w-3 h-3" />Auto-updates every 30s</span>
        <span>Last updated: {new Date(direction.timestamp).toLocaleTimeString('en-IN')}</span>
      </div>
    </div>
  )
}

// ==================== MAIN COMPONENT ====================

function QuickAction({ to, icon, label }: { to: string; icon: React.ReactNode; label: string }) {
  return (
    <Link to={to} className="rounded-xl bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 p-4 flex flex-col items-center justify-center gap-2 hover:border-primary-400 hover:shadow-md transition-all text-center">
      <span className="w-9 h-9 rounded-lg bg-primary-50 dark:bg-primary-500/10 text-primary-600 dark:text-primary-400 flex items-center justify-center">{icon}</span>
      <span className="text-xs font-semibold text-gray-700 dark:text-dark-200">{label}</span>
    </Link>
  )
}

function StatusPill({ label, value, variant }: { label: string; value: string; variant: 'success' | 'danger' | 'warning' | 'paper' | 'live' | 'neutral' }) {
  return (
    <div className="rounded-xl bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 px-3 py-2.5 flex items-center justify-between gap-2">
      <span className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-dark-400 font-bold">{label}</span>
      <Badge variant={variant}>{value}</Badge>
    </div>
  )
}

export default function Dashboard() {
  // Store Hooks
  const { marketStatus, indices, fetchIndices } = useMarketStore()
  const { strategies, engineStatus, decisions, fetchStrategies, fetchEngineStatus, fetchDecision, startStrategy, stopStrategy } = useStrategyStore()
  const { dailyPnl, activeTrades, fetchDailyPnl, fetchActiveTrades } = useTradeStore()
  const { settings, addToast } = useUIStore()
  const { directions, fetchAllDirections, fetchDirection } = useDirectionStore()
  const { health } = useHealthStore()
  const { user } = useAuthStore()
  
  // Local State
  const [currentTime, setCurrentTime] = useState(getISTString())
  const [refreshing, setRefreshing] = useState(false)
  const [analysisSymbol, setAnalysisSymbol] = useState<string>('NIFTY')
  // Read the selected symbol's decision from the per-symbol map (not the shared
  // field, which another page could overwrite with a different symbol).
  const decision = decisions[analysisSymbol] || null
  const [showDirectionModal, setShowDirectionModal] = useState(false)
  
  // CHANGED: Instead of storing the full object, store the Symbol. 
  // This allows the Modal to read directly from the 'directions' store, ensuring sync.
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)
  
  const [directionLoading, setDirectionLoading] = useState(false)

  // 1. Clock Timer (1s)
  useEffect(() => { 
    const timer = setInterval(() => setCurrentTime(getISTString()), 1000)
    return () => clearInterval(timer) 
  }, [])

  // 2. Market Direction Polling (30s)
  // This updates the 'directions' store. Since the modal uses 'directions[selectedSymbol]',
  // it will automatically update when the store updates.
  useEffect(() => { 
    // Initial load (Shows spinner)
    fetchAllDirections(false) 
    
    // Background polling (Silent - No spinner)
    const timer = setInterval(() => fetchAllDirections(true), 30000) 
    
    return () => clearInterval(timer) 
  }, [fetchAllDirections])

  // 3. AI Decision Polling (When symbol changes)
  useEffect(() => { 
    fetchDecision(analysisSymbol, 5) 
  }, [analysisSymbol, fetchDecision])

  // Actions
  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await Promise.all([
        fetchIndices(), 
        fetchStrategies(), 
        fetchEngineStatus(), 
        fetchDailyPnl(), 
        fetchActiveTrades(), 
        fetchDecision(analysisSymbol, 5), 
        fetchAllDirections()
      ])
      addToast('success', 'Dashboard refreshed')
    } catch (error) {
      addToast('error', 'Failed to refresh dashboard')
    } finally {
      setRefreshing(false)
    }
  }

  const handleToggleStrategy = async (strategyId: string, isActive: boolean) => {
    try { 
      if (isActive) { 
        await stopStrategy(strategyId)
        addToast('info', 'Strategy stopped') 
      } else { 
        await startStrategy(strategyId)
        addToast('success', 'Strategy started') 
      } 
    } catch (err: any) { 
      addToast('error', err.error || 'Failed to toggle strategy') 
    }
  }

  const handleDirectionClick = async (symbol: string) => {
    setSelectedSymbol(symbol)
    setShowDirectionModal(true)
    setDirectionLoading(true)
    
    // Fetch fresh data immediately on click
    await fetchDirection(symbol, true)
    
    setDirectionLoading(false)
  }

  const handleModalClose = () => {
    setShowDirectionModal(false)
    setSelectedSymbol(null)
  }

  // Derived State
  const activeStrategies = useMemo(() => strategies.filter(s => s.is_active), [strategies])
  const todayPnl = dailyPnl?.total_pnl || 0
  const indicatorCount = useMemo(() => Object.keys(decision?.indicators || {}).length, [decision])

  // Derived Direction for Modal (Reactive to Store)
  const selectedDirectionData = selectedSymbol ? directions[selectedSymbol] : null

  return (
    <div className="space-y-8 animate-fade-in pb-10">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white tracking-tight">Dashboard</h1>
          <p className="text-gray-500 dark:text-dark-400 flex items-center gap-3 mt-2 text-sm font-medium">
            <span className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full border ${marketStatus?.is_open ? 'bg-emerald-100 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20 text-emerald-600 dark:text-emerald-400' : 'bg-red-100 dark:bg-red-500/10 border-red-200 dark:border-red-500/20 text-red-600 dark:text-red-400'}`}>
              <span className={`w-2 h-2 rounded-full ${marketStatus?.is_open ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`} />
              {marketStatus?.is_open ? 'Market Open' : 'Market Closed'}
            </span>
            <span className="text-gray-400 dark:text-dark-600">|</span>
            <span className="flex items-center gap-1.5 text-gray-600 dark:text-dark-300">
              <Clock className="w-4 h-4 text-blue-500 dark:text-blue-400" /> {currentTime}
            </span>
          </p>
        </div>
        <button onClick={handleRefresh} disabled={refreshing} className="btn-secondary group">
          <RefreshCw className={`w-4 h-4 group-hover:text-blue-500 transition-colors ${refreshing ? 'animate-spin' : ''}`} />
          Refresh Data
        </button>
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <QuickAction to="/trades" icon={<Play className="w-5 h-5" />} label="Paper Trade" />
        <QuickAction to="/backtest" icon={<FlaskConical className="w-5 h-5" />} label="Backtest" />
        <QuickAction to="/strategy" icon={<Layers className="w-5 h-5" />} label="Strategy Lab" />
        <QuickAction to="/safety" icon={<ShieldCheck className="w-5 h-5" />} label="Safety Center" />
      </div>

      {/* System status strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatusPill label="Mode" value={settings?.execution_mode || 'PAPER'} variant={settings?.execution_mode === 'LIVE' ? 'live' : 'paper'} />
        <StatusPill label="Scheduler" value={health?.scheduler_stale ? 'Down' : 'Healthy'} variant={health?.scheduler_stale ? 'danger' : 'success'} />
        <StatusPill label="Data feed" value={health?.scheduler_stale ? 'Stale' : 'Live'} variant={health?.scheduler_stale ? 'warning' : 'success'} />
        <StatusPill label="Token" value={user?.broker_connected ? (user?.needs_groww_refresh ? 'Stale' : 'Fresh') : 'Not set'} variant={user?.broker_connected ? (user?.needs_groww_refresh ? 'warning' : 'success') : 'neutral'} />
      </div>

      {/* Kill Switch Alert */}
      {settings?.kill_switch && (
        <div className="relative overflow-hidden rounded-xl bg-red-100 dark:bg-red-500/10 border border-red-200 dark:border-red-500/40 p-4 flex items-center gap-4 animate-pulse-slow">
          <div className="p-2 bg-red-200 dark:bg-red-500/20 rounded-lg"><AlertTriangle className="w-6 h-6 text-red-600 dark:text-red-500" /></div>
          <div>
            <h3 className="font-bold text-red-600 dark:text-red-400 text-lg">Kill Switch Active</h3>
            <p className="text-red-600/80 dark:text-red-400/80 text-sm">All trading operations are currently halted. Go to Settings to disable.</p>
          </div>
        </div>
      )}

      {/* Market Direction Engine Panel */}
      <div className="card p-5 bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-purple-500" />
            <h3 className="font-bold text-gray-900 dark:text-white">Market Direction Engine</h3>
            <span className="text-[10px] px-2 py-0.5 bg-purple-100 dark:bg-purple-500/10 text-purple-600 dark:text-purple-400 rounded-full font-bold">LIVE</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-dark-400">{currentTime}</span>
            <button onClick={() => fetchAllDirections()} className="p-1.5 rounded-lg text-gray-500 dark:text-dark-400 hover:bg-gray-100 dark:hover:bg-dark-800 transition-colors">
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {['NIFTY', 'BANKNIFTY', 'SENSEX'].map(symbol => {
            const dir = directions[symbol]
            const cfg = getDirectionConfig(dir?.direction || 'NEUTRAL')
            const Icon = cfg.icon
            const strength = Math.round(dir?.strength || 0)
            
            return (
              <div key={symbol} onClick={() => handleDirectionClick(symbol)} className={`bg-white dark:bg-dark-900 border ${dir ? cfg.borderColor : 'border-gray-200 dark:border-dark-700'} border-opacity-30 rounded-xl p-4 transition-all cursor-pointer hover:shadow-lg hover:scale-[1.02] group`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${cfg.bgColor}`}><Icon className={`w-5 h-5 ${cfg.color}`} /></div>
                    <div><h3 className="font-bold text-gray-900 dark:text-white">{symbol}</h3><p className={`text-sm font-semibold ${cfg.color}`}>{cfg.label}</p></div>
                  </div>
                  <div className="text-right"><p className={`text-2xl font-bold ${cfg.color}`}>{strength}%</p><p className="text-xs text-gray-500 dark:text-dark-400">Strength</p></div>
                </div>
                <div className="mt-3 h-2 bg-gray-200 dark:bg-dark-700 rounded-full overflow-hidden">
                  <div className={`h-full ${cfg.barColor} transition-all duration-500`} style={{ width: `${strength}%` }} />
                </div>
                <div className="mt-2 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                  <span className="text-[10px] text-gray-400 dark:text-dark-500 flex items-center gap-1"><Eye className="w-3 h-3" /> Click for details</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Main Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
        {/* Engine Status */}
        <div className="card p-5 relative overflow-hidden group hover:border-blue-500/30 transition-all bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700">
          <div className="flex justify-between items-start mb-4">
            <div><p className="text-gray-500 dark:text-dark-400 text-xs font-bold uppercase tracking-wider">Engine Status</p><h3 className={`text-2xl font-bold mt-1 ${engineStatus?.is_running ? 'text-emerald-500' : 'text-gray-700 dark:text-dark-300'}`}>{engineStatus?.is_running ? 'Active' : 'Stopped'}</h3></div>
            <div className={`p-3 rounded-xl ${engineStatus?.is_running ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-gray-100 dark:bg-dark-700 text-gray-500 dark:text-dark-400'}`}><Zap className="w-6 h-6" /></div>
          </div>
          <div className="flex items-center justify-between text-sm"><span className="text-gray-600 dark:text-dark-400">{activeStrategies.length} Strategies Running</span><Link to="/strategy" className="text-blue-500 dark:text-blue-400 hover:text-blue-600 dark:hover:text-blue-300 flex items-center gap-1 text-xs font-bold uppercase">Manage <ChevronRight className="w-3 h-3" /></Link></div>
        </div>

        {/* AI Signal */}
        <div className="card p-5 relative overflow-hidden group hover:border-purple-500/30 transition-all bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700">
          <div className="flex justify-between items-start mb-4">
            <div><p className="text-gray-500 dark:text-dark-400 text-xs font-bold uppercase tracking-wider">AI Signal ({analysisSymbol})</p><h3 className={`text-2xl font-bold mt-1 ${decision?.signal === 'BULLISH' ? 'text-emerald-500' : decision?.signal === 'BEARISH' ? 'text-red-500' : 'text-yellow-500'}`}>{decision?.signal || 'NEUTRAL'}</h3></div>
            <div className={`p-3 rounded-xl ${decision?.signal === 'BULLISH' ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : decision?.signal === 'BEARISH' ? 'bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-400' : 'bg-yellow-100 dark:bg-yellow-500/10 text-yellow-600 dark:text-yellow-400'}`}>
              {decision?.signal === 'BULLISH' ? <TrendingUp className="w-6 h-6" /> : decision?.signal === 'BEARISH' ? <TrendingDown className="w-6 h-6" /> : <Activity className="w-6 h-6" />}
            </div>
          </div>
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <div className="w-16 h-1.5 bg-gray-200 dark:bg-dark-700 rounded-full overflow-hidden">
                <div className={`h-full ${decision?.signal === 'BULLISH' ? 'bg-emerald-500' : decision?.signal === 'BEARISH' ? 'bg-red-500' : 'bg-yellow-500'}`} style={{ width: `${(decision?.confidence || 0) * 100}%` }} />
              </div>
              <span className="text-gray-600 dark:text-dark-400 text-xs">{((decision?.confidence || 0) * 100).toFixed(0)}% Confidence</span>
            </div>
          </div>
        </div>

        {/* Execution Mode */}
        <div className="card p-5 relative overflow-hidden group hover:border-blue-500/30 transition-all bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700">
          <div className="flex justify-between items-start mb-4">
            <div><p className="text-gray-500 dark:text-dark-400 text-xs font-bold uppercase tracking-wider">Execution Mode</p><h3 className={`text-2xl font-bold mt-1 ${settings?.execution_mode === 'LIVE' ? 'text-red-500' : 'text-blue-500'}`}>{settings?.execution_mode || 'PAPER'}</h3></div>
            <div className={`p-3 rounded-xl ${settings?.execution_mode === 'LIVE' ? 'bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-400' : 'bg-blue-100 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400'}`}><Target className="w-6 h-6" /></div>
          </div>
          <p className="text-sm text-gray-600 dark:text-dark-400">{settings?.execution_mode === 'LIVE' ? 'Real Money Trading' : 'Simulated Trading Environment'}</p>
        </div>

        {/* P&L */}
        <div className="card p-5 relative overflow-hidden group hover:border-emerald-500/30 transition-all bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700">
          <div className="flex justify-between items-start mb-4">
            <div><p className="text-gray-500 dark:text-dark-400 text-xs font-bold uppercase tracking-wider">Today's P&L</p><h3 className={`text-2xl font-bold mt-1 font-mono ${getPnlClass(todayPnl)}`}>{formatCurrency(todayPnl)}</h3></div>
            <div className={`p-3 rounded-xl ${todayPnl >= 0 ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-400'}`}><DollarSign className="w-6 h-6" /></div>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-emerald-500 font-bold">Wins: {dailyPnl?.winning || 0}</span>
            <span className="text-red-500 font-bold">Losses: {dailyPnl?.losing || 0}</span>
          </div>
        </div>
      </div>

      {/* Market Overview + Analysis Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {/* Market Overview */}
          <div className="card p-5 bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700">
            <div className="flex items-center justify-between mb-4"><h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2"><BarChart3 className="w-5 h-5 text-blue-500" /> Market Overview</h3></div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {indices.map(index => (
                <div key={index.symbol} className="bg-gray-50 dark:bg-dark-800/50 p-4 rounded-xl border border-gray-200 dark:border-dark-700">
                  <div className="flex justify-between items-start">
                    <p className="text-gray-500 dark:text-dark-400 font-bold text-xs uppercase">{index.symbol}</p>
                    <span className={`flex items-center gap-0.5 text-xs font-bold ${index.change >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                      {index.change >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                      {formatPercent(index.change_percent)}
                    </span>
                  </div>
                  <p className="text-xl font-bold text-gray-900 dark:text-white mt-1 font-mono">{formatCurrency(index.price)}</p>
                  <p className={`text-xs ${index.change >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>{index.change >= 0 ? '+' : ''}{index.change.toFixed(2)} pts</p>
                </div>
              ))}
            </div>
          </div>

          {/* AI Analysis Panel */}
          <div className="card p-5 bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2"><Activity className="w-5 h-5 text-purple-500" /> AI Analysis</h3>
              <div className="flex items-center gap-2">
                {['NIFTY', 'BANKNIFTY', 'SENSEX'].map(sym => (
                  <button key={sym} onClick={() => setAnalysisSymbol(sym)} className={`px-3 py-1 text-xs font-bold rounded-lg transition-all ${analysisSymbol === sym ? 'bg-purple-500 text-white' : 'bg-gray-100 dark:bg-dark-800 text-gray-600 dark:text-dark-400 hover:bg-gray-200 dark:hover:bg-dark-700'}`}>{sym}</button>
                ))}
              </div>
            </div>
            {decision ? (
              <div className="space-y-4">
                <div className={`p-4 rounded-xl ${decision.signal === 'BULLISH' ? 'bg-emerald-50 dark:bg-emerald-500/5 border border-emerald-200 dark:border-emerald-500/20' : decision.signal === 'BEARISH' ? 'bg-red-50 dark:bg-red-500/5 border border-red-200 dark:border-red-500/20' : 'bg-yellow-50 dark:bg-yellow-500/5 border border-yellow-200 dark:border-yellow-500/20'}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {decision.signal === 'BULLISH' ? <TrendingUp className="w-6 h-6 text-emerald-500" /> : decision.signal === 'BEARISH' ? <TrendingDown className="w-6 h-6 text-red-500" /> : <Minus className="w-6 h-6 text-yellow-500" />}
                      <div>
                        <p className={`font-bold text-lg ${decision.signal === 'BULLISH' ? 'text-emerald-600 dark:text-emerald-400' : decision.signal === 'BEARISH' ? 'text-red-600 dark:text-red-400' : 'text-yellow-600 dark:text-yellow-400'}`}>{decision.signal}</p>
                        <p className="text-xs text-gray-500 dark:text-dark-400">{((decision.confidence || 0) * 100).toFixed(0)}% Confidence</p>
                      </div>
                    </div>
                    <div className="text-right"><p className="text-2xl font-bold text-gray-900 dark:text-white font-mono">{formatCurrency(decision.current_price || 0)}</p><p className="text-xs text-gray-500 dark:text-dark-400">LTP</p></div>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-gray-50 dark:bg-dark-800 p-3 rounded-lg border border-gray-200 dark:border-dark-700"><p className="text-gray-500 dark:text-dark-500 text-xs uppercase font-bold">Indicators</p><p className="text-blue-500 dark:text-blue-400 font-bold text-lg">{indicatorCount}</p></div>
                  <div className="bg-gray-50 dark:bg-dark-800 p-3 rounded-lg border border-gray-200 dark:border-dark-700"><p className="text-gray-500 dark:text-dark-500 text-xs uppercase font-bold">Patterns</p><p className="text-purple-500 dark:text-purple-400 font-bold text-lg">{decision.pattern_count || 0}</p></div>
                  <div className="bg-gray-50 dark:bg-dark-800 p-3 rounded-lg border border-gray-200 dark:border-dark-700"><p className="text-gray-500 dark:text-dark-500 text-xs uppercase font-bold">Momentum</p><p className="text-yellow-500 dark:text-yellow-400 font-bold text-lg">{((decision.momentum?.score || 0) * 100).toFixed(0)}</p></div>
                </div>
                <div><div className="flex justify-between text-xs mb-1 font-bold"><span className="text-emerald-500">Bullish Strength</span><span className="text-red-500">Bearish Strength</span></div><div className="h-2 bg-gray-200 dark:bg-dark-700 rounded-full overflow-hidden flex"><div className="bg-emerald-500 h-full" style={{ width: `${(decision.bullish_score || 0) * 100}%` }} /><div className="bg-red-500 h-full" style={{ width: `${(decision.bearish_score || 0) * 100}%` }} /></div></div>
              </div>
            ) : (
              <div className="py-8 text-center text-gray-500 dark:text-dark-500"><RefreshCw className="w-8 h-8 mx-auto mb-2 animate-spin opacity-50" /><p>Analyzing Market Data...</p></div>
            )}
          </div>

          {/* Active Trades */}
          <div className="card overflow-hidden bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700">
            <div className="p-5 border-b border-gray-200 dark:border-dark-700 flex justify-between items-center"><h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2"><Target className="w-5 h-5 text-blue-500" /> Active Trades</h3><Link to="/trades" className="text-xs font-bold text-blue-500 dark:text-blue-400 hover:text-gray-900 dark:hover:text-white transition-colors">View All</Link></div>
            {activeTrades.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="bg-gray-50 dark:bg-dark-800/50 text-gray-500 dark:text-dark-400 font-bold text-xs uppercase"><tr><th className="p-4">Symbol</th><th className="p-4">Side</th><th className="p-4">Entry</th><th className="p-4">LTP</th><th className="p-4 text-right">P&L</th></tr></thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-dark-700">
                    {activeTrades.slice(0, 5).map(trade => {
                      const currentPrice = trade.ltp || trade.entry_price || 0
                      // `side` may be absent (backend sends transaction_type); default BUY.
                      const side = trade.side || trade.transaction_type || 'BUY'
                      const pnl = (currentPrice - (trade.entry_price ?? 0)) * trade.quantity * (side === 'BUY' ? 1 : -1)
                      return (
                        <tr key={trade._id} className="hover:bg-gray-50 dark:hover:bg-dark-800/30 transition-colors">
                          <td className="p-4 font-mono font-medium text-gray-900 dark:text-white">{trade.trading_symbol}</td>
                          <td className="p-4"><span className={`px-2 py-0.5 rounded text-[10px] font-bold ${side === 'BUY' ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-400'}`}>{side}</span></td>
                          <td className="p-4 text-gray-500 dark:text-dark-300">{formatCurrency(trade.entry_price)}</td>
                          <td className="p-4 text-gray-900 dark:text-white font-bold">{formatCurrency(currentPrice)}</td>
                          <td className={`p-4 text-right font-bold ${getPnlClass(pnl)}`}>{formatCurrency(pnl)}</td>
                        </tr>
                      ) 
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-8 text-center text-gray-500 dark:text-dark-500"><p>No active trades currently.</p></div>
            )}
          </div>
        </div>

        {/* Strategies Column */}
        <div className="space-y-6">
          <div className="card h-full flex flex-col bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700">
            <div className="p-5 border-b border-gray-200 dark:border-dark-700 flex justify-between items-center"><h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2"><Layers className="w-5 h-5 text-amber-500" /> Strategies</h3><Link to="/strategy" className="p-1 hover:bg-gray-100 dark:hover:bg-dark-700 rounded transition-colors"><ChevronRight className="w-4 h-4 text-gray-500 dark:text-dark-400" /></Link></div>
            <div className="p-3 flex-1 overflow-y-auto space-y-3 custom-scrollbar max-h-[500px]">
              {strategies.length > 0 ? (strategies.map(strategy => (
                <div key={strategy._id} className={`p-4 rounded-xl border transition-all ${strategy.is_active ? 'bg-gray-50 dark:bg-dark-800/80 border-emerald-500/30 shadow-lg shadow-emerald-500/5' : 'bg-gray-50 dark:bg-dark-800/40 border-gray-200 dark:border-dark-700 hover:border-gray-300 dark:hover:border-dark-600'}`}>
                  <div className="flex justify-between items-start mb-2">
                    <div><h4 className="font-bold text-gray-900 dark:text-white text-sm">{strategy.name}</h4><p className="text-xs text-gray-500 dark:text-dark-400 mt-0.5">{strategy.index} • {strategy.quantity} Qty</p></div>
                    <button onClick={() => handleToggleStrategy(strategy._id, strategy.is_active)} className={`p-2 rounded-lg transition-all shadow-lg ${strategy.is_active ? 'bg-amber-500 text-white hover:bg-amber-600' : 'bg-emerald-600 text-white hover:bg-emerald-700'}`} title={strategy.is_active ? 'Stop Strategy' : 'Start Strategy'}>
                      {strategy.is_active ? <Pause className="w-3 h-3 fill-current" /> : <Play className="w-3 h-3 fill-current" />}
                    </button>
                  </div>
                  <div className="flex items-center justify-between pt-3 border-t border-gray-200 dark:border-dark-700/50 mt-3">
                    <div className="flex gap-2"><span className={`text-[10px] px-1.5 py-0.5 rounded font-bold uppercase ${strategy.is_active ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-gray-200 dark:bg-dark-700 text-gray-500 dark:text-dark-400'}`}>{strategy.is_active ? 'Running' : 'Stopped'}</span></div>
                    <p className={`text-sm font-bold font-mono ${getPnlClass(strategy.today_pnl || 0)}`}>{formatCurrency(strategy.today_pnl || 0)}</p>
                  </div>
                </div>
              ))) : (
                <div className="text-center py-10"><Target className="w-10 h-10 mx-auto text-gray-400 dark:text-dark-600 mb-3" /><p className="text-gray-500 dark:text-dark-400 text-sm">No strategies configured</p><Link to="/strategy" className="mt-3 text-blue-500 dark:text-blue-400 text-xs font-bold hover:underline">Create New</Link></div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Direction Analysis Modal */}
      <Modal isOpen={showDirectionModal} onClose={handleModalClose} title="" size="lg">
        {selectedDirectionData && <DirectionAnalysisContent direction={selectedDirectionData} loading={directionLoading} onRefresh={() => handleDirectionClick(selectedDirectionData.symbol)} />}
      </Modal>
    </div>
  )
}