import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Target, Activity, Zap, LineChart } from 'lucide-react'

// Mobile app-style bottom tab bar (hidden on desktop). Settings lives in the
// drawer (hamburger) to keep the tab bar to 5 thumb-reachable targets.
const tabs = [
  { name: 'Home', href: '/', icon: LayoutDashboard },
  { name: 'Signals', href: '/signals', icon: Zap },
  { name: 'Trades', href: '/trades', icon: Activity },
  { name: 'Charts', href: '/charts', icon: LineChart },
  { name: 'Strategy', href: '/strategy', icon: Target },
]

export default function BottomNav() {
  return (
    <nav
      className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-white/90 dark:bg-dark-900/90 backdrop-blur-xl border-t border-gray-200 dark:border-dark-700 pb-[env(safe-area-inset-bottom)]"
      aria-label="Primary"
    >
      <div className="grid grid-cols-5">
        {tabs.map((t) => (
          <NavLink
            key={t.name}
            to={t.href}
            end={t.href === '/'}
            className={({ isActive }) =>
              `flex flex-col items-center justify-center gap-1 py-2 min-h-[56px] text-[10px] font-medium transition-colors ${
                isActive
                  ? 'text-primary-600 dark:text-primary-400'
                  : 'text-gray-500 dark:text-dark-400 active:bg-gray-100 dark:active:bg-dark-800'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <t.icon className={`w-5 h-5 ${isActive ? 'fill-primary-500/10' : ''}`} />
                <span className="leading-none">{t.name}</span>
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
