import type { Candle } from '../types'

// Helper to get time field (handle timestamp vs datetime)
const getTime = (c: Candle) => c.timestamp || (new Date(c.datetime).getTime() / 1000)

export const calculateSMA = (data: Candle[], period: number) => {
  const result = []
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) continue
    let sum = 0
    for (let j = 0; j < period; j++) {
      sum += data[i - j].close
    }
    result.push({ time: getTime(data[i]), value: sum / period })
  }
  return result
}

export const calculateEMA = (data: Candle[], period: number) => {
  const result = []
  const k = 2 / (period + 1)
  let ema = data[0].close
  
  for (let i = 0; i < data.length; i++) {
    ema = data[i].close * k + ema * (1 - k)
    if (i >= period - 1) {
      result.push({ time: getTime(data[i]), value: ema })
    }
  }
  return result
}

export const calculateRSI = (data: Candle[], period: number = 14) => {
  const result = []
  let gains = 0
  let losses = 0

  // First avg
  for (let i = 1; i <= period; i++) {
    const change = data[i].close - data[i - 1].close
    if (change > 0) gains += change
    else losses += Math.abs(change)
  }

  let avgGain = gains / period
  let avgLoss = losses / period

  for (let i = period + 1; i < data.length; i++) {
    const change = data[i].close - data[i - 1].close
    const gain = change > 0 ? change : 0
    const loss = change < 0 ? Math.abs(change) : 0

    avgGain = (avgGain * (period - 1) + gain) / period
    avgLoss = (avgLoss * (period - 1) + loss) / period

    const rs = avgGain / avgLoss
    const rsi = 100 - (100 / (1 + rs))
    
    result.push({ time: getTime(data[i]), value: rsi })
  }
  return result
}

export const calculateBollingerBands = (data: Candle[], period: number = 20, multiplier: number = 2) => {
  const upper = []
  const lower = []
  const basis = []

  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) continue
    
    let sum = 0
    for (let j = 0; j < period; j++) sum += data[i - j].close
    const sma = sum / period
    
    let sumSqDiff = 0
    for (let j = 0; j < period; j++) {
      sumSqDiff += Math.pow(data[i - j].close - sma, 2)
    }
    const stdDev = Math.sqrt(sumSqDiff / period)

    basis.push({ time: getTime(data[i]), value: sma })
    upper.push({ time: getTime(data[i]), value: sma + stdDev * multiplier })
    lower.push({ time: getTime(data[i]), value: sma - stdDev * multiplier })
  }
  return { upper, lower, basis }
}