import { useState, useEffect, useCallback } from 'react'
import { 
  Plus, Play, Pause, Edit2, Trash2, Target, RefreshCw,
  Zap, AlertTriangle, CheckCircle2, Settings, Shield, Clock, 
  Activity, Briefcase, Info, RotateCcw, Gauge
} from 'lucide-react'

import { useStrategyStore } from '../store/strategy.store'
import { useMarketStore } from '../store/market.store'
import { useUIStore } from '../store/ui.store'
import { useTradeStore } from '../store/trade.store'
import { marketApi, instrumentsApi } from '../api/market.api'
import { settingsApi } from '../api/settings.api'
import { formatCurrency, getPnlClass } from '../utils/formatter'
import { config } from '../config'
import Modal from '../components/common/Modal'
import { ConfidenceConfig } from '../components/strategy'
import type { Strategy, StrategyFormData, Instrument } from '../types'

interface AtmResponse {
  atm_strike: number
  spot_price: number
  strikes: number[]
}

type TabType = 'ENTRY' | 'RISK' | 'SAFEGUARDS' | 'CONFIDENCE'

const defaultForm: StrategyFormData = {
  name: '',
  index: 'NIFTY',
  selection_mode: 'DYNAMIC',
  atm_offset: 0,
  exchange_segment: 'nse_fo',
  product: 'MIS',
  expiry: '',
  strike_price: '',
  ce_symbol: '',
  pe_symbol: '',
  quantity: 50,
  stop_loss: 20,
  target: 40,
  trailing_sl_enabled: true,
  trailing_sl_value: 10,
  break_even_enabled: false,
  break_even_trigger: 20,
  partial_exit_enabled: false,
  partial_exit_percent: 50,
  time_exit_enabled: true,
  max_orders_per_day: 3,
  max_profit_limit: 5000,
  max_loss_limit: 2000,
  confidence_preset: 'balanced',
  min_confidence: 70,
  volume_confirmation: true,
  volatility_filter: true,
  trend_alignment: false,
  allowed_signals: 'BOTH',
  time_filter_enabled: false,
  time_filter_start: '09:30',
  time_filter_end: '15:00',
  use_direction_engine: true,
  direction_min_strength: 60,
}

