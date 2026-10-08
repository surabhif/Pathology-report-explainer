import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { HighlightedReport } from '../components/HighlightedReport'
import type { AnnotationTaskOut, FactSpan } from '../types'
import { FACT_FIELD_KEYS, FACT_FIELD_LABELS } from '../types'

/**
 * Annotator UI: gold-label fact spans on report text.
 * MUST NOT show model output (API also omits generations).
 */
export function AnnotatePage() {
  const { user } = useAuth()
  const [tasks, setTasks] = useState<AnnotationTaskOut[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [task, setTask] = useState<AnnotationTaskOut | null>(null)
  const [labels, setLabels] = useState<Record<string, FactSpan | null>>({})
  const [activeField, setActiveField] = useState<string>(FACT_FIELD_KEYS[0])
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!user || (user.role !== 'annotator' && user.role !== 'admin')) return
    api
      .listAnnotateTasks()
      .then(setTasks)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.detail : 'Failed to load tasks'))
  }, [user])

  async function openTask(id: number) {
    setError(null)
    setMessage(null)
    setActiveId(id)
    try {
      const t = await api.getAnnotateTask(id)
      setTask(t)
      const initial: Record<string, FactSpan | null> = {}
      for (const k of FACT_FIELD_KEYS) {
        initial[k] = t.gold_labels?.[k] ?? null
      }
      setLabels(initial)
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.detail : 'Failed to open task')
    }
  }

  const reportText = task?.report?.report_text ?? ''

  const previewHighlight = useMemo(() => {
    const span = labels[activeField]
    return {
      quote: span?.quote ?? null,
      start: span?.start_char ?? null,
      end: span?.end_char ?? null,
    }
  }, [labels, activeField])

  function captureSelection() {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || !reportText) return
    const selected = sel.toString()
    if (!selected.trim()) return

    // Prefer offsets within the report text container when possible
    let start = reportText.indexOf(selected)
    let end = start >= 0 ? start + selected.length : -1
    if (start < 0) {
      // fallback: leave offsets null, keep quote
      start = -1
      end = -1
    }

    setLabels((prev) => ({
      ...prev,
      [activeField]: {
        value: selected.trim(),
        quote: selected,
        start_char: start >= 0 ? start : null,
        end_char: end >= 0 ? end : null,
      },
    }))
  }

  function clearField() {
    setLabels((prev) => ({ ...prev, [activeField]: null }))
  }

  async function submit() {
    if (!task) return
    setBusy(true)
    setError(null)
    try {
      const updated = await api.submitGold(task.id, labels)
      setMessage(`Task #${updated.id} submitted.`)
      setTasks((prev) => prev.map((t) => (t.id === updated.id ? { ...t, status: updated.status } : t)))
      setTask(updated)
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.detail : 'Submit failed')
    } finally {
      setBusy(false)
    }
  }

  if (!user) {
    return (
      <p>
        <Link to="/login">Log in</Link> as annotator to label reports.
      </p>
    )
  }
  if (user.role !== 'annotator' && user.role !== 'admin') {
    return <p className="error-text">Annotator role required.</p>
  }

  return (
    <div className="page-enter stack">
      <div className="page-intro">
        <h1>Annotate</h1>
        <p className="muted">
          Highlight spans in the report for each fact field. Model explanations are intentionally
          hidden.
        </p>
      </div>

      {error && <p className="error-text">{error}</p>}
      {message && <p className="success-text">{message}</p>}

      <div className="panel">
        <h2 className="section-title" style={{ fontSize: '1.1rem' }}>
          Task list
        </h2>
        <ul className="task-list">
          {tasks.map((t) => (
            <li key={t.id}>
              <span>
                Task #{t.id} · report {t.report_id} · <em>{t.status}</em>
              </span>
              <button type="button" className="btn btn-ghost" onClick={() => void openTask(t.id)}>
                {activeId === t.id ? 'Open' : 'Open'}
              </button>
            </li>
          ))}
          {!tasks.length && <li className="muted">No annotation tasks assigned.</li>}
        </ul>
      </div>

      {task?.report && (
        <div className="annotate-layout">
          <div className="panel">
            <h3 className="section-title" style={{ fontSize: '1.05rem' }}>
              Report text
            </h3>
            <p className="span-hint">
              Select text in the browser, then click “Capture selection” for the active field.
            </p>
            <div onMouseUp={captureSelection}>
              <HighlightedReport
                text={reportText}
                highlightQuote={previewHighlight.quote}
                startChar={previewHighlight.start}
                endChar={previewHighlight.end}
              />
            </div>
            <div className="row" style={{ marginTop: '0.75rem' }}>
              <button type="button" className="btn btn-primary" onClick={captureSelection}>
                Capture selection → {FACT_FIELD_LABELS[activeField as keyof typeof FACT_FIELD_LABELS]}
              </button>
              <button type="button" className="btn btn-ghost" onClick={clearField}>
                Clear field
              </button>
            </div>
          </div>

          <div className="panel stack">
            <h3 className="section-title" style={{ fontSize: '1.05rem' }}>
              Gold labels
            </h3>
            {FACT_FIELD_KEYS.map((key) => {
              const span = labels[key]
              return (
                <button
                  key={key}
                  type="button"
                  className={`sentence ${activeField === key ? 'active' : ''}`}
                  onClick={() => setActiveField(key)}
                >
                  <span className="fact-key">{FACT_FIELD_LABELS[key]}</span>
                  <span className="fact-value">
                    {span?.value != null
                      ? typeof span.value === 'object'
                        ? JSON.stringify(span.value)
                        : String(span.value)
                      : '— not set —'}
                  </span>
                  {span?.quote && (
                    <span className="muted" style={{ display: 'block', fontSize: '0.8rem' }}>
                      “{span.quote.slice(0, 80)}
                      {span.quote.length > 80 ? '…' : ''}”
                    </span>
                  )}
                </button>
              )
            })}
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || task.status === 'completed'}
              onClick={() => void submit()}
            >
              {task.status === 'completed' ? 'Already completed' : busy ? 'Submitting…' : 'Submit gold labels'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
