/**
 * Renders report text with an optional highlighted quote span.
 *
 * Locate by text search first (same normalization as the grounding check).
 * Trust stored character offsets only when the text at those offsets actually
 * matches the quote. If nothing matches, show "quote not found" instead of a
 * wrong highlight — LLM-written offsets are often wrong.
 */

import { resolveHighlightSpan } from '../grounding'

interface Props {
  text: string
  highlightQuote?: string | null
  startChar?: number | null
  endChar?: number | null
}

export function HighlightedReport({ text, highlightQuote, startChar, endChar }: Props) {
  const wantsHighlight =
    Boolean(highlightQuote && highlightQuote.trim()) ||
    (startChar != null && endChar != null)

  if (!wantsHighlight) {
    return <div className="report-text">{text}</div>
  }

  const span = resolveHighlightSpan(text, highlightQuote, startChar, endChar)

  if (!span) {
    return (
      <div className="report-text">
        <p className="quote-not-found" role="status" data-testid="quote-not-found">
          Quote not found in this text
        </p>
        {text}
      </div>
    )
  }

  const before = text.slice(0, span.start)
  const mid = text.slice(span.start, span.end)
  const after = text.slice(span.end)

  return (
    <div className="report-text">
      {before}
      <mark className="quote-highlight" data-testid="quote-highlight">
        {mid}
      </mark>
      {after}
    </div>
  )
}
