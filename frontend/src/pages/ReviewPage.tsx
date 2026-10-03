import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { ExplanationPanel } from '../components/ExplanationPanel'
import { FactSheetPanel } from '../components/FactSheetPanel'
import { HighlightedReport } from '../components/HighlightedReport'
import type {
  ExplanationPayload,
  FactSheet,
  FactSpan,
  ReviewScores,
  ReviewTaskOut,
} from '../types'

function asFactSheet(raw: unknown): FactSheet | null {
  if (!raw || typeof raw !== 'object') return null
  return raw as FactSheet
}

function asExplanation(raw: unknown): ExplanationPayload | null {
  if (!raw || typeof raw !== 'object') return null
  const maybe = raw as ExplanationPayload
  if (!Array.isArray(maybe.sentences)) return null
  return maybe
}

/**
 * Clinician review: side-by-side report + explanation, 1–5 scores,
 * flag sentences, comments. Model/prompt versions are omitted by the API.
 */
export function ReviewPage() {
  const { user } = useAuth()
  const [tasks, setTasks] = useState<ReviewTaskOut[]>([])
  const [task, setTask] = useState<ReviewTaskOut | null>(null)
  const [scores, setScores] = useState<ReviewScores>({
    accuracy: 3,
    completeness: 3,
    harm_potential: 1,
  })
  const [flagged, setFlagged] = useState<number[]>([])
  const [comments, setComments] = useState('')
  const [activeSentence, setActiveSentence] = useState<number | null>(null)
  const [activeFact, setActiveFact] = useState<string | null>(null)
  const [highlight, setHighlight] = useState<{
    quote: string | null
    start: number | null
    end: number | null
  }>({ quote: null, start: null, end: null })
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!user || (user.role !== 'clinician' && user.role !== 'admin')) return
    api
      .listReviewTasks()
      .then(setTasks)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.detail : 'Failed to load tasks'))
  }, [user])

  async function openTask(id: number) {
    setError(null)
    setMessage(null)
    try {
      const t = await api.getReviewTask(id)
      setTask(t)
      setScores(t.scores ?? { accuracy: 3, completeness: 3, harm_potential: 1 })
      setFlagged((t.flagged_sentences as number[]) ?? [])
      setComments(t.comments ?? '')
      setActiveSentence(null)
      setActiveFact(null)
      setHighlight({ quote: null, start: null, end: null })
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.detail : 'Failed to open task')
    }
  }

  function setScore(key: keyof ReviewScores, value: number) {
    setScores((prev) => ({ ...prev, [key]: value }))
  }

  function toggleFlag(index: number) {
    setFlagged((prev) => (prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index]))
  }

  async function submit() {
    if (!task) return
    setBusy(true)
    setError(null)
    try {
      const updated = await api.submitReview(task.id, {
        scores,
        flagged_sentences: flagged,
        comments: comments || null,
      })
      setMessage(`Review #${updated.id} submitted.`)
      setTask(updated)
      setTasks((prev) => prev.map((t) => (t.id === updated.id ? { ...t, status: updated.status } : t)))
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.detail : 'Submit failed')
    } finally {
      setBusy(false)
    }
  }

  if (!user) {
    return (
      <p>
        <Link to="/login">Log in</Link> as clinician to review explanations.
      </p>
    )
  }
  if (user.role !== 'clinician' && user.role !== 'admin') {
    return <p className="error-text">Clinician role required.</p>
  }

  const facts = asFactSheet(task?.facts)
  const explanation = asExplanation(task?.explanation)

  return (
    <div className="page-enter stack">
      <div>
        <h1 className="section-title">Clinician review</h1>
        <p className="muted">
          Score accuracy, completeness, and harm potential. Flag unsupported or risky sentences.
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
                Review #{t.id} · generation {t.generation_id} · <em>{t.status}</em>
              </span>
              <button type="button" className="btn btn-ghost" onClick={() => void openTask(t.id)}>
                Open
              </button>
            </li>
          ))}
          {!tasks.length && <li className="muted">No review tasks assigned.</li>}
        </ul>
      </div>

      {task && (
        <>
          <div className="explain-layout">
            <div className="panel">
              <h3 className="section-title" style={{ fontSize: '1.05rem' }}>
                Report {task.tcga_barcode ? `(${task.tcga_barcode})` : ''}
              </h3>
              <HighlightedReport
                text={task.report_text || ''}
                highlightQuote={highlight.quote}
                startChar={highlight.start}
                endChar={highlight.end}
              />
            </div>
            <div className="stack">
              {facts && (
                <div className="panel">
                  <h3 className="section-title" style={{ fontSize: '1.05rem' }}>
                    Extracted facts
                  </h3>
                  <FactSheetPanel
                    facts={facts}
                    activeKey={activeFact}
                    onSelect={(key: keyof FactSheet, span: FactSpan | null) => {
                      setActiveFact(key)
                      setActiveSentence(null)
                      setHighlight({
                        quote: span?.quote ?? null,
                        start: span?.start_char ?? null,
                        end: span?.end_char ?? null,
                      })
                    }}
                  />
                </div>
              )}
              {explanation && (
                <div className="panel">
                  <h3 className="section-title" style={{ fontSize: '1.05rem' }}>
                    Explanation
                  </h3>
                  <ExplanationPanel
                    explanation={explanation}
                    activeIndex={activeSentence}
                    flagged={flagged}
                    onSelect={(i, quote) => {
                      setActiveSentence(i)
                      setActiveFact(null)
                      setHighlight({ quote, start: null, end: null })
                    }}
                    onToggleFlag={toggleFlag}
                  />
                </div>
              )}
            </div>
          </div>

          <div className="panel stack">
            <h3 className="section-title" style={{ fontSize: '1.05rem' }}>
              Scores (1–5)
            </h3>
            {(
              [
                ['accuracy', 'Accuracy'],
                ['completeness', 'Completeness'],
                ['harm_potential', 'Harm potential'],
              ] as const
            ).map(([key, label]) => (
              <div key={key} className="row">
                <span style={{ minWidth: '9rem', fontWeight: 600 }}>{label}</span>
                <div className="score-row" role="group" aria-label={label}>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      type="button"
                      className={scores[key] === n ? 'selected' : ''}
                      onClick={() => setScore(key, n)}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            <div className="field">
              <label htmlFor="comments">Comments</label>
              <textarea
                id="comments"
                value={comments}
                onChange={(e) => setComments(e.target.value)}
                placeholder="Optional notes for the study team"
              />
            </div>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || task.status === 'completed'}
              onClick={() => void submit()}
            >
              {task.status === 'completed' ? 'Already completed' : busy ? 'Submitting…' : 'Submit review'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
