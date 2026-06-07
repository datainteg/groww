import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { 
  Menu, Bell, User, LogOut, Settings, Moon, Sun, 
  Zap, AlertTriangle, ChevronDown 
} from 'lucide-react'
import { useAuthStore, useUIStore, useMarketStore, useStrategyStore } from '../../store'
import { getISTString } from '../../utils/formatter'

interface HeaderProps {
  onToggleSidebar: () => void
}

export default function Header({ onToggleSidebar }: HeaderProps) {
  const { user, logout } = useAuthStore()
  const { settings, theme, setTheme } = useUIStore()
  const { marketStatus } = useMarketStore()
  const { engineStatus } = useStrategyStore()
  
  const [currentTime, setCurrentTime] = useState(getISTString())
  const [showUserMenu, setShowUserMenu] = useState(false)

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(getISTString()), 1000)
    return () => clearInterval(timer)
  }, [])

  const handleLogout = () => {
    if (confirm('Logout from dashboard?')) {
      logout()
      setShowUserMenu(false)
    }
  }

  const isMarketOpen = marketStatus?.is_open

  return (
    // FIX: Theme-aware background and border
    <header className="h-16 bg-white/80 dark:bg-dark-900/80 backdrop-blur-xl border-b border-gray-200 dark:border-dark-700 flex items-center justify-between px-4 sm:px-6 sticky top-0 z-30 shadow-sm transition-colors duration-200">

      {/* Left Section */}
      <div className="flex items-center gap-2 sm:gap-4">
        {/* Hamburger opens the drawer on mobile; desktop sidebar is always shown */}
        <button
          onClick={onToggleSidebar}
          className="lg:hidden p-2 rounded-lg text-gray-500 dark:text-dark-400 hover:bg-gray-100 dark:hover:bg-dark-800 transition-colors"
          aria-label="Open menu"
        >
          <Menu className="w-5 h-5" />
        </button>

        {/* Market Status Pill */}
        <div className="hidden md:flex items-center gap-3 px-3 py-1.5 rounded-full bg-gray-100 dark:bg-dark-800/50 border border-gray-200 dark:border-dark-700">
          <div className={`w-2 h-2 rounded-full ${isMarketOpen ? 'bg-emerald-500 shadow-emerald-500/50' : 'bg-red-500'}`} />
          <span className={`text-xs font-bold uppercase ${isMarketOpen ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
            {isMarketOpen ? 'Market Open' : 'Closed'}
          </span>
          <div className="w-px h-3 bg-gray-300 dark:bg-dark-700 mx-1" />
          <span className="text-xs text-gray-500 dark:text-dark-300 font-mono tracking-wide">{currentTime}</span>
        </div>

        {/* Engine Status */}
        <div className={`hidden lg:flex items-center gap-2 px-3 py-1.5 rounded-full border transition-colors ${
          engineStatus?.is_running 
            ? 'bg-blue-50 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/20 text-blue-600 dark:text-blue-400' 
            : 'bg-gray-100 dark:bg-dark-800/50 border-gray-200 dark:border-dark-700 text-gray-500 dark:text-dark-400'
        }`}>
          <Zap className={`w-3 h-3 ${engineStatus?.is_running ? 'animate-pulse fill-current' : ''}`} />
          <span className="text-xs font-bold uppercase">
            {engineStatus?.is_running ? 'Engine Active' : 'Engine Idle'}
          </span>
        </div>

        {/* Kill Switch Warning */}
        {settings?.kill_switch && (
          <div className="hidden xl:flex items-center gap-2 px-3 py-1.5 rounded-full bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-red-600 dark:text-red-400 animate-pulse">
            <AlertTriangle className="w-3 h-3" />
            <span className="text-xs font-bold uppercase">Kill Switch ON</span>
          </div>
        )}
      </div>

      {/* Right Section */}
      <div className="flex items-center gap-2 sm:gap-4">

        {/* Mode Badge */}
        <div className={`px-3 py-1 rounded-md text-[10px] font-black uppercase tracking-wider border ${
          settings?.execution_mode === 'LIVE'
            ? 'bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-500 border-red-200 dark:border-red-500/20'
            : 'bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-500 border-amber-200 dark:border-amber-500/20'
        }`}>
          {settings?.execution_mode || 'PAPER'}
        </div>

        <div className="h-6 w-px bg-gray-200 dark:bg-dark-700" />

        {/* Theme Toggle */}
        <button
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          className="p-2 rounded-lg text-gray-500 dark:text-dark-400 hover:bg-gray-100 dark:hover:bg-dark-800 transition-colors"
        >
          {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
        </button>

        {/* Notifications */}
        <button aria-label="Notifications" className="relative p-2 rounded-lg text-gray-500 dark:text-dark-400 hover:bg-gray-100 dark:hover:bg-dark-800 transition-colors">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-primary-500 rounded-full border-2 border-white dark:border-dark-900" />
        </button>

        {/* User Menu */}
        <div className="relative">
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center gap-3 pl-3 py-1.5 pr-2 rounded-full hover:bg-gray-100 dark:hover:bg-dark-800 transition-colors border border-transparent hover:border-gray-200 dark:hover:border-dark-700"
          >
            <div className="text-right hidden md:block">
              <p className="text-xs font-bold text-gray-900 dark:text-white leading-tight">{user?.name || 'Trader'}</p>
              <p className="text-[10px] text-gray-500 dark:text-dark-400 leading-tight">
                {user?.broker_connected ? 'Connected' : 'Paper Only'}
              </p>
            </div>
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary-500 to-purple-600 flex items-center justify-center text-white shadow-lg shadow-primary-500/20">
              <User className="w-4 h-4" />
            </div>
            <ChevronDown className={`w-3 h-3 text-gray-400 transition-transform ${showUserMenu ? 'rotate-180' : ''}`} />
          </button>

          {/* Dropdown Menu - FIX: Added light mode backgrounds */}
          {showUserMenu && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowUserMenu(false)} />
              <div className="absolute right-0 top-full mt-2 w-56 bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 rounded-xl shadow-2xl z-50 overflow-hidden animate-in fade-in zoom-in-95 duration-100">
                <div className="p-1">
                  <Link
                    to="/profile"
                    onClick={() => setShowUserMenu(false)}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-gray-600 dark:text-dark-300 hover:bg-gray-100 dark:hover:bg-dark-800 transition-colors group"
                  >
                    <User className="w-4 h-4 text-gray-400 group-hover:text-primary-500" />
                    <span className="text-sm font-medium">Profile</span>
                  </Link>
                  <Link
                    to="/settings"
                    onClick={() => setShowUserMenu(false)}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-gray-600 dark:text-dark-300 hover:bg-gray-100 dark:hover:bg-dark-800 transition-colors group"
                  >
                    <Settings className="w-4 h-4 text-gray-400 group-hover:text-primary-500" />
                    <span className="text-sm font-medium">Settings</span>
                  </Link>
                  <div className="h-px bg-gray-200 dark:bg-dark-700 my-1 mx-2" />
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                  >
                    <LogOut className="w-4 h-4" />
                    <span className="text-sm font-medium">Logout</span>
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  )
}