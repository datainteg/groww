import { useEffect, useRef } from 'react'
import { createChart, ColorType } from 'lightweight-charts'
import type { EquityPoint, DrawdownPoint, DailyPnlPoint } from '../../types'

const _baseOpts = {
  layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#9ca3af', fontSize: 11 },
  grid: { vertLines: { visible: false }, horzLines: { color: 'rgba(127,127,127,0.12)' } },
  rightPriceScale: { borderVisible: false },
  timeScale: { borderVisible: false, fixLeftEdge: true, fixRightEdge: true },
  handleScroll: false,
  handleScale: false,
}

// lightweight-charts needs strictly-ascending unique `time`. Parse the ISO time
// when present; otherwise fall back to the sequential index, and bump on ties.
function ascendingTimes<T extends { time?: string | null }>(points: T[]): number[] {
  let last = 0
  return points.map((p, idx) => {
    let t = p.time ? Math.floor(new Date(p.time).getTime() / 1000) : idx + 1
    if (!t || isNaN(t)) t = idx + 1
    if (t <= last) t = last + 1
    last = t
    return t
  })
}

export function EquityCurveChart({ equity, drawdown }: { equity: EquityPoint[]; drawdown?: DrawdownPoint[] }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current || !equity?.length) return
    const chart = createChart(ref.current, { ..._baseOpts, height: 260, autoSize: true } as any)
    const line = chart.addLineSeries({ color: '#00d09c', lineWidth: 2, priceLineVisible: false })
    const et = ascendingTimes(equity)
    line.setData(equity.map((p, i) => ({ time: et[i] as any, value: p.equity })))
    if (drawdown?.length) {
      const dd = chart.addAreaSeries({
        lineColor: '#ef4444', topColor: 'rgba(239,68,68,0.05)', bottomColor: 'rgba(239,68,68,0.25)',
        priceScaleId: 'dd', lineWidth: 1, priceLineVisible: false,
      })
      chart.priceScale('dd').applyOptions({ scaleMargins: { top: 0.75, bottom: 0 } })
      const dt = ascendingTimes(drawdown)
      dd.setData(drawdown.map((p, i) => ({ time: dt[i] as any, value: -Math.abs(p.drawdown) })))
    }
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [equity, drawdown])
  return <div ref={ref} className="w-full" />
}

export function DailyPnlChart({ daily }: { daily: DailyPnlPoint[] }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current || !daily?.length) return
    const chart = createChart(ref.current, { ..._baseOpts, height: 200, autoSize: true } as any)
    const hist = chart.addHistogramSeries({ priceLineVisible: false })
    let last = 0
    hist.setData(daily.map((d, idx) => {
      let t = Math.floor(new Date(d.date).getTime() / 1000)
      if (!t || isNaN(t)) t = idx + 1
      if (t <= last) t = last + 1
      last = t
      return { time: t as any, value: d.net, color: d.net >= 0 ? '#00d09c' : '#ef4444' }
    }))
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [daily])
  return <div ref={ref} className="w-full" />
}
