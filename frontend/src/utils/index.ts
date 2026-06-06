// ==================== CURRENCY FORMATTER ====================
export function formatCurrency(amount: number, decimals: number = 0): string {
  if (amount === null || amount === undefined || isNaN(amount)) return '₹0'
  
  const absAmount = Math.abs(amount)
  const sign = amount < 0 ? '-' : ''
  
  // Indian numbering system
  if (absAmount >= 10000000) { // 1 Crore+
    return `${sign}₹${(absAmount / 10000000).toFixed(2)}Cr`
  }
  if (absAmount >= 100000) { // 1 Lakh+
    return `${sign}₹${(absAmount / 100000).toFixed(2)}L`
  }
  if (absAmount >= 1000) { // 1 Thousand+
    return `${sign}₹${(absAmount / 1000).toFixed(1)}K`
  }
  
  return `${sign}₹${absAmount.toFixed(decimals)}`
}

export function formatCurrencyFull(amount: number, decimals: number = 2): string {
  if (amount === null || amount === undefined || isNaN(amount)) return '₹0.00'
  
  const sign = amount < 0 ? '-' : ''
  const absAmount = Math.abs(amount)
  
  return `${sign}₹${absAmount.toLocaleString('en-IN', { 
    minimumFractionDigits: decimals, 
    maximumFractionDigits: decimals 
  })}`
}

// ==================== PERCENTAGE FORMATTER ====================
export function formatPercent(value: number, decimals: number = 2): string {
  if (value === null || value === undefined || isNaN(value)) return '0%'
  return `${value >= 0 ? '+' : ''}${value.toFixed(decimals)}%`
}

export function formatPercentRaw(value: number, decimals: number = 2): string {
  if (value === null || value === undefined || isNaN(value)) return '0%'
  return `${value.toFixed(decimals)}%`
}

// ==================== NUMBER FORMATTER ====================
export function formatNumber(num: number, decimals: number = 2): string {
  if (num === null || num === undefined || isNaN(num)) return '0'
  
  if (num >= 10000000) return `${(num / 10000000).toFixed(2)}Cr`
  if (num >= 100000) return `${(num / 100000).toFixed(2)}L`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
  
  return num.toFixed(decimals)
}

export function formatVolume(volume: number): string {
  if (!volume) return '0'
  if (volume >= 10000000) return `${(volume / 10000000).toFixed(2)}Cr`
  if (volume >= 100000) return `${(volume / 100000).toFixed(2)}L`
  if (volume >= 1000) return `${(volume / 1000).toFixed(1)}K`
  return volume.toString()
}

// ==================== TIME FORMATTER ====================
export function formatTime(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleTimeString('en-IN', { 
    timeZone: 'Asia/Kolkata',
    hour: '2-digit', 
    minute: '2-digit',
    second: '2-digit'
  })
}

export function formatDate(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleDateString('en-IN', { 
    timeZone: 'Asia/Kolkata',
    day: '2-digit', 
    month: 'short', 
    year: 'numeric' 
  })
}

export function formatDateTime(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleString('en-IN', { 
    timeZone: 'Asia/Kolkata',
    day: '2-digit', 
    month: 'short',
    hour: '2-digit', 
    minute: '2-digit'
  })
}

export function formatTimeAgo(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  
  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)
  
  if (seconds < 60) return 'Just now'
  if (minutes < 60) return `${minutes}m ago`
  if (hours < 24) return `${hours}h ago`
  if (days < 7) return `${days}d ago`
  
  return formatDate(d)
}

export function getCurrentIST(): Date {
  return new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }))
}

export function getISTString(): string {
  return new Date().toLocaleTimeString('en-IN', { 
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  }) + ' IST'
}

// ==================== MARKET HOURS ====================
export function isMarketOpen(): boolean {
  const now = getCurrentIST()
  const hours = now.getHours()
  const minutes = now.getMinutes()
  const day = now.getDay()
  
  // Weekend check
  if (day === 0 || day === 6) return false
  
  const currentMinutes = hours * 60 + minutes
  const openMinutes = 9 * 60 + 15   // 9:15 AM
  const closeMinutes = 15 * 60 + 30 // 3:30 PM
  
  return currentMinutes >= openMinutes && currentMinutes <= closeMinutes
}

export function getMarketSession(): 'PRE_MARKET' | 'TRADING' | 'POST_MARKET' | 'CLOSED' {
  const now = getCurrentIST()
  const hours = now.getHours()
  const minutes = now.getMinutes()
  const day = now.getDay()
  
  if (day === 0 || day === 6) return 'CLOSED'
  
  const currentMinutes = hours * 60 + minutes
  
  if (currentMinutes < 9 * 60) return 'CLOSED'
  if (currentMinutes < 9 * 60 + 15) return 'PRE_MARKET'
  if (currentMinutes <= 15 * 60 + 30) return 'TRADING'
  if (currentMinutes <= 16 * 60) return 'POST_MARKET'
  return 'CLOSED'
}

// ==================== PNL HELPERS ====================
export function getPnlClass(pnl: number): string {
  if (pnl > 0) return 'text-emerald-400'
  if (pnl < 0) return 'text-red-400'
  return 'text-dark-400'
}

export function getPnlBgClass(pnl: number): string {
  if (pnl > 0) return 'bg-emerald-500/10'
  if (pnl < 0) return 'bg-red-500/10'
  return 'bg-dark-800'
}

// ==================== SIGNAL HELPERS ====================
export function getSignalClass(signal: string | null): string {
  if (signal === 'BULLISH') return 'text-emerald-400'
  if (signal === 'BEARISH') return 'text-red-400'
  return 'text-dark-400'
}

export function getSignalBgClass(signal: string | null): string {
  if (signal === 'BULLISH') return 'bg-emerald-500/20'
  if (signal === 'BEARISH') return 'bg-red-500/20'
  return 'bg-dark-700'
}

export function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.7) return 'text-emerald-400'
  if (confidence >= 0.5) return 'text-amber-400'
  return 'text-dark-400'
}

// ==================== MISC HELPERS ====================
export function truncateSymbol(symbol: string, maxLen: number = 15): string {
  if (!symbol) return '-'
  if (symbol.length <= maxLen) return symbol
  return symbol.slice(-maxLen)
}

export function generateId(): string {
  return Math.random().toString(36).substring(2) + Date.now().toString(36)
}

export function classNames(...classes: (string | boolean | undefined | null)[]): string {
  return classes.filter(Boolean).join(' ')
}

export function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}
