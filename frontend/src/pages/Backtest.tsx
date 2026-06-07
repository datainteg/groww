import { useEffect, useState } from 'react'
import { FlaskConical, Play, RefreshCw, AlertTriangle, CheckCircle2, XCircle, BarChart3, Activity, GitCompare, Brain, Repeat } from 'lucide-react'
import { useBacktestStore, useUIStore } from '../store'
import { backtestApi, instrumentsApi } from '../api'
import { EquityCurveChart, DailyPnlChart } from '../components/backtest/BacktestCharts'
import type { BacktestConfig, BacktestMode } from '../types'

const SYMBOLS = ['NIFTY', 'BANKNIFTY', 'SENSEX']
const TIMEFRAMES = ['1', '5', '15', '60']

const inr = (v: any) => {
  const n = Number(v) || 0
  return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}
const num = (v: any, d = 2) => (v === undefined || v === null || !isFinite(Number(v)) ? '—' : Number(v).toFixed(d))
const pct = (v: any) => (v === undefined || v === null ? '—' : `${(Number(v) * 100).toFixed(1)}%`)

function MetricCard({ label, value, tone }: { label: string; value: string; tone?: 'pos' | 'neg' | 'neutral' }) {
  const color = tone === 'pos' ? 'text-emerald-500' : tone === 'neg' ? 'text-red-500' : 'text-gray-900 dark:text-white'
  return (
    <div className="rounded-xl bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 p-3">
      <p className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-dark-400 font-bold">{label}</p>
      <p className={`text-lg font-bold mt-1 ${color}`}>{value}</p>
    </div>
  )
}

const TABS = [
  { id: 'run', label: 'Run', icon: Play },
  { id: 'results', label: 'Results', icon: BarChart3 },
  { id: 'runs', label: 'Runs', icon: Activity },
  { id: 'compare', label: 'Compare', icon: GitCompare },
  { id: 'walkforward', label: 'Walk-Forward', icon: Repeat },
  { id: 'calibration', label: 'Calibration', icon: Brain },
] as const

