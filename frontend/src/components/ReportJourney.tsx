/**
 * Three-stage journey: scanned page → OCR text (TCGA-Reports) → PathExplain facts.
 * OCR is attributed to Kefeli et al. / Textract — this app does not run OCR.
 */
import { useState } from 'react'
import { ExplanationPanel } from './ExplanationPanel'
import { FactSheetPanel } from './FactSheetPanel'
import { GlossaryPanel } from './GlossaryPanel'
import { HighlightedReport } from './HighlightedReport'
import { ReadingLevel } from './ReadingLevel'
import type {
  ExplainResponse,
  FactSheet,
  FactSpan,
  GlossaryTerm,
  ReportJourneyOut,
} from '../types'

type Stage = 'scan' | 'ocr' | 'explain'

interface Props {
  journey: ReportJourneyOut
  result: ExplainResponse
  glossary?: GlossaryTerm[]
  activeFact: string | null
  activeSentence: number | null
  highlight: { quote: string | null; start: number | null; end: number | null }
  onFactSelect: (key: keyof FactSheet, span: FactSpan | null) => void
  onSentenceSelect: (index: number, quote: string | null) => void
}

const STAGES: { id: Stage; n: string; title: string }[] = [
  { id: 'scan', n: '1', title: 'Scanned report' },
  { id: 'ocr', n: '2', title: 'OCR text' },
  { id: 'explain', n: '3', title: 'Facts & explanation' },
]

export function ReportJourney({
  journey,
  result,
  glossary = [],
  activeFact,
  activeSentence,
  highlight,
  onFactSelect,
  onSentenceSelect,
}: Props) {
  const [stage, setStage] = useState<Stage>('scan')
  const isFacsimile = journey.scan_source === 'ocr_text_facsimile'
  const isGdc = journey.scan_source === 'gdc_pdf'

  return (
    <div className="journey stack">
      <div className="journey-steps" role="tablist" aria-label="Report journey stages">
        {STAGES.map((s) => (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={stage === s.id}
            className={`journey-step ${stage === s.id ? 'active' : ''}`}
            onClick={() => setStage(s.id)}
          >
            <span className="journey-step-n">{s.n}</span>
            <span>{s.title}</span>
          </button>
        ))}
      </div>

      {stage === 'scan' && (
        <div className="panel stack" role="tabpanel">
          <h3 className="section-title" style={{ fontSize: '1.1rem' }}>
            Stage 1 — Original scanned pathology report
          </h3>
          <p className="muted">
            {journey.scan_label ||
              'Open-access TCGA pathology report page image cached for this demo.'}
          </p>
          {isGdc && (
            <p className="muted">
              Source: NCI GDC (Clinical → Pathology Report → PDF), page render stored locally — not
              hot-linked at runtime.
            </p>
          )}
          {isFacsimile && (
            <p className="error-text" role="note">
              Honesty note: the NCI GDC was unreachable while packaging these demo assets, so this
              image is a <strong>layout facsimile rendered from the public OCR text</strong>, not an
              authentic GDC scan page. Re-run{' '}
              <code>python backend/scripts/fetch_scan_pages.py --from-sample-data --force</code> when
              GDC is available to replace it with real PDF page renders. {journey.scan_citation}
            </p>
          )}
          {!journey.scan_pages.length && (
            <p className="muted">
              No scan pages cached yet. Run the fetch script to pull GDC pathology PDFs.
            </p>
          )}
          <div className="scan-pages">
            {journey.scan_pages.map((p) => (
              <figure key={p.page} className="scan-figure">
                <img
                  src={p.url}
                  alt={`Pathology report scan page ${p.page} for ${journey.tcga_barcode}`}
                  width={p.width ?? undefined}
                  height={p.height ?? undefined}
                  loading="lazy"
                />
                <figcaption className="muted">Page {p.page}</figcaption>
              </figure>
            ))}
          </div>
        </div>
      )}

      {stage === 'ocr' && (
        <div className="explain-layout" role="tabpanel">
          <div className="panel stack">
            <h3 className="section-title" style={{ fontSize: '1.1rem' }}>
              Stage 2 — Machine-readable OCR text
            </h3>
            <p className="muted">{journey.ocr_label}</p>
            <p className="muted">
              Citation: {journey.ocr_citation} PathExplain’s contribution starts at stage 3
              (structured extraction + grounded explanation), not OCR.
            </p>
            <HighlightedReport
              text={journey.report_text}
              highlightQuote={highlight.quote}
              startChar={highlight.start}
              endChar={highlight.end}
            />
          </div>
          <div className="panel stack">
            <h3 className="section-title" style={{ fontSize: '1.05rem' }}>
              Preview: facts (from stage 3)
            </h3>
            <p className="muted">Click a fact to highlight its quote in the OCR text.</p>
            <FactSheetPanel facts={result.facts} activeKey={activeFact} onSelect={onFactSelect} />
          </div>
        </div>
      )}

      {stage === 'explain' && (
        <div className="stack" role="tabpanel">
          <div className="panel">
            <h3 className="section-title" style={{ fontSize: '1.1rem' }}>
              Stage 3 — Structured facts & plain-language explanation
            </h3>
            <p className="muted">
              PathExplain extracts a fact sheet with source quotes, then writes a grounded
              explanation. Click a fact or sentence to highlight its quote in the OCR text.
            </p>
            {result.provider && (
              <p className="muted">
                Provider: {result.provider} / {result.model}
                {result.explanation_retried ? ' · explanation retried for grounding' : ''}
              </p>
            )}
          </div>
          <div className="explain-layout">
            <div className="panel">
              <h3 className="section-title" style={{ fontSize: '1.05rem' }}>
                OCR text (quote highlighting)
              </h3>
              <HighlightedReport
                text={result.report_text}
                highlightQuote={highlight.quote}
                startChar={highlight.start}
                endChar={highlight.end}
              />
            </div>
            <div className="stack">
              <div className="panel">
                <h3 className="section-title" style={{ fontSize: '1.05rem' }}>
                  Structured facts
                </h3>
                <FactSheetPanel
                  facts={result.facts}
                  activeKey={activeFact}
                  onSelect={onFactSelect}
                />
              </div>
              <div className="panel">
                <h3 className="section-title" style={{ fontSize: '1.05rem' }}>
                  Plain-language explanation
                </h3>
                <ExplanationPanel
                  explanation={result.explanation}
                  reportText={result.report_text}
                  activeIndex={activeSentence}
                  onSelect={onSentenceSelect}
                />
                <ReadingLevel
                  original={result.reading_level_original}
                  explanation={result.reading_level_explanation}
                />
              </div>
            </div>
          </div>
          <div className="panel">
            <h3 className="section-title" style={{ fontSize: '1.05rem' }}>
              Glossary
            </h3>
            <GlossaryPanel terms={glossary} />
          </div>
        </div>
      )}
    </div>
  )
}
