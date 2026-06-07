/**
 * Confidence Configuration Component
 * Used in Strategy creation/edit form to configure signal confidence thresholds
 */
import { useState } from 'react'
import { 
  Zap, Shield, TrendingUp, Volume2,
  Clock, ChevronDown, ChevronUp, Info, Gauge
} from 'lucide-react'
import type { ConfidencePreset, AllowedSignals } from '../../types'

interface ConfidenceConfigProps {
  values: {
    confidence_preset: ConfidencePreset
    min_confidence: number
    volume_confirmation: boolean
    volatility_filter: boolean
    trend_alignment: boolean
    allowed_signals: AllowedSignals
    time_filter_enabled: boolean
    time_filter_start: string
    time_filter_end: string
    use_direction_engine: boolean
    direction_min_strength: number
  }
  onChange: (field: string, value: any) => void
  collapsed?: boolean
}

const PRESETS: Record<ConfidencePreset, { label: string; confidence: number; description: string; color: string }> = {
  conservative: {
    label: 'Conservative',
    confidence: 80,
    description: 'High confidence trades only, fewer but safer signals',
    color: 'text-blue-500'
  },
  balanced: {
    label: 'Balanced',
    confidence: 70,
    description: 'Default balanced risk/reward ratio',
    color: 'text-emerald-500'
  },
  aggressive: {
    label: 'Aggressive',
    confidence: 60,
    description: 'More trades, higher risk tolerance',
    color: 'text-amber-500'
  },
  custom: {
    label: 'Custom',
    confidence: 70,
    description: 'Set your own thresholds',
    color: 'text-purple-500'
  }
}

