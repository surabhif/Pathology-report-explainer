/**
 * Three-stage journey: scanned page → OCR text → PathExplain facts.
 * Stage 2 can switch between Our OCR (PathExplain) and TCGA-Reports (Textract) reference,
 * with an optional word-level diff. Stage 3 waits for Generate (or a cached generation).
 */
import { useEffect, useState } from 'react'
import { ApiError, api, apiUrl } from '../api/client'
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
  result: ExplainResponse | null
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
  const [stage, setStage] = useState<Stage>(() =>
    result ? 'explain' : journey.has_real_scan ? 'scan' : 'ocr',
  )
  const [ocrView, setOcrView] = useState<OcrView>(journey.has_real_scan ? 'our' : 'reference')
  const [ourOcr, setOurOcr] = useState<OurOcrOut | null>(journey.our_ocr ?? null)
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrError, setOcrError] = useState<string | null>(null)
  const [diff, setDiff] = useState<OcrDiffOut | null>(null)
  const hasRealScan = Boolean(journey.has_real_scan)
  const isGdc = journey.scan_source === 'gdc_pdf'
  const isTatonetti = journey.scan_source === 'tatonetti_textract_input'

  const visibleStages = STAGES.filter((s) => s.id !== 'scan' || hasRealScan)

  useEffect(() => {
    setOurOcr(journey.our_ocr ?? null)
    setOcrView(journey.has_real_scan ? 'our' : 'reference')
    setDiff(null)
    if (result) {
      setStage('explain')
    } else {
      setStage(journey.has_real_scan ? 'scan' : 'ocr')
    }
  }, [journey.our_ocr, journey.report_id, journey.has_real_scan, result?.generation_id])

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
        source: run.source ?? (run.precomputed === false ? 'live' : 'precomputed'),
        precomputed_at: run.precomputed_at ?? null,
        label:
          run.source === 'live' || run.precomputed === false
            ? 'Our OCR (live)'
            : 'Our OCR (precomputed)',
        note:
          run.source === 'live' || run.precomputed === false
            ? `Live PathExplain OCR (${run.engine} / ${run.engine_version}).`
            : `Precomputed PathExplain OCR (${run.engine} / ${run.engine_version}${
                run.precomputed_at ? `, generated ${run.precomputed_at}` : ''
              }). Visitors never trigger live Tesseract.`,
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

  const preferredSource: 'our_ocr' | 'reference' = hasRealScan ? 'our_ocr' : 'reference'

  return (
    <div className="journey stack">
      <div className="journey-steps" role="tablist" aria-label="Report journey stages">
        {visibleStages.map((s) => (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={stage === s.id}
            className={`journey-step ${stage === s.id ? 'active' : ''}`}
            onClick={() => {
              setStage(s.id)
              if (s.id === 'ocr' && hasRealScan) void ensureOurOcr()
            }}
          >
            <span className="journey-step-n">{s.n}</span>
            <span>{s.title}</span>
          </button>
        ))}
      </div>

      {!hasRealScan && (
        <p className="muted" role="note">
          Stage 1 (scanned page) is hidden for this sample — no authentic scan page is cached.
          Facsimiles rendered from OCR text are never shown in the public demo.
        </p>
      )}

      {stage === 'scan' && hasRealScan && (
        <div className="panel stack" role="tabpanel">
          <h3 className="section-title" style={{ fontSize: '1.1rem' }}>
            Stage 1 — Original scanned pathology report
          </h3>
          <p className="muted">
            {journey.scan_label ||
              'Open-access TCGA pathology report page image cached for this demo.'}
          </p>
          {isTatonetti && (
            <p className="muted">
              Source: Tatonetti lab Textract input page images (range-fetched from{' '}
              <code>imgs_for_aws.zip</code>) — the same pages Kefeli et al. sent to AWS Textract.
              Cached locally; not hot-linked at runtime. {journey.scan_citation}
            </p>
          )}
          {isGdc && (
            <p className="muted">
              Source: NCI GDC (Clinical → Pathology Report → PDF), page render stored locally — not
              hot-linked at runtime. {journey.scan_citation}
            </p>
          )}
          {!journey.scan_pages.length && (
            <p className="muted">No scan pages cached for this sample.</p>
          )}
          <div className="scan-pages">
            {journey.scan_pages.map((p) => (
              <figure key={p.page} className="scan-figure">
                <img
                  src={apiUrl(p.url)}
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
              {hasRealScan
                ? `PathExplain shows precomputed OCR on authentic cached scan pages (default: ${journey.default_ocr_engine}). Compare against the TCGA-Reports / Textract reference (Kefeli et al.).`
                : 'No authentic scan is cached for this sample, so PathExplain OCR is unavailable here. The TCGA-Reports / Textract reference text is shown for reading only.'}{' '}
              Public demo never accepts arbitrary uploads (PHI).
            </p>
            <div className="pill-group" role="group" aria-label="OCR source">
              {hasRealScan && (
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
              )}
              <button
                type="button"
                className={`pill ${ocrView === 'reference' ? 'active' : ''}`}
                onClick={() => setOcrView('reference')}
              >
                TCGA-Reports OCR (Kefeli et al.)
              </button>
              {hasRealScan && (
                <button
                  type="button"
                  className={`pill ${ocrView === 'diff' ? 'active' : ''}`}
                  onClick={() => void showDiff()}
                >
                  Diff
                </button>
              )}
            </div>
            {ocrLoading && <p className="muted">Loading precomputed OCR…</p>}
            {ocrError && <p className="error-text">{ocrError}</p>}
            {ocrView === 'our' && ourOcr && (
              <p className="muted">
                {ourOcr.source === 'live'
                  ? 'Live OCR (admin-triggered)'
                  : 'Precomputed OCR (offline)'}
                : {ourOcr.engine} / {ourOcr.engine_version}
                {ourOcr.precomputed_at ? ` · generated ${ourOcr.precomputed_at}` : ''}
                {ourOcr.duration_ms != null ? ` · ${Math.round(ourOcr.duration_ms)} ms` : ''}
                {ourOcr.estimated_cost_usd != null
                  ? ` · est. $${ourOcr.estimated_cost_usd.toFixed(4)}`
                  : ''}
                {ourOcr.cer != null ? ` · CER ${ourOcr.cer.toFixed(3)}` : ''}
                {ourOcr.wer != null ? ` · WER ${ourOcr.wer.toFixed(3)}` : ''} (vs Textract
                reference)
              </p>
            )}
            {ocrView === 'our' && ourOcr?.note && <p className="muted">{ourOcr.note}</p>}
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
                  Next: Stage 3 explanation
                </h3>
                <p className="muted">
                  Stages 1–2 never call the language model. Click Generate to extract facts and write
                  a grounded explanation from the transcript you prefer.
                </p>
                {onExplainWithSource && (
                  <div className="pill-group" style={{ marginTop: '0.75rem' }}>
                    {hasRealScan && (
                      <button
                        type="button"
                        className="btn btn-primary"
                        disabled={explaining}
                        onClick={() => onExplainWithSource('our_ocr')}
                      >
                        {explaining ? 'Generating…' : 'Generate explanation (Our OCR)'}
                      </button>
                    )}
                    <button
                      type="button"
                      className={hasRealScan ? 'btn btn-ghost' : 'btn btn-primary'}
                      disabled={explaining}
                      onClick={() => onExplainWithSource('reference')}
                    >
                      {explaining
                        ? 'Generating…'
                        : hasRealScan
                          ? 'Generate from reference'
                          : 'Generate explanation'}
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
            {!result ? (
              <>
                <p className="muted">
                  No explanation loaded yet. Generating uses the language model (or returns a cached
                  generation when one exists for this report and text source).
                </p>
                {onExplainWithSource && (
                  <div className="pill-group" style={{ marginTop: '0.75rem' }}>
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={explaining}
                      onClick={() => onExplainWithSource(preferredSource)}
                    >
                      {explaining ? 'Generating…' : 'Generate explanation'}
                    </button>
                    {hasRealScan && preferredSource === 'our_ocr' && (
                      <button
                        type="button"
                        className="btn btn-ghost"
                        disabled={explaining}
                        onClick={() => onExplainWithSource('reference')}
                      >
                        Generate from reference
                      </button>
                    )}
                  </div>
                )}
              </>
            ) : (
              <p className="muted">
                PathExplain extracts a fact sheet with source quotes, then writes a grounded
                explanation. Text source:{' '}
                <strong>
                  {result.text_source === 'our_ocr' ? 'Our OCR' : 'TCGA-Reports reference'}
                </strong>
                . Click a fact or sentence to highlight its quote.
              </p>
            )}
            {result?.provider && (
              <p className="muted">
                Provider: {result.provider} / {result.model}
                {result.explanation_retried ? ' · explanation retried for grounding' : ''}
                {result.readability_retried ? ' · readability simplify retry' : ''}
              </p>
            )}
          </div>
          {result && (
            <>
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
            </>
          )}
        </div>
      )}
    </div>
  )
}
