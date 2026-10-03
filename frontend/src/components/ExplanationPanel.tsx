import type { ExplanationPayload } from '../types'
import { assessSentenceGrounding, groundingLabel } from '../grounding'

interface Props {
  explanation: ExplanationPayload
  /** Required to verify quotes word-for-word against the source report. */
  reportText: string
  activeIndex: number | null
  flagged?: number[]
  onSelect: (index: number, quote: string | null) => void
  onToggleFlag?: (index: number) => void
}

/**
 * Each explanation sentence is clickable to highlight its source quote.
 * Sentences with empty quotes or quotes not found in the report are marked
 * as ungrounded — they must never look as evidence-backed as grounded ones.
 */
export function ExplanationPanel({
  explanation,
  reportText,
  activeIndex,
  flagged = [],
  onSelect,
  onToggleFlag,
}: Props) {
  return (
    <div>
      {explanation.sentences.map((s, i) => {
        const isFlagged = flagged.includes(i)
        const reasons = assessSentenceGrounding(s, reportText)
        const ungrounded = reasons.length > 0
        const classes = [
          'sentence',
          activeIndex === i ? 'active' : '',
          isFlagged ? 'flagged' : '',
          ungrounded ? 'ungrounded' : '',
        ]
          .filter(Boolean)
          .join(' ')
        return (
          <div key={i} className="sentence-row">
            <button
              type="button"
              className={classes}
              onClick={() => onSelect(i, ungrounded ? null : s.quote)}
              aria-description={ungrounded ? groundingLabel(reasons) : 'Grounded sentence'}
            >
              <span className="sentence-text">{s.sentence}</span>
              {ungrounded && (
                <span className="ungrounded-badge" title={reasons.join(', ')}>
                  {groundingLabel(reasons)}
                </span>
              )}
            </button>
            {onToggleFlag && (
              <button
                type="button"
                className="btn btn-ghost"
                style={{ padding: '0.35rem 0.5rem', fontSize: '0.8rem' }}
                onClick={() => onToggleFlag(i)}
                aria-pressed={isFlagged}
                title="Flag sentence for review"
              >
                {isFlagged ? 'Flagged' : 'Flag'}
              </button>
            )}
          </div>
        )
      })}
    </div>
  )
}
