import type { ExplanationPayload } from '../types'

interface Props {
  explanation: ExplanationPayload
  activeIndex: number | null
  flagged?: number[]
  onSelect: (index: number, quote: string | null) => void
  onToggleFlag?: (index: number) => void
}

/** Each explanation sentence is clickable to highlight its source quote. */
export function ExplanationPanel({
  explanation,
  activeIndex,
  flagged = [],
  onSelect,
  onToggleFlag,
}: Props) {
  return (
    <div>
      {explanation.sentences.map((s, i) => {
        const isFlagged = flagged.includes(i)
        return (
          <div key={i} className="row" style={{ alignItems: 'flex-start' }}>
            <button
              type="button"
              className={`sentence ${activeIndex === i ? 'active' : ''} ${isFlagged ? 'flagged' : ''}`}
              onClick={() => onSelect(i, s.quote)}
            >
              {s.sentence}
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
