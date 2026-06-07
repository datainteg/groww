import { useEffect, useState } from 'react'
import { AlertTriangle, RefreshCw, X, KeyRound } from 'lucide-react'
import { useAuthStore, useUIStore } from '../../store'

/**
 * Groww access tokens expire daily (~6 AM IST). When the stored token is
 * stale/expired, the API serves older data — so we surface a persistent banner
 * and auto-open an update modal (once per login) prompting the user to
 * re-connect their Groww credentials.
 */
export default function GrowwTokenBanner() {
  const { user, updateGrowwCredentials, isLoading } = useAuthStore()
  const { addToast } = useUIStore()

  const needsRefresh = !!(user?.broker_connected && user?.needs_groww_refresh)

  const [open, setOpen] = useState(false)
  const [autoOpened, setAutoOpened] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')

  // Auto-open the modal ONCE when a stale token is first detected this session.
  useEffect(() => {
    if (needsRefresh && !autoOpened) {
      setOpen(true)
      setAutoOpened(true)
    }
    if (!needsRefresh) setAutoOpened(false) // reset for the next day's expiry
  }, [needsRefresh, autoOpened])

  if (!needsRefresh) return null

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!apiKey.trim() || !apiSecret.trim()) {
      addToast('error', 'Enter both API key and secret')
      return
    }
    try {
      await updateGrowwCredentials(apiKey.trim(), apiSecret.trim())
      addToast('success', 'Groww token refreshed — live data restored')
      setApiKey('')
      setApiSecret('')
      setOpen(false)
    } catch (err: any) {
      addToast('error', err?.error || 'Token update failed — check credentials')
    }
  }

  return (
    <>
      {/* Persistent stale-data banner */}
      <div className="sticky top-16 z-20 mx-0 mb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 rounded-xl border border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 px-4 py-3">
        <div className="flex items-start gap-2 text-amber-700 dark:text-amber-400">
          <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
          <p className="text-sm font-medium leading-snug">
            Groww token expired (refreshes daily ~6 AM IST). You're seeing{' '}
            <span className="font-bold">older data</span> — update to restore live prices &amp; trading.
          </p>
        </div>
        <button
          onClick={() => setOpen(true)}
          className="shrink-0 inline-flex items-center justify-center gap-2 rounded-lg bg-amber-500 hover:bg-amber-600 text-white text-sm font-bold px-4 py-2 transition-colors"
        >
          <RefreshCw className="w-4 h-4" /> Update token
        </button>
      </div>

      {/* Update modal */}
      {open && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 shadow-2xl overflow-hidden animate-fade-in">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-dark-700">
              <div className="flex items-center gap-2">
                <div className="w-9 h-9 rounded-lg bg-primary-50 dark:bg-primary-500/10 flex items-center justify-center">
                  <KeyRound className="w-5 h-5 text-primary-600 dark:text-primary-400" />
                </div>
                <h3 className="font-bold text-gray-900 dark:text-white">Reconnect Groww</h3>
              </div>
              <button onClick={() => setOpen(false)} className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-800" aria-label="Close">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={submit} className="p-5 space-y-4">
              <p className="text-xs text-gray-500 dark:text-dark-400">
                Groww access tokens expire every day around 6 AM IST. Re-enter your API key &amp; secret
                to generate a fresh token. Until then the app shows the last synced (older) data.
              </p>
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-dark-400 mb-1">API Key</label>
                <input className="input-field" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="Groww API key" autoComplete="off" />
              </div>
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-dark-400 mb-1">API Secret</label>
                <input className="input-field" type="password" value={apiSecret} onChange={(e) => setApiSecret(e.target.value)} placeholder="Groww API secret" autoComplete="off" />
              </div>
              <div className="flex gap-2 pt-1">
                <button type="button" onClick={() => setOpen(false)} className="btn-secondary flex-1">Later</button>
                <button type="submit" disabled={isLoading} className="btn-primary flex-1">
                  {isLoading ? 'Connecting…' : 'Generate fresh token'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}
