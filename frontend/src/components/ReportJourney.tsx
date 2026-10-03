/**
 * Three-stage journey: scanned page → OCR text → PathExplain facts.
 * Stage 2 can switch between Our OCR (PathExplain) and TCGA-Reports (Textract) reference,
 * with an optional word-level diff.
 */
import { useEffect, useState } from 'react'
import { ApiError, api } from '../api/client'
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
  OcrDiffOut,
  OurOcrOut,
  ReportJourneyOut,
} from '../types'

type Stage = 'scan' | 'ocr' | 'explain'
type OcrView = 'our' | 'reference' | 'diff'

interface Props {
  journey: ReportJourneyOut
  result: ExplainResponse
  glossary?: GlossaryTerm[]
  activeFact: string | null
  activeSentence: number | null
  highlight: { quote: string | null; start: number | null; end: number | null }
  onFactSelect: (key: keyof FactSheet, span: FactSpan | null) => void
  onSentenceSelect: (index: number, quote: string | null) => void
  onExplainWithSource?: (source: 'our_ocr' | 'reference') => void
  explaining?: boolean
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
  onExplainWithSource,
  explaining = false,
}: Props) {
  const [stage, setStage] = useState<Stage>('scan')
  const [ocrView, setOcrView] = useState<OcrView>('our')
  const [ourOcr, setOurOcr] = useState<OurOcrOut | null>(journey.our_ocr ?? null)
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrError, setOcrError] = useState<string | null>(null)
  const [diff, setDiff] = useState<OcrDiffOut | null>(null)
  const isFacsimile = journey.scan_source === 'ocr_text_facsimile'
  const isGdc = journey.scan_source === 'gdc_pdf'

  useEffect(() => {
    setOurOcr(journey.our_ocr ?? null)
  }, [journey.our_ocr, journey.report_id])

  async function ensureOurOcr() {
    if (ourOcr || ocrLoading) return ourOcr
    setOcrLoading(true)
    setOcrError(null)
    try {
      const run = await api.runReportOcr(journey.report_id, journey.default_ocr_engine)
      const mapped: OurOcrOut = {
        ocr_run_id: run.id,
        engine: run.engine,
        engine_version: run.engine_version,
        model: run.model,
        text: run.text,
        duration_ms: run.duration_ms,
        estimated_cost_usd: run.estimated_cost_usd,
        cer: run.cer,
        wer: run.wer,
        page_count: run.pages?.length ?? 0,
        label: 'Our OCR (PathExplain)',
        note: 'Transcribed by PathExplain from cached scan page images.',
      }
      setOurOcr(mapped)
      return mapped
    } catch (e: unknown) {
      setOcrError(e instanceof ApiError ? e.detail : 'OCR failed')
      return null
    } finally {
      setOcrLoading(false)
    }
  }

  async function showDiff() {
    setOcrView('diff')
    const ready = ourOcr ?? (await ensureOurOcr())
    if (!ready) return
    try {
      const d = await api.getOcrDiff(journey.report_id, ready.engine)
      setDiff(d)
    } catch (e: unknown) {
      setOcrError(e instanceof ApiError ? e.detail : 'Diff failed')
    }
  }

  const stage2Text =
    ocrView === 'our'
      ? ourOcr?.text ?? ''
      : ocrView === 'reference'
        ? journey.report_text
        : ''

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
            onClick={() => {
              setStage(s.id)
              if (s.id === 'ocr') void ensureOurOcr()
            }}
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
        <div className="stack" role="tabpanel">
          <div className="panel stack">
            <h3 className="section-title" style={{ fontSize: '1.1rem' }}>
              Stage 2 — Machine-readable OCR text
            </h3>
            <p className="muted">
              PathExplain runs its own OCR on the cached scan pages (default:{' '}
              <code>{journey.default_ocr_engine}</code>). Compare against the TCGA-Reports / Textract
              reference (Kefeli et al.). Public demo never accepts arbitrary uploads (PHI).
            </p>
            <div className="pill-group" role="group" aria-label="OCR source">
              <button
                type="button"
                className={`pill ${ocrView === 'our' ? 'active' : ''}`}
                onClick={() => {
                  setOcrView('our')
                  void ensureOurOcr()
                }}
              >
                Our OCR
              </button>
              <button
                type="button"
                className={`pill ${ocrView === 'reference' ? 'active' : ''}`}
                onClick={() => setOcrView('reference')}
              >
                TCGA-Reports OCR (Kefeli et al.)
              </button>
              <button
                type="button"
                className={`pill ${ocrView === 'diff' ? 'active' : ''}`}
                onClick={() => void showDiff()}
              >
                Diff
              </button>
            </div>
            {ocrLoading && <p className="muted">Running OCR on cached scan pages…</p>}
            {ocrError && <p className="error-text">{ocrError}</p>}
            {ocrView === 'our' && ourOcr && (
              <p className="muted">
                Engine: {ourOcr.engine} / {ourOcr.engine_version}
                {ourOcr.duration_ms != null ? ` · ${Math.round(ourOcr.duration_ms)} ms` : ''}
                {ourOcr.estimated_cost_usd != null
                  ? ` · est. $${ourOcr.estimated_cost_usd.toFixed(4)}`
                  : ''}
                {ourOcr.cer != null ? ` · CER ${ourOcr.cer.toFixed(3)}` : ''}
                {ourOcr.wer != null ? ` · WER ${ourOcr.wer.toFixed(3)}` : ''} (vs Textract
                reference)
              </p>
            )}
            {ocrView === 'reference' && (
              <p className="muted">
                Citation: {journey.ocr_citation} This is the reference transcript for CER/WER — not
                PathExplain OCR.
              </p>
            )}
          </div>

          {ocrView === 'diff' ? (
            <div className="panel">
              <h3 className="section-title" style={{ fontSize: '1.05rem' }}>
                Word-level diff (reference vs our OCR)
              </h3>
              {diff && (
                <p className="muted">
                  Changed tokens: {diff.changed}
                  {diff.cer != null ? ` · CER ${diff.cer.toFixed(3)}` : ''}
                  {diff.wer != null ? ` · WER ${diff.wer.toFixed(3)}` : ''}
                </p>
              )}
              <div className="ocr-diff report-text" aria-label="OCR word diff">
                {(diff?.ops || []).map((op, i) => (
                  <span key={i} className={`diff-${op.op}`}>
                    {op.op === 'equal' && `${op.hyp} `}
                    {op.op === 'insert' && <ins>{op.hyp} </ins>}
                    {op.op === 'delete' && <del>{op.ref} </del>}
                  </span>
                ))}
                {!diff && <p className="muted">Loading diff…</p>}
              </div>
            </div>
          ) : (
            <div className="explain-layout">
              <div className="panel stack">
                <h3 className="section-title" style={{ fontSize: '1.05rem' }}>
                  {ocrView === 'our' ? 'Our OCR text' : 'TCGA-Reports reference text'}
                </h3>
                {stage2Text ? (
                  <HighlightedReport
                    text={stage2Text}
                    highlightQuote={highlight.quote}
                    startChar={highlight.start}
                    endChar={highlight.end}
                  />
                ) : (
                  <p className="muted">OCR text not loaded yet.</p>
                )}
              </div>
              <div className="panel stack">
                <h3 className="section-title" style={{ fontSize: '1.05rem' }}>
                  Preview: facts (from stage 3)
                </h3>
                <p className="muted">
                  Click a fact to highlight its quote in the OCR text currently shown. Prefer
                  explaining from Our OCR so quotes ground in PathExplain’s transcript.
                </p>
                <FactSheetPanel facts={result.facts} activeKey={activeFact} onSelect={onFactSelect} />
                {onExplainWithSource && (
                  <div className="pill-group" style={{ marginTop: '0.75rem' }}>
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={explaining}
                      onClick={() => onExplainWithSource('our_ocr')}
                    >
                      Explain from Our OCR
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      disabled={explaining}
                      onClick={() => onExplainWithSource('reference')}
                    >
                      Explain from reference
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
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
              explanation. Text source:{' '}
              <strong>{result.text_source === 'our_ocr' ? 'Our OCR' : 'TCGA-Reports reference'}</strong>
              . Click a fact or sentence to highlight its quote.
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
