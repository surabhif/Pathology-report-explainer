/**
 * Renders report text with an optional highlighted quote span.
 * Prefer character offsets from FactSpan; fall back to normalized quote match
 * (lowercase, collapse whitespace, strip punctuation) so OCR stray periods
 * like "free of. tumor" still highlight when the model quote omits them.
 */

interface Props {
  text: string
  highlightQuote?: string | null
  startChar?: number | null
  endChar?: number | null
}

function findNormalizedSpan(text: string, quote: string): { start: number; end: number } | null {
  const exact = text.indexOf(quote)
  if (exact >= 0) return { start: exact, end: exact + quote.length }
  const lowerIdx = text.toLowerCase().indexOf(quote.toLowerCase())
  if (lowerIdx >= 0) return { start: lowerIdx, end: lowerIdx + quote.length }

  const isPunct = (ch: string) => /[!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]/.test(ch)
  const normChars: string[] = []
  const indexMap: number[] = []
  let prevSpace = true
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    const low = ch.toLowerCase()
    if (isPunct(ch)) {
      if (!prevSpace && normChars.length) {
        normChars.push(' ')
        indexMap.push(i)
        prevSpace = true
      }
      continue
    }
    if (/\s/.test(ch)) {
      if (!prevSpace && normChars.length) {
        normChars.push(' ')
        indexMap.push(i)
        prevSpace = true
      }
      continue
    }
    normChars.push(low)
    indexMap.push(i)
    prevSpace = false
  }
  if (normChars.length && normChars[normChars.length - 1] === ' ') {
    normChars.pop()
    indexMap.pop()
  }
  const normReport = normChars.join('')
  const normQuote = quote
    .toLowerCase()
    .replace(/[!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (!normQuote || !normReport) return null
  const pos = normReport.indexOf(normQuote)
  if (pos < 0) return null
  const start = indexMap[pos]
  const end = indexMap[pos + normQuote.length - 1] + 1
  return { start, end }
}

export function HighlightedReport({ text, highlightQuote, startChar, endChar }: Props) {
  let start = startChar ?? null
  let end = endChar ?? null

  if ((start == null || end == null) && highlightQuote) {
    const span = findNormalizedSpan(text, highlightQuote)
    if (span) {
      start = span.start
      end = span.end
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
