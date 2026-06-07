import { useEffect, useState } from 'react'
import { Shield, Zap, AlertTriangle, RefreshCw, Power, Save, MessageSquare, CheckCircle } from 'lucide-react'
import { useUIStore, useTradeStore, useStrategyStore } from '../store'
import { settingsApi } from '../api/settings.api'

export default function Settings() {
  const { settings, fetchSettings, updateSettings, toggleKillSwitch, setExecutionMode, addToast } = useUIStore()
  const { resetPaperAccount } = useTradeStore()
  const { stopAllStrategies } = useStrategyStore()
  
  const [saving, setSaving] = useState(false)
  const [testingTelegram, setTestingTelegram] = useState(false)
  const [form, setForm] = useState({
    overall_max_profit: 0,
    overall_max_loss: 0
  })
  
  // Telegram Form State
  const [telegramForm, setTelegramForm] = useState({
    bot_token: '',
    chat_id: ''
  })

  // Load Settings on Mount
  useEffect(() => {
    fetchSettings()
  }, [])

  // Sync Form with Settings
  useEffect(() => {
    if (settings) {
      setForm({
        overall_max_profit: settings.overall_max_profit || 0,
        overall_max_loss: settings.overall_max_loss || 0
      })
      // Pre-fill telegram fields if they exist (masked for security usually, but here simple)
      setTelegramForm({
        bot_token: settings.telegram_bot_token || '',
        chat_id: settings.telegram_chat_id || ''
      })
    }
  }, [settings])

  const handleModeChange = async (mode: 'PAPER' | 'LIVE') => {
    if (mode === settings?.execution_mode) return
    
    if (mode === 'LIVE') {
      const confirmLive = window.confirm('⚠️ WARNING: You are switching to LIVE trading mode.\n\nReal money will be used for all trades. Are you sure?')
      if (!confirmLive) return
    }
    
    try {
      await setExecutionMode(mode)
      addToast('success', `Switched to ${mode} mode`)
    } catch (err: any) {
      addToast('error', 'Failed to change mode')
    }
  }

  const handleKillSwitch = async () => {
    const newState = !settings?.kill_switch
    try {
      await toggleKillSwitch(newState)
      if (newState) {
        await stopAllStrategies()
        addToast('error', '🚨 Kill Switch Activated! All trading halted.')
      } else {
        addToast('success', 'Kill Switch Deactivated')
      }
    } catch (err: any) {
      addToast('error', 'Failed to toggle kill switch')
    }
  }

  const handleSaveRisk = async () => {
    setSaving(true)
    try {
      await updateSettings({
        overall_max_profit: Number(form.overall_max_profit),
        overall_max_loss: Number(form.overall_max_loss)
      })
      addToast('success', 'Risk limits updated')
    } catch (err: any) {
      addToast('error', 'Failed to update settings')
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    if (confirm('Are you sure? This will clear all paper trades and reset balance to ₹10,00,000.')) {
      try {
        await resetPaperAccount()
        addToast('success', 'Paper account reset successfully')
      } catch (err: any) {
        addToast('error', err.error || 'Reset failed')
      }
    }
  }

  // --- Telegram Handlers ---
  const handleSaveTelegram = async () => {
    try {
      await settingsApi.configureTelegram(telegramForm.bot_token, telegramForm.chat_id)
      addToast('success', 'Telegram configuration saved')
      fetchSettings() // Refresh state
    } catch (err: any) {
      addToast('error', err.response?.data?.error || 'Failed to save Telegram config')
    }
  }

  const handleTestTelegram = async () => {
    setTestingTelegram(true)
    try {
      const res = await settingsApi.testTelegram()
      if (res.success) {
        addToast('success', 'Test message sent successfully!')
      } else {
        addToast('error', 'Test failed. Check bot token/chat ID.')
      }
    } catch (err: any) {
      addToast('error', 'Failed to send test message')
    } finally {
      setTestingTelegram(false)
    }
  }

  const handleDisconnectTelegram = async () => {
    if (confirm('Disconnect Telegram? You will stop receiving alerts.')) {
      try {
        await settingsApi.disconnectTelegram()
        setTelegramForm({ bot_token: '', chat_id: '' })
        addToast('info', 'Telegram disconnected')
        fetchSettings()
      } catch (err) {
        addToast('error', 'Failed to disconnect')
      }
    }
  }

  return (
    <div className="space-y-8 animate-fade-in pb-10 max-w-4xl mx-auto">
      
      {/* --- Header --- */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white tracking-tight flex items-center gap-3">
          <SettingsIcon className="w-8 h-8 text-blue-500" /> Settings
        </h1>
        <p className="text-gray-500 dark:text-dark-400 mt-2 text-sm font-medium">Manage execution modes, risk limits, notifications, and system safeguards.</p>
      </div>

      {/* --- Execution Mode --- */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card p-6 border-l-4 border-l-blue-500 bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <Zap className="w-6 h-6 text-blue-500" />
            <div>
              <h2 className="text-lg font-bold text-gray-900 dark:text-white">Execution Mode</h2>
              <p className="text-xs text-gray-500 dark:text-dark-400">Choose between simulation and real money.</p>
            </div>
          </div>
          
          <div className="flex bg-gray-100 dark:bg-dark-900 p-1.5 rounded-xl border border-gray-200 dark:border-dark-700">
            <button 
              onClick={() => handleModeChange('PAPER')} 
              className={`flex-1 py-3 rounded-lg text-sm font-bold transition-all flex flex-col items-center gap-1 ${
                settings?.execution_mode === 'PAPER' 
                  ? 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-400 shadow-sm border border-amber-200 dark:border-amber-500/30' 
                  : 'text-gray-500 dark:text-dark-400 hover:text-gray-900 dark:hover:text-white hover:bg-white dark:hover:bg-dark-800'
              }`}
            >
              <span>PAPER</span>
              <span className="text-[10px] font-normal opacity-70">Simulated</span>
            </button>
            <button 
              onClick={() => handleModeChange('LIVE')} 
              className={`flex-1 py-3 rounded-lg text-sm font-bold transition-all flex flex-col items-center gap-1 ${
                settings?.execution_mode === 'LIVE' 
                  ? 'bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-400 shadow-sm border border-red-200 dark:border-red-500/30' 
                  : 'text-gray-500 dark:text-dark-400 hover:text-gray-900 dark:hover:text-white hover:bg-white dark:hover:bg-dark-800'
              }`}
            >
              <span>LIVE</span>
              <span className="text-[10px] font-normal opacity-70">Real Money</span>
            </button>
          </div>
        </div>

        {/* --- Kill Switch --- */}
        <div className={`card p-6 border-l-4 transition-colors bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 shadow-sm ${settings?.kill_switch ? 'border-l-red-500 bg-red-50 dark:bg-red-500/5' : 'border-l-emerald-500'}`}>
          <div className="flex items-center gap-3 mb-4">
            <Power className={`w-6 h-6 ${settings?.kill_switch ? 'text-red-500' : 'text-emerald-500'}`} />
            <div>
              <h2 className="text-lg font-bold text-gray-900 dark:text-white">System Kill Switch</h2>
              <p className="text-xs text-gray-500 dark:text-dark-400">Emergency stop for all trading activities.</p>
            </div>
          </div>

          <div className="flex items-center justify-between mt-6">
            <span className={`text-sm font-bold ${settings?.kill_switch ? 'text-red-500' : 'text-emerald-500'}`}>
              {settings?.kill_switch ? '⛔ SYSTEM HALTED' : '✅ SYSTEM ACTIVE'}
            </span>
            <button 
              onClick={handleKillSwitch}
              className={`px-6 py-2.5 rounded-lg text-sm font-bold shadow-lg transition-all ${
                settings?.kill_switch 
                  ? 'bg-emerald-600 hover:bg-emerald-700 text-white' 
                  : 'bg-red-600 hover:bg-red-700 text-white'
              }`}
            >
              {settings?.kill_switch ? 'Resume Trading' : 'STOP TRADING'}
            </button>
          </div>
        </div>
      </div>

      {/* --- Risk Limits --- */}
      <div className="card p-6 border border-gray-200 dark:border-dark-700 bg-white dark:bg-dark-900 shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Shield className="w-6 h-6 text-purple-500" />
            <div>
              <h2 className="text-lg font-bold text-gray-900 dark:text-white">Global Risk Limits</h2>
              <p className="text-xs text-gray-500 dark:text-dark-400">Daily profit/loss caps for the entire account.</p>
            </div>
          </div>
          <button 
            onClick={handleSaveRisk} 
            disabled={saving}
            className="btn-primary flex items-center gap-2 px-4 py-2"
          >
            {saving ? <RefreshCw className="w-4 h-4 animate-spin"/> : <Save className="w-4 h-4"/>}
            Save Limits
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="text-xs font-bold text-gray-500 dark:text-dark-400 uppercase mb-2 block">Max Daily Profit (₹)</label>
            <div className="relative">
              <input 
                type="number" 
                value={form.overall_max_profit}
                onChange={(e) => setForm({ ...form, overall_max_profit: Number(e.target.value) })}
                className="input-field w-full pl-8 font-mono text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/30 focus:border-emerald-500 bg-white dark:bg-dark-900"
              />
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-emerald-500/50">₹</span>
            </div>
            <p className="text-[10px] text-gray-400 dark:text-dark-500 mt-1">Trading stops if daily profit exceeds this amount.</p>
          </div>

          <div>
            <label className="text-xs font-bold text-gray-500 dark:text-dark-400 uppercase mb-2 block">Max Daily Loss (₹)</label>
            <div className="relative">
              <input 
                type="number" 
                value={form.overall_max_loss}
                onChange={(e) => setForm({ ...form, overall_max_loss: Number(e.target.value) })}
                className="input-field w-full pl-8 font-mono text-red-600 dark:text-red-400 border-red-200 dark:border-red-500/30 focus:border-red-500 bg-white dark:bg-dark-900"
              />
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-red-500/50">₹</span>
            </div>
            <p className="text-[10px] text-gray-400 dark:text-dark-500 mt-1">Trading stops if daily loss exceeds this amount.</p>
          </div>
        </div>
      </div>

      {/* --- Telegram Configuration --- */}
      <div className="card p-6 border border-gray-200 dark:border-dark-700 bg-white dark:bg-dark-900 shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <MessageSquare className="w-6 h-6 text-blue-400" />
            <div>
              <h2 className="text-lg font-bold text-gray-900 dark:text-white">Telegram Alerts</h2>
              <p className="text-xs text-gray-500 dark:text-dark-400">Configure bot to receive trade notifications.</p>
            </div>
          </div>
          {settings?.telegram_configured && (
            <span className="flex items-center gap-1 text-xs font-bold text-emerald-500 bg-emerald-50 dark:bg-emerald-500/10 px-2 py-1 rounded-full">
              <CheckCircle className="w-3 h-3" /> Connected
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          <div>
            <label className="text-xs font-bold text-gray-500 dark:text-dark-400 uppercase mb-2 block">Bot Token</label>
            <input 
              type="text" 
              value={telegramForm.bot_token}
              onChange={(e) => setTelegramForm({ ...telegramForm, bot_token: e.target.value })}
              className="input-field w-full bg-white dark:bg-dark-900"
              placeholder="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
            />
          </div>
          <div>
            <label className="text-xs font-bold text-gray-500 dark:text-dark-400 uppercase mb-2 block">Chat ID</label>
            <input 
              type="text" 
              value={telegramForm.chat_id}
              onChange={(e) => setTelegramForm({ ...telegramForm, chat_id: e.target.value })}
              className="input-field w-full bg-white dark:bg-dark-900"
              placeholder="-1001234567890"
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button 
            onClick={handleSaveTelegram}
            className="btn-primary px-4 py-2 text-sm"
          >
            Save Configuration
          </button>
          
          {settings?.telegram_configured && (
            <>
              <button 
                onClick={handleTestTelegram}
                disabled={testingTelegram}
                className="px-4 py-2 bg-gray-100 dark:bg-dark-800 hover:bg-gray-200 dark:hover:bg-dark-700 text-gray-700 dark:text-gray-300 rounded-lg text-sm font-bold transition-all flex items-center gap-2"
              >
                {testingTelegram ? <RefreshCw className="w-3 h-3 animate-spin"/> : 'Test Message'}
              </button>
              <button 
                onClick={handleDisconnectTelegram}
                className="px-4 py-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg text-sm font-bold transition-all"
              >
                Disconnect
              </button>
            </>
          )}
        </div>
      </div>

      {/* --- Danger Zone --- */}
      <div className="card p-6 border border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/5 shadow-sm">
        <div className="flex items-center gap-3 mb-4">
          <AlertTriangle className="w-6 h-6 text-red-500" />
          <div>
            <h2 className="text-lg font-bold text-gray-900 dark:text-white">Danger Zone</h2>
            <p className="text-xs text-red-500 dark:text-red-400">Irreversible actions.</p>
          </div>
        </div>

        <div className="flex items-center justify-between bg-white dark:bg-dark-900/50 p-4 rounded-xl border border-red-100 dark:border-red-500/10">
          <div>
            <p className="font-bold text-gray-900 dark:text-white">Reset Paper Account</p>
            <p className="text-xs text-gray-500 dark:text-dark-400">Clears all trade history and resets balance to ₹10,00,000.</p>
          </div>
          <button 
            onClick={handleReset}
            className="px-4 py-2 bg-white dark:bg-dark-800 hover:bg-red-50 dark:hover:bg-red-500/20 text-red-500 dark:text-red-400 border border-red-200 dark:border-red-500/30 rounded-lg text-sm font-bold transition-all shadow-sm"
          >
            Reset Account
          </button>
        </div>
      </div>

    </div>
  )
}

// Icon Helper
function SettingsIcon(props: any) {
  return (
    <svg 
      {...props} 
      xmlns="http://www.w3.org/2000/svg" 
      width="24" 
      height="24" 
      viewBox="0 0 24 24" 
      fill="none" 
      stroke="currentColor" 
      strokeWidth="2" 
      strokeLinecap="round" 
      strokeLinejoin="round"
    >
      <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.47a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"></path>
      <circle cx="12" cy="12" r="3"></circle>
    </svg>
  )
}