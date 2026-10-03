import { describe, expect, it } from 'vitest'
import { assessSentenceGrounding, groundingLabel, quoteFoundInReport } from '../grounding'

const REPORT = 'Procedure: Left total mastectomy and axillary lymph node dissection.'

describe('sentence grounding', () => {
  it('flags empty quotes', () => {
    const reasons = assessSentenceGrounding(
      {
        sentence: 'The doctor removed your left breast and some lymph nodes in surgery.',
        source_fact_keys: [],
        quote: '',
      },
      REPORT,
    )
    expect(reasons).toContain('missing_quote')
    expect(groundingLabel(reasons)).toBe('No source quote')
  })

  it('flags paraphrase quotes not in the report', () => {
    const reasons = assessSentenceGrounding(
      {
        sentence: 'Surgery removed the breast.',
        source_fact_keys: ['diagnosis_or_histologic_type'],
        quote: 'the doctor removed your left breast',
      },
      REPORT,
    )
    expect(reasons).toContain('quote_not_in_report')
  })

  it('accepts verbatim quotes', () => {
    expect(quoteFoundInReport('Left total mastectomy', REPORT)).toBe(true)
    const reasons = assessSentenceGrounding(
      {
        sentence: 'You had a left total mastectomy.',
        source_fact_keys: ['diagnosis_or_histologic_type'],
        quote: 'Left total mastectomy',
      },
      REPORT,
    )
    expect(reasons).toEqual([])
  })
})
