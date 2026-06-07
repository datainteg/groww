import { useEffect, useRef, useState, useCallback } from 'react'
import { createChart, ColorType, CrosshairMode, IChartApi, ISeriesApi, LineStyle, Time } from 'lightweight-charts'
import { 
  Activity, RefreshCw,
  TrendingUp, ChevronDown, Zap, Target,
  Plus, Trash2, X, PenTool
} from 'lucide-react'
import { useStrategyStore, useDirectionStore, useUIStore } from '../store'
import { strategyApi } from '../api/strategy.api'
import { config } from '../config'
import { calculateSMA, calculateEMA, calculateBollingerBands } from '../utils/indicators'
import { MarketDirectionCard } from '../components/direction'
import Modal from '../components/common/Modal'
import type { Candle } from '../types'

// Types
type IndicatorType = 'SMA' | 'EMA' | 'BOLLINGER' | 'RSI' | 'NONE'

interface CustomLine {
  id: string
  price: number
  label: string
  color: string
  visible: boolean
}

// Helper for IST Time Formatting
const formatTimeIST = (timestamp: number) => {
  return new Date(timestamp * 1000).toLocaleTimeString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  })
}

export default function Charts() {
  // --- Stores & State ---
  const { decision, fetchDecision } = useStrategyStore()
  const { directions, fetchDirection } = useDirectionStore()
  const { addToast } = useUIStore()
  
  const [symbol, setSymbol] = useState('NIFTY')
  const [interval, setInterval] = useState('5')
  const [candles, setCandles] = useState<Candle[]>([])
  const [loading, setLoading] = useState(false)
  
  // UI State
  const [activeIndicator, setActiveIndicator] = useState<IndicatorType>('NONE')
  const [showAIOverlay, setShowAIOverlay] = useState(true)
  const [showLevels, setShowLevels] = useState(true)
  const [showDirectionPanel, setShowDirectionPanel] = useState(false)
  const [showLinesPanel, setShowLinesPanel] = useState(false)

  // Custom Line State
  const [customLines, setCustomLines] = useState<CustomLine[]>([])
  const [isDrawing, setIsDrawing] = useState(false)
  const [lineModal, setLineModal] = useState<{ open: boolean; price: number }>({ open: false, price: 0 })
  const [lineForm, setLineForm] = useState({ label: '', color: '#f59e0b' })

  // Chart Refs
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null)
  const indicatorSeriesRef = useRef<ISeriesApi<"Line">[]>([])
  const priceLinesRef = useRef<any[]>([]) // System Levels
  const customPriceLinesRef = useRef<any[]>([]) // User Custom Lines
  
  const shouldFitContent = useRef(false)
  const currentDirection = directions[symbol] || null

  // --- 1. Load Saved Lines from LocalStorage ---
  useEffect(() => {
    const saved = localStorage.getItem(`chart_lines_${symbol}`)
    if (saved) {
      try {
        setCustomLines(JSON.parse(saved))
      } catch (e) {
        console.error("Failed to load saved lines")
      }
    } else {
      setCustomLines([])
    }
  }, [symbol])

  // --- 2. Data Fetching ---
  // Track the latest selected symbol so an in-flight request for a PREVIOUS
  // symbol can't overwrite the chart after the user switches (race guard).
  const latestSymbolRef = useRef(symbol)
  useEffect(() => { latestSymbolRef.current = symbol }, [symbol])

  const loadData = useCallback(async (isFreshLoad = false) => {
    if (isFreshLoad) {
      setLoading(true)
      shouldFitContent.current = true
    }

    try {
      // Fetch Candles
      const res = await strategyApi.getCandles(symbol, interval, 300)
      // Discard a stale response if the symbol changed while this was in flight.
      if (symbol !== latestSymbolRef.current) return
      const data = (res.candles || []).sort((a, b) => a.timestamp - b.timestamp)
      const uniqueData = data.filter((v, i, a) => i === 0 || v.timestamp !== a[i - 1].timestamp)
      setCandles(uniqueData)

      // Fetch AI Data
      fetchDecision(symbol, Number(interval))
      fetchDirection(symbol)
    } catch (err) {
      console.error('Chart data load failed:', err)
    } finally {
      if (isFreshLoad) setLoading(false)
    }
  }, [symbol, interval, fetchDecision, fetchDirection])

  useEffect(() => {
    loadData(true)
    const timer = window.setInterval(() => loadData(false), config.MARKET_POLL_INTERVAL || 5000)
    return () => window.clearInterval(timer)
  }, [loadData])

  // --- 3. Chart Initialization ---
  useEffect(() => {
    if (!chartContainerRef.current) return

    const isDark = document.documentElement.classList.contains('dark')
    const bgColor = isDark ? '#0a0f1a' : '#ffffff'
    const textColor = isDark ? '#9ca3af' : '#374151'
    const gridColor = isDark ? '#1f2937' : '#e5e7eb'

    const chart = createChart(chartContainerRef.current, {
      layout: { background: { type: ColorType.Solid, color: bgColor }, textColor },
      grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
      width: chartContainerRef.current.clientWidth,
      height: 500,
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { timeVisible: true, secondsVisible: false, tickMarkFormatter: (time: number) => formatTimeIST(time) },
      localization: { timeFormatter: (time: number) => formatTimeIST(time) }
    })
    
    chartRef.current = chart

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10b981', downColor: '#ef4444',
      borderVisible: false, wickUpColor: '#10b981', wickDownColor: '#ef4444',
    })
    candleSeriesRef.current = candleSeries

    // Subscribe to Click for Drawing
    chart.subscribeClick((param) => {
      if (!param.point || !candleSeriesRef.current) return
      
      // Access current isDrawing state via ref or closure check
      // Since useEffect has no dependency on isDrawing, we need to be careful.
      // Using a ref to track isDrawing inside the callback
      if (drawingRef.current) {
        const price = candleSeriesRef.current.coordinateToPrice(param.point.y)
        if (price) {
          setLineModal({ open: true, price })
          setLineForm(prev => ({ ...prev, label: `Level ${price.toFixed(0)}` }))
          setIsDrawing(false) // Turn off drawing mode
        }
      }
    })

    const handleResize = () => chartContainerRef.current && chart.applyOptions({ width: chartContainerRef.current.clientWidth })
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [])

  // Ref to track drawing state for the chart event listener
  const drawingRef = useRef(isDrawing)
  useEffect(() => { drawingRef.current = isDrawing }, [isDrawing])

  // --- 4. Render Chart Elements ---
  useEffect(() => {
    if (!chartRef.current || !candleSeriesRef.current || candles.length === 0) return

    // A. Update Candles
    const formattedData = candles.map(c => ({
      time: c.timestamp as Time, open: c.open, high: c.high, low: c.low, close: c.close
    }))
    candleSeriesRef.current.setData(formattedData)

    if (shouldFitContent.current) {
      chartRef.current.timeScale().fitContent()
      shouldFitContent.current = false
    }

    // B. Update Indicators
    indicatorSeriesRef.current.forEach(s => chartRef.current?.removeSeries(s))
    indicatorSeriesRef.current = []

    if (activeIndicator === 'SMA') {
      const sma = chartRef.current.addLineSeries({ color: '#3b82f6', lineWidth: 2 })
      sma.setData(calculateSMA(candles, 20) as any)
      indicatorSeriesRef.current.push(sma)
    } else if (activeIndicator === 'EMA') {
      const ema = chartRef.current.addLineSeries({ color: '#f59e0b', lineWidth: 2 })
      ema.setData(calculateEMA(candles, 20) as any)
      indicatorSeriesRef.current.push(ema)
    } else if (activeIndicator === 'BOLLINGER') {
      const bb = calculateBollingerBands(candles)
      const u = chartRef.current.addLineSeries({ color: 'rgba(34,197,94,0.5)', lineWidth: 1 })
      const l = chartRef.current.addLineSeries({ color: 'rgba(239,68,68,0.5)', lineWidth: 1 })
      u.setData(bb.upper as any); l.setData(bb.lower as any)
      indicatorSeriesRef.current.push(u, l)
    }

    // C. Update System Lines
    priceLinesRef.current.forEach(l => candleSeriesRef.current?.removePriceLine(l))
    priceLinesRef.current = []

    if (showLevels && decision?.support_resistance) {
      const levels: any = (decision.support_resistance as any).levels || decision.support_resistance
      const addSysLine = (price: number, title: string, color: string) => {
        if (!price) return
        priceLinesRef.current.push(candleSeriesRef.current?.createPriceLine({
          price, color, title, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true
        }))
      }
      addSysLine(levels.r1, 'R1', '#ef4444'); addSysLine(levels.s1, 'S1', '#10b981')
    }

    // D. Update Custom Lines
    customPriceLinesRef.current.forEach(l => candleSeriesRef.current?.removePriceLine(l))
    customPriceLinesRef.current = []

    customLines.forEach(line => {
      if (!line.visible) return
      const pl = candleSeriesRef.current?.createPriceLine({
        price: line.price,
        color: line.color,
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: true,
        title: line.label,
      })
      if (pl) customPriceLinesRef.current.push(pl)
    })

    // E. AI Markers
    if (showAIOverlay && decision?.signal) {
      const lastCandle = formattedData[formattedData.length - 1]
      if (lastCandle) {
        candleSeriesRef.current.setMarkers([{
          time: lastCandle.time,
          position: decision.signal === 'BULLISH' ? 'belowBar' : 'aboveBar',
          color: decision.signal === 'BULLISH' ? '#10b981' : '#ef4444',
          shape: decision.signal === 'BULLISH' ? 'arrowUp' : 'arrowDown',
          text: `AI: ${decision.signal}`
        } as any])
      }
    } else {
      candleSeriesRef.current.setMarkers([])
    }

  }, [candles, activeIndicator, showLevels, showAIOverlay, decision, customLines])

  // --- 5. Handlers ---
  const handleAddLine = () => {
    const newLine: CustomLine = {
      id: Date.now().toString(),
      price: lineModal.price,
      label: lineForm.label,
      color: lineForm.color,
      visible: true
    }
    const updated = [...customLines, newLine]
    setCustomLines(updated)
    localStorage.setItem(`chart_lines_${symbol}`, JSON.stringify(updated))
    setLineModal({ ...lineModal, open: false })
    addToast('success', 'Line added')
  }

  const handleDeleteLine = (id: string) => {
    const updated = customLines.filter(l => l.id !== id)
    setCustomLines(updated)
    localStorage.setItem(`chart_lines_${symbol}`, JSON.stringify(updated))
  }

  return (
    <div className="space-y-6 h-[calc(100vh-140px)] flex flex-col animate-fade-in relative">
      
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 p-3 rounded-xl shadow-sm z-20">
        
        {/* Left: Symbol & Interval */}
        <div className="flex items-center gap-3">
          <div className="relative">
            <select value={symbol} onChange={(e) => setSymbol(e.target.value)} className="appearance-none bg-gray-50 dark:bg-dark-800 text-gray-900 dark:text-white pl-3 pr-8 py-1.5 rounded-lg border border-gray-200 dark:border-dark-700 text-sm font-medium focus:border-primary-500 focus:outline-none">
              {config.INDICES.map(idx => <option key={idx} value={idx}>{idx}</option>)}
            </select>
            <ChevronDown className="w-4 h-4 text-gray-400 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
          <div className="flex bg-gray-100 dark:bg-dark-800 rounded-lg p-1 border border-gray-200 dark:border-dark-700">
            {['1', '5', '15', '60'].map((m) => (
              <button key={m} onClick={() => setInterval(m)} className={`px-3 py-1 rounded text-xs font-bold transition-all ${interval === m ? 'bg-white dark:bg-dark-700 text-primary-600 dark:text-white shadow-sm' : 'text-gray-500 dark:text-gray-400'}`}>{m}m</button>
            ))}
          </div>
        </div>

        {/* Right: Tools */}
        <div className="flex items-center gap-2">
          
          {/* Draw Button */}
          <button 
            onClick={() => setIsDrawing(!isDrawing)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-bold transition-all ${isDrawing ? 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 border-amber-500 animate-pulse' : 'bg-gray-50 dark:bg-dark-800 text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-700'}`}
          >
            <Plus className="w-3 h-3" /> {isDrawing ? 'Click Chart...' : 'Draw Line'}
          </button>

          {/* Manage Lines Button */}
          <button 
            onClick={() => setShowLinesPanel(!showLinesPanel)}
            className={`p-2 rounded-lg border transition-all ${showLinesPanel ? 'bg-blue-50 dark:bg-blue-500/20 border-blue-500 text-blue-600' : 'bg-gray-50 dark:bg-dark-800 border-gray-200 dark:border-dark-700 text-gray-500'}`}
            title="Manage Lines"
          >
            <PenTool className="w-4 h-4" />
          </button>

          <div className="h-6 w-px bg-gray-200 dark:bg-dark-700 mx-1" />

          {/* Indicators */}
          <select value={activeIndicator} onChange={(e) => setActiveIndicator(e.target.value as any)} className="bg-gray-50 dark:bg-dark-800 text-gray-900 dark:text-white text-xs py-1.5 px-2 rounded border border-gray-200 dark:border-dark-700 focus:outline-none">
            <option value="NONE">Indicators</option>
            <option value="SMA">SMA (20)</option>
            <option value="EMA">EMA (20)</option>
            <option value="BOLLINGER">Bollinger</option>
          </select>

          {/* Toggles */}
          <button onClick={() => setShowLevels(!showLevels)} className={`p-2 rounded-lg border ${showLevels ? 'bg-emerald-50 dark:bg-emerald-500/20 border-emerald-500 text-emerald-600' : 'bg-gray-50 dark:bg-dark-800 text-gray-500'}`}>
            <Target className="w-4 h-4" />
          </button>
          
          <button onClick={() => setShowAIOverlay(!showAIOverlay)} className={`p-2 rounded-lg border ${showAIOverlay ? 'bg-purple-50 dark:bg-purple-500/20 border-purple-500 text-purple-600' : 'bg-gray-50 dark:bg-dark-800 text-gray-500'}`}>
            <Zap className="w-4 h-4" />
          </button>

          <button onClick={() => setShowDirectionPanel(!showDirectionPanel)} className={`p-2 rounded-lg border ${showDirectionPanel ? 'bg-blue-50 dark:bg-blue-500/20 border-blue-500 text-blue-600' : 'bg-gray-50 dark:bg-dark-800 text-gray-500'}`}>
            <TrendingUp className="w-4 h-4" />
          </button>

          <button onClick={() => loadData(true)} disabled={loading} className="p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-800 transition-colors">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="flex-1 flex gap-4 overflow-hidden relative">
        {/* Main Chart */}
        <div className={`flex-1 relative bg-white dark:bg-dark-900 rounded-xl border border-gray-200 dark:border-dark-700 shadow-sm overflow-hidden ${isDrawing ? 'cursor-crosshair' : ''}`}>
          {loading && candles.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center bg-white/80 dark:bg-dark-900/80 z-20 backdrop-blur-sm">
              <Activity className="w-10 h-10 text-primary-500 animate-pulse" />
            </div>
          )}
          <div ref={chartContainerRef} className="w-full h-full" />
          
          {/* Symbol Overlay */}
          <div className="absolute top-4 left-4 z-10 pointer-events-none">
            <h2 className="text-3xl font-black text-gray-200 dark:text-dark-800 select-none tracking-tighter">{symbol}</h2>
            {isDrawing && <span className="bg-amber-500 text-white text-xs px-2 py-1 rounded shadow animate-pulse">Click chart to set line</span>}
          </div>
        </div>

        {/* Custom Lines Sidebar */}
        {showLinesPanel && (
          <div className="w-64 bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 rounded-xl flex flex-col shadow-xl animate-slide-in-right z-30">
            <div className="p-3 border-b border-gray-200 dark:border-dark-700 flex justify-between items-center">
              <h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2 text-sm"><PenTool className="w-4 h-4" /> Custom Lines</h3>
              <button onClick={() => setShowLinesPanel(false)}><X className="w-4 h-4 text-gray-500" /></button>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-2">
              {customLines.length === 0 ? (
                <div className="text-center text-gray-500 text-xs py-10">No custom lines.<br/>Click "+ Draw Line" to add.</div>
              ) : (
                customLines.map(line => (
                  <div key={line.id} className="p-2 rounded bg-gray-50 dark:bg-dark-800 border border-gray-200 dark:border-dark-700 flex justify-between items-center group">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-8 rounded-full" style={{ backgroundColor: line.color }} />
                      <div>
                        <p className="font-bold text-xs text-gray-900 dark:text-white">{line.label}</p>
                        <p className="text-[10px] font-mono text-gray-500">{line.price.toFixed(2)}</p>
                      </div>
                    </div>
                    <button onClick={() => handleDeleteLine(line.id)} className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 rounded transition-colors"><Trash2 className="w-3 h-3" /></button>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      {/* Direction Panel */}
      {showDirectionPanel && currentDirection && (
        <div className="absolute bottom-4 left-4 z-20 w-72">
          <MarketDirectionCard direction={currentDirection} symbol={symbol} compact={true} showComponents={false} />
        </div>
      )}

      {/* Add Line Modal */}
      <Modal isOpen={lineModal.open} onClose={() => setLineModal({ ...lineModal, open: false })} title="Add Horizontal Line">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Price Level</label>
            <input type="number" value={lineModal.price} onChange={(e) => setLineModal({ ...lineModal, price: parseFloat(e.target.value) })} className="w-full p-2 rounded-lg border border-gray-300 dark:border-dark-600 bg-white dark:bg-dark-800 text-gray-900 dark:text-white" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Label</label>
            <input type="text" value={lineForm.label} onChange={(e) => setLineForm({ ...lineForm, label: e.target.value })} className="w-full p-2 rounded-lg border border-gray-300 dark:border-dark-600 bg-white dark:bg-dark-800 text-gray-900 dark:text-white" placeholder="e.g. Resistance" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Line Color</label>
            <div className="flex gap-2">
              {['#ef4444', '#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ffffff'].map(c => (
                <button key={c} onClick={() => setLineForm({ ...lineForm, color: c })} className={`w-8 h-8 rounded-full border-2 ${lineForm.color === c ? 'border-gray-900 dark:border-white scale-110' : 'border-transparent'}`} style={{ backgroundColor: c }} />
              ))}
            </div>
          </div>
          <button onClick={handleAddLine} className="w-full btn-primary mt-4 flex items-center justify-center gap-2">Add Line</button>
        </div>
      </Modal>
    </div>
  )
}