import type { ExplanationPayload, ExplanationSentence } from './types'

/** Reason codes mirrored from backend app.services.grounding */
export type GroundingReason = 'missing_quote' | 'quote_not_in_report' | 'missing_source_fact_keys'

export function normalizeQuote(quote: string | null | undefined): string {
  return (quote ?? '').trim()
}

export function quoteFoundInReport(quote: string, reportText: string): boolean {
  const q = normalizeQuote(quote)
  if (!q || !reportText) return false
  const pieces = q
    .split(/\.{3}|…/)
    .map((p) => p.trim())
    .filter(Boolean)
  const parts = pieces.length ? pieces : [q]
  return parts.every((part) => {
    if (reportText.includes(part)) return true
    return reportText.toLowerCase().includes(part.toLowerCase())
  })
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
