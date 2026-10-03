import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, api } from '../api/client'
import { ExplanationPanel } from '../components/ExplanationPanel'
import { FactSheetPanel } from '../components/FactSheetPanel'
import { GlossaryPanel } from '../components/GlossaryPanel'
import { HighlightedReport } from '../components/HighlightedReport'
import { ReadingLevel } from '../components/ReadingLevel'
import type {
  CancerType,
  ExplainResponse,
  FactSheet,
  FactSpan,
  ReportSummary,
} from '../types'
import { CANCER_OPTIONS } from '../types'

/**
 * Public demo home: pick cancer type → pick report → show grounded explain UI.
 * Intentionally NO free-text paste box for real/PHI reports.
 */
export function HomePage() {
  const [cancer, setCancer] = useState<CancerType | null>(null)
  const [reports, setReports] = useState<ReportSummary[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [result, setResult] = useState<ExplainResponse | null>(null)
  const [loading, setLoading] = useState(false)
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

  async function runExplain(reportId: number) {
    setSelectedId(reportId)
    setLoading(true)
    setError(null)
    setResult(null)
    setActiveFact(null)
    setActiveSentence(null)
    setHighlight({ quote: null, start: null, end: null })
    try {
      const expl = await api.explainReport(reportId)
      setResult(expl)
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.detail : 'Explain failed')
    } finally {
      setLoading(false)
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
            A research prototype that extracts grounded facts from sample TCGA-style reports and
            explains them with source quotes — never for clinical decisions.
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
          Choose a cancer type and a seeded sample report. There is no paste box — real patient text
          must not be entered here.
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
                    onClick={() => void runExplain(r.id)}
                  >
                    {r.tcga_barcode}
                  </button>
                ))}
                {!reports.length && <span className="muted">No reports for this type.</span>}
              </div>
            </div>
          )}
        </div>

        {loading && <p className="muted">Running extract + explain pipeline…</p>}
        {error && <p className="error-text">{error}</p>}

        {result && (
          <div className="stack">
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
            </div>
            <div className="explain-layout">
              <div className="panel">
                <h3 className="section-title">Report</h3>
                <p className="muted">
                  Click a fact or explanation sentence to highlight its grounding quote.
                </p>
                <HighlightedReport
                  text={result.report_text}
                  highlightQuote={highlight.quote}
                  startChar={highlight.start}
                  endChar={highlight.end}
                />
              </div>
              <div className="stack">
                <div className="panel">
                  <h3 className="section-title">Structured facts</h3>
                  <FactSheetPanel
                    facts={result.facts}
                    activeKey={activeFact}
                    onSelect={onFactSelect}
                  />
                </div>
                <div className="panel">
                  <h3 className="section-title">Plain-language explanation</h3>
                  <ExplanationPanel
                    explanation={result.explanation}
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
              <h3 className="section-title">Glossary</h3>
              <GlossaryPanel terms={result.glossary ?? []} />
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