export default function ConfidenceConfig({ values, onChange, collapsed: initialCollapsed = true }: ConfidenceConfigProps) {
  const [showAdvanced, setShowAdvanced] = useState(!initialCollapsed)

  const handlePresetChange = (preset: ConfidencePreset) => {
    onChange('confidence_preset', preset)
    if (preset !== 'custom') {
      onChange('min_confidence', PRESETS[preset].confidence)
    }
  }

  const handleConfidenceChange = (value: number) => {
    onChange('min_confidence', value)
    // Check if value matches a preset
    const matchingPreset = Object.entries(PRESETS).find(
      ([key, preset]) => preset.confidence === value && key !== 'custom'
    )
    if (matchingPreset) {
      onChange('confidence_preset', matchingPreset[0])
    } else {
      onChange('confidence_preset', 'custom')
    }
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Gauge className="w-5 h-5 text-purple-500" />
          <h4 className="font-bold text-gray-900 dark:text-white">Signal Confidence</h4>
        </div>
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="text-xs text-blue-500 hover:text-blue-600 flex items-center gap-1"
        >
          {showAdvanced ? 'Hide' : 'Show'} Advanced
          {showAdvanced ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </button>
      </div>

      {/* Preset Selection */}
      <div className="grid grid-cols-4 gap-2">
        {(Object.keys(PRESETS) as ConfidencePreset[]).map((preset) => (
          <button
            key={preset}
            type="button"
            onClick={() => handlePresetChange(preset)}
            className={`p-3 rounded-xl border-2 transition-all ${
              values.confidence_preset === preset
                ? 'border-purple-500 bg-purple-50 dark:bg-purple-500/10'
                : 'border-gray-200 dark:border-dark-700 hover:border-gray-300 dark:hover:border-dark-600'
            }`}
          >
            <p className={`text-sm font-bold ${values.confidence_preset === preset ? PRESETS[preset].color : 'text-gray-700 dark:text-gray-300'}`}>
              {PRESETS[preset].label}
            </p>
            <p className="text-lg font-bold text-gray-900 dark:text-white mt-1">
              {preset === 'custom' ? values.min_confidence : PRESETS[preset].confidence}%
            </p>
          </button>
        ))}
      </div>

      {/* Confidence Slider */}
      <div className="p-4 bg-gray-50 dark:bg-dark-800/50 rounded-xl border border-gray-200 dark:border-dark-700">
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm text-gray-600 dark:text-dark-300">Minimum Confidence</label>
          <span className="text-lg font-bold text-purple-500">{values.min_confidence}%</span>
        </div>
        <input
          type="range"
          min="50"
          max="95"
          step="5"
          value={values.min_confidence}
          onChange={(e) => handleConfidenceChange(Number(e.target.value))}
          className="w-full h-2 bg-gray-200 dark:bg-dark-700 rounded-full appearance-none cursor-pointer accent-purple-500"
        />
        <div className="flex justify-between text-[10px] text-gray-400 dark:text-dark-500 mt-1">
          <span>50% (Aggressive)</span>
          <span>70% (Balanced)</span>
          <span>95% (Very Safe)</span>
        </div>
        <p className="text-xs text-gray-500 dark:text-dark-400 mt-2">
          {PRESETS[values.confidence_preset].description}
        </p>
      </div>

      {/* Direction Engine Toggle */}
      <div className="p-4 bg-gradient-to-r from-purple-50 to-blue-50 dark:from-purple-500/5 dark:to-blue-500/5 rounded-xl border border-purple-200 dark:border-purple-500/20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-100 dark:bg-purple-500/20 rounded-lg">
              <Zap className="w-5 h-5 text-purple-500" />
            </div>
            <div>
              <p className="font-bold text-gray-900 dark:text-white">Use Direction Engine</p>
              <p className="text-xs text-gray-500 dark:text-dark-400">New simplified 12-indicator system</p>
            </div>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={values.use_direction_engine}
              onChange={(e) => onChange('use_direction_engine', e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-gray-200 dark:bg-dark-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-500"></div>
          </label>
        </div>

        {values.use_direction_engine && (
          <div className="mt-3 pt-3 border-t border-purple-200 dark:border-purple-500/20">
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm text-gray-600 dark:text-dark-300">Min Direction Strength</label>
              <span className="text-sm font-bold text-purple-500">{values.direction_min_strength}%</span>
            </div>
            <input
              type="range"
              min="40"
              max="90"
              step="5"
              value={values.direction_min_strength}
              onChange={(e) => onChange('direction_min_strength', Number(e.target.value))}
              className="w-full h-2 bg-purple-200 dark:bg-purple-500/20 rounded-full appearance-none cursor-pointer accent-purple-500"
            />
          </div>
        )}
      </div>

      {/* Advanced Filters */}
      {showAdvanced && (
        <div className="space-y-3 p-4 bg-gray-50 dark:bg-dark-800/50 rounded-xl border border-gray-200 dark:border-dark-700">
          <p className="text-xs font-bold text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-3">
            Advanced Signal Filters
          </p>

          {/* Volume Confirmation */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Volume2 className="w-4 h-4 text-blue-500" />
              <div>
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Volume Confirmation</p>
                <p className="text-xs text-gray-500 dark:text-dark-400">Require volume support for signals</p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={values.volume_confirmation}
                onChange={(e) => onChange('volume_confirmation', e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-9 h-5 bg-gray-200 dark:bg-dark-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-500"></div>
            </label>
          </div>

          {/* Volatility Filter */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Shield className="w-4 h-4 text-amber-500" />
              <div>
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Volatility Filter</p>
                <p className="text-xs text-gray-500 dark:text-dark-400">Skip signals in extreme volatility</p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={values.volatility_filter}
                onChange={(e) => onChange('volatility_filter', e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-9 h-5 bg-gray-200 dark:bg-dark-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-amber-500"></div>
            </label>
          </div>

          {/* Trend Alignment */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <TrendingUp className="w-4 h-4 text-emerald-500" />
              <div>
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Trend Alignment</p>
                <p className="text-xs text-gray-500 dark:text-dark-400">Higher timeframe must confirm</p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={values.trend_alignment}
                onChange={(e) => onChange('trend_alignment', e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-9 h-5 bg-gray-200 dark:bg-dark-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-500"></div>
            </label>
          </div>

          {/* Allowed Signals */}
          <div className="pt-3 border-t border-gray-200 dark:border-dark-700">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Allowed Signals</p>
            <div className="grid grid-cols-3 gap-2">
              {(['BOTH', 'BULLISH', 'BEARISH'] as AllowedSignals[]).map((signal) => (
                <button
                  key={signal}
                  type="button"
                  onClick={() => onChange('allowed_signals', signal)}
                  className={`py-2 px-3 rounded-lg border text-xs font-bold transition-all ${
                    values.allowed_signals === signal
                      ? signal === 'BULLISH'
                        ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600'
                        : signal === 'BEARISH'
                        ? 'border-red-500 bg-red-50 dark:bg-red-500/10 text-red-600'
                        : 'border-blue-500 bg-blue-50 dark:bg-blue-500/10 text-blue-600'
                      : 'border-gray-200 dark:border-dark-700 text-gray-600 dark:text-gray-400 hover:border-gray-300'
                  }`}
                >
                  {signal === 'BOTH' ? '↕ Both' : signal === 'BULLISH' ? '↑ Bullish' : '↓ Bearish'}
                </button>
              ))}
            </div>
          </div>

          {/* Time Filter */}
          <div className="pt-3 border-t border-gray-200 dark:border-dark-700">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-3">
                <Clock className="w-4 h-4 text-purple-500" />
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Time Filter</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={values.time_filter_enabled}
                  onChange={(e) => onChange('time_filter_enabled', e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-9 h-5 bg-gray-200 dark:bg-dark-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-purple-500"></div>
              </label>
            </div>
            {values.time_filter_enabled && (
              <div className="flex items-center gap-2 mt-2">
                <input
                  type="time"
                  value={values.time_filter_start}
                  onChange={(e) => onChange('time_filter_start', e.target.value)}
                  className="flex-1 px-3 py-2 bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 rounded-lg text-sm"
                />
                <span className="text-gray-500">to</span>
                <input
                  type="time"
                  value={values.time_filter_end}
                  onChange={(e) => onChange('time_filter_end', e.target.value)}
                  className="flex-1 px-3 py-2 bg-white dark:bg-dark-900 border border-gray-200 dark:border-dark-700 rounded-lg text-sm"
                />
              </div>
            )}
          </div>
        </div>
      )}

      {/* Info Box */}
      <div className="flex items-start gap-2 p-3 bg-blue-50 dark:bg-blue-500/5 rounded-lg border border-blue-200 dark:border-blue-500/20">
        <Info className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
        <p className="text-xs text-blue-600 dark:text-blue-400">
          Higher confidence thresholds mean fewer but more reliable signals. 
          The Direction Engine uses simplified 12 indicators for faster, more accurate signals.
        </p>
      </div>
    </div>
  )
}
