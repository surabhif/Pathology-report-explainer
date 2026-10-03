import type { FactSheet, FactSpan } from '../types'
import { FACT_FIELD_KEYS, FACT_FIELD_LABELS } from '../types'

function formatValue(span: FactSpan | null | undefined): string {
  if (!span || span.value == null || span.value === '') return '—'
  if (typeof span.value === 'object') {
    return Object.entries(span.value)
      .map(([k, v]) => `${k}: ${String(v)}`)
      .join(', ')
  }
  return String(span.value)
}

interface Props {
  facts: FactSheet
  activeKey: string | null
  onSelect: (key: keyof FactSheet, span: FactSpan | null) => void
}

/** Clickable structured fact sheet — selecting a row highlights its quote. */
export function FactSheetPanel({ facts, activeKey, onSelect }: Props) {
  return (
    <ul className="fact-list">
      {FACT_FIELD_KEYS.map((key) => {
        const span = facts[key]
        return (
          <li
            key={key}
            className={activeKey === key ? 'active' : ''}
            onClick={() => onSelect(key, span)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onSelect(key, span)
              }
            }}
            role="button"
            tabIndex={0}
          >
            <span className="fact-key">{FACT_FIELD_LABELS[key]}</span>
            <span className="fact-value">{formatValue(span)}</span>
          </li>
        )
      })}
    </ul>
  )
}
