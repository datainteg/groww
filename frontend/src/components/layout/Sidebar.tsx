import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Target,
  LineChart,
  Settings,
  Activity,
  Zap,
  TrendingUp,
  FlaskConical,
  ShieldCheck,
  X,
} from 'lucide-react'

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Strategies', href: '/strategy', icon: Target },
  { name: 'Live Trades', href: '/trades', icon: Activity },
  { name: 'Charts', href: '/charts', icon: LineChart },
  { name: 'AI Signals', href: '/signals', icon: Zap },
  { name: 'Backtest Lab', href: '/backtest', icon: FlaskConical },
  { name: 'Safety Center', href: '/safety', icon: ShieldCheck },
  { name: 'Settings', href: '/settings', icon: Settings },
]

interface SidebarProps {
  isOpen: boolean
  onClose: () => void
}

export default function Sidebar({ isOpen, onClose }: SidebarProps) {
  return (
    // Off-canvas drawer on mobile (slides via isOpen); always visible on lg+.
    <aside
      className={`fixed inset-y-0 left-0 z-50 w-64 transform transition-transform duration-300 lg:translate-x-0 ${
        isOpen ? 'translate-x-0' : '-translate-x-full'
      }`}
    >
      <div className="h-full bg-white dark:bg-dark-900 border-r border-gray-200 dark:border-dark-700 flex flex-col transition-colors duration-200">

        {/* Logo + mobile close */}
        <div className="h-16 flex items-center justify-between px-4 border-b border-gray-200 dark:border-dark-700">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-500 to-cyan-500 flex items-center justify-center shrink-0 shadow-lg shadow-primary-500/20">
              <TrendingUp className="w-5 h-5 text-white" />
            </div>
            <div className="overflow-hidden whitespace-nowrap">
              <h1 className="font-bold text-gray-900 dark:text-white text-lg">AI Trader</h1>
              <p className="text-[10px] text-gray-500 dark:text-dark-400 uppercase tracking-widest">PRO v2.0</p>
            </div>
          </div>
          {/* Close button (mobile drawer only) */}
          <button
            onClick={onClose}
            className="lg:hidden p-2 -mr-2 rounded-lg text-gray-500 dark:text-dark-400 hover:bg-gray-100 dark:hover:bg-dark-800"
            aria-label="Close menu"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto custom-scrollbar">
          {navigation.map((item) => (
            <NavLink
              key={item.name}
              to={item.href}
              end={item.href === '/'}
              onClick={onClose}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-3 rounded-lg transition-all duration-200 group relative overflow-hidden ${
                  isActive
                    ? 'bg-primary-50 dark:bg-primary-500/10 text-primary-600 dark:text-primary-400 border border-primary-200 dark:border-primary-500/20'
                    : 'text-gray-600 dark:text-dark-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-dark-800'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary-500" />}
                  <item.icon
                    className={`w-5 h-5 flex-shrink-0 transition-colors ${
                      isActive
                        ? 'text-primary-500 dark:text-primary-400'
                        : 'text-gray-400 dark:text-gray-500 group-hover:text-gray-900 dark:group-hover:text-white'
                    }`}
                  />
                  <span className="font-medium truncate">{item.name}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-gray-200 dark:border-dark-700">
          <div className="px-3 py-2 rounded-lg bg-gray-50 dark:bg-dark-800/50 border border-gray-200 dark:border-dark-700">
            <p className="text-[10px] text-gray-500 dark:text-dark-400 uppercase font-bold tracking-wider mb-1">Market Hours</p>
            <div className="flex items-center justify-between">
              <p className="text-xs text-gray-900 dark:text-white font-mono">09:15 - 15:30</p>
              <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" title="Market Open" />
            </div>
          </div>
        </div>
      </div>
    </aside>
  )
}
