import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ReportJourney } from '../components/ReportJourney'
import type { ExplainResponse, ReportJourneyOut } from '../types'

const journey: ReportJourneyOut = {
  report_id: 1,
  tcga_barcode: 'TCGA-B6-A401',
  cancer_type: 'BRCA',
  scan_source: 'ocr_text_facsimile',
  scan_label: 'Page facsimile from OCR text',
  scan_citation: 'GDC unreachable; facsimile from OCR.',
  scan_pages: [
    {
      page: 1,
      url: '/api/public/reports/1/scan-pages/page-01.jpg',
      width: 850,
      height: 1100,
    },
  ],
  ocr_label: 'Machine-readable OCR text from TCGA-Reports (Kefeli et al., Patterns 2024; AWS Textract).',
  ocr_citation: 'Kefeli et al., Patterns 2024.',
  report_text: 'Histologic type: Invasive ductal carcinoma. Tumor size: 2.1 cm.',
  our_ocr: {
    ocr_run_id: 1,
    engine: 'tesseract',
    engine_version: 'tesseract-5.3.4',
    text: 'Histologic type: Invasive ductal carcinoma. Tumor size: 2.1 cm.',
    duration_ms: 120,
    cer: 0.02,
    wer: 0.05,
    page_count: 1,
  },
  default_ocr_engine: 'tesseract',
  explain_path: '/api/public/reports/1/explain',
}

const result: ExplainResponse = {
  report_id: 1,
  generation_id: 1,
  report_text: journey.report_text,
  facts: {
    diagnosis_or_histologic_type: {
      value: 'Invasive ductal carcinoma',
      quote: 'Invasive ductal carcinoma',
      start_char: 17,
      end_char: 42,
    },
    grade: null,
    tumor_size: {
      value: '2.1 cm',
      quote: 'Tumor size: 2.1 cm',
      start_char: 44,
      end_char: 62,
    },
    margins: null,
    lymph_nodes_positive: null,
    lymph_nodes_examined: null,
    pathologic_tnm_stage: null,
    biomarkers: null,
  },
  explanation: {
    sentences: [
      {
        sentence: 'The tissue type is invasive ductal carcinoma.',
        source_fact_keys: ['diagnosis_or_histologic_type'],
        quote: 'Invasive ductal carcinoma',
        grounding: { ok: true, reasons: [] },
      },
    ],
  },
  reading_level_original: 12,
  reading_level_explanation: 7,
  provider: 'mock',
  model: 'mock-heuristic-v1',
  journey,
}

describe('ReportJourney', () => {
  it('shows three stages and honest OCR attribution', () => {
    const onFact = vi.fn()
    const onSentence = vi.fn()
    render(
      <ReportJourney
        journey={journey}
        result={result}
        glossary={[]}
        activeFact={null}
        activeSentence={null}
        highlight={{ quote: null, start: null, end: null }}
        onFactSelect={onFact}
        onSentenceSelect={onSentence}
      />,
    )

    expect(screen.getByRole('tab', { name: /Scanned report/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /OCR text/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Facts & explanation/i })).toBeInTheDocument()
    expect(screen.getByText(/layout facsimile/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /OCR text/i }))
    expect(screen.getByRole('button', { name: /Our OCR/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /TCGA-Reports OCR/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /Facts & explanation/i }))
    expect(screen.getByRole('heading', { name: /^Structured facts$/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /^Plain-language explanation$/i })).toBeInTheDocument()
  })
})
