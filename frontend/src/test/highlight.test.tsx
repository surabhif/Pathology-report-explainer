import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HighlightedReport } from '../components/HighlightedReport'
import {
  findQuoteSpan,
  offsetsMatchQuote,
  resolveHighlightSpan,
} from '../grounding'

/**
 * Colon 9 (TCGA-A6-3808) excerpt: wrong LLM offsets land on the lymph-node
 * fragment; the diagnosis quote actually appears later (with a newline).
 */
const COLON9_OCR = `
keeping with lymph nodes measuring up to 1.4 cm. in greatest
dimension are recovered from the attached mesocolon and mesentery.
Representative sections are submitted in 13 blocks as labeled.
DIAGNOSIS
Colon, right and terminal ileum, resection:
Invasive moderately-differentiated colonic adenocarcinoma with
mucinous differentiation extending through the wall of the colon
into the pericolonic fat.
The proximal, distal and radial margins of resection are free of
tumor.
Histologic grade: Moderately-differentiated.
On opening there is a well circumscribed, 4.4 x 4.0 cm. rubbery tan
`.trim()

const DIAGNOSIS_QUOTE =
  'Invasive moderately-differentiated colonic adenocarcinoma with mucinous differentiation'

describe('resolveHighlightSpan / grounding locate', () => {
  it('finds diagnosis by text search despite wrong stored offsets (colon 9)', () => {
    const wrongStart = COLON9_OCR.indexOf('keeping with lymph nodes')
    const wrongEnd = wrongStart + DIAGNOSIS_QUOTE.length
    // Confirm the bug shape: offsets point at lymph-node text
    expect(COLON9_OCR.slice(wrongStart, wrongEnd)).toMatch(/lymph nodes measuring/)

    const span = resolveHighlightSpan(COLON9_OCR, DIAGNOSIS_QUOTE, wrongStart, wrongEnd)
    expect(span).not.toBeNull()
    const highlighted = COLON9_OCR.slice(span!.start, span!.end)
    expect(highlighted.toLowerCase()).toContain('adenocarcinoma')
    expect(highlighted.toLowerCase()).not.toContain('lymph nodes measuring')
  })

  it('rejects stored offsets that do not match the quote', () => {
    const start = COLON9_OCR.indexOf('keeping with lymph nodes')
    expect(offsetsMatchQuote(COLON9_OCR, start, start + 40, DIAGNOSIS_QUOTE)).toBe(false)
  })

  it('accepts stored offsets when the slice matches under normalization', () => {
    const found = findQuoteSpan(DIAGNOSIS_QUOTE, COLON9_OCR)
    expect(found).not.toBeNull()
    expect(offsetsMatchQuote(COLON9_OCR, found!.start, found!.end, DIAGNOSIS_QUOTE)).toBe(true)
  })

  it('returns null when quote is absent', () => {
    expect(resolveHighlightSpan(COLON9_OCR, 'totally fabricated quote', 0, 10)).toBeNull()
  })

  it('highlights against whichever text is shown (reference vs OCR)', () => {
    const reference = 'Diagnosis: adenocarcinoma. Grade: 2. Size 4.4 x 4.0 cm.'
    const ocr = 'Diagnosis: adenocarcinoma .\nGrade 2.\nSize 4.4 x 4.0 cm'
    const quote = '4.4 x 4.0 cm'
    const refSpan = resolveHighlightSpan(reference, quote, 0, 5)
    const ocrSpan = resolveHighlightSpan(ocr, quote, 0, 5)
    expect(reference.slice(refSpan!.start, refSpan!.end)).toBe(quote)
    expect(ocr.slice(ocrSpan!.start, ocrSpan!.end)).toBe(quote)
  })
})

describe('HighlightedReport', () => {
  it('highlights the correct diagnosis span for colon 9 despite bad offsets', () => {
    const wrongStart = COLON9_OCR.indexOf('keeping with lymph nodes')
    const wrongEnd = wrongStart + 40
    render(
      <HighlightedReport
        text={COLON9_OCR}
        highlightQuote={DIAGNOSIS_QUOTE}
        startChar={wrongStart}
        endChar={wrongEnd}
      />,
    )
    const mark = screen.getByTestId('quote-highlight')
    expect(mark.textContent?.toLowerCase()).toContain('adenocarcinoma')
    expect(mark.textContent?.toLowerCase()).not.toContain('lymph nodes measuring')
  })

  it('shows quote not found when nothing matches', () => {
    render(
      <HighlightedReport
        text={COLON9_OCR}
        highlightQuote="this quote does not exist anywhere in the report"
        startChar={0}
        endChar={10}
      />,
    )
    expect(screen.getByTestId('quote-not-found')).toHaveTextContent(/quote not found/i)
    expect(screen.queryByTestId('quote-highlight')).toBeNull()
  })

  it('uses matching offsets only as a fallback when text search would work anyway', () => {
    const found = findQuoteSpan('Moderately-differentiated', COLON9_OCR)!
    render(
      <HighlightedReport
        text={COLON9_OCR}
        highlightQuote="Moderately-differentiated"
        startChar={found.start}
        endChar={found.end}
      />,
    )
    expect(screen.getByTestId('quote-highlight').textContent).toMatch(/Moderately-differentiated/i)
  })
})
