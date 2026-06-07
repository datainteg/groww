import { useEffect, useState, type ReactNode } from 'react'
import { ShieldCheck, Power, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useHealthStore, useUIStore, useAuthStore } from '../store'
import { settingsApi } from '../api'
import { Panel, Badge } from '../components/ui'

type RowState = 'ok' | 'warn' | 'bad' | 'na'

function Row({ label, state, value }: { label: string; state: RowState; value: ReactNode }) {
  const variant = state === 'ok' ? 'success' : state === 'warn' ? 'warning' : state === 'bad' ? 'danger' : 'neutral'
  const txt = state === 'ok' ? 'OK' : state === 'warn' ? 'WARN' : state === 'bad' ? 'ISSUE' : '—'
  return (
    <div className="flex items-center justify-between gap-3 py-2.5 border-b border-gray-100 dark:border-dark-800 last:border-0">
      <span className="text-sm text-gray-700 dark:text-dark-300">{label}</span>
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-xs text-gray-500 dark:text-dark-400">{value}</span>
        <Badge variant={variant as any}>{txt}</Badge>
      </div>
    </div>
  )
}

const ago = (epoch?: number) => {
  if (!epoch) return 'never'
  const s = Math.max(0, Math.floor(Date.now() / 1000 - epoch))
  return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.floor(s / 60)}m ago` : `${Math.floor(s / 3600)}h ago`
}

export default function SafetyCenter() {
  const { health, reconciliation, fetchHealth, isLoading } = useHealthStore()
  const { settings, fetchSettings } = useUIStore()
  const { user } = useAuthStore()
  const [busy, setBusy] = useState(false)

  useEffect(() => { fetchHealth() }, [])

  const sched = health?.scheduler || {}
  const mode = (settings?.execution_mode || health?.execution_mode || 'PAPER').toUpperCase()
  const killOn = !!settings?.kill_switch
  const tokenOk = user?.broker_connected ? !user?.needs_groww_refresh : null
  const reconcileOk = !reconciliation?.reconcile_blocked
  const schedulerOk = !health?.scheduler_stale
  const autoOn = !!health?.auto_trading_enabled

  const toggleKill = async () => {
    setBusy(true)
    try { await settingsApi.toggleKillSwitch(!killOn); await fetchSettings(); await fetchHealth() }
    finally { setBusy(false) }
  }

  let rec = 'All systems nominal.'
  if (killOn) rec = 'Kill switch is ON — new entries blocked. Resolve the cause, then disable it to resume.'
  else if (!schedulerOk) rec = 'Scheduler heartbeat is stale. Start the scheduler process (run_scheduler.py) to resume automation.'
  else if (!reconcileOk) rec = 'Reconciliation mismatch — verify broker positions vs open trades before trading.'
  else if (tokenOk === false) rec = 'Groww token is stale — reconnect from Profile to restore live data.'
  else if (mode === 'LIVE' && !autoOn) rec = 'LIVE mode with auto-trading OFF — running in shadow (no auto orders). Enable only after backtest validation.'

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary-50 dark:bg-primary-500/10 flex items-center justify-center">
            <ShieldCheck className="w-5 h-5 text-primary-600 dark:text-primary-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-white">Safety Center</h1>
            <p className="text-xs text-gray-500 dark:text-dark-400">Live system + risk status</p>
          </div>
        </div>
        <button onClick={fetchHealth} className="btn-secondary text-xs" aria-label="Refresh status">
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <Panel className={killOn || !schedulerOk || !reconcileOk ? 'border-red-300 dark:border-red-500/30' : ''}>
        <p className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-dark-400 font-bold mb-1">Recommended action</p>
        <p className="text-sm text-gray-900 dark:text-white">{rec}</p>
      </Panel>

      <Panel title="Execution & automation">
        <Row label="Execution mode" state="na" value={<Badge variant={mode === 'LIVE' ? 'live' : 'paper'}>{mode}</Badge>} />
        <Row label="Auto-trading" state={autoOn ? 'warn' : 'ok'} value={autoOn ? 'ENABLED' : 'disabled (safe)'} />
        <Row label="Kill switch" state={killOn ? 'bad' : 'ok'} value={killOn ? 'ACTIVE' : 'off'} />
        <div className="pt-3">
          <button onClick={toggleKill} disabled={busy} className={`${killOn ? 'btn-secondary' : 'btn-danger'} w-full`}>
            <Power className="w-4 h-4" /> {busy ? '…' : killOn ? 'Disable kill switch' : 'Activate kill switch (stop all)'}
          </button>
        </div>
      </Panel>

      <Panel title="Data & broker health">
        <Row label="Groww token" state={tokenOk === null ? 'na' : tokenOk ? 'ok' : 'bad'}
          value={tokenOk === null ? 'not connected' : tokenOk ? 'fresh' : <Link to="/profile" className="underline">reconnect</Link>} />
        <Row label="Reconciliation" state={reconcileOk ? 'ok' : 'bad'} value={reconcileOk ? 'matched' : 'mismatch'} />
        <Row label="Auto-entry gate" state={sched.blocked_reason ? 'warn' : 'ok'} value={sched.blocked_reason || 'clear'} />
        <Row label="Scheduler heartbeat" state={schedulerOk ? 'ok' : 'bad'} value={ago(health?.scheduler_last_heartbeat)} />
        <Row label="Last candle sync" state="na" value={ago(sched.last_candle_sync)} />
        <Row label="Last reconciliation" state="na" value={ago(sched.last_reconciliation)} />
        <Row label="Market" state="na" value={sched.market_open ? 'OPEN' : 'closed'} />
      </Panel>

      <Panel title="Risk limits (per day)">
        <Row label="Max daily loss" state="na" value={`₹${(settings?.overall_max_loss ?? 0).toLocaleString('en-IN')}`} />
        <Row label="Max daily profit" state="na" value={`₹${(settings?.overall_max_profit ?? 0).toLocaleString('en-IN')}`} />
        <Row label="Max concurrent trades" state="na" value={String(settings?.max_concurrent_trades ?? '—')} />
        <p className="text-[11px] text-gray-500 dark:text-dark-400 mt-3">Adjust limits in <Link to="/settings" className="underline">Settings</Link>.</p>
      </Panel>
    </div>
  )
}
