/**
 * Renders report text with an optional highlighted quote span.
 * Prefer character offsets from FactSpan; fall back to first quote match.
 */

interface Props {
  text: string
  highlightQuote?: string | null
  startChar?: number | null
  endChar?: number | null
}

export function HighlightedReport({ text, highlightQuote, startChar, endChar }: Props) {
  let start = startChar ?? null
  let end = endChar ?? null

  if ((start == null || end == null) && highlightQuote) {
    const idx = text.indexOf(highlightQuote)
    if (idx >= 0) {
      start = idx
      end = idx + highlightQuote.length
    } else {
      const lower = text.toLowerCase()
      const q = highlightQuote.toLowerCase()
      const i = lower.indexOf(q)
      if (i >= 0) {
        start = i
        end = i + highlightQuote.length
      }
    }
  }

  if (start == null || end == null || start < 0 || end > text.length || start >= end) {
    return <div className="report-text">{text}</div>
  }

  const before = text.slice(0, start)
  const mid = text.slice(start, end)
  const after = text.slice(end)

  return (
    <div className="report-text">
      {before}
      <mark className="quote-highlight">{mid}</mark>
      {after}
    </div>
  )
}
