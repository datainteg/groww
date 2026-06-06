import { useUIStore } from '../../store'
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react'

export default function Toast() {
  const { toasts, removeToast } = useUIStore()

  if (toasts.length === 0) return null

  const icons = {
    success: <CheckCircle className="w-5 h-5 text-emerald-500 dark:text-emerald-400" />,
    error: <XCircle className="w-5 h-5 text-red-500 dark:text-red-400" />,
    warning: <AlertTriangle className="w-5 h-5 text-amber-500 dark:text-amber-400" />,
    info: <Info className="w-5 h-5 text-blue-500 dark:text-blue-400" />,
  }

  // FIX: Added theme-aware backgrounds and borders
  const bgColors = {
    success: 'bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/30',
    error: 'bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/30',
    warning: 'bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/30',
    info: 'bg-blue-50 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/30',
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`flex items-center gap-3 px-4 py-3 rounded-lg border backdrop-blur-xl shadow-lg animate-slide-up ${bgColors[toast.type]}`}
        >
          {icons[toast.type]}
          
          <span className="text-sm font-medium text-gray-900 dark:text-white">
            {toast.message}
          </span>
          
          <button
            onClick={() => removeToast(toast.id)}
            className="ml-2 p-1 rounded-md text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      ))}
    </div>
  )
}