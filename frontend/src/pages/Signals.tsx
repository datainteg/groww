import { useEffect, useState } from 'react'
import { 
  TrendingUp, TrendingDown, Activity, Zap, BarChart3,
  Target, RefreshCw,
  Layers, Clock
} from 'lucide-react'
import { useStrategyStore } from '../store/strategy.store'
import { config } from '../config'
import { formatCurrency } from '../utils/formatter'

// Helper to get color based on signal
const getSignalColor = (signal: string | undefined | null) => {
  if (signal === 'BULLISH') return 'text-emerald-500 dark:text-emerald-400'
  if (signal === 'BEARISH') return 'text-red-500 dark:text-red-400'
  return 'text-gray-500 dark:text-gray-400'
}

const getSignalBg = (signal: string | undefined | null) => {
  if (signal === 'BULLISH') return 'bg-emerald-100 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20'
  if (signal === 'BEARISH') return 'bg-red-100 dark:bg-red-500/10 border-red-200 dark:border-red-500/20'
  return 'bg-gray-100 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700'
}

export default function Signals() {
  const { decision, decisions, fetchDecision, isAnalyzing } = useStrategyStore()
  const [selectedSymbol, setSelectedSymbol] = useState('NIFTY')
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date())

  // Poll for signals every 10 seconds
  useEffect(() => {
    const load = async () => {
      await fetchDecision(selectedSymbol, 5)
      setLastUpdated(new Date())
    }
    load()
    const interval = setInterval(load, 10000)
    return () => clearInterval(interval)
  }, [selectedSymbol])

  // Get data for selected symbol
  const data = decisions[selectedSymbol] || decision

  // Fallback if no data
  if (!data && isAnalyzing) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center text-center">
        <div className="relative">
          <div className="w-16 h-16 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin"></div>
          <Zap className="w-6 h-6 text-blue-500 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 animate-pulse" />
        </div>
        <h2 className="mt-6 text-xl font-bold text-gray-900 dark:text-white">Analyzing {selectedSymbol} Market Data</h2>
        <p className="text-gray-500 dark:text-gray-400 mt-2">Calculating 67 indicators & detecting patterns...</p>
      </div>
    )
  }

  if (!data) return null

  return (
    <div className="space-y-6 animate-fade-in pb-10">
      
      {/* --- Header --- */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Zap className="w-6 h-6 text-blue-500" />
            AI Signal Analysis
          </h1>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-1 flex items-center gap-2">
            <Clock className="w-3 h-3" /> Updated: {lastUpdated.toLocaleTimeString()} 
            <span className="text-gray-400 dark:text-gray-600">•</span>
            Interval: 5m
          </p>
        </div>
        
        {/* Symbol Selector */}
        <div className="flex bg-gray-100 dark:bg-gray-900 p-1 rounded-xl border border-gray-200 dark:border-gray-700">
          {config.INDICES.map(sym => (
            <button 
              key={sym} 
              onClick={() => setSelectedSymbol(sym)} 
              className={`px-4 py-2 text-sm font-bold rounded-lg transition-all ${
                selectedSymbol === sym 
                  ? 'bg-blue-600 text-white shadow-lg' 
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-white dark:hover:bg-gray-800'
              }`}
            >
              {sym}
            </button>
          ))}
        </div>
      </div>

      {/* --- Main Decision Card --- */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className={`lg:col-span-2 rounded-2xl border p-6 relative overflow-hidden ${getSignalBg(data.signal)}`}>
          <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
            
            {/* Left: Signal Status */}
            <div className="flex items-center gap-5">
              <div className={`w-20 h-20 rounded-2xl flex items-center justify-center shadow-2xl ${
                data.signal === 'BULLISH' ? 'bg-emerald-500 text-white' : 
                data.signal === 'BEARISH' ? 'bg-red-500 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-300'
              }`}>
                {data.signal === 'BULLISH' ? <TrendingUp className="w-10 h-10" /> : 
                 data.signal === 'BEARISH' ? <TrendingDown className="w-10 h-10" /> : 
                 <Activity className="w-10 h-10" />}
              </div>
              
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-mono text-gray-600 dark:text-gray-400 bg-white/50 dark:bg-black/20 px-2 py-0.5 rounded border border-gray-200 dark:border-transparent">
                    {data.symbol}
                  </span>
                  <span className="text-sm font-bold text-gray-800 dark:text-gray-300 bg-white/50 dark:bg-black/20 px-2 py-0.5 rounded border border-gray-200 dark:border-transparent">
                    ₹{data.current_price?.toLocaleString()}
                  </span>
                </div>
                <h2 className={`text-4xl font-black tracking-tight ${getSignalColor(data.signal)}`}>
                  {data.signal || 'NEUTRAL'}
                </h2>
                <p className="text-gray-600 dark:text-gray-300 font-medium mt-1">
                  {data.recommendation || 'Wait for clearer signals'}
                </p>
              </div>
            </div>

            {/* Right: Confidence */}
            <div className="text-right bg-white/50 dark:bg-black/20 p-4 rounded-xl backdrop-blur-sm border border-gray-200/50 dark:border-white/5 shadow-sm">
              <p className="text-xs text-gray-500 dark:text-gray-400 uppercase font-bold tracking-wider mb-1">AI Confidence</p>
              <div className="flex items-end justify-end gap-1">
                <span className="text-4xl font-bold text-gray-900 dark:text-white">
                  {((data.confidence || 0) * 100).toFixed(0)}
                </span>
                <span className="text-lg text-gray-500 dark:text-gray-400 mb-1">%</span>
              </div>
              <div className="w-32 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full mt-2 overflow-hidden">
                <div 
                  className={`h-full rounded-full transition-all duration-1000 ${data.signal === 'BEARISH' ? 'bg-red-500' : 'bg-emerald-500'}`} 
                  style={{ width: `${(data.confidence || 0) * 100}%` }}
                />
              </div>
            </div>
          </div>

          {/* Background Glow - Only visible in dark mode or subtly in light mode */}
          <div className={`absolute top-0 right-0 w-64 h-64 blur-[100px] opacity-10 dark:opacity-20 pointer-events-none rounded-full ${
            data.signal === 'BULLISH' ? 'bg-emerald-500' : data.signal === 'BEARISH' ? 'bg-red-500' : 'bg-blue-500'
          }`} />
        </div>

        {/* --- Market Regime & Scores --- */}
        <div className="grid grid-rows-2 gap-4">
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-5 flex items-center justify-between shadow-sm">
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400 uppercase font-bold mb-1">Market Regime</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">{data.market_regime}</p>
            </div>
            <div className={`px-3 py-1.5 rounded-lg text-xs font-bold border ${
              data.market_regime === 'TRENDING' 
                ? 'bg-purple-100 dark:bg-purple-500/20 text-purple-600 dark:text-purple-400 border-purple-200 dark:border-purple-500/30' 
                : 'bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-500/30'
            }`}>
              {data.market_regime === 'TRENDING' ? 'High Volatility' : 'Low Volatility'}
            </div>
          </div>

          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-5 shadow-sm">
            <div className="flex justify-between items-center mb-3">
              <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400 uppercase">Bullish Score</span>
              <span className="text-xs font-bold text-red-600 dark:text-red-400 uppercase">Bearish Score</span>
            </div>
            <div className="flex h-3 rounded-full overflow-hidden bg-gray-200 dark:bg-gray-700">
              <div 
                className="bg-emerald-500 transition-all duration-700" 
                style={{ width: `${(data.bullish_score || 0) * 100}%` }} 
              />
              <div 
                className="bg-red-500 transition-all duration-700" 
                style={{ width: `${(data.bearish_score || 0) * 100}%` }} 
              />
            </div>
            <div className="flex justify-between mt-1 text-xs text-gray-500 dark:text-gray-400 font-mono">
              <span>{((data.bullish_score || 0) * 100).toFixed(0)}%</span>
              <span>{((data.bearish_score || 0) * 100).toFixed(0)}%</span>
            </div>
          </div>
        </div>
      </div>

      {/* --- Component Breakdown Grid --- */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: 'Momentum', score: data.momentum?.score, icon: Activity },
          { label: 'Volatility', score: data.volatility?.score, icon: RefreshCw },
          { label: 'Pattern', score: data.scores?.pattern_score, icon: Layers },
          { label: 'Volume', score: data.volume?.score, icon: BarChart3 },
          { label: 'Support/Res', score: data.support_resistance?.score, icon: Target },
        ].map((item, i) => (
          <div key={i} className="bg-white dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 p-4 rounded-xl flex flex-col items-center justify-center text-center hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors shadow-sm">
            <item.icon className="w-5 h-5 text-gray-400 dark:text-gray-500 mb-2" />
            <p className="text-xs text-gray-500 dark:text-gray-400 uppercase font-bold">{item.label}</p>
            <p className={`text-xl font-bold mt-1 ${
              (item.score || 0) > 0.6 ? 'text-emerald-500 dark:text-emerald-400' : (item.score || 0) < 0.4 ? 'text-red-500 dark:text-red-400' : 'text-yellow-500 dark:text-yellow-400'
            }`}>
              {((item.score || 0) * 100).toFixed(0)}%
            </p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* --- Left Column: Technical Indicators --- */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden shadow-sm">
            <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-850 flex justify-between items-center">
              <h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2">
                <Activity className="w-4 h-4 text-blue-500" /> Technical Indicators
              </h3>
              <span className="text-xs text-gray-500 dark:text-gray-500 bg-gray-200 dark:bg-gray-900 px-2 py-1 rounded">Momentum & Trend</span>
            </div>
            <div className="divide-y divide-gray-200 dark:divide-gray-700/50">
              {/* Dynamic Indicator Rows from 'momentum.details' */}
              {Object.entries(data.momentum?.details || {}).map(([key, ind]: any) => (
                <div key={key} className="px-6 py-4 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-700/20 transition-colors">
                  <div>
                    <p className="text-sm font-bold text-gray-700 dark:text-gray-300 uppercase">{key.replace('_', ' ')}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-500 font-mono mt-0.5">Value: {ind.value?.toFixed(2)}</p>
                  </div>
                  <div className={`px-3 py-1 rounded text-xs font-bold border ${getSignalBg(ind.signal)} ${getSignalColor(ind.signal)}`}>
                    {ind.signal}
                  </div>
                </div>
              ))}
              
              {/* Volatility Indicators */}
              <div className="px-6 py-4 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-700/20 bg-gray-50 dark:bg-gray-800/30">
                <div>
                  <p className="text-sm font-bold text-gray-700 dark:text-gray-300 uppercase">INDIA VIX</p>
                  <p className="text-xs text-gray-500 dark:text-gray-500 font-mono">
                    Val: {data.volatility?.details?.india_vix?.value?.toFixed(2)}
                  </p>
                </div>
                <div className="text-xs font-bold text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-800 px-3 py-1 rounded border border-gray-200 dark:border-gray-700">
                  {data.volatility?.details?.india_vix?.regime || 'NORMAL'}
                </div>
              </div>
            </div>
          </div>

          {/* --- Pattern Recognition --- */}
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden shadow-sm">
            <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-850">
              <h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2">
                <Layers className="w-4 h-4 text-purple-500" /> 
                Detected Patterns <span className="text-xs bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 px-2 py-0.5 rounded-full">{data.patterns?.length || 0}</span>
              </h3>
            </div>
            
            {data.patterns && data.patterns.length > 0 ? (
              <div className="p-4 grid gap-4">
                {data.patterns.map((pat: any, i: number) => (
                  <div key={i} className={`p-4 rounded-xl border relative overflow-hidden ${getSignalBg(pat.signal)}`}>
                    <div className="flex justify-between items-start mb-3">
                      <div>
                        <h4 className="font-bold text-gray-900 dark:text-white text-lg capitalize">{pat.pattern.replace(/_/g, ' ')}</h4>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                            pat.signal === 'BULLISH' 
                              ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400' 
                              : 'bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-400'
                          }`}>
                            {pat.signal}
                          </span>
                          <span className="text-xs text-gray-500 dark:text-gray-400">Conf: {(pat.confidence * 100).toFixed(0)}%</span>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-[10px] text-gray-500 dark:text-gray-500 uppercase font-bold">Target</p>
                        <p className="text-lg font-mono font-bold text-gray-900 dark:text-white">{formatCurrency(pat.target)}</p>
                      </div>
                    </div>
                    
                    <div className="grid grid-cols-3 gap-2 pt-3 border-t border-gray-200 dark:border-gray-700/50">
                      <div className="bg-white/50 dark:bg-black/20 p-2 rounded text-center">
                        <p className="text-[10px] text-gray-500">Entry</p>
                        <p className="text-xs font-mono text-blue-500 dark:text-blue-300">{formatCurrency(pat.entry)}</p>
                      </div>
                      <div className="bg-white/50 dark:bg-black/20 p-2 rounded text-center">
                        <p className="text-[10px] text-gray-500">Stop Loss</p>
                        <p className="text-xs font-mono text-red-500 dark:text-red-300">{formatCurrency(pat.stop_loss)}</p>
                      </div>
                      <div className="bg-white/50 dark:bg-black/20 p-2 rounded text-center">
                        <p className="text-[10px] text-gray-500">Risk/Reward</p>
                        <p className="text-xs font-mono text-emerald-500 dark:text-emerald-300">
                          {(() => {
                            const risk = Math.abs(pat.entry - pat.stop_loss)
                            return risk > 0
                              ? `1 : ${(Math.abs(pat.target - pat.entry) / risk).toFixed(1)}`
                              : 'N/A'
                          })()}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-8 text-center text-gray-500 dark:text-gray-500">
                <Layers className="w-12 h-12 mx-auto mb-3 opacity-20" />
                <p>No clear chart patterns detected at this moment.</p>
              </div>
            )}
          </div>
        </div>

        {/* --- Right Column: Support & Resistance --- */}
        <div className="space-y-6">
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden shadow-sm">
            <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-850">
              <h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2">
                <Target className="w-4 h-4 text-red-500 dark:text-red-400" /> Key Levels
              </h3>
            </div>
            <div className="p-6 relative">
              <div className="absolute left-1/2 top-4 bottom-4 w-0.5 bg-gray-200 dark:bg-gray-700 -translate-x-1/2" />
              
              <div className="space-y-6 relative z-10">
                {/* Resistance */}
                <div className="space-y-2">
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-bold text-red-500 dark:text-red-400">R2</span>
                    <span className="font-mono bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-400 px-2 py-0.5 rounded">{data.support_resistance?.levels?.r2?.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-bold text-red-500 dark:text-red-400">R1</span>
                    <span className="font-mono bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-400 px-2 py-0.5 rounded">{data.support_resistance?.levels?.r1?.toFixed(2)}</span>
                  </div>
                </div>

                {/* Pivot / Current */}
                <div className="bg-white dark:bg-gray-900 border border-blue-200 dark:border-blue-500/30 rounded-lg p-3 text-center shadow-sm dark:shadow-lg my-4">
                  <p className="text-[10px] text-blue-500 dark:text-blue-400 uppercase font-bold tracking-wider mb-1">Pivot Point</p>
                  <p className="text-lg font-mono font-bold text-gray-900 dark:text-white">{data.support_resistance?.levels?.pivot?.toFixed(2)}</p>
                </div>

                {/* Support */}
                <div className="space-y-2">
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-bold text-emerald-500 dark:text-emerald-400">S1</span>
                    <span className="font-mono bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 px-2 py-0.5 rounded">{data.support_resistance?.levels?.s1?.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-bold text-emerald-500 dark:text-emerald-400">S2</span>
                    <span className="font-mono bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 px-2 py-0.5 rounded">{data.support_resistance?.levels?.s2?.toFixed(2)}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-5 shadow-sm">
            <h3 className="font-bold text-gray-900 dark:text-white text-sm mb-4">Volume Analysis</h3>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-500 dark:text-gray-400">Volume Trend</span>
              <span className={`text-sm font-bold ${data.volume?.confirmed ? 'text-emerald-500 dark:text-emerald-400' : 'text-gray-500'}`}>
                {data.volume?.confirmed ? 'High Vol Confirmed' : 'Low / Unconfirmed'}
              </span>
            </div>
            <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div 
                className="h-full bg-blue-500" 
                style={{ width: `${(data.volume?.score || 0) * 100}%` }} 
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}