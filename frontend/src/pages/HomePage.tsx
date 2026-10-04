import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, api } from '../api/client'
import { ReportJourney } from '../components/ReportJourney'
import type {
  CancerType,
  ExplainResponse,
  FactSheet,
  FactSpan,
  ReportJourneyOut,
  ReportSummary,
} from '../types'
import { CANCER_OPTIONS } from '../types'

/**
 * Public demo home: pick cancer type → pick report → three-stage journey
 * (scan → OCR text → PathExplain facts). Stages 1–2 load immediately;
 * stage 3 (extract + explain) runs only on demand or when a cached generation exists.
 * No free-text paste for real/PHI reports.
 */
export function HomePage() {
  const [cancer, setCancer] = useState<CancerType | null>(null)
  const [reports, setReports] = useState<ReportSummary[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [journey, setJourney] = useState<ReportJourneyOut | null>(null)
  const [result, setResult] = useState<ExplainResponse | null>(null)
  const [loadingJourney, setLoadingJourney] = useState(false)
  const [explaining, setExplaining] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [activeFact, setActiveFact] = useState<string | null>(null)
  const [activeSentence, setActiveSentence] = useState<number | null>(null)
  const [highlight, setHighlight] = useState<{
    quote: string | null
    start: number | null
    end: number | null
  }>({ quote: null, start: null, end: null })

  useEffect(() => {
    if (!cancer) {
      setReports([])
      return
    }
    let cancelled = false
    setError(null)
    api
      .listReports(cancer)
      .then((rows) => {
        if (!cancelled) setReports(rows)
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof ApiError ? e.detail : 'Failed to load reports')
      })
    return () => {
      cancelled = true
    }
  }, [cancer])

  async function runExplain(
    reportId: number,
    opts?: { text_source?: 'reference' | 'our_ocr' },
  ) {
    setExplaining(true)
    setError(null)
    setActiveFact(null)
    setActiveSentence(null)
    setHighlight({ quote: null, start: null, end: null })
    try {
      const expl = await api.explainReport(reportId, {
        text_source: opts?.text_source ?? 'our_ocr',
      })
      setResult(expl)
      if (expl.journey) setJourney(expl.journey)
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.detail : 'Explain failed')
    } finally {
      setExplaining(false)
    }
  }

  async function selectReport(reportId: number) {
    setSelectedId(reportId)
    setResult(null)
    setJourney(null)
    setLoadingJourney(true)
    setError(null)
    setActiveFact(null)
    setActiveSentence(null)
    setHighlight({ quote: null, start: null, end: null })
    try {
      // Stages 1–2 only — never call explain/xAI just by opening a case.
      const j = await api.getReportJourney(reportId)
      setJourney(j)
      const preferred: 'our_ocr' | 'reference' = j.has_real_scan ? 'our_ocr' : 'reference'
      const cached = j.cached_text_sources ?? []
      if (cached.includes(preferred) || cached.includes('reference')) {
        const source = cached.includes(preferred) ? preferred : 'reference'
        // Cache hit: loads stored Generation without a new LLM call.
        await runExplain(reportId, { text_source: source })
      }
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.detail : 'Failed to load report journey')
    } finally {
      setLoadingJourney(false)
    }
  }

  function onFactSelect(key: keyof FactSheet, span: FactSpan | null) {
    setActiveFact(key)
    setActiveSentence(null)
    setHighlight({
      quote: span?.quote ?? null,
      start: span?.start_char ?? null,
      end: span?.end_char ?? null,
    })
  }

  function onSentenceSelect(index: number, quote: string | null) {
    setActiveSentence(index)
    setActiveFact(null)
    setHighlight({ quote, start: null, end: null })
  }

  return (
    <div className="page-enter">
      {/* First viewport: one composition — brand, headline, support, CTA, atmosphere */}
      <section className="hero" aria-label="PathExplain introduction">
        <div>
          <h1 className="hero-brand">PathExplain</h1>
          <p className="hero-headline">Pathology reports, explained in plain language.</p>
          <p className="hero-support">
            A research prototype that walks from a scanned TCGA page through OCR text to grounded
            facts and plain-language explanation — never for clinical decisions.
          </p>
          <div className="hero-cta">
            <a className="btn btn-primary" href="#demo">
              Try the demo
            </a>
            <Link className="btn btn-ghost" to="/about">
              Model card
            </Link>
          </div>
        </div>
        <div className="hero-visual" aria-hidden="true" title="Abstract pathology microscopy atmosphere" />
      </section>

      <section id="demo">
        <h2 className="section-title">Public demo</h2>
        <p className="muted">
          Choose a cancer type and a seeded sample report. Stages 1–2 (scan + OCR) load immediately.
          Stage 3 (extract + explain) runs only when you click Generate — opening a case spends no
          model calls. There is no paste box — real patient text must not be entered here.
        </p>

        <div className="demo-controls">
          <div>
            <div className="fact-key" style={{ marginBottom: '0.4rem' }}>
              Cancer type
            </div>
            <div className="pill-group" role="group" aria-label="Cancer type">
              {CANCER_OPTIONS.map((opt) => (
                <button
                  key={opt.code}
                  type="button"
                  className={`pill ${cancer === opt.code ? 'active' : ''}`}
                  onClick={() => {
                    setCancer(opt.code)
                    setSelectedId(null)
                    setResult(null)
                    setJourney(null)
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {cancer && (
            <div style={{ flex: 1, minWidth: '220px' }}>
              <div className="fact-key" style={{ marginBottom: '0.4rem' }}>
                Sample report
              </div>
              <div className="pill-group">
                {reports.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    className={`pill ${selectedId === r.id ? 'active' : ''}`}
                    onClick={() => void selectReport(r.id)}
                  >
                    {r.tcga_barcode}
                  </button>
                ))}
                {!reports.length && <span className="muted">No reports for this type.</span>}
              </div>
            </div>
          )}
        </div>

        {loadingJourney && <p className="muted">Loading scan and OCR…</p>}
        {explaining && <p className="muted">Generating explanation…</p>}
        {error && <p className="error-text">{error}</p>}

        {journey && (
          <div className="stack">
            {result && (
              <div className="panel" style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                <div>
                  <div className="fact-key">Provider</div>
                  <div>
                    {result.provider ?? '—'} / {result.model ?? '—'}
                  </div>
                </div>
                {result.is_fallback && (
                  <div className="error-text" role="status">
                    Heuristic fallback — not attributed to{' '}
                    {result.requested_provider ?? 'the hosted model'}
                    {result.requested_model ? ` (${result.requested_model})` : ''}. Reason:{' '}
                    {result.fallback_reason ?? 'validation failure'}. Do not treat this as a model
                    evaluation sample.
                  </div>
                )}
                {result.explanation_retried && (
                  <div className="muted" role="status">
                    Explainer retried once after unsupported sentences (empty or non-verbatim quotes).
                  </div>
                )}
                {result.readability_retried && (
                  <div className="muted" role="status">
                    Explainer retried once to simplify reading level (target: below source, ≤ 8th
                    grade).
                  </div>
                )}
                {(result.grounding_check?.unsupported_count ?? 0) > 0 && (
                  <div className="error-text" role="status">
                    {result.grounding_check?.unsupported_count} sentence
                    {(result.grounding_check?.unsupported_count ?? 0) === 1 ? '' : 's'} still lack a
                    source quote found word-for-word in the report (marked below).
                  </div>
                )}
              </div>
            )}

            <ReportJourney
              journey={journey}
              result={result}
              glossary={result?.glossary ?? []}
              activeFact={activeFact}
              activeSentence={activeSentence}
              highlight={highlight}
              onFactSelect={onFactSelect}
              onSentenceSelect={onSentenceSelect}
              explaining={explaining}
              onExplainWithSource={(source) => {
                if (selectedId != null) void runExplain(selectedId, { text_source: source })
              }}
            />
          </div>
        )}
      </section>
    </div>
  )
}
