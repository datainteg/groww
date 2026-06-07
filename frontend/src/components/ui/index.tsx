import { useEffect, useState, type ReactNode } from 'react'
import { AlertCircle, RefreshCw, Inbox } from 'lucide-react'

/* ------------------------------------------------------------------ *
 * Reusable design-system primitives. Tailwind + project tokens.
 * Status is NEVER conveyed by color alone (always a label/icon too).
 * ------------------------------------------------------------------ */

type BadgeVariant = 'success' | 'danger' | 'warning' | 'neutral' | 'info' | 'paper' | 'live'

const BADGE: Record<BadgeVariant, string> = {
  success: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
  danger: 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20',
  warning: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
  info: 'bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border-cyan-500/20',
  neutral: 'bg-gray-500/10 text-gray-600 dark:text-gray-300 border-gray-500/20',
  paper: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30',
  live: 'bg-red-500/15 text-red-600 dark:text-red-400 border-red-500/40',
}

export function Badge({ variant = 'neutral', children, className = '' }:
  { variant?: BadgeVariant; children: ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border ${BADGE[variant]} ${className}`}>
      {children}
    </span>
  )
}

export function StatCard({ label, value, sub, tone = 'neutral', icon }:
  { label: string; value: ReactNode; sub?: ReactNode; tone?: 'pos' | 'neg' | 'neutral'; icon?: ReactNode }) {
  const color = tone === 'pos' ? 'text-emerald-500' : tone === 'neg' ? 'text-red-500' : 'text-gray-900 dark:text-white'
  return (
    <div className="rounded-xl bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 p-4">
      <div className="flex items-center justify-between">
        <p className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-dark-400 font-bold">{label}</p>
        {icon && <span className="text-gray-300 dark:text-dark-500">{icon}</span>}
      </div>
      <p className={`text-xl font-bold mt-1 ${color}`}>{value}</p>
      {sub != null && <p className="text-[11px] text-gray-500 dark:text-dark-400 mt-0.5">{sub}</p>}
    </div>
  )
}

export function Panel({ title, action, children, className = '' }:
  { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 p-4 ${className}`}>
      {(title || action) && (
        <div className="flex items-center justify-between mb-3">
          {title && <h3 className="font-bold text-gray-900 dark:text-white text-sm">{title}</h3>}
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function EmptyState({ icon, title, message, action }:
  { icon?: ReactNode; title: string; message?: string; action?: ReactNode }) {
  return (
    <div className="text-center py-10 px-4">
      <div className="mx-auto w-12 h-12 rounded-full bg-gray-100 dark:bg-dark-800 flex items-center justify-center text-gray-400 dark:text-dark-500 mb-3">
        {icon || <Inbox className="w-6 h-6" />}
      </div>
      <p className="text-sm font-semibold text-gray-900 dark:text-white">{title}</p>
      {message && <p className="text-xs text-gray-500 dark:text-dark-400 mt-1 max-w-sm mx-auto">{message}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Skeleton({ className = 'h-12' }: { className?: string }) {
  return <div className={`rounded-lg bg-gray-100 dark:bg-dark-800 animate-pulse ${className}`} />
}

export function SkeletonList({ rows = 3 }: { rows?: number }) {
  return <div className="space-y-2">{Array.from({ length: rows }).map((_, i) => <Skeleton key={i} />)}</div>
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-red-300 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 px-4 py-3 flex items-start gap-2">
      <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
      <div className="flex-1">
        <p className="text-sm text-red-700 dark:text-red-400">{message}</p>
        {onRetry && (
          <button onClick={onRetry} className="mt-1 text-xs font-semibold text-red-600 dark:text-red-400 inline-flex items-center gap-1">
            <RefreshCw className="w-3 h-3" /> Retry
          </button>
        )}
      </div>
    </div>
  )
}

/**
 * Safety-first confirm dialog. For irreversible/LIVE actions set requireText
 * (e.g. "EXIT ALL") — the confirm button stays disabled until typed exactly.
 */
export function ConfirmDialog({ open, title, message, confirmLabel = 'Confirm', danger = false, requireText, onConfirm, onClose }:
  { open: boolean; title: string; message?: ReactNode; confirmLabel?: string; danger?: boolean; requireText?: string; onConfirm: () => void; onClose: () => void }) {
  const [typed, setTyped] = useState('')
  useEffect(() => { if (!open) setTyped('') }, [open])
  if (!open) return null
  const ready = !requireText || typed.trim() === requireText
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" role="dialog" aria-modal="true">
      <div className="w-full max-w-sm rounded-2xl bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 shadow-2xl p-5">
        <h3 className="font-bold text-gray-900 dark:text-white">{title}</h3>
        {message && <div className="text-sm text-gray-600 dark:text-dark-300 mt-2">{message}</div>}
        {requireText && (
          <div className="mt-3">
            <label className="block text-xs text-gray-500 dark:text-dark-400 mb-1">Type <b>{requireText}</b> to confirm</label>
            <input className="input-field" value={typed} onChange={(e) => setTyped(e.target.value)} autoFocus />
          </div>
        )}
        <div className="flex gap-2 mt-4">
          <button onClick={onClose} className="btn-secondary flex-1">Cancel</button>
          <button onClick={() => { if (ready) { onConfirm(); onClose() } }} disabled={!ready}
            className={`${danger ? 'btn-danger' : 'btn-primary'} flex-1`}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}
