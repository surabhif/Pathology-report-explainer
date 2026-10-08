import type { ExplanationPayload, ExplanationSentence } from './types'

/** Reason codes mirrored from backend app.services.grounding */
export type GroundingReason = 'missing_quote' | 'quote_not_in_report' | 'missing_source_fact_keys'

export function normalizeQuote(quote: string | null | undefined): string {
  return (quote ?? '').trim()
}

/** Lowercase, strip punctuation to spaces, collapse whitespace — mirrors backend. */
export function normalizeForGrounding(text: string): string {
  if (!text) return ''
  return text
    .toLowerCase()
    .replace(/[!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export function splitEllipsisQuote(quote: string): string[] {
  const q = normalizeQuote(quote)
  if (!q) return []
  const parts = q
    .split(/\.{3}|…/)
    .map((p) => p.trim())
    .filter(Boolean)
  return parts.length ? parts : [q]
}

function normalizedWithIndexMap(text: string): { norm: string; indexMap: number[] } {
  const isPunct = (ch: string) => /[!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]/.test(ch)
  const normChars: string[] = []
  const indexMap: number[] = []
  let prevSpace = true
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
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
    normChars.push(ch.toLowerCase())
    indexMap.push(i)
    prevSpace = false
  }
  if (normChars.length && normChars[normChars.length - 1] === ' ') {
    normChars.pop()
    indexMap.pop()
  }
  return { norm: normChars.join(''), indexMap }
}

function findSingleSpan(quote: string, reportText: string): { start: number; end: number } | null {
  const q = normalizeQuote(quote)
  if (!q || !reportText) return null
  const exact = reportText.indexOf(q)
  if (exact >= 0) return { start: exact, end: exact + q.length }
  const lowerIdx = reportText.toLowerCase().indexOf(q.toLowerCase())
  if (lowerIdx >= 0) return { start: lowerIdx, end: lowerIdx + q.length }

  const { norm: normReport, indexMap } = normalizedWithIndexMap(reportText)
  const normQuote = normalizeForGrounding(q)
  if (!normQuote || !normReport) return null
  const pos = normReport.indexOf(normQuote)
  if (pos < 0) return null
  const start = indexMap[pos]
  const end = indexMap[pos + normQuote.length - 1] + 1
  return { start, end }
}

/**
 * Locate ``quote`` in ``reportText`` after grounding normalization.
 * Ellipsis-stitched quotes require every piece to match; highlight span uses
 * the first matching piece (mirrors backend ``find_quote_span``).
 */
export function findQuoteSpan(
  quote: string | null | undefined,
  reportText: string,
): { start: number; end: number } | null {
  const parts = splitEllipsisQuote(quote ?? '')
  if (!parts.length) return null
  const spans: { start: number; end: number }[] = []
  for (const part of parts) {
    const span = findSingleSpan(part, reportText)
    if (!span) return null
    spans.push(span)
  }
  return spans[0] ?? null
}

/** True when text at [start,end) matches quote under grounding normalization. */
export function offsetsMatchQuote(
  reportText: string,
  start: number | null | undefined,
  end: number | null | undefined,
  quote: string | null | undefined,
): boolean {
  if (start == null || end == null || start < 0 || end > reportText.length || start >= end) {
    return false
  }
  const q = normalizeQuote(quote)
  if (!q) return false
  const slice = reportText.slice(start, end)
  // Prefer first ellipsis piece — that is what we highlight.
  const piece = splitEllipsisQuote(q)[0] ?? q
  if (slice === piece || slice.toLowerCase() === piece.toLowerCase()) return true
  return normalizeForGrounding(slice) === normalizeForGrounding(piece)
}

/**
 * Resolve the highlight span for a fact/sentence quote against the *displayed* text.
 * 1. Text-search first (grounding normalization).
 * 2. Fall back to stored offsets only when that slice actually matches the quote.
 * 3. Otherwise null → UI shows "quote not found".
 */
export function resolveHighlightSpan(
  reportText: string,
  quote: string | null | undefined,
  startChar?: number | null,
  endChar?: number | null,
): { start: number; end: number } | null {
  if (quote) {
    const fromText = findQuoteSpan(quote, reportText)
    if (fromText) return fromText
  }
  if (offsetsMatchQuote(reportText, startChar, endChar, quote)) {
    return { start: startChar as number, end: endChar as number }
  }
  return null
}

export function quoteFoundInReport(quote: string, reportText: string): boolean {
  return findQuoteSpan(quote, reportText) != null
}

export function assessSentenceGrounding(
  sentence: ExplanationSentence,
  reportText: string,
): GroundingReason[] {
  // Prefer server-annotated grounding when present (matches stored eval checks).
  if (sentence.grounding && typeof sentence.grounding.ok === 'boolean') {
    return (sentence.grounding.reasons ?? []) as GroundingReason[]
  }
  const reasons: GroundingReason[] = []
  const keys = sentence.source_fact_keys ?? []
  const quote = normalizeQuote(sentence.quote)
  if (!keys.length) reasons.push('missing_source_fact_keys')
  if (!quote) reasons.push('missing_quote')
  else if (!quoteFoundInReport(quote, reportText)) reasons.push('quote_not_in_report')
  return reasons
}

export function groundingLabel(reasons: GroundingReason[]): string {
  if (reasons.includes('missing_quote')) return 'No source quote'
  if (reasons.includes('quote_not_in_report')) return 'Quote not in report'
  if (reasons.includes('missing_source_fact_keys')) return 'No linked facts'
  return 'Ungrounded'
}

export function countUngrounded(explanation: ExplanationPayload, reportText: string): number {
  return explanation.sentences.filter((s) => assessSentenceGrounding(s, reportText).length > 0)
    .length
}