export default function StrategyPage() {
  const { strategies, fetchStrategies, createStrategy, updateStrategy, deleteStrategy, startStrategy, stopStrategy } = useStrategyStore()
  const { syncInfo, fetchSyncInfo } = useMarketStore()
  const { executeStrategy } = useTradeStore() 
  const { addToast } = useUIStore()
  
  const [showForm, setShowForm] = useState(false)
  const [activeTab, setActiveTab] = useState<TabType>('ENTRY')
  const [editingStrategy, setEditingStrategy] = useState<Strategy | null>(null)
  
  const [syncing, setSyncing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [executing, setExecuting] = useState<string | null>(null)
  
  const [loadingExpiries, setLoadingExpiries] = useState(false)
  const [loadingAtm, setLoadingAtm] = useState(false)
  const [, setLoadingSymbols] = useState(false)
  
  const [formError, setFormError] = useState('')

  const [form, setForm] = useState<StrategyFormData>(defaultForm)
  const [expiries, setExpiries] = useState<string[]>([])
  const [atmInfo, setAtmInfo] = useState<AtmResponse | null>(null)
  const [ceInstruments, setCeInstruments] = useState<Instrument[]>([])
  const [peInstruments, setPeInstruments] = useState<Instrument[]>([])
  const [, setLotSize] = useState(50)

  useEffect(() => {
    fetchStrategies()
    fetchSyncInfo()
  }, [])

  // --- Helper: Generic Notification ---
  const notifyAction = async (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    addToast(type, message)
    try {
      const emoji = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️'
      await settingsApi.sendMessage(`${emoji} <b>Strategy Alert</b>\n${message}`)
    } catch (e) {
      console.warn("Failed to send telegram notification", e)
    }
  }

  // --- Helper: Send Detailed Summary on Create ---
  const sendCreationSummary = async (data: StrategyFormData) => {
    const summary = `
✨ <b>NEW STRATEGY CREATED</b> ✨

<b>Name:</b> ${data.name}
<b>Index:</b> ${data.index} (${data.product})
<b>Expiry:</b> ${data.expiry}
<b>Quantity:</b> ${data.quantity}

🛡️ <b>Risk Management</b>
• Stop Loss: ${data.stop_loss} pts
• Target: ${data.target} pts
• Trailing: ${data.trailing_sl_enabled ? 'ON' : 'OFF'} (${data.trailing_sl_value} pts)

⚙️ <b>Configuration</b>
• Mode: ${data.selection_mode}
• Offset: ${data.atm_offset}
• Max Orders: ${data.max_orders_per_day}
`.trim();

    try {
      await settingsApi.sendMessage(summary)
    } catch (e) {
      console.warn("Failed to send creation summary", e)
    }
  }

  const loadIndexInfo = useCallback(async (index: string) => {
    try {
      const info = await instrumentsApi.getIndexInfo(index)
      const size = info.lot_size || config.LOT_SIZES[index as keyof typeof config.LOT_SIZES] || 50
      setLotSize(size)
      if (!editingStrategy) {
        setForm(f => ({ ...f, quantity: size }))
      }
    } catch (err) {
      console.error('Index info error', err)
    }
  }, [editingStrategy])

  const loadExpiries = useCallback(async (index: string) => {
    setLoadingExpiries(true)
    try {
      const list = await instrumentsApi.getExpiries(index)
      setExpiries(list)
      if (!editingStrategy && list.length > 0 && !form.expiry) {
        setForm(f => ({ ...f, expiry: list[0] }))
      }
    } catch (err) {
      console.error('Expiry load error', err)
    } finally {
      setLoadingExpiries(false)
    }
  }, [editingStrategy, form.expiry])

  const loadAtmInfo = useCallback(async (index: string, expiry: string) => {
    if (!index || !expiry) return
    setLoadingAtm(true)
    try {
      const data = await marketApi.getATMOptions(index, expiry)
      if (data && typeof data.atm_strike === 'number') {
        setAtmInfo(data as AtmResponse)
      } else {
        setAtmInfo(null)
      }
    } catch (err) {
      console.error('ATM Info error', err)
      setAtmInfo(null)
    } finally {
      setLoadingAtm(false)
    }
  }, [])

  const loadInstruments = useCallback(async (index: string, expiry: string) => {
    if (!index || !expiry) return
    setLoadingSymbols(true)
    try {
      const [ce, pe] = await Promise.all([
        instrumentsApi.getInstruments(index, expiry, 'CE'),
        instrumentsApi.getInstruments(index, expiry, 'PE')
      ])
      
      const sortFn = (a: Instrument, b: Instrument) => (a.strike_price || 0) - (b.strike_price || 0)
      setCeInstruments((ce || []).sort(sortFn))
      setPeInstruments((pe || []).sort(sortFn))
    } catch (err) {
      console.error('Symbol fetch error', err)
    } finally {
      setLoadingSymbols(false)
    }
  }, [])

  useEffect(() => {
    if (showForm && form.index) {
      loadIndexInfo(form.index)
      loadExpiries(form.index)
    }
  }, [showForm, form.index, loadIndexInfo, loadExpiries])

  useEffect(() => {
    if (showForm && form.index && form.expiry) {
      loadAtmInfo(form.index, form.expiry)
    }
  }, [showForm, form.index, form.expiry, loadAtmInfo])

  useEffect(() => {
    if (showForm && form.selection_mode === 'MANUAL' && form.index && form.expiry) {
      loadInstruments(form.index, form.expiry)
    }
  }, [showForm, form.selection_mode, form.index, form.expiry, loadInstruments])

  const handleSync = async () => {
    setSyncing(true)
    try {
      const res = await instrumentsApi.syncInstruments()
      if (res.success) {
        await fetchSyncInfo() 
        notifyAction(`Synced ${res.total} instruments successfully`, 'success')
      } else {
        notifyAction('Sync completed but no data returned', 'error')
      }
    } catch (err: any) {
      notifyAction('Instrument sync failed', 'error')
    } finally {
      setSyncing(false)
    }
  }

  const openForm = (strategy?: Strategy) => {
    setFormError('')
    setExpiries([])
    setAtmInfo(null)
    setCeInstruments([])
    setPeInstruments([])
    setActiveTab('ENTRY')

    if (strategy) {
      setEditingStrategy(strategy)
      setForm({ ...defaultForm, ...strategy })
    } else {
      setEditingStrategy(null)
      setForm(defaultForm)
    }
    setShowForm(true)
  }

  const handleSave = async () => {
    setFormError('')
    if (!form.name.trim()) return setFormError('Name required')
    if (!form.expiry) return setFormError('Expiry required')
    
    setSaving(true)
    try {
      if (editingStrategy) {
        await updateStrategy(editingStrategy._id, form)
        notifyAction(`Strategy Updated: ${form.name}`, 'success')
      } else {
        await createStrategy(form)
        // Send specific summary only on creation
        await sendCreationSummary(form)
        addToast('success', 'Strategy Created')
      }
      setShowForm(false)
    } catch (err: any) {
      setFormError(err.error || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const updateField = (key: keyof StrategyFormData, val: any) => {
    setForm(prev => {
      const newState = { ...prev, [key]: val }
      if (key === 'index') {
        newState.exchange_segment = (val === 'SENSEX' || val === 'BANKEX') ? 'bse_fo' : 'nse_fo'
      }
      return newState
    })
  }

  const handleToggle = async (s: Strategy) => {
    try {
      if (s.is_active) {
        await stopStrategy(s._id)
        notifyAction(`${s.name} Stopped`, 'info')
      } else {
        await startStrategy(s._id)
        notifyAction(`${s.name} Started`, 'success')
      }
    } catch (err) {
      notifyAction(`Failed to change status for ${s.name}`, 'error')
    }
  }

  const handleDelete = async (id: string, name: string) => {
    if (!confirm('Delete this strategy?')) return
    try {
      await deleteStrategy(id)
      notifyAction(`Strategy Deleted: ${name}`, 'info')
    } catch (err) {
      notifyAction('Failed to delete strategy', 'error')
    }
  }

  const handleExecuteNow = async (strategyId: string, strategyName: string, optionType: 'CE' | 'PE') => {
    if (!confirm(`Execute ${optionType} trade for ${strategyName}?\n\nThis will place a MARKET order.`)) return
    
    setExecuting(`${strategyId}-${optionType}`)
    try {
      await executeStrategy(strategyId, optionType)
      notifyAction(`Manual ${optionType} Order Executed for ${strategyName}`, 'success')
      fetchStrategies()
    } catch (err: any) {
      const msg = err.response?.data?.error || err.error || 'Execution failed'
      notifyAction(`Order Failed: ${msg}`, 'error')
    } finally {
      setExecuting(null)
    }
  }

  const renderTabButton = (tab: TabType, label: string, icon: any) => (
    <button
      onClick={() => setActiveTab(tab)}
      className={`flex-1 py-3 text-sm font-medium flex items-center justify-center gap-2 border-b-2 transition-colors ${
        activeTab === tab 
          ? 'border-blue-500 text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-500/5' 
          : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'
      }`}
    >
      {icon} {label}
    </button>
  )

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Activity className="w-6 h-6 text-blue-500" /> Strategy Management
          </h1>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">Configure automated trading rules.</p>
        </div>
        <button onClick={() => openForm()} className="btn-primary flex items-center gap-2 shadow-lg shadow-blue-500/20">
          <Plus className="w-4 h-4" /> New Strategy
        </button>
      </div>

      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-4">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center border ${
            (syncInfo?.total ?? 0) > 0 
              ? 'bg-emerald-100 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/30 text-emerald-600 dark:text-emerald-400' 
              : 'bg-amber-100 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/30 text-amber-600 dark:text-amber-400'
          }`}>
            <RefreshCw className={`w-5 h-5 ${syncing ? 'animate-spin' : ''}`} />
          </div>
          <div>
            <h3 className="text-gray-900 dark:text-white font-medium">Market Data</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {(syncInfo?.total ?? 0) > 0 
                ? <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1"><CheckCircle2 className="w-3 h-3"/> {syncInfo!.total.toLocaleString()} instruments available</span>
                : <span className="text-amber-600 dark:text-amber-400 flex items-center gap-1"><AlertTriangle className="w-3 h-3"/> No instruments synced</span>}
            </p>
          </div>
        </div>
        <button onClick={handleSync} disabled={syncing} className="btn-ghost text-sm border-gray-200 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300">
          {syncing ? 'Syncing...' : 'Sync Now'}
        </button>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {strategies.map(strategy => (
          <div key={strategy._id} className={`p-5 rounded-xl border relative overflow-hidden transition-all shadow-sm ${
            strategy.is_active 
              ? 'bg-white dark:bg-gray-800 border-emerald-500/50 shadow-emerald-500/10' 
              : 'bg-white dark:bg-gray-800/50 border-gray-200 dark:border-gray-700'
          }`}>
            {strategy.is_active && <div className="absolute left-0 top-0 bottom-0 w-1 bg-emerald-500"></div>}
            
            <div className="flex justify-between items-start mb-4 pl-3">
              <div>
                <h3 className="text-lg font-bold text-gray-900 dark:text-white">{strategy.name}</h3>
                <div className="flex gap-2 mt-1 text-xs text-gray-500 dark:text-gray-400">
                  <span className="bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded border border-gray-200 dark:border-gray-600">{strategy.index}</span>
                  <span className="bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded border border-gray-200 dark:border-gray-600">{strategy.selection_mode}</span>
                  <span className="bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded border border-gray-200 dark:border-gray-600">{strategy.quantity} Qty</span>
                </div>
              </div>
              <div className="text-right">
                <p className="text-xs text-gray-500 dark:text-gray-500 uppercase font-bold">P&L</p>
                <p className={`text-lg font-mono font-bold ${getPnlClass(strategy.today_pnl || 0)}`}>
                  {formatCurrency(strategy.today_pnl || 0)}
                </p>
              </div>
            </div>

            <div className="flex gap-2 mb-4 pl-3">
              <button 
                onClick={() => handleExecuteNow(strategy._id, strategy.name, 'CE')}
                disabled={executing === `${strategy._id}-CE`}
                className="flex-1 py-2 rounded-lg text-sm font-bold bg-emerald-600 hover:bg-emerald-700 text-white flex justify-center items-center gap-2 transition-colors shadow-lg shadow-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {executing === `${strategy._id}-CE` ? (
                  <><RefreshCw className="w-4 h-4 animate-spin" /> Executing...</>
                ) : (
                  <><Zap className="w-4 h-4" /> Buy CE</>
                )}
              </button>
              <button 
                onClick={() => handleExecuteNow(strategy._id, strategy.name, 'PE')}
                disabled={executing === `${strategy._id}-PE`}
                className="flex-1 py-2 rounded-lg text-sm font-bold bg-red-600 hover:bg-red-700 text-white flex justify-center items-center gap-2 transition-colors shadow-lg shadow-red-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {executing === `${strategy._id}-PE` ? (
                  <><RefreshCw className="w-4 h-4 animate-spin" /> Executing...</>
                ) : (
                  <><Zap className="w-4 h-4" /> Buy PE</>
                )}
              </button>
            </div>

            <div className="flex gap-3 border-t border-gray-200 dark:border-gray-700 pt-4 pl-3">
              <button 
                onClick={() => handleToggle(strategy)}
                className={`flex-1 py-2 rounded-lg text-sm font-medium flex justify-center items-center gap-2 transition-colors ${
                  strategy.is_active 
                    ? 'bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 hover:bg-amber-200 dark:hover:bg-amber-500/20' 
                    : 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 hover:bg-emerald-200 dark:hover:bg-emerald-500/20'
                }`}
              >
                {strategy.is_active ? <><Pause className="w-4 h-4"/> Stop</> : <><Play className="w-4 h-4"/> Start</>}
              </button>
              <button onClick={() => openForm(strategy)} disabled={strategy.is_active} className="p-2 rounded bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-600 dark:text-gray-300 disabled:opacity-50">
                <Edit2 className="w-4 h-4"/>
              </button>
              <button onClick={() => handleDelete(strategy._id, strategy.name)} disabled={strategy.is_active} className="p-2 rounded bg-red-100 dark:bg-red-500/10 hover:bg-red-200 dark:hover:bg-red-500/20 text-red-600 dark:text-red-400 disabled:opacity-50">
                <Trash2 className="w-4 h-4"/>
              </button>
            </div>
          </div>
        ))}
      </div>

      <Modal isOpen={showForm} onClose={() => setShowForm(false)} title={editingStrategy ? 'Edit Strategy' : 'New Strategy'} size="xl">
        <div className="flex flex-col h-[70vh]">
          <div className="flex border-b border-gray-200 dark:border-gray-700 mb-4 bg-gray-50 dark:bg-gray-800/50 -mx-6 px-6 pt-2">
            {renderTabButton('ENTRY', 'Entry', <Target className="w-4 h-4"/>)}
            {renderTabButton('RISK', 'Risk', <Shield className="w-4 h-4"/>)}
            {renderTabButton('SAFEGUARDS', 'Safeguards', <Settings className="w-4 h-4"/>)}
            {renderTabButton('CONFIDENCE', 'Confidence', <Gauge className="w-4 h-4"/>)}
          </div>

          <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
            {formError && (
              <div className="mb-4 p-3 bg-red-100 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-lg text-red-600 dark:text-red-400 text-sm flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" /> {formError}
              </div>
            )}

            {activeTab === 'ENTRY' && (
              <div className="space-y-5">
                <div className="relative overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
                  <div className="flex items-center justify-between p-3">
                    <div className="flex gap-6">
                      <div>
                        <p className="text-[10px] text-gray-500 dark:text-gray-500 uppercase font-bold tracking-wider">Spot Price</p>
                        <p className={`text-lg font-mono font-bold ${loadingAtm ? 'animate-pulse text-gray-400' : 'text-gray-900 dark:text-white'}`}>
                          {atmInfo ? atmInfo.spot_price : '---'}
                        </p>
                      </div>
                      <div>
                        <p className="text-[10px] text-gray-500 dark:text-gray-500 uppercase font-bold tracking-wider">ATM Strike</p>
                        <p className={`text-lg font-mono font-bold ${loadingAtm ? 'animate-pulse text-gray-400' : 'text-amber-600 dark:text-yellow-400'}`}>
                          {atmInfo ? atmInfo.atm_strike : '---'}
                        </p>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-4">
                      {form.selection_mode === 'DYNAMIC' && (
                        <div className="text-right">
                          <p className="text-[10px] text-gray-500 dark:text-gray-500 uppercase font-bold tracking-wider">Target</p>
                          <p className={`text-lg font-mono font-bold ${loadingAtm ? 'animate-pulse text-gray-400' : 'text-emerald-600 dark:text-green-400'}`}>
                            {atmInfo ? atmInfo.atm_strike + form.atm_offset : '---'}
                          </p>
                        </div>
                      )}
                      
                      <button 
                        onClick={() => form.index && form.expiry && loadAtmInfo(form.index, form.expiry)}
                        className="p-2 rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
                        title="Refresh Rates"
                      >
                        <RotateCcw className={`w-4 h-4 ${loadingAtm ? 'animate-spin' : ''}`} />
                      </button>
                    </div>
                  </div>
                  {loadingAtm && <div className="absolute bottom-0 left-0 h-0.5 w-full bg-blue-500 animate-progress"></div>}
                </div>

                <div className="grid grid-cols-12 gap-3">
                  <div className="col-span-12 md:col-span-6">
                    <label className="text-xs text-gray-500 dark:text-gray-400 block mb-1">Strategy Name</label>
                    <input type="text" value={form.name} onChange={e => updateField('name', e.target.value)} className="input-field w-full bg-white dark:bg-gray-900 border-gray-300 dark:border-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600" placeholder="e.g. NIFTY Scalper" />
                  </div>
                  <div className="col-span-6 md:col-span-3">
                    <label className="text-xs text-gray-500 dark:text-gray-400 block mb-1">Index</label>
                    <select value={form.index} onChange={e => updateField('index', e.target.value)} className="input-field w-full bg-white dark:bg-gray-900 border-gray-300 dark:border-gray-700 text-gray-900 dark:text-white">
                      {config.INDICES.map(i => <option key={i} value={i}>{i}</option>)}
                    </select>
                  </div>
                  <div className="col-span-6 md:col-span-3">
                    <label className="text-xs text-gray-500 dark:text-gray-400 block mb-1">Expiry {loadingExpiries && '...'}</label>
                    <select value={form.expiry} onChange={e => updateField('expiry', e.target.value)} className="input-field w-full bg-white dark:bg-gray-900 border-gray-300 dark:border-gray-700 text-gray-900 dark:text-white" disabled={loadingExpiries}>
                      {!loadingExpiries && expiries.length === 0 && <option value="">No Expiries</option>}
                      {expiries.map(e => <option key={e} value={e}>{e}</option>)}
                    </select>
                  </div>
                </div>

                <div className="p-4 bg-gray-50 dark:bg-gray-800/30 rounded-xl border border-gray-200 dark:border-gray-700">
                  <div className="flex gap-2 mb-4 bg-gray-200 dark:bg-gray-900 p-1 rounded-lg">
                    {['DYNAMIC', 'MANUAL'].map(mode => (
                      <button key={mode} onClick={() => updateField('selection_mode', mode)}
                        className={`flex-1 py-1.5 text-xs font-bold rounded-md transition-all ${
                          form.selection_mode === mode 
                            ? 'bg-blue-600 text-white shadow-md' 
                            : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                        }`}>
                        {mode === 'DYNAMIC' ? 'Dynamic (Auto ATM)' : 'Manual (Fixed)'}
                      </button>
                    ))}
                  </div>

                  {form.selection_mode === 'DYNAMIC' ? (
                    <div>
                      <label className="text-xs text-gray-500 dark:text-gray-400 block mb-1">Strike Offset</label>
                      <select value={form.atm_offset} onChange={e => updateField('atm_offset', Number(e.target.value))} className="input-field w-full bg-white dark:bg-gray-900 border-gray-300 dark:border-gray-700 text-gray-900 dark:text-white">
                        {config.ATM_OFFSETS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </select>
                      <p className="text-[10px] text-gray-500 mt-2 flex items-center gap-1"><Info className="w-3 h-3"/> Will select {form.atm_offset === 0 ? 'ATM' : `${form.atm_offset > 0 ? 'OTM' : 'ITM'} ${Math.abs(form.atm_offset)}`} strike.</p>
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="text-xs text-gray-500 dark:text-gray-400 block mb-1">CE Symbol</label>
                        <select value={form.ce_symbol} onChange={e => updateField('ce_symbol', e.target.value)} className="input-field w-full bg-white dark:bg-gray-900 border-gray-300 dark:border-gray-700 text-gray-900 dark:text-white text-xs">
                          <option value="">Select CE</option>
                          {ceInstruments.map(i => <option key={i._id} value={i.trading_symbol}>{i.trading_symbol} (₹{i.strike_price})</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="text-xs text-gray-500 dark:text-gray-400 block mb-1">PE Symbol</label>
                        <select value={form.pe_symbol} onChange={e => updateField('pe_symbol', e.target.value)} className="input-field w-full bg-white dark:bg-gray-900 border-gray-300 dark:border-gray-700 text-gray-900 dark:text-white text-xs">
                          <option value="">Select PE</option>
                          {peInstruments.map(i => <option key={i._id} value={i.trading_symbol}>{i.trading_symbol} (₹{i.strike_price})</option>)}
                        </select>
                      </div>
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs text-gray-500 dark:text-gray-400 block mb-1">Product</label>
                    <select value={form.product} onChange={e => updateField('product', e.target.value)} className="input-field w-full bg-white dark:bg-gray-900 border-gray-300 dark:border-gray-700 text-gray-900 dark:text-white">
                      <option value="MIS">MIS (Intraday)</option>
                      <option value="NRML">NRML (Overnight)</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 dark:text-gray-400 block mb-1">Exchange</label>
                    <input type="text" value={form.exchange_segment?.toUpperCase() || 'NSE_FO'} disabled className="input-field w-full bg-gray-100 dark:bg-gray-800 border-gray-300 dark:border-gray-700 text-gray-500 cursor-not-allowed" />
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'RISK' && (
              <div className="space-y-6">
                <div className="grid grid-cols-3 gap-4">
                  <div><label className="text-xs text-gray-500 dark:text-gray-400 block mb-1">Qty</label><input type="number" value={form.quantity} onChange={e => updateField('quantity', Number(e.target.value))} className="input-field w-full bg-white dark:bg-gray-900 border-gray-300 dark:border-gray-700 text-gray-900 dark:text-white" /></div>
                  <div><label className="text-xs text-gray-500 dark:text-gray-400 block mb-1">SL (Pts)</label><input type="number" value={form.stop_loss} onChange={e => updateField('stop_loss', Number(e.target.value))} className="input-field w-full bg-white dark:bg-gray-900 border-red-200 dark:border-red-900/50 focus:border-red-500 text-gray-900 dark:text-white" /></div>
                  <div><label className="text-xs text-gray-500 dark:text-gray-400 block mb-1">Target (Pts)</label><input type="number" value={form.target} onChange={e => updateField('target', Number(e.target.value))} className="input-field w-full bg-white dark:bg-gray-900 border-green-200 dark:border-green-900/50 focus:border-green-500 text-gray-900 dark:text-white" /></div>
                </div>

                <div className="space-y-3 p-4 bg-gray-50 dark:bg-gray-800/50 rounded-xl border border-gray-200 dark:border-gray-700">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <input type="checkbox" checked={form.trailing_sl_enabled} onChange={e => updateField('trailing_sl_enabled', e.target.checked)} className="w-4 h-4 rounded bg-gray-200 dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-blue-600" />
                      <span className="text-sm text-gray-700 dark:text-gray-300">Trailing Stop Loss</span>
                    </div>
                    {form.trailing_sl_enabled && <input type="number" value={form.trailing_sl_value} onChange={e => updateField('trailing_sl_value', Number(e.target.value))} className="w-20 input-field h-8 bg-white dark:bg-gray-900 border-gray-300 dark:border-gray-700 text-gray-900 dark:text-white text-center" />}
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <input type="checkbox" checked={form.break_even_enabled} onChange={e => updateField('break_even_enabled', e.target.checked)} className="w-4 h-4 rounded bg-gray-200 dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-blue-600" />
                      <span className="text-sm text-gray-700 dark:text-gray-300">Move SL to Cost</span>
                    </div>
                    {form.break_even_enabled && <input type="number" value={form.break_even_trigger} onChange={e => updateField('break_even_trigger', Number(e.target.value))} className="w-20 input-field h-8 bg-white dark:bg-gray-900 border-gray-300 dark:border-gray-700 text-gray-900 dark:text-white text-center" />}
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'SAFEGUARDS' && (
              <div className="space-y-6">
                <div className="grid grid-cols-2 gap-4">
                  <div><label className="text-xs text-gray-500 dark:text-gray-400 block mb-1">Max Profit</label><input type="number" value={form.max_profit_limit} onChange={e => updateField('max_profit_limit', Number(e.target.value))} className="input-field w-full bg-white dark:bg-gray-900 border-gray-300 dark:border-gray-700 text-emerald-600 dark:text-green-400 font-bold" /></div>
                  <div><label className="text-xs text-gray-500 dark:text-gray-400 block mb-1">Max Loss</label><input type="number" value={form.max_loss_limit} onChange={e => updateField('max_loss_limit', Number(e.target.value))} className="input-field w-full bg-white dark:bg-gray-900 border-gray-300 dark:border-gray-700 text-red-600 dark:text-red-400 font-bold" /></div>
                </div>

                <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800/50 rounded-xl border border-gray-200 dark:border-gray-700">
                  <div className="flex items-center gap-3">
                    <Briefcase className="w-5 h-5 text-blue-500" />
                    <div>
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-200">Max Orders / Day</p>
                      <p className="text-xs text-gray-500">Stop after N orders</p>
                    </div>
                  </div>
                  <input type="number" value={form.max_orders_per_day} onChange={e => updateField('max_orders_per_day', Number(e.target.value))} className="w-20 input-field bg-white dark:bg-gray-900 border-gray-300 dark:border-gray-700 text-gray-900 dark:text-white text-center" />
                </div>

                <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800/50 rounded-xl border border-gray-200 dark:border-gray-700">
                  <div className="flex items-center gap-3">
                    <Clock className="w-5 h-5 text-amber-500" />
                    <div>
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-200">Time Exit</p>
                      <p className="text-xs text-gray-500">Square-off at 3:20 PM</p>
                    </div>
                  </div>
                  <input type="checkbox" checked={form.time_exit_enabled} onChange={e => updateField('time_exit_enabled', e.target.checked)} className="toggle" />
                </div>
              </div>
            )}

            {activeTab === 'CONFIDENCE' && (
              <ConfidenceConfig
                values={{
                  confidence_preset: form.confidence_preset,
                  min_confidence: form.min_confidence,
                  volume_confirmation: form.volume_confirmation,
                  volatility_filter: form.volatility_filter,
                  trend_alignment: form.trend_alignment,
                  allowed_signals: form.allowed_signals,
                  time_filter_enabled: form.time_filter_enabled,
                  time_filter_start: form.time_filter_start,
                  time_filter_end: form.time_filter_end,
                  use_direction_engine: form.use_direction_engine,
                  direction_min_strength: form.direction_min_strength,
                }}
                onChange={(key, val) => updateField(key as keyof StrategyFormData, val)}
                collapsed={false}
              />
            )}
          </div>

          <div className="pt-4 mt-4 border-t border-gray-200 dark:border-gray-700 flex gap-3">
            <button onClick={() => setShowForm(false)} className="btn-ghost flex-1 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">Cancel</button>
            <button onClick={handleSave} disabled={saving} className="btn-primary flex-[2]">{saving ? 'Saving...' : 'Save Strategy'}</button>
          </div>
        </div>
      </Modal>
    </div>
  )
}