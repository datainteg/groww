import { useEffect, useState, useMemo } from 'react'
import { 
  Activity, RefreshCw, X, DollarSign, PieChart, 
  BarChart3, CheckCircle2, TrendingUp, TrendingDown,
  Plus, ArrowUpRight, ArrowDownRight, Edit2, Calculator
} from 'lucide-react'
import { useTradeStore, useUIStore, useStrategyStore } from '../store' 
import { formatCurrency, getPnlClass } from '../utils/formatter'
import Modal from '../components/common/Modal'
import { tradeApi } from '../api/trade.api'
import { settingsApi } from '../api/settings.api'
import type { Trade } from '../types'

// Helper to enforce IST display
const formatDateTimeIST = (dateString: string | undefined) => {
  if (!dateString) return '-'
  
  let normalizeDate = dateString
  if (!dateString.endsWith('Z') && !dateString.includes('+')) {
    normalizeDate = `${dateString}Z`
  }

  try {
    const date = new Date(normalizeDate)
    return new Intl.DateTimeFormat('en-IN', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: true,
      timeZone: 'Asia/Kolkata'
    }).format(date)
  } catch (e) { return dateString }
}

export default function Trades() {
  const { 
    trades, activeTrades, dailyPnl, 
    fetchTrades, fetchActiveTrades, fetchPositions, fetchDailyPnl,
    exitTrade, modifyTrade
  } = useTradeStore()

  const { strategies, fetchStrategies } = useStrategyStore()
  const { addToast } = useUIStore()
  
  const [refreshing, setRefreshing] = useState(false)
  const [showManualModal, setShowManualModal] = useState(false)
  const [showModifyModal, setShowModifyModal] = useState(false)
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null)
  const [exiting, setExiting] = useState<string | null>(null)
  
  // Manual Trade Form State
  const [selectedStrategyId, setSelectedStrategyId] = useState('')
  const [manualQty, setManualQty] = useState(0)
  const [placingOrder, setPlacingOrder] = useState(false)
  
  // Modify Trade Form State
  const [slPoints, setSlPoints] = useState(0)
  const [targetPoints, setTargetPoints] = useState(0)
  const [modifyTrailingSL, setModifyTrailingSL] = useState(false)
  const [modifyTrailingValue, setModifyTrailingValue] = useState(10)
  const [modifying, setModifying] = useState(false)

  // --- Helper: Central Notification (Toast + Telegram) ---
  const notifyAction = async (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    addToast(type, message)
    try {
      const emoji = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️'
      await settingsApi.sendMessage(`${emoji} <b>Trade Alert</b>\n${message}`)
    } catch (e) {
      console.warn("Failed to send telegram notification", e)
    }
  }

  // --- Helper: Calculated Stats (Fixes 0% Win Rate Issue) ---
  const stats = useMemo(() => {
    // 1. Calculate from Trade History
    const closedTrades = trades.filter(t => t.status === 'CLOSED')
    const wins = closedTrades.filter(t => t.pnl > 0).length
    const losses = closedTrades.filter(t => t.pnl <= 0).length
    const totalTrades = wins + losses
    const winRate = totalTrades > 0 ? (wins / totalTrades) * 100 : 0
    
    // 2. Calculate Realized P&L locally if backend is zero
    const localRealized = closedTrades.reduce((sum, t) => sum + (t.pnl || 0), 0)
    
    // 3. Use Backend values if available, else fallback to local
    const finalRealized = (dailyPnl?.realized_pnl && dailyPnl.realized_pnl !== 0) 
      ? dailyPnl.realized_pnl 
      : localRealized

    const finalUnrealized = dailyPnl?.unrealized_pnl || 0
    
    return {
      totalPnl: finalRealized + finalUnrealized,
      realized: finalRealized,
      unrealized: finalUnrealized,
      winRate: (dailyPnl?.trades_today || 0) > 0
        ? ((dailyPnl?.winning || 0) / (dailyPnl?.trades_today || 1)) * 100
        : winRate,
      wins: dailyPnl?.winning || wins,
      losses: dailyPnl?.losing || losses
    }
  }, [trades, dailyPnl])

  const loadData = async () => {
    setRefreshing(true)
    try {
      await Promise.all([
        fetchTrades(), fetchActiveTrades(), fetchPositions(), fetchDailyPnl(), fetchStrategies()
      ])
      addToast('success', 'Trade data updated')
    } catch (err) {
      addToast('error', 'Failed to refresh data')
    } finally {
      setRefreshing(false)
    }
  }

  useEffect(() => {
    loadData()
    const interval = setInterval(() => {
      fetchActiveTrades(); fetchPositions(); fetchDailyPnl()
    }, 10000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    if (selectedStrategyId) {
      const strat = strategies.find(s => s._id === selectedStrategyId)
      if (strat) setManualQty(strat.quantity)
    }
  }, [selectedStrategyId, strategies])

  // --- 1. Exit Trade Handler ---
  const handleExit = async (tradeId: string) => {
    if (!confirm('Are you sure you want to exit this trade immediately?')) return
    setExiting(tradeId)
    try {
      await exitTrade(tradeId)
      notifyAction(`Manual Exit Executed for Trade ID: ${tradeId.slice(-6)}`, 'success')
      setTimeout(loadData, 500)
    } catch (err: any) {
      notifyAction(err.response?.data?.error || err.error || 'Failed to exit trade', 'error')
    } finally {
      setExiting(null)
    }
  }

  // --- 2. Modify Modal Logic ---
  const openModifyModal = (trade: Trade) => {
    setSelectedTrade(trade)
    const entry = trade.entry_price || 0
    const currentSLPoints = trade.stop_loss ? Math.abs(entry - trade.stop_loss) : 20
    const currentTargetPoints = trade.target ? Math.abs(trade.target - entry) : 40

    setSlPoints(parseFloat(currentSLPoints.toFixed(2)))
    setTargetPoints(parseFloat(currentTargetPoints.toFixed(2)))
    setModifyTrailingSL(trade.trailing_sl_enabled || false)
    setModifyTrailingValue(trade.trailing_sl_value || 10)
    setShowModifyModal(true)
  }

  const getCalculatedPrices = () => {
    if (!selectedTrade) return { slPrice: 0, targetPrice: 0 }
    
    const entry = selectedTrade.entry_price || 0
    const side = selectedTrade.side || 'BUY'
    
    let slPrice = 0, targetPrice = 0

    if (side === 'BUY') {
      slPrice = entry - slPoints
      targetPrice = entry + targetPoints
    } else {
      slPrice = entry + slPoints
      targetPrice = entry - targetPoints
    }

    return { slPrice: parseFloat(slPrice.toFixed(2)), targetPrice: parseFloat(targetPrice.toFixed(2)) }
  }

  const handleModify = async () => {
    if (!selectedTrade) return
    const { slPrice, targetPrice } = getCalculatedPrices()

    if (slPrice < 0 || targetPrice < 0) return addToast('error', 'Prices cannot be negative')

    setModifying(true)
    try {
      await modifyTrade(selectedTrade._id, {
        stop_loss: slPrice,
        target: targetPrice,
        trailing_sl_enabled: modifyTrailingSL,
        trailing_sl_value: modifyTrailingValue
      })
      
      const msg = `Trade Modified: ${selectedTrade.trading_symbol}\nNew SL: ${slPrice}\nNew Target: ${targetPrice}`
      notifyAction(msg, 'success')

      setShowModifyModal(false)
      setSelectedTrade(null)
      setTimeout(loadData, 500)
    } catch (err: any) {
      notifyAction(err.response?.data?.error || err.error || 'Failed to modify trade', 'error')
    } finally {
      setModifying(false)
    }
  }

  // --- 3. Manual Order Logic ---
  const handlePlaceOrder = async (transactionType: 'BUY' | 'SELL', optionType: 'CE' | 'PE') => {
    if (!selectedStrategyId) return addToast('error', 'Please select a strategy first')
    if (manualQty <= 0) return addToast('error', 'Quantity must be greater than 0')
    if (!confirm(`Confirm ${transactionType} ${optionType} order for ${manualQty} qty?`)) return

    setPlacingOrder(true)
    try {
      const strategy = strategies.find(s => s._id === selectedStrategyId)
      if (!strategy) throw new Error("Strategy not found")

      const result = await tradeApi.quickTrade({
        strategy_id: selectedStrategyId,
        option_type: optionType,
        transaction_type: transactionType,
        quantity: manualQty
      })

      const tradeData = result.trade_id ? result : (result as any).trade
      const tradeId = tradeData.trade_id || tradeData._id
      const entryPrice = tradeData.entry_price
      const symbol = tradeData.trading_symbol || tradeData.symbol || 'Unknown'

      if (tradeId && entryPrice) {
        const slPts = strategy.stop_loss || 20
        const tgtPts = strategy.target || 40
        let absSL = 0, absTarget = 0

        if (transactionType === 'BUY') {
          absSL = entryPrice - slPts
          absTarget = entryPrice + tgtPts
        } else {
          absSL = entryPrice + slPts
          absTarget = entryPrice - tgtPts
        }

        await modifyTrade(tradeId, {
          stop_loss: parseFloat(absSL.toFixed(2)),
          target: parseFloat(absTarget.toFixed(2)),
          trailing_sl_enabled: strategy.trailing_sl_enabled,
          trailing_sl_value: strategy.trailing_sl_value
        })

        const msg = `Manual Order Executed:\n${symbol} (${transactionType})\nQty: ${manualQty} @ ₹${entryPrice}`
        notifyAction(msg, 'success')
      } else {
        notifyAction('Order placed, but failed to apply SL/Target automatically.', 'info')
      }
      
      setShowManualModal(false)
      setTimeout(loadData, 1000) 
    } catch (err: any) {
      notifyAction(err.response?.data?.error || err.message || 'Failed to place order', 'error')
    } finally {
      setPlacingOrder(false)
    }
  }

  const { slPrice, targetPrice } = getCalculatedPrices()

  return (
    <div className="space-y-6 animate-fade-in pb-10">
      
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white tracking-tight flex items-center gap-3">
            <BarChart3 className="w-7 h-7 text-blue-500" />
            Trades & Positions
          </h1>
          <p className="text-gray-500 dark:text-dark-400 mt-1 text-sm font-medium">
            Monitor active positions and execute manual trades.
          </p>
        </div>
        <div className="flex gap-3">
          <button onClick={() => setShowManualModal(true)} className="btn-primary flex items-center gap-2 shadow-lg shadow-blue-500/20 py-2">
            <Plus className="w-4 h-4" /> New Trade
          </button>
          <button onClick={loadData} disabled={refreshing} className="btn-secondary group py-2">
            <RefreshCw className={`w-4 h-4 group-hover:text-blue-400 transition-colors ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* P&L Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total P&L */}
        <div className="card p-4 border border-gray-200 dark:border-dark-700 bg-white dark:bg-dark-900 shadow-sm relative overflow-hidden">
          <div className="flex justify-between items-start mb-2">
            <p className="text-gray-500 dark:text-gray-400 text-xs font-bold uppercase tracking-wider">Total P&L</p>
            <div className={`p-1.5 rounded-lg ${stats.totalPnl >= 0 ? 'bg-emerald-100 text-emerald-600' : 'bg-red-100 text-red-600'}`}>
              <DollarSign className="w-4 h-4" />
            </div>
          </div>
          <h3 className={`text-2xl font-mono font-bold ${getPnlClass(stats.totalPnl)}`}>
            {formatCurrency(stats.totalPnl)}
          </h3>
          {/* Progress Bar */}
          <div className="absolute bottom-0 left-0 w-full h-1 bg-gray-200 dark:bg-dark-700">
            <div className={`h-full ${stats.totalPnl >= 0 ? 'bg-emerald-500' : 'bg-red-500'}`} style={{ width: '100%' }} />
          </div>
        </div>

        {/* Realized P&L */}
        <div className="card p-4 border border-gray-200 dark:border-dark-700 bg-white dark:bg-dark-900 shadow-sm">
          <div className="flex justify-between items-start mb-2">
            <p className="text-gray-500 dark:text-gray-400 text-xs font-bold uppercase tracking-wider">Realized P&L</p>
            <div className="p-1.5 rounded-lg bg-gray-100 dark:bg-dark-700 text-gray-500">
              <CheckCircle2 className="w-4 h-4" />
            </div>
          </div>
          <h3 className={`text-xl font-mono font-bold ${getPnlClass(stats.realized)}`}>
            {formatCurrency(stats.realized)}
          </h3>
        </div>

        {/* Unrealized P&L */}
        <div className="card p-4 border border-gray-200 dark:border-dark-700 bg-white dark:bg-dark-900 shadow-sm">
          <div className="flex justify-between items-start mb-2">
            <p className="text-gray-500 dark:text-gray-400 text-xs font-bold uppercase tracking-wider">Unrealized P&L</p>
            <div className="p-1.5 rounded-lg bg-gray-100 dark:bg-dark-700 text-gray-500">
              <Activity className="w-4 h-4" />
            </div>
          </div>
          <h3 className={`text-xl font-mono font-bold ${getPnlClass(stats.unrealized)}`}>
            {formatCurrency(stats.unrealized)}
          </h3>
        </div>

        {/* Win Rate */}
        <div className="card p-4 border border-gray-200 dark:border-dark-700 bg-white dark:bg-dark-900 shadow-sm">
          <div className="flex justify-between items-start mb-2">
            <p className="text-gray-500 dark:text-gray-400 text-xs font-bold uppercase tracking-wider">Win Rate</p>
            <div className="p-1.5 rounded-lg bg-purple-100 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400">
              <PieChart className="w-4 h-4" />
            </div>
          </div>
          <h3 className="text-xl font-bold text-gray-900 dark:text-white">
            {stats.winRate.toFixed(1)}%
          </h3>
          <div className="flex gap-2 text-[10px] font-bold mt-1">
            <span className="text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-100">W: {stats.wins}</span>
            <span className="text-red-600 bg-red-50 px-1.5 py-0.5 rounded border border-red-100">L: {stats.losses}</span>
          </div>
        </div>
      </div>

      {/* Active Positions Table */}
      {activeTrades.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500"></span>
              </span>
              Active Positions <span className="bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 text-xs px-2 py-0.5 rounded-full">{activeTrades.length}</span>
            </h2>
          </div>

          <div className="card overflow-hidden bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-50 dark:bg-dark-800/50 text-gray-500 dark:text-dark-400 font-bold text-xs uppercase border-b border-gray-200 dark:border-dark-700">
                  <tr>
                    <th className="px-4 py-3">Symbol</th>
                    <th className="px-4 py-3">Side</th>
                    <th className="px-4 py-3">Qty</th>
                    <th className="px-4 py-3">Entry</th>
                    <th className="px-4 py-3">LTP</th>
                    <th className="px-4 py-3">SL</th>
                    <th className="px-4 py-3">Target</th>
                    <th className="px-4 py-3 text-right">P&L</th>
                    <th className="px-4 py-3 text-center">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-dark-700">
                  {activeTrades.map(trade => {
                    const currentPrice = trade.ltp || trade.entry_price
                    const side = trade.side || 'BUY'
                    const symbol = trade.trading_symbol || 'Unknown'
                    const pnl = (currentPrice - trade.entry_price) * trade.quantity * (side === 'BUY' ? 1 : -1)
                    
                    return (
                      <tr key={trade._id} className="hover:bg-gray-50 dark:hover:bg-dark-800/30 transition-colors">
                        <td className="px-4 py-3 font-mono font-bold text-gray-900 dark:text-white">{symbol}</td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider ${
                            side === 'BUY' 
                              ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/20' 
                              : 'bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-500/20'
                          }`}>
                            {side}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-gray-900 dark:text-white">{trade.quantity}</td>
                        <td className="px-4 py-3 text-gray-500 dark:text-dark-300 font-mono">₹{trade.entry_price.toFixed(2)}</td>
                        <td className="px-4 py-3 text-gray-900 dark:text-white font-mono font-bold">₹{currentPrice.toFixed(2)}</td>
                        <td className="px-4 py-3 text-red-500 dark:text-red-400 font-mono">₹{trade.stop_loss.toFixed(2)}</td>
                        <td className="px-4 py-3 text-emerald-500 dark:text-emerald-400 font-mono">₹{trade.target.toFixed(2)}</td>
                        <td className={`px-4 py-3 font-mono font-bold text-right ${getPnlClass(pnl)}`}>
                          {formatCurrency(pnl)}
                        </td>
                        <td className="px-4 py-3 text-center">
                          <div className="flex items-center justify-center gap-2">
                            <button onClick={() => openModifyModal(trade)} className="p-1.5 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 text-blue-500 transition-colors">
                              <Edit2 className="w-4 h-4" />
                            </button>
                            <button onClick={() => handleExit(trade._id)} disabled={exiting === trade._id} className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-red-500 transition-colors disabled:opacity-50">
                              {exiting === trade._id ? <RefreshCw className="w-4 h-4 animate-spin"/> : <X className="w-4 h-4" />}
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* --- Trade History --- */}
      <div className="space-y-4">
        <h2 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <RefreshCw className="w-5 h-5 text-gray-500 dark:text-dark-400" /> Trade History
        </h2>
        {trades.length > 0 && (
          <div className="card overflow-hidden bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-50 dark:bg-dark-800/50 text-gray-500 dark:text-dark-400 font-bold text-xs uppercase border-b border-gray-200 dark:border-dark-700">
                  <tr>
                    <th className="px-4 py-3">Time</th>
                    <th className="px-4 py-3">Symbol</th>
                    <th className="px-4 py-3">Side</th>
                    <th className="px-4 py-3">Qty</th>
                    <th className="px-4 py-3">Entry</th>
                    <th className="px-4 py-3">Exit</th>
                    <th className="px-4 py-3">P&L</th>
                    <th className="px-4 py-3 text-center">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-dark-700">
                  {trades.slice(0, 20).map(trade => {
                    // FIX: Backend sends transaction_type, not side
                    const side = trade.side || trade.transaction_type || 'BUY'
                    const symbol = trade.trading_symbol || trade.symbol || 'Unknown'
                    return (
                      <tr key={trade._id} className="hover:bg-gray-50 dark:hover:bg-dark-800/30 transition-colors">
                        <td className="px-4 py-3 text-gray-500 dark:text-dark-400 text-xs font-mono">
                          {formatDateTimeIST(trade.entry_time)}
                        </td>
                        <td className="px-4 py-3 font-mono font-medium text-gray-900 dark:text-white">{symbol}</td>
                        <td className="px-4 py-3">
                          <span className={`flex items-center gap-1 text-xs font-bold ${
                            side === 'BUY' ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'
                          }`}>
                            {side === 'BUY' ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                            {side}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-gray-500 dark:text-dark-300">{trade.quantity}</td>
                        <td className="px-4 py-3 text-gray-500 dark:text-dark-300 font-mono">₹{trade.entry_price?.toFixed(2) || '0.00'}</td>
                        <td className="px-4 py-3 text-gray-500 dark:text-dark-300 font-mono">
                          {trade.exit_price ? `₹${trade.exit_price.toFixed(2)}` : '-'}
                        </td>
                        <td className={`px-4 py-3 font-mono font-bold ${getPnlClass(trade.pnl)}`}>
                          {trade.status === 'CLOSED' ? formatCurrency(trade.pnl) : '-'}
                        </td>
                        <td className="px-4 py-3 text-center">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                            trade.status === 'CLOSED' 
                              ? 'bg-gray-100 text-gray-600 dark:bg-dark-700 dark:text-gray-400' 
                              : 'bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400'
                          }`}>
                            {trade.status}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Manual Trade Modal */}
      <Modal isOpen={showManualModal} onClose={() => setShowManualModal(false)} title="Execute Manual Trade" size="lg">
        <div className="space-y-6">
          <div className="space-y-2">
            <label className="text-sm font-bold text-gray-500 dark:text-gray-400 uppercase">Select Strategy</label>
            <select value={selectedStrategyId} onChange={(e) => setSelectedStrategyId(e.target.value)} className="input-field w-full bg-white dark:bg-dark-900 border-gray-300 dark:border-dark-700 text-gray-900 dark:text-white p-3">
              <option value="">-- Choose a Strategy to Apply Rules --</option>
              {strategies.filter(s => s.is_active).length > 0 ? (
                strategies.filter(s => s.is_active).map(s => <option key={s._id} value={s._id}>{s.name} ({s.index}) - {s.quantity} Qty</option>)
              ) : <option disabled>No active strategies found</option>}
            </select>
          </div>
          {selectedStrategyId && (
            <div className="p-4 bg-gray-50 dark:bg-dark-800/50 border border-gray-200 dark:border-dark-700 rounded-xl animate-fade-in">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <p className="text-xs text-gray-500 uppercase font-bold">Quantity</p>
                  <input type="number" value={manualQty} onChange={(e) => setManualQty(Number(e.target.value))} className="bg-transparent text-xl font-bold text-gray-900 dark:text-white border-b border-gray-300 dark:border-gray-600 w-24 focus:outline-none focus:border-blue-500"/>
                </div>
                <div className="text-right">
                  <p className="text-xs text-gray-500 uppercase font-bold">Order Type</p>
                  <span className="text-sm font-bold text-blue-500 bg-blue-100 dark:bg-blue-500/10 px-2 py-1 rounded">MARKET</span>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <button onClick={() => handlePlaceOrder('BUY', 'CE')} disabled={placingOrder} className="w-full py-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold shadow-lg flex flex-col items-center gap-1"><span className="flex items-center gap-2 text-lg"><ArrowUpRight className="w-5 h-5"/> BUY CALL (CE)</span></button>
                  <button onClick={() => handlePlaceOrder('SELL', 'CE')} disabled={placingOrder} className="w-full py-3 rounded-xl bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-500/30">SELL CALL (CE)</button>
                </div>
                <div className="space-y-2">
                  <button onClick={() => handlePlaceOrder('BUY', 'PE')} disabled={placingOrder} className="w-full py-4 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold shadow-lg flex flex-col items-center gap-1"><span className="flex items-center gap-2 text-lg"><ArrowDownRight className="w-5 h-5"/> BUY PUT (PE)</span></button>
                  <button onClick={() => handlePlaceOrder('SELL', 'PE')} disabled={placingOrder} className="w-full py-3 rounded-xl bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-500/30">SELL PUT (PE)</button>
                </div>
              </div>
            </div>
          )}
          {placingOrder && <div className="flex justify-center text-blue-500 font-bold animate-pulse">Executing Order...</div>}
        </div>
      </Modal>

      {/* Modify Modal */}
      <Modal isOpen={showModifyModal} onClose={() => setShowModifyModal(false)} title="Modify Trade Risk" size="md">
        {selectedTrade && (
          <div className="space-y-6">
            <div className="p-4 bg-gray-50 dark:bg-dark-800/50 rounded-xl border border-gray-200 dark:border-dark-700">
              <div className="flex justify-between items-center mb-3">
                <span className={`px-2 py-1 rounded text-xs font-bold uppercase tracking-wider ${
                  (selectedTrade.side || 'BUY') === 'BUY' ? 'bg-emerald-100 text-emerald-600' : 'bg-red-100 text-red-600'
                }`}>{selectedTrade.side || 'BUY'}</span>
                <span className="text-lg font-mono font-bold text-gray-900 dark:text-white">Entry: ₹{selectedTrade.entry_price.toFixed(2)}</span>
              </div>
              <div className="flex items-center gap-2 text-sm text-gray-500"><Calculator className="w-4 h-4" /><span>Adjust points to calculate new SL & Target</span></div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-bold text-gray-500 uppercase">SL Points</label>
                <input type="number" step="1" value={slPoints} onChange={(e) => setSlPoints(Number(e.target.value))} className="input-field w-full bg-white dark:bg-dark-900 border-red-300 dark:border-red-900/50 text-gray-900 dark:text-white p-3 font-mono text-lg"/>
                <p className="text-xs text-red-500 mt-1">Price: ₹{slPrice.toFixed(2)}</p>
              </div>
              <div>
                <label className="text-xs font-bold text-gray-500 uppercase">Target Points</label>
                <input type="number" step="1" value={targetPoints} onChange={(e) => setTargetPoints(Number(e.target.value))} className="input-field w-full bg-white dark:bg-dark-900 border-green-300 dark:border-green-900/50 text-gray-900 dark:text-white p-3 font-mono text-lg"/>
                <p className="text-xs text-green-500 mt-1">Price: ₹{targetPrice.toFixed(2)}</p>
              </div>
            </div>
            <div className="p-4 bg-gray-50 dark:bg-dark-800/50 rounded-xl border border-gray-200 dark:border-dark-700 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <input type="checkbox" checked={modifyTrailingSL} onChange={(e) => setModifyTrailingSL(e.target.checked)} className="w-4 h-4 rounded bg-gray-200 dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-blue-600"/>
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Trailing SL</span>
              </div>
              {modifyTrailingSL && (
                <div className="flex items-center gap-2">
                  <input type="number" value={modifyTrailingValue} onChange={(e) => setModifyTrailingValue(Number(e.target.value))} className="w-16 input-field h-8 bg-white dark:bg-dark-900 border-gray-300 dark:border-gray-700 text-gray-900 dark:text-white text-center font-mono"/>
                  <span className="text-xs text-gray-500">Pts</span>
                </div>
              )}
            </div>
            <div className="flex gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
              <button onClick={() => setShowModifyModal(false)} className="btn-ghost flex-1 text-gray-600 dark:text-gray-400">Cancel</button>
              <button onClick={handleModify} disabled={modifying} className="btn-primary flex-[2]">{modifying ? 'Updating...' : 'Confirm Changes'}</button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}