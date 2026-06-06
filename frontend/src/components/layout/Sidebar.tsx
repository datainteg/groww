import { NavLink, useLocation } from 'react-router-dom'
import { 
  LayoutDashboard, 
  Target, 
  LineChart, 
  Settings, 
  Activity,
  Zap,
  TrendingUp
} from 'lucide-react'

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Strategies', href: '/strategy', icon: Target },
  { name: 'Live Trades', href: '/trades', icon: Activity },
  { name: 'Charts', href: '/charts', icon: LineChart },
  { name: 'AI Signals', href: '/signals', icon: Zap },
  { name: 'Settings', href: '/settings', icon: Settings },
]

interface SidebarProps {
  isOpen: boolean
}

export default function Sidebar({ isOpen }: SidebarProps) {
  const location = useLocation()

  return (
    <aside className={`fixed left-0 top-0 z-40 h-screen transition-all duration-300 ${
      isOpen ? 'w-64' : 'w-20'
    }`}>
      {/* FIX: Dynamic Background & Border for Light/Dark */}
      <div className="h-full bg-white dark:bg-dark-900 border-r border-gray-200 dark:border-dark-700 flex flex-col transition-colors duration-200">
        
        {/* Logo */}
        <div className="h-16 flex items-center px-4 border-b border-gray-200 dark:border-dark-700">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-500 to-cyan-500 flex items-center justify-center shrink-0 shadow-lg shadow-primary-500/20">
              <TrendingUp className="w-5 h-5 text-white" />
            </div>
            {isOpen && (
              <div className="animate-fade-in overflow-hidden whitespace-nowrap">
                <h1 className="font-bold text-gray-900 dark:text-white text-lg">AI Trader</h1>
                <p className="text-[10px] text-gray-500 dark:text-dark-400 uppercase tracking-widest">PRO v2.0</p>
              </div>
            )}
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto custom-scrollbar">
          {navigation.map((item) => {
            const isActive = location.pathname === item.href
            return (
              <NavLink
                key={item.name}
                to={item.href}
                className={`flex items-center gap-3 px-3 py-3 rounded-lg transition-all duration-200 group relative overflow-hidden ${
                  isActive
                    ? 'bg-primary-50 dark:bg-primary-500/10 text-primary-600 dark:text-primary-400 border border-primary-200 dark:border-primary-500/20'
                    : 'text-gray-600 dark:text-dark-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-dark-800'
                }`}
              >
                {isActive && <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary-500" />}
                <item.icon className={`w-5 h-5 flex-shrink-0 transition-colors ${isActive ? 'text-primary-500 dark:text-primary-400' : 'text-gray-400 dark:text-gray-500 group-hover:text-gray-900 dark:group-hover:text-white'}`} />
                {isOpen && (
                  <span className="font-medium truncate animate-fade-in">{item.name}</span>
                )}
              </NavLink>
            )
          })}
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-gray-200 dark:border-dark-700">
          {isOpen ? (
            <div className="px-3 py-2 rounded-lg bg-gray-50 dark:bg-dark-800/50 border border-gray-200 dark:border-dark-700">
              <p className="text-[10px] text-gray-500 dark:text-dark-400 uppercase font-bold tracking-wider mb-1">Market Hours</p>
              <div className="flex items-center justify-between">
                <p className="text-xs text-gray-900 dark:text-white font-mono">09:15 - 15:30</p>
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" title="Market Open" />
              </div>
            </div>
          ) : (
            <div className="w-full flex justify-center">
              <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" title="Market Open" />
            </div>
          )}
        </div>
      </div>
    </aside>
  )
}