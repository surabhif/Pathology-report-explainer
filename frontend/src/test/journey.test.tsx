import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ReportJourney } from '../components/ReportJourney'
import type { ExplainResponse, ReportJourneyOut } from '../types'

const realScanJourney: ReportJourneyOut = {
  report_id: 1,
  tcga_barcode: 'TCGA-B6-A401',
  cancer_type: 'BRCA',
  scan_source: 'tatonetti_textract_input',
  scan_label: 'Original pathology report page image (Tatonetti lab / Textract input)',
  scan_citation: 'Tatonetti lab Textract input page images.',
  scan_pages: [
    {
      page: 1,
      url: '/api/public/reports/1/scan-pages/page-01.jpg',
      width: 1400,
      height: 1800,
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
    cer: 0.12,
    wer: 0.18,
    page_count: 1,
  },
  default_ocr_engine: 'tesseract',
  has_real_scan: true,
  scan_scorable: true,
  explain_path: '/api/public/reports/1/explain',
}

const noScanJourney: ReportJourneyOut = {
  ...realScanJourney,
  scan_source: null,
  scan_label: null,
  scan_citation: null,
  scan_pages: [],
  our_ocr: null,
  has_real_scan: false,
  scan_scorable: false,
}

function makeResult(journey: ReportJourneyOut): ExplainResponse {
  return {
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
}

describe('ReportJourney', () => {
  it('shows three stages for authentic Tatonetti scans', () => {
    const onFact = vi.fn()
    const onSentence = vi.fn()
    render(
      <ReportJourney
        journey={realScanJourney}
        result={makeResult(realScanJourney)}
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
    expect(screen.getByText(/Tatonetti lab Textract input/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /OCR text/i }))
    expect(screen.getByRole('button', { name: /Our OCR/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /TCGA-Reports OCR/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /Facts & explanation/i }))
    expect(screen.getByRole('heading', { name: /^Structured facts$/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /^Plain-language explanation$/i })).toBeInTheDocument()
  })

  it('hides stage 1 and Our OCR when no authentic scan is cached', () => {
    render(
      <ReportJourney
        journey={noScanJourney}
        result={makeResult(noScanJourney)}
        glossary={[]}
        activeFact={null}
        activeSentence={null}
        highlight={{ quote: null, start: null, end: null }}
        onFactSelect={vi.fn()}
        onSentenceSelect={vi.fn()}
        onExplainWithSource={vi.fn()}
      />,
    )

    expect(screen.queryByRole('tab', { name: /Scanned report/i })).not.toBeInTheDocument()
    expect(screen.getByText(/Stage 1 \(scanned page\) is hidden/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Our OCR$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Explain from Our OCR/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Explain from reference/i })).toBeInTheDocument()
  })
})
