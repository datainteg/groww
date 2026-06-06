interface LoadingProps {
  size?: 'sm' | 'md' | 'lg'
  text?: string
  fullScreen?: boolean
}

export default function Loading({ size = 'md', text, fullScreen }: LoadingProps) {
  const sizeClasses = {
    sm: 'w-5 h-5 border-2',
    md: 'w-8 h-8 border-2',
    lg: 'w-12 h-12 border-3',
  }

  const spinner = (
    <div className="flex flex-col items-center gap-3">
      <div className={`${sizeClasses[size]} border-primary-500/30 border-t-primary-500 rounded-full animate-spin`} />
      {text && <span className="text-sm text-gray-500 dark:text-dark-400 font-medium">{text}</span>}
    </div>
  )

  if (fullScreen) {
    return (
      // FIX: Theme-aware background
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-white/80 dark:bg-dark-950/80 backdrop-blur-sm transition-colors duration-200">
        {spinner}
      </div>
    )
  }

  return spinner
}

// Skeleton loaders
export function Skeleton({ className = '' }: { className?: string }) {
  // FIX: Theme-aware skeleton background
  return <div className={`animate-pulse bg-gray-200 dark:bg-dark-700 rounded ${className}`} />
}

export function SkeletonCard() {
  return (
    // FIX: Theme-aware card background
    <div className="p-5 rounded-xl border border-gray-200 dark:border-dark-700 bg-white dark:bg-dark-900 space-y-4 shadow-sm">
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-4 w-full" />
    </div>
  )
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      <Skeleton className="h-10 w-full rounded-lg" />
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full rounded-lg" />
      ))}
    </div>
  )
}