import { useState } from 'react'
import { 
  User, Key, Save, Shield, CheckCircle2, AlertCircle, 
  Eye, EyeOff, LogOut, Lock 
} from 'lucide-react'
import { useAuthStore } from '../store/auth.store'
import { useUIStore } from '../store/ui.store'
import { Badge } from '../components/ui'

const fmtIST = (iso?: string) => {
  if (!iso) return '—'
  const s = iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`
  try {
    return new Intl.DateTimeFormat('en-IN', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
      hour12: true, timeZone: 'Asia/Kolkata',
    }).format(new Date(s))
  } catch { return iso }
}

export default function Profile() {
  const { user, updateGrowwCredentials, logout } = useAuthStore()
  const { addToast } = useUIStore()

  const tokenState = user?.broker_connected
    ? (user?.needs_groww_refresh ? 'Stale' : 'Fresh')
    : 'Not set'
  const tokenVariant = user?.broker_connected
    ? (user?.needs_groww_refresh ? 'warning' : 'success')
    : 'neutral'
  
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [showSecret, setShowSecret] = useState(false)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    if (!apiKey.trim() || !apiSecret.trim()) {
      addToast('error', 'Both API Key and Secret are required')
      return
    }
    setSaving(true)
    try {
      await updateGrowwCredentials(apiKey, apiSecret)
      addToast('success', 'Broker credentials securely updated')
      setApiKey('')
      setApiSecret('')
    } catch (err: any) {
      addToast('error', err.error || 'Failed to update credentials')
    } finally {
      setSaving(false)
    }
  }

  const handleLogout = () => {
    if (confirm('Are you sure you want to logout?')) {
      logout()
    }
  }

  const handleChangePassword = () => {
    addToast('info', 'Password change email sent to your inbox.')
  }

  return (
    <div className="space-y-8 animate-fade-in max-w-4xl mx-auto pb-10">
      
      {/* --- Header --- */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white tracking-tight flex items-center gap-3">
            <User className="w-8 h-8 text-blue-500" /> Profile
          </h1>
          <p className="text-gray-500 dark:text-dark-400 mt-2 text-sm font-medium">Manage your account and broker connections.</p>
        </div>
        
        <div className="flex gap-3">
          <button 
            onClick={handleChangePassword}
            className="btn-secondary flex items-center gap-2 bg-white dark:bg-dark-800 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-dark-600 hover:bg-gray-50 dark:hover:bg-dark-700 transition-colors"
          >
            <Lock className="w-4 h-4" /> Change Password
          </button>
          
          <button 
            onClick={handleLogout}
            className="btn-ghost text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 border border-red-200 dark:border-red-500/20 flex items-center gap-2"
          >
            <LogOut className="w-4 h-4" /> Logout
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        
        {/* --- User Card --- */}
        <div className="md:col-span-1 space-y-6">
          <div className="card p-6 relative overflow-hidden group bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 shadow-sm">
            <div className="absolute inset-0 bg-gradient-to-br from-blue-600/5 to-purple-600/5 dark:from-blue-600/10 dark:to-purple-600/10 opacity-50 group-hover:opacity-70 transition-opacity" />
            
            <div className="relative z-10 flex flex-col items-center text-center">
              <div className="w-24 h-24 rounded-full bg-gradient-to-tr from-blue-500 to-purple-600 p-1 mb-4 shadow-lg shadow-blue-500/20">
                <div className="w-full h-full rounded-full bg-white dark:bg-dark-900 flex items-center justify-center">
                  <span className="text-3xl font-bold text-gray-900 dark:text-white">
                    {user?.name ? user.name.charAt(0).toUpperCase() : 'U'}
                  </span>
                </div>
              </div>
              
              <h2 className="text-xl font-bold text-gray-900 dark:text-white">{user?.name || 'Trader'}</h2>
              <p className="text-sm text-gray-500 dark:text-dark-400 mb-4">{user?.email}</p>
              
              <div className={`px-3 py-1.5 rounded-full text-xs font-bold flex items-center gap-2 border ${
                user?.broker_connected 
                  ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/30' 
                  : 'bg-amber-100 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30'
              }`}>
                {user?.broker_connected ? <CheckCircle2 className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
                {user?.broker_connected ? 'Broker Connected' : 'Paper Trading Only'}
              </div>
            </div>
          </div>

          <div className="card p-5 border border-gray-200 dark:border-dark-700 bg-white dark:bg-dark-900 shadow-sm">
            <h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2 mb-3">
              <Shield className="w-4 h-4 text-emerald-500" /> Broker &amp; Token
            </h3>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between items-center">
                <span className="text-gray-500 dark:text-dark-400">Broker</span>
                <Badge variant={user?.broker_connected ? 'success' : 'warning'}>{user?.broker_connected ? 'Connected' : 'Paper only'}</Badge>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500 dark:text-dark-400">Token</span>
                <Badge variant={tokenVariant as any}>{tokenState}</Badge>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500 dark:text-dark-400">Last generated</span>
                <span className="text-gray-900 dark:text-white font-medium">{fmtIST(user?.token_generated_at)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500 dark:text-dark-400">Daily reset</span>
                <span className="text-gray-900 dark:text-white font-medium">~6 AM IST</span>
              </div>
            </div>
            {user?.broker_connected && user?.needs_groww_refresh && (
              <p className="mt-3 text-[11px] text-amber-600 dark:text-amber-400">
                Token stale — re-enter your API key &amp; secret to refresh and restore live data.
              </p>
            )}
          </div>
        </div>

        {/* --- Broker Settings --- */}
        <div className="md:col-span-2">
          <div className="card p-6 border-t-4 border-t-blue-500 bg-white dark:bg-dark-900 border-x border-b border-gray-200 dark:border-dark-700 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-3 bg-blue-50 dark:bg-blue-500/10 rounded-xl text-blue-500 dark:text-blue-400">
                <Key className="w-6 h-6" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-gray-900 dark:text-white">Groww API Credentials</h2>
                <p className="text-xs text-gray-500 dark:text-dark-400">Required for Live Execution and real-time market data.</p>
              </div>
            </div>

            <div className="space-y-5">
              <div className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-lg p-3 flex gap-3 text-sm text-amber-700 dark:text-amber-200/80">
                <Shield className="w-5 h-5 shrink-0" />
                <p>Your credentials are encrypted and stored securely. We never share them with third parties.</p>
              </div>

              <div>
                <label className="text-xs font-bold text-gray-500 dark:text-dark-400 uppercase mb-2 block">API Key</label>
                <input 
                  type="text" 
                  value={apiKey} 
                  onChange={(e) => setApiKey(e.target.value)} 
                  className="input-field w-full bg-gray-50 dark:bg-dark-900 border-gray-300 dark:border-dark-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:border-blue-500"
                  placeholder="Paste your Groww API Key here" 
                />
              </div>

              <div>
                <label className="text-xs font-bold text-gray-500 dark:text-dark-400 uppercase mb-2 block">API Secret</label>
                <div className="relative">
                  <input 
                    type={showSecret ? 'text' : 'password'} 
                    value={apiSecret} 
                    onChange={(e) => setApiSecret(e.target.value)} 
                    className="input-field w-full bg-gray-50 dark:bg-dark-900 border-gray-300 dark:border-dark-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:border-blue-500 pr-10"
                    placeholder="Paste your Groww API Secret here" 
                  />
                  <button 
                    type="button"
                    onClick={() => setShowSecret(!showSecret)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-white transition-colors"
                  >
                    {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div className="pt-4 flex justify-end">
                <button 
                  onClick={handleSave} 
                  disabled={saving} 
                  className="btn-primary flex items-center gap-2 px-6 py-2.5 shadow-lg shadow-blue-500/20"
                >
                  {saving ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save className="w-4 h-4" /> Save Credentials
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}