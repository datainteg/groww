/**
 * Format number as currency (INR)
 */
export const formatCurrency = (value: number, decimals: number = 2): string => {
  if (value === undefined || value === null) return '₹0.00'
  const formatted = Math.abs(value).toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  })
  return value < 0 ? `-₹${formatted}` : `₹${formatted}`
}

/**
 * Format percentage
 */
export const formatPercent = (value: number): string => {
  if (value === undefined || value === null) return '0.00%'
  const formatted = Math.abs(value).toFixed(2)
  return value < 0 ? `-${formatted}%` : `${formatted}%`
}

/**
 * Get CSS class for Profit/Loss
 */
export const getPnlClass = (value: number): string => {
  if (!value) return 'text-gray-400'
  if (value > 0) return 'text-emerald-400'
  if (value < 0) return 'text-red-400'
  return 'text-gray-400'
}

/**
 * Format Date to readable string
 */
export const formatDateTime = (dateString: string | Date): string => {
  if (!dateString) return '-'
  const date = new Date(dateString)
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true
  })
}

/**
 * Get current time in IST string format (e.g., "09:30:45 am IST")
 */
export const getISTString = (): string => {
  return new Date().toLocaleTimeString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true
  }) + ' IST'
}

/**
 * Check if Indian Markets are currently open (09:15 - 15:30 IST)
 */
export const isMarketOpen = (): boolean => {
  const now = new Date()
  const istDate = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }))
  
  const day = istDate.getDay()
  if (day === 0 || day === 6) return false // Weekend

  const hours = istDate.getHours()
  const minutes = istDate.getMinutes()
  const time = hours * 60 + minutes

  // 09:15 = 555 minutes
  // 15:30 = 930 minutes
  return time >= 555 && time <= 930
}