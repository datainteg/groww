import { useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { useAuthStore, useUIStore } from '../../store'

/**
 * First-login gate: a single default user ships with a default password and
 * must_change_password=true. This blocking modal forces a password change
 * before the app can be used; it clears once the new password is saved.
 */
export default function ForceChangePassword() {
  const { user, changePassword, isLoading } = useAuthStore()
  const { addToast } = useUIStore()

  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')

  if (!user?.must_change_password) return null

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (next.length < 8) {
      addToast('error', 'New password must be at least 8 characters')
      return
    }
    if (next !== confirm) {
      addToast('error', 'Passwords do not match')
      return
    }
    try {
      await changePassword(current, next)
      addToast('success', 'Password changed — welcome!')
    } catch (err: any) {
      addToast('error', err?.error || 'Could not change password (check current password)')
    }
  }

  return (
    // Full-screen blocking overlay (no dismiss).
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 shadow-2xl overflow-hidden">
        <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-200 dark:border-dark-700">
          <div className="w-9 h-9 rounded-lg bg-primary-50 dark:bg-primary-500/10 flex items-center justify-center">
            <ShieldCheck className="w-5 h-5 text-primary-600 dark:text-primary-400" />
          </div>
          <div>
            <h3 className="font-bold text-gray-900 dark:text-white">Set a new password</h3>
            <p className="text-xs text-gray-500 dark:text-dark-400">Required before you continue</p>
          </div>
        </div>

        <form onSubmit={submit} className="p-5 space-y-4">
          <p className="text-xs text-gray-500 dark:text-dark-400">
            You're signed in with a default password. Choose your own to secure the account.
          </p>
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-dark-400 mb-1">Current password</label>
            <input className="input-field" type="password" value={current} onChange={(e) => setCurrent(e.target.value)} placeholder="Current (default) password" autoComplete="current-password" />
          </div>
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-dark-400 mb-1">New password</label>
            <input className="input-field" type="password" value={next} onChange={(e) => setNext(e.target.value)} placeholder="At least 8 characters" autoComplete="new-password" />
          </div>
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-dark-400 mb-1">Confirm new password</label>
            <input className="input-field" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="Re-enter new password" autoComplete="new-password" />
          </div>
          <button type="submit" disabled={isLoading} className="btn-primary w-full">
            {isLoading ? 'Saving…' : 'Change password & continue'}
          </button>
        </form>
      </div>
    </div>
  )
}
