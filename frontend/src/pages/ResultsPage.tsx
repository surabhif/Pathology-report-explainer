import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { MetricWithCI, ResultsSummary } from '../types'
import { FACT_FIELD_LABELS } from '../types'

function pct(m: MetricWithCI): string {
  // Wilson proportions are 0–1; means (grades, Likert) stay as-is.
  if (m.method === 'wilson' || (m.value >= 0 && m.value <= 1 && m.name.includes('rate'))) {
    return `${(m.value * 100).toFixed(1)}%`
  }
  if (m.method === 'wilson') return `${(m.value * 100).toFixed(1)}%`
  return m.value.toFixed(2)
}

function ci(m: MetricWithCI): string {
  const scale = m.method === 'wilson' ? 100 : 1
  const fmt = (x: number) => (scale === 100 ? `${(x * scale).toFixed(1)}%` : x.toFixed(2))
  return `[${fmt(m.ci_low)}, ${fmt(m.ci_high)}]`
}

function MetricTable({ rows }: { rows: MetricWithCI[] }) {
  if (!rows.length) return <p className="muted">No metrics yet.</p>
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Metric</th>
          <th>Value</th>
          <th>95% CI</th>
          <th>n</th>
          <th>Method</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((m) => (
          <tr key={m.name}>
            <td>{m.name}</td>
            <td>{pct(m)}</td>
            <td>{ci(m)}</td>
            <td>{m.n}</td>
            <td>{m.method}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function asMetric(raw: unknown): MetricWithCI | null {
  if (!raw || typeof raw !== 'object') return null
  const m = raw as Partial<MetricWithCI>
  if (typeof m.name !== 'string' || typeof m.value !== 'number') return null
  return {
    name: m.name,
    value: m.value,
    n: m.n ?? 0,
    ci_low: m.ci_low ?? m.value,
    ci_high: m.ci_high ?? m.value,
    method: m.method ?? 'normal',
  }
}

function OcrBenchmarkPanel({ summary }: { summary: Record<string, unknown> }) {
  const overall = (summary.overall || {}) as Record<string, unknown>
  const byCancer = (summary.by_cancer_type || {}) as Record<string, Record<string, unknown>>
  const impact = (summary.extraction_impact || {}) as Record<string, unknown>
  const rows: MetricWithCI[] = []
  const cer = asMetric(overall.cer)
  const wer = asMetric(overall.wer)
  if (cer) rows.push({ ...cer, name: 'ocr_cer' })
  if (wer) rows.push({ ...wer, name: 'ocr_wer' })
  for (const [ct, block] of Object.entries(byCancer)) {
    const c = asMetric(block.cer)
    const w = asMetric(block.wer)
    if (c) rows.push({ ...c, name: `ocr_cer_${ct}` })
    if (w) rows.push({ ...w, name: `ocr_wer_${ct}` })
  }
  const ourAcc = asMetric(impact.field_accuracy_from_our_ocr)
  const refAcc = asMetric(impact.field_accuracy_from_reference)
  if (ourAcc) rows.push(ourAcc)
  if (refAcc) rows.push(refAcc)
  return (
    <>
      <MetricTable rows={rows} />
      {typeof impact.note === 'string' && <p className="muted">{impact.note}</p>}
    </>
  )
}

export function ResultsPage() {
  const { user } = useAuth()
  const [data, setData] = useState<ResultsSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    if (!user) return
    api
      .getResultsSummary()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.detail : 'Failed to load results'))
  }, [user])

  async function downloadCsv() {
    setDownloading(true)
    setError(null)
    try {
      const blob = await api.downloadResultsCsv()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'pathexplain-results.csv'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.detail : 'CSV download failed (admin only)')
    } finally {
      setDownloading(false)
    }
  }

  if (!user) {
    return (
      <p>
        <Link to="/login">Log in</Link> to view the results dashboard.
      </p>
    )
  }

  return (
    <div className="page-enter stack">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div>
          <h1 className="section-title">Results</h1>
          <p className="muted">Per-field and per-cancer metrics with 95% confidence intervals.</p>
        </div>
        {user.role === 'admin' && (
          <button
            type="button"
            className="btn btn-primary"
            disabled={downloading}
            onClick={() => void downloadCsv()}
          >
            {downloading ? 'Preparing…' : 'Download CSV'}
          </button>
        )}
      </div>

      {error && <p className="error-text">{error}</p>}

      {data && (
        <>
          <div className="admin-grid">
            <div className="panel">
              <div className="stat">{data.generations}</div>
              <div className="muted">Generations (non-fallback)</div>
            </div>
            <div className="panel">
              <div className="stat">{data.fallback_generations ?? 0}</div>
              <div className="muted">Fallback generations (excluded)</div>
            </div>
            <div className="panel">
              <div className="stat">{data.gold_annotations}</div>
              <div className="muted">Gold annotations</div>
            </div>
            <div className="panel">
              <div className="stat">{data.clinician_reviews}</div>
              <div className="muted">Clinician reviews</div>
            </div>
            <div className="panel">
              <div className="stat">{data.auto_check_runs}</div>
              <div className="muted">Auto-check runs</div>
            </div>
          </div>

          {data.fallback_excluded_from_metrics !== false && (
            <p className="muted">
              Primary metrics exclude heuristic fallback generations so research results are not
              mislabeled as hosted-model output.
            </p>
          )}

          <div className="panel">
            <h2 className="section-title" style={{ fontSize: '1.1rem' }}>
              Overall metrics
            </h2>
            <MetricTable rows={data.metrics} />
          </div>

          <div className="panel">
            <h2 className="section-title" style={{ fontSize: '1.1rem' }}>
              Per cancer type
            </h2>
            {Object.keys(data.by_cancer_type || {}).length === 0 && (
              <p className="muted">No per-cancer metrics yet — run auto-checks from Admin.</p>
            )}
            {Object.entries(data.by_cancer_type || {}).map(([ct, rows]) => (
              <div key={ct} style={{ marginBottom: '1rem' }}>
                <h3 style={{ fontSize: '1rem' }}>{ct}</h3>
                <MetricTable rows={rows} />
              </div>
            ))}
          </div>

          <div className="panel">
            <h2 className="section-title" style={{ fontSize: '1.1rem' }}>
              Per field accuracy
            </h2>
            {data.by_field && Object.keys(data.by_field).length > 0 ? (
              <table className="table">
                <thead>
                  <tr>
                    <th>Field</th>
                    <th>Accuracy</th>
                    <th>95% CI</th>
                    <th>n</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(data.by_field).map(([field, rows]) => {
                    const m = rows[0]
                    if (!m) return null
                    const label =
                      FACT_FIELD_LABELS[field as keyof typeof FACT_FIELD_LABELS] ?? field
                    return (
                      <tr key={field}>
                        <td>{label}</td>
                        <td>{pct(m)}</td>
                        <td>{ci(m)}</td>
                        <td>{m.n}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            ) : (
              <p className="muted">
                Per-field metrics appear after gold annotations + auto-checks with field_accuracy.
              </p>
            )}
          </div>

          <div className="panel">
            <h2 className="section-title" style={{ fontSize: '1.1rem' }}>
              OCR benchmark (vs TCGA-Reports / Textract)
            </h2>
            {data.ocr_benchmark?.summary ? (
              <>
                <p className="muted">
                  Engine: {data.ocr_benchmark.engine} / {data.ocr_benchmark.engine_version} · n=
                  {data.ocr_benchmark.n_reports} · reference: {data.ocr_benchmark.reference}
                </p>
                <OcrBenchmarkPanel summary={data.ocr_benchmark.summary} />
              </>
            ) : (
              <p className="muted">
                No OCR benchmark yet. Admins can run one from Admin → Run OCR benchmark (stratified
                by cancer type; measures CER/WER and extraction impact).
              </p>
            )}
          </div>

          <div className="panel">
            <h2 className="section-title" style={{ fontSize: '1.1rem' }}>
              Clinician scores
            </h2>
            {data.clinician_scores && data.clinician_scores.n_reviews > 0 ? (
              <table className="table">
                <thead>
                  <tr>
                    <th>Dimension</th>
                    <th>Mean</th>
                    <th>95% CI</th>
                    <th>n</th>
                  </tr>
                </thead>
                <tbody>
                  {(
                    [
                      ['accuracy', data.clinician_scores.accuracy],
                      ['completeness', data.clinician_scores.completeness],
                      ['harm_potential', data.clinician_scores.harm_potential],
                    ] as const
                  ).map(([name, m]) =>
                    m ? (
                      <tr key={name}>
                        <td>{name}</td>
                        <td>{m.value.toFixed(2)}</td>
                        <td>
                          [{m.ci_low.toFixed(2)}, {m.ci_high.toFixed(2)}]
                        </td>
                        <td>{m.n}</td>
                      </tr>
                    ) : null,
                  )}
                </tbody>
              </table>
            ) : (
              <p className="muted">No completed clinician reviews yet.</p>
            )}
          </div>

          <div className="panel">
            <h2 className="section-title" style={{ fontSize: '1.1rem' }}>
              Inter-rater agreement
            </h2>
            {data.inter_rater?.available && data.inter_rater.metric ? (
              <>
                <p className="muted">
                  Pairwise exact agreement on Likert dimensions when ≥2 clinicians review the same
                  explanation ({data.inter_rater.n_items_with_multiple_raters} multi-rated items,{' '}
                  {data.inter_rater.n_pairs} pairs).
                </p>
                <MetricTable rows={[data.inter_rater.metric]} />
              </>
            ) : (
              <p className="muted">
                Appears when several clinicians review the same item (assign multiple reviewers in a
                review batch).
              </p>
            )}
          </div>

          <div className="panel">
            <h2 className="section-title" style={{ fontSize: '1.1rem' }}>
              Failure examples
            </h2>
            {data.failure_examples && data.failure_examples.length > 0 ? (
              <table className="table">
                <thead>
                  <tr>
                    <th>Generation</th>
                    <th>Report</th>
                    <th>Cancer</th>
                    <th>Check</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {data.failure_examples.map((f, i) => (
                    <tr key={`${f.generation_id}-${f.check_name}-${i}`}>
                      <td>{f.generation_id}</td>
                      <td>{f.report_id}</td>
                      <td>{f.cancer_type ?? '—'}</td>
                      <td>{f.check_name}</td>
                      <td>{f.detail ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="muted">No failure examples from auto-check runs yet.</p>
            )}
          </div>
        </>
      )}
    </div>
  )
}