export default function Backtest() {
  const { runs, selectedRun, trades, equity, report, activeTab, isRunning, isLoading, error,
          setTab, fetchRuns, runBacktest, selectRun } = useBacktestStore()
  const { addToast } = useUIStore()

  const [cfg, setCfg] = useState<BacktestConfig>({
    symbol: 'NIFTY', timeframe: '5', mode: 'INDEX_PROXY',
    start_date: '', end_date: '',
    option_symbol: '', option_type: 'CE',
    parameters: { sl_points: 20, target_points: 40, min_confidence: 0.5 },
    risk: { lot_size: 50, capital: 1000000, risk_pct: 0.01 },
    costs: { slippage_pct: 0.0005, brokerage_per_order: 20 },
  })

  // OPTION_PREMIUM: auto-load real strikes (no manual symbol typing).
  const [optExpiries, setOptExpiries] = useState<string[]>([])
  const [optExpiry, setOptExpiry] = useState('')
  const [optInstruments, setOptInstruments] = useState<any[]>([])
  const [loadingOpt, setLoadingOpt] = useState(false)

  useEffect(() => { fetchRuns() }, [])
  useEffect(() => { if (error) addToast('error', error) }, [error])

  // Load expiries for the chosen index when Option Premium is active.
  useEffect(() => {
    if (cfg.mode !== 'OPTION_PREMIUM' || !cfg.symbol) return
    let alive = true
    instrumentsApi.getExpiries(cfg.symbol)
      .then((list: string[]) => { if (alive) { setOptExpiries(list || []); if (!optExpiry && list?.length) setOptExpiry(list[0]) } })
      .catch(() => { if (alive) setOptExpiries([]) })
    return () => { alive = false }
  }, [cfg.mode, cfg.symbol])

  // Load strikes (CE/PE) for the chosen expiry; auto-select the first.
  useEffect(() => {
    if (cfg.mode !== 'OPTION_PREMIUM' || !cfg.symbol || !optExpiry) return
    let alive = true
    setLoadingOpt(true)
    instrumentsApi.getInstruments(cfg.symbol, optExpiry, cfg.option_type || 'CE')
      .then((rows: any[]) => {
        if (!alive) return
        const sorted = (rows || []).sort((a, b) => (a.strike_price || 0) - (b.strike_price || 0))
        setOptInstruments(sorted)
        setCfg((c) => ({ ...c, option_symbol: sorted[0]?.trading_symbol || '' }))
      })
      .catch(() => { if (alive) setOptInstruments([]) })
      .finally(() => { if (alive) setLoadingOpt(false) })
    return () => { alive = false }
  }, [cfg.mode, cfg.symbol, optExpiry, cfg.option_type])

  const p = (k: string, v: any) => setCfg((c) => ({ ...c, parameters: { ...c.parameters, [k]: v } }))
  const r = (k: string, v: any) => setCfg((c) => ({ ...c, risk: { ...c.risk, [k]: v } }))
  const co = (k: string, v: any) => setCfg((c) => ({ ...c, costs: { ...c.costs, [k]: v } }))

  const m = report?.metrics || selectedRun?.summary || {}
  const edgePass = (Number(m.expectancy) > 0) && (Number(m.profit_factor) > 1)

  const onRun = async () => {
    if (cfg.mode === 'OPTION_PREMIUM' && !cfg.option_symbol?.trim()) {
      addToast('error', 'Enter the option symbol (e.g. NIFTY25JAN23000CE) for OPTION_PREMIUM mode')
      return
    }
    const id = await runBacktest(cfg)
    if (id) addToast('success', 'Backtest complete')
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-primary-50 dark:bg-primary-500/10 flex items-center justify-center">
          <FlaskConical className="w-5 h-5 text-primary-600 dark:text-primary-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">Backtesting Machine</h1>
          <p className="text-xs text-gray-500 dark:text-dark-400">Strategy Lab — replay the live decision engine on history</p>
        </div>
      </div>

      {/* INDEX_PROXY caveat — always visible */}
      <div className="rounded-xl border border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 px-4 py-2.5 flex items-start gap-2">
        <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
        <p className="text-xs text-amber-700 dark:text-amber-400">
          <b>INDEX_PROXY</b> measures direction using index points (delta≈1) — it is <b>not</b> real option P&amp;L.
          <b> OPTION_PREMIUM</b> (real strike candles) is required before any live validation.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 overflow-x-auto border-b border-gray-200 dark:border-dark-700">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id as any)}
            className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors ${
              activeTab === t.id ? 'border-primary-500 text-primary-600 dark:text-primary-400'
              : 'border-transparent text-gray-500 dark:text-dark-400 hover:text-gray-900 dark:hover:text-white'}`}>
            <t.icon className="w-4 h-4" /> {t.label}
          </button>
        ))}
      </div>

      {/* ---------- RUN ---------- */}
      {activeTab === 'run' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 p-4 space-y-3">
            <h3 className="font-bold text-gray-900 dark:text-white text-sm">Setup</h3>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Symbol">
                <select className="input-field" value={cfg.symbol} onChange={(e) => setCfg({ ...cfg, symbol: e.target.value })}>
                  {SYMBOLS.map((s) => <option key={s}>{s}</option>)}
                </select>
              </Field>
              <Field label="Timeframe">
                <select className="input-field" value={cfg.timeframe} onChange={(e) => setCfg({ ...cfg, timeframe: e.target.value })}>
                  {TIMEFRAMES.map((t) => <option key={t} value={t}>{t}m</option>)}
                </select>
              </Field>
              <Field label="Start date"><input type="date" className="input-field" value={cfg.start_date} onChange={(e) => setCfg({ ...cfg, start_date: e.target.value })} /></Field>
              <Field label="End date"><input type="date" className="input-field" value={cfg.end_date} onChange={(e) => setCfg({ ...cfg, end_date: e.target.value })} /></Field>
              <Field label="Data mode">
                <select className="input-field" value={cfg.mode} onChange={(e) => setCfg({ ...cfg, mode: e.target.value as BacktestMode })}>
                  <option value="INDEX_PROXY">Index Proxy (directional)</option>
                  <option value="OPTION_PREMIUM">Option Premium (real)</option>
                </select>
              </Field>
            </div>

            {cfg.mode === 'OPTION_PREMIUM' && (
              <div className="space-y-2 rounded-lg border border-cyan-200 dark:border-cyan-500/20 bg-cyan-50 dark:bg-cyan-500/5 p-3">
                <div className="grid grid-cols-3 gap-2">
                  <Field label="Type">
                    <select className="input-field" value={cfg.option_type || 'CE'} onChange={(e) => setCfg({ ...cfg, option_type: e.target.value as 'CE' | 'PE' })}>
                      <option value="CE">CE</option>
                      <option value="PE">PE</option>
                    </select>
                  </Field>
                  <Field label="Expiry">
                    <select className="input-field" value={optExpiry} onChange={(e) => setOptExpiry(e.target.value)}>
                      {!optExpiries.length && <option value="">—</option>}
                      {optExpiries.map((e) => <option key={e} value={e}>{e}</option>)}
                    </select>
                  </Field>
                  <Field label={`Strike ${loadingOpt ? '…' : ''}`}>
                    <select className="input-field" value={cfg.option_symbol || ''} onChange={(e) => setCfg({ ...cfg, option_symbol: e.target.value })}>
                      {!optInstruments.length && <option value="">No strikes</option>}
                      {optInstruments.map((i) => <option key={i._id || i.trading_symbol} value={i.trading_symbol}>{i.strike_price} — {i.trading_symbol}</option>)}
                    </select>
                  </Field>
                </div>
                <p className="text-[11px] text-cyan-700 dark:text-cyan-300">
                  Strikes load automatically for the index + expiry. The chosen strike's
                  <b> real candles must be synced</b> first, else the run returns a clear message —
                  use Index Proxy for directional validation.
                </p>
              </div>
            )}
          </div>

          <div className="rounded-xl bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 p-4 space-y-3">
            <h3 className="font-bold text-gray-900 dark:text-white text-sm">Strategy, risk &amp; costs</h3>
            <div className="grid grid-cols-2 gap-3">
              <Field label="SL points"><input type="number" className="input-field" value={cfg.parameters?.sl_points} onChange={(e) => p('sl_points', +e.target.value)} /></Field>
              <Field label="Target points"><input type="number" className="input-field" value={cfg.parameters?.target_points} onChange={(e) => p('target_points', +e.target.value)} /></Field>
              <Field label="Min confidence"><input type="number" step="0.05" className="input-field" value={cfg.parameters?.min_confidence} onChange={(e) => p('min_confidence', +e.target.value)} /></Field>
              <Field label="Min p_win"><input type="number" step="0.05" className="input-field" value={cfg.parameters?.min_p_win ?? ''} onChange={(e) => p('min_p_win', +e.target.value)} /></Field>
              <Field label="Lot size"><input type="number" className="input-field" value={cfg.risk?.lot_size} onChange={(e) => r('lot_size', +e.target.value)} /></Field>
              <Field label="Capital"><input type="number" className="input-field" value={cfg.risk?.capital} onChange={(e) => r('capital', +e.target.value)} /></Field>
              <Field label="Risk %/trade"><input type="number" step="0.005" className="input-field" value={cfg.risk?.risk_pct} onChange={(e) => r('risk_pct', +e.target.value)} /></Field>
              <Field label="Slippage %"><input type="number" step="0.0001" className="input-field" value={cfg.costs?.slippage_pct} onChange={(e) => co('slippage_pct', +e.target.value)} /></Field>
              <Field label="Brokerage/order"><input type="number" className="input-field" value={cfg.costs?.brokerage_per_order} onChange={(e) => co('brokerage_per_order', +e.target.value)} /></Field>
            </div>
            <button onClick={onRun} disabled={isRunning} className="btn-primary w-full flex items-center justify-center gap-2">
              {isRunning ? <><RefreshCw className="w-4 h-4 animate-spin" /> Running…</> : <><Play className="w-4 h-4" /> Run Backtest</>}
            </button>
          </div>
        </div>
      )}

      {/* ---------- RESULTS ---------- */}
      {activeTab === 'results' && (
        !selectedRun ? <Empty msg="No run selected. Run a backtest or pick one from Runs." />
        : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold text-gray-900 dark:text-white">{selectedRun.symbol} · {selectedRun.timeframe}m</span>
            <Badge tone={selectedRun.mode === 'INDEX_PROXY' ? 'warn' : 'info'}>{selectedRun.mode}</Badge>
            <Badge tone={edgePass ? 'pos' : 'neg'}>{edgePass ? 'Edge: PASS' : 'Edge: FAIL'}</Badge>
            <span className="text-xs text-gray-500 dark:text-dark-400">{selectedRun.trade_count ?? trades.length} trades</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
            <MetricCard label="Net P&L" value={inr(m.total_net)} tone={Number(m.total_net) >= 0 ? 'pos' : 'neg'} />
            <MetricCard label="Win rate" value={pct(m.win_rate)} />
            <MetricCard label="Expectancy" value={inr(m.expectancy)} tone={Number(m.expectancy) >= 0 ? 'pos' : 'neg'} />
            <MetricCard label="Profit factor" value={num(m.profit_factor)} />
            <MetricCard label="Max DD" value={inr(m.max_drawdown)} tone="neg" />
            <MetricCard label="Sharpe" value={num(m.sharpe)} />
            <MetricCard label="Sortino" value={num(m.sortino)} />
            <MetricCard label="Payoff" value={num(m.payoff_ratio)} />
            <MetricCard label="Recovery" value={num(m.recovery_factor)} />
            <MetricCard label="Avg hold (bars)" value={num(m.avg_holding_bars, 1)} />
            <MetricCard label="Trades/day" value={num(m.trades_per_day, 1)} />
            <MetricCard label="Max DD %" value={`${num(m.max_drawdown_pct, 1)}%`} tone="neg" />
          </div>

          {edgePass && (
            <button onClick={() => addToast('info', 'Switch to PAPER mode in Settings and create a strategy with these params. Live is intentionally not enabled here.')}
              className="btn-secondary text-sm">Use this strategy in Paper Mode</button>
          )}

          <Panel title="Equity & drawdown">
            {equity?.equity_curve?.length ? <EquityCurveChart equity={equity.equity_curve} drawdown={equity.drawdown_curve} /> : <Empty msg="No equity data" />}
          </Panel>
          <Panel title="Daily P&L">
            {equity?.daily_pnl?.length ? <DailyPnlChart daily={equity.daily_pnl} /> : <Empty msg="No daily data" />}
          </Panel>

          <div className="grid gap-4 md:grid-cols-2">
            <Panel title="By market regime"><Breakdown data={m.by_regime} /></Panel>
            <Panel title="By confidence bucket"><Breakdown data={m.by_confidence_bucket} /></Panel>
          </div>

          <Panel title={`Trades (${trades.length})`}>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead><tr className="text-left text-gray-500 dark:text-dark-400 border-b border-gray-200 dark:border-dark-700">
                  {['Dir', 'Entry', 'Exit', 'Qty', 'Gross', 'Charges', 'Net', 'Reason', 'Conf', 'Regime'].map((h) => <th key={h} className="px-2 py-2 font-semibold whitespace-nowrap">{h}</th>)}
                </tr></thead>
                <tbody>
                  {trades.slice(0, 200).map((t, i) => (
                    <tr key={i} className="border-b border-gray-100 dark:border-dark-800">
                      <td className="px-2 py-1.5"><Badge tone={t.direction === 'BULLISH' ? 'pos' : 'neg'}>{t.direction === 'BULLISH' ? 'CE' : 'PE'}</Badge></td>
                      <td className="px-2 py-1.5 whitespace-nowrap">{num(t.entry_index)}</td>
                      <td className="px-2 py-1.5 whitespace-nowrap">{num(t.exit_index)}</td>
                      <td className="px-2 py-1.5">{t.qty}</td>
                      <td className="px-2 py-1.5">{inr(t.gross)}</td>
                      <td className="px-2 py-1.5 text-gray-400">{inr((t.charges || 0) + (t.slippage || 0))}</td>
                      <td className={`px-2 py-1.5 font-semibold ${Number(t.net) >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>{inr(t.net)}</td>
                      <td className="px-2 py-1.5">{t.exit_reason}</td>
                      <td className="px-2 py-1.5">{num(t.confidence)}</td>
                      <td className="px-2 py-1.5 text-gray-400">{t.regime || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
        )
      )}

      {/* ---------- RUNS ---------- */}
      {activeTab === 'runs' && (
        <Panel title="Recent runs" action={<button onClick={fetchRuns} className="text-xs text-primary-600 dark:text-primary-400 flex items-center gap-1"><RefreshCw className="w-3 h-3" /> Refresh</button>}>
          {isLoading ? <Skeleton /> : !runs.length ? <Empty msg="No runs yet. Run your first backtest." /> : (
            <div className="space-y-2">
              {runs.map((run) => (
                <button key={run.run_id} onClick={() => { selectRun(run.run_id); setTab('results') }}
                  className="w-full text-left rounded-lg border border-gray-200 dark:border-dark-700 px-3 py-2 hover:border-primary-400 transition-colors flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm text-gray-900 dark:text-white">{run.symbol} · {run.timeframe}m</span>
                      <Badge tone={run.status === 'COMPLETED' ? 'pos' : run.status === 'FAILED' ? 'neg' : 'neutral'}>{run.status}</Badge>
                      <Badge tone={run.mode === 'INDEX_PROXY' ? 'warn' : 'info'}>{run.mode}</Badge>
                    </div>
                    <p className="text-[11px] text-gray-500 dark:text-dark-400 truncate">{run.error || `${run.trade_count ?? 0} trades`}</p>
                  </div>
                  {run.summary && <span className={`text-sm font-bold shrink-0 ${Number(run.summary.total_net) >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>{inr(run.summary.total_net)}</span>}
                </button>
              ))}
            </div>
          )}
        </Panel>
      )}

      {/* ---------- COMPARE ---------- */}
      {activeTab === 'compare' && <CompareTab runs={runs} />}

      {/* ---------- WALK-FORWARD ---------- */}
      {activeTab === 'walkforward' && <WalkForwardTab cfg={cfg} />}

      {/* ---------- CALIBRATION ---------- */}
      {activeTab === 'calibration' && <CalibrationTab />}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block"><span className="block text-[10px] uppercase tracking-wider text-gray-500 dark:text-dark-400 font-bold mb-1">{label}</span>{children}</label>
}
function Panel({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 p-4">
      <div className="flex items-center justify-between mb-3"><h3 className="font-bold text-gray-900 dark:text-white text-sm">{title}</h3>{action}</div>
      {children}
    </div>
  )
}
function Empty({ msg }: { msg: string }) { return <div className="text-center py-10 text-sm text-gray-400 dark:text-dark-500">{msg}</div> }
function Skeleton() { return <div className="space-y-2">{[0, 1, 2].map((i) => <div key={i} className="h-12 rounded-lg bg-gray-100 dark:bg-dark-800 animate-pulse" />)}</div> }
function Badge({ tone, children }: { tone: 'pos' | 'neg' | 'warn' | 'info' | 'neutral'; children: React.ReactNode }) {
  const map: Record<string, string> = {
    pos: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
    neg: 'bg-red-500/10 text-red-600 dark:text-red-400',
    warn: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
    info: 'bg-cyan-500/10 text-cyan-600 dark:text-cyan-400',
    neutral: 'bg-gray-500/10 text-gray-600 dark:text-gray-400',
  }
  return <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${map[tone]}`}>{children}</span>
}

function CompareTab({ runs }: { runs: any[] }) {
  const { addToast } = useUIStore()
  const [sel, setSel] = useState<string[]>([])
  const [result, setResult] = useState<any[]>([])
  const toggle = (id: string) => setSel((s) => s.includes(id) ? s.filter((x) => x !== id) : s.length < 5 ? [...s, id] : s)
  const compare = async () => {
    if (sel.length < 2) { addToast('error', 'Select 2-5 runs'); return }
    try { setResult((await backtestApi.compareRuns(sel)).runs || []) } catch (e: any) { addToast('error', e.response?.data?.error || 'Compare failed') }
  }
  return (
    <div className="space-y-3">
      <Panel title="Pick 2–5 runs" action={<button onClick={compare} className="btn-primary text-xs py-1.5 px-3">Compare</button>}>
        <div className="space-y-1 max-h-60 overflow-y-auto">
          {runs.filter((r) => r.status === 'COMPLETED').map((r) => (
            <label key={r.run_id} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-gray-50 dark:hover:bg-dark-800 cursor-pointer">
              <input type="checkbox" checked={sel.includes(r.run_id)} onChange={() => toggle(r.run_id)} />
              <span className="text-sm text-gray-900 dark:text-white">{r.symbol} · {r.timeframe}m</span>
              <span className="text-xs text-gray-400 ml-auto">{inr(r.summary?.total_net)}</span>
            </label>
          ))}
        </div>
      </Panel>
      {result.length > 0 && (
        <Panel title="Comparison">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-left text-gray-500 dark:text-dark-400 border-b border-gray-200 dark:border-dark-700">
                {['Run', 'Net', 'Win%', 'Expectancy', 'PF', 'Max DD', 'Sharpe'].map((h) => <th key={h} className="px-2 py-2">{h}</th>)}
              </tr></thead>
              <tbody>
                {result.map((rr) => {
                  const s = rr.summary || {}
                  return <tr key={rr.run_id} className="border-b border-gray-100 dark:border-dark-800">
                    <td className="px-2 py-1.5 whitespace-nowrap">{rr.symbol} {rr.timeframe}m</td>
                    <td className={`px-2 py-1.5 font-semibold ${Number(s.total_net) >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>{inr(s.total_net)}</td>
                    <td className="px-2 py-1.5">{pct(s.win_rate)}</td>
                    <td className="px-2 py-1.5">{inr(s.expectancy)}</td>
                    <td className="px-2 py-1.5">{num(s.profit_factor)}</td>
                    <td className="px-2 py-1.5">{inr(s.max_drawdown)}</td>
                    <td className="px-2 py-1.5">{num(s.sharpe)}</td>
                  </tr>
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </div>
  )
}

function Breakdown({ data }: { data?: Record<string, any> }) {
  const entries = Object.entries(data || {})
  if (!entries.length) return <Empty msg="No data" />
  return (
    <div className="space-y-2">
      {entries.map(([k, v]: any) => (
        <div key={k} className="text-xs">
          <div className="flex justify-between mb-0.5">
            <span className="text-gray-700 dark:text-dark-300 font-medium">{k}</span>
            <span className="text-gray-500 dark:text-dark-400">{v.count} · exp {inr(v.expectancy)}</span>
          </div>
          <div className="h-1.5 rounded bg-gray-100 dark:bg-dark-800 overflow-hidden">
            <div className="h-full bg-primary-500" style={{ width: `${Math.round((v.win_rate || 0) * 100)}%` }} />
          </div>
        </div>
      ))}
    </div>
  )
}

function WalkForwardTab({ cfg }: { cfg: BacktestConfig }) {
  const { addToast } = useUIStore()
  const [train, setTrain] = useState(500)
  const [test, setTest] = useState(100)
  const [step, setStep] = useState<number | ''>('')
  const [busy, setBusy] = useState(false)
  const [wf, setWf] = useState<any>(null)
  const run = async () => {
    setBusy(true)
    try {
      const res = await backtestApi.walkForward({ ...cfg, train_bars: train, test_bars: test, step_bars: step || undefined })
      setWf(res)
      if (!res.ok) addToast('error', res.reason || 'Walk-forward produced no windows')
    } catch (e: any) { addToast('error', e.response?.data?.error || 'Walk-forward failed') }
    finally { setBusy(false) }
  }
  const pooled = wf?.pooled || {}
  return (
    <div className="space-y-4">
      <Panel title="Walk-forward (rolling out-of-sample)" action={
        <button onClick={run} disabled={busy} className="btn-primary text-xs py-1.5 px-3 flex items-center gap-1">
          {busy ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Repeat className="w-3 h-3" />} Run
        </button>}>
        <p className="text-xs text-gray-500 dark:text-dark-400 mb-3">Uses {cfg.symbol} · {cfg.timeframe}m with the current Run params. Metrics are computed only on data the fitter never saw.</p>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Train bars"><input type="number" className="input-field" value={train} onChange={(e) => setTrain(+e.target.value)} /></Field>
          <Field label="Test bars"><input type="number" className="input-field" value={test} onChange={(e) => setTest(+e.target.value)} /></Field>
          <Field label="Step (opt)"><input type="number" className="input-field" value={step} onChange={(e) => setStep(e.target.value ? +e.target.value : '')} /></Field>
        </div>
      </Panel>
      {wf?.ok && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={wf.overfit_warning ? 'neg' : 'pos'}>{wf.overfit_warning ? 'OVERFIT WARNING' : 'OOS STABLE'}</Badge>
            <span className="text-xs text-gray-500 dark:text-dark-400">stability {num(wf.stability_score)} · {wf.n_windows} windows · {wf.n_trades} OOS trades</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <MetricCard label="Pooled net" value={inr(pooled.total_net)} tone={Number(pooled.total_net) >= 0 ? 'pos' : 'neg'} />
            <MetricCard label="Pooled win%" value={pct(pooled.win_rate)} />
            <MetricCard label="Pooled expectancy" value={inr(pooled.expectancy)} tone={Number(pooled.expectancy) >= 0 ? 'pos' : 'neg'} />
            <MetricCard label="Pooled PF" value={num(pooled.profit_factor)} />
          </div>
          <Panel title="Per-window OOS">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead><tr className="text-left text-gray-500 dark:text-dark-400 border-b border-gray-200 dark:border-dark-700">
                  {['#', 'Test bars', 'Trades', 'Win%', 'Expectancy', 'Net'].map((h) => <th key={h} className="px-2 py-2">{h}</th>)}
                </tr></thead>
                <tbody>
                  {(wf.windows || []).map((w: any) => (
                    <tr key={w.index} className="border-b border-gray-100 dark:border-dark-800">
                      <td className="px-2 py-1.5">{w.index + 1}</td>
                      <td className="px-2 py-1.5 whitespace-nowrap">{w.test_start}–{w.test_end}</td>
                      <td className="px-2 py-1.5">{w.n_trades}</td>
                      <td className="px-2 py-1.5">{pct(w.metrics?.win_rate)}</td>
                      <td className="px-2 py-1.5">{inr(w.metrics?.expectancy)}</td>
                      <td className={`px-2 py-1.5 font-semibold ${Number(w.metrics?.total_net) >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>{inr(w.metrics?.total_net)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
    </div>
  )
}

function CalibrationTab() {
  const { addToast } = useUIStore()
  const [status, setStatus] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const load = async () => { try { setStatus(await backtestApi.calibrationStatus()) } catch { /* ignore */ } }
  useEffect(() => { load() }, [])
  const run = async () => {
    setBusy(true)
    try {
      const res = await backtestApi.calibrate(50)
      addToast(res.success ? 'success' : 'error', res.success ? `Calibrated on ${res.n_samples} samples (Brier ${res.brier_score})` : res.reason)
      load()
    } catch (e: any) { addToast('error', e.response?.data?.reason || e.response?.data?.error || 'Calibration failed') }
    finally { setBusy(false) }
  }
  return (
    <Panel title="P(win) calibration">
      <div className="flex items-center gap-2 mb-3">
        {status?.fitted ? <CheckCircle2 className="w-5 h-5 text-emerald-500" /> : <XCircle className="w-5 h-5 text-gray-400" />}
        <span className="text-sm text-gray-900 dark:text-white">{status?.fitted ? 'Model fitted' : status?.exists ? 'Model present (unfitted)' : 'No model yet'}</span>
      </div>
      <p className="text-xs text-gray-500 dark:text-dark-400 mb-3">
        Trains a probability calibrator from labeled signals (same features the live engine uses).
        Saving a model does <b>not</b> enable live trading — that still needs out-of-sample expectancy and the explicit safety flag.
      </p>
      <button onClick={run} disabled={busy} className="btn-primary text-sm flex items-center gap-2">
        {busy ? <><RefreshCw className="w-4 h-4 animate-spin" /> Calibrating…</> : <><Brain className="w-4 h-4" /> Calibrate now</>}
      </button>
    </Panel>
  )
}
