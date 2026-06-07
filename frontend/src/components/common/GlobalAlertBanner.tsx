import { AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useHealthStore, useUIStore } from '../../store'

type Alert = { tone: 'danger' | 'warning'; text: string }

/**
 * System-wide safety banner. Surfaces the conditions that must never be hidden:
 * scheduler down, reconciliation mismatch, blocked auto-entry, kill switch.
 * (Stale Groww token has its own reconnect banner.)
 */
export default function GlobalAlertBanner() {
  const { health, reconciliation } = useHealthStore()
  const { settings } = useUIStore()

  const alerts: Alert[] = []
  if (health?.scheduler_stale) alerts.push({ tone: 'danger', text: 'Scheduler is down — automated monitoring and entries are paused.' })
  if (reconciliation?.reconcile_blocked) alerts.push({ tone: 'danger', text: 'Broker↔DB reconciliation mismatch — new entries blocked and kill switch engaged.' })
  if (settings?.kill_switch) alerts.push({ tone: 'danger', text: 'Kill switch is ACTIVE — all new entries are blocked.' })
  const blocked = health?.scheduler?.blocked_reason
  if (blocked && !settings?.kill_switch) alerts.push({ tone: 'warning', text: `Auto-entry blocked: ${blocked}` })

  if (!alerts.length) return null
  return (
    <div className="space-y-2 mb-4">
      {alerts.map((a, i) => (
        <div key={i} role="alert"
          className={`rounded-xl border px-4 py-2.5 flex items-start gap-2 ${
            a.tone === 'danger'
              ? 'border-red-300 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400'
              : 'border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400'}`}>
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <p className="text-xs font-medium flex-1 leading-snug">{a.text}</p>
          <Link to="/safety" className="text-xs font-bold underline shrink-0 whitespace-nowrap">Safety Center</Link>
        </div>
      ))}
    </div>
  )
}
