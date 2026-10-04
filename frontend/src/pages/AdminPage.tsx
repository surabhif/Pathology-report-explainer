import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type {
  EvaluationSetOut,
  ProgressOut,
  ReportSummary,
  TaskBatchOut,
  UserOut,
} from '../types'
import { CANCER_OPTIONS } from '../types'

/**
 * Admin tools: import status (via progress), evaluation sets, batches,
 * invites, progress, and auto-checks.
 */
export function AdminPage() {
  const { user } = useAuth()
  const [progress, setProgress] = useState<ProgressOut | null>(null)
  const [users, setUsers] = useState<UserOut[]>([])
  const [sets, setSets] = useState<EvaluationSetOut[]>([])
  const [batches, setBatches] = useState<TaskBatchOut[]>([])
  const [reports, setReports] = useState<ReportSummary[]>([])
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Invite form
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteName, setInviteName] = useState('')
  const [inviteRole, setInviteRole] = useState<'clinician' | 'annotator' | 'admin'>('clinician')

  // Eval set form
  const [setName, setSetName] = useState('')
  const [setCancer, setSetCancer] = useState('BRCA')
  const [setReportIds, setSetReportIds] = useState('')

  // Batch form
  const [batchName, setBatchName] = useState('')
  const [batchType, setBatchType] = useState<'annotate' | 'review' | 'auto_check'>('annotate')
  const [batchSetId, setBatchSetId] = useState<number | ''>('')
  const [batchUserIds, setBatchUserIds] = useState('')

  const refresh = useCallback(async () => {
    const [p, u, s, b, r] = await Promise.all([
      api.getProgress(),
      api.listUsers(),
      api.listEvalSets(),
      api.listBatches(),
      api.listReports(),
    ])
    setProgress(p)
    setUsers(u)
    setSets(s)
    setBatches(b)
    setReports(r)
  }, [])

  useEffect(() => {
    if (user?.role !== 'admin') return
    refresh().catch((e: unknown) =>
      setError(e instanceof ApiError ? e.detail : 'Failed to load admin data'),
    )
  }, [user, refresh])

  if (!user) {
    return (
      <p>
        <Link to="/login">Log in</Link> as admin to use this page.
      </p>
    )
  }
  if (user.role !== 'admin') {
    return <p className="error-text">Admin role required.</p>
  }

  async function wrap(action: () => Promise<void>) {
    setError(null)
    setMessage(null)
    try {
      await action()
      await refresh()
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.detail : 'Action failed')
    }
  }

  return (
    <div className="page-enter stack">
      <div>
        <h1 className="section-title">Admin</h1>
        <p className="muted">Import status, evaluation sets, batches, invites, and auto-checks.</p>
      </div>

      {error && <p className="error-text">{error}</p>}
      {message && <p className="success-text">{message}</p>}

      <div className="admin-grid">
        <div className="panel">
          <h2 className="section-title" style={{ fontSize: '1.1rem' }}>
            Import / corpus status
          </h2>
          {progress ? (
            <div className="stack">
              <div>
                <div className="stat">{progress.total_reports}</div>
                <div className="muted">Reports imported</div>
              </div>
              <div>
                <div className="stat">{progress.total_generations}</div>
                <div className="muted">Generations cached</div>
              </div>
              <p className="muted" style={{ fontSize: '0.85rem' }}>
                Seeded sample barcodes:{' '}
                {reports.map((r) => r.tcga_barcode).join(', ') || 'none yet'}
              </p>
            </div>
          ) : (
            <p className="muted">Loading…</p>
          )}
        </div>

        <div className="panel">
          <h2 className="section-title" style={{ fontSize: '1.1rem' }}>
            Annotation / review progress
          </h2>
          {progress && (
            <table className="table">
              <tbody>
                <tr>
                  <td>Annotation pending</td>
                  <td>{progress.annotation_pending}</td>
                </tr>
                <tr>
                  <td>Annotation completed</td>
                  <td>{progress.annotation_completed}</td>
                </tr>
                <tr>
                  <td>Review pending</td>
                  <td>{progress.review_pending}</td>
                </tr>
                <tr>
                  <td>Review completed</td>
                  <td>{progress.review_completed}</td>
                </tr>
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="panel">
        <h2 className="section-title" style={{ fontSize: '1.1rem' }}>
          Invite clinician / annotator
        </h2>
        <form
          className="grid-2"
          onSubmit={(e) => {
            e.preventDefault()
            void wrap(async () => {
              const created = await api.createInvite({
                email: inviteEmail,
                name: inviteName,
                role: inviteRole,
              })
              setMessage(`Created ${created.email} (invite_token on user record).`)
              setInviteEmail('')
              setInviteName('')
            })
          }}
        >
          <div className="field">
            <label htmlFor="inv-email">Email</label>
            <input
              id="inv-email"
              type="email"
              required
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="inv-name">Name</label>
            <input
              id="inv-name"
              required
              value={inviteName}
              onChange={(e) => setInviteName(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="inv-role">Role</label>
            <select
              id="inv-role"
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value as typeof inviteRole)}
            >
              <option value="clinician">Clinician</option>
              <option value="annotator">Annotator</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <div style={{ alignSelf: 'end' }}>
            <button className="btn btn-primary" type="submit">
              Create invite
            </button>
          </div>
        </form>
        <h3 style={{ marginTop: '1rem', fontSize: '1rem' }}>Users</h3>
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.id}</td>
                <td>{u.name}</td>
                <td>{u.email}</td>
                <td>{u.role}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h2 className="section-title" style={{ fontSize: '1.1rem' }}>
          Evaluation sets
        </h2>
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault()
            const ids = setReportIds
              .split(/[,\s]+/)
              .map((x) => Number(x.trim()))
              .filter((n) => Number.isFinite(n) && n > 0)
            void wrap(async () => {
              await api.createEvalSet({
                name: setName,
                cancer_types: [setCancer],
                report_ids: ids,
              })
              setMessage(`Created evaluation set “${setName}”.`)
              setSetName('')
              setSetReportIds('')
            })
          }}
        >
          <div className="grid-2">
            <div className="field">
              <label htmlFor="set-name">Name</label>
              <input id="set-name" required value={setName} onChange={(e) => setSetName(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="set-cancer">Cancer type</label>
              <select id="set-cancer" value={setCancer} onChange={(e) => setSetCancer(e.target.value)}>
                {CANCER_OPTIONS.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.label} ({c.code})
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="field">
            <label htmlFor="set-ids">Report IDs (comma-separated)</label>
            <input
              id="set-ids"
              value={setReportIds}
              onChange={(e) => setSetReportIds(e.target.value)}
              placeholder={reports.map((r) => r.id).join(', ')}
            />
          </div>
          <button className="btn btn-primary" type="submit">
            Create evaluation set
          </button>
        </form>
        <table className="table" style={{ marginTop: '1rem' }}>
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Cancer types</th>
              <th>Reports</th>
            </tr>
          </thead>
          <tbody>
            {sets.map((s) => (
              <tr key={s.id}>
                <td>{s.id}</td>
                <td>{s.name}</td>
                <td>{(s.cancer_types || []).join(', ')}</td>
                <td>{(s.report_ids || []).join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h2 className="section-title" style={{ fontSize: '1.1rem' }}>
          Create &amp; assign batches
        </h2>
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault()
            const assigned = batchUserIds
              .split(/[,\s]+/)
              .map((x) => Number(x.trim()))
              .filter((n) => Number.isFinite(n) && n > 0)
            void wrap(async () => {
              await api.createBatch({
                name: batchName,
                batch_type: batchType,
                evaluation_set_id: batchSetId === '' ? null : Number(batchSetId),
                assigned_user_ids: assigned,
              })
              setMessage(`Created batch “${batchName}”.`)
              setBatchName('')
            })
          }}
        >
          <div className="grid-2">
            <div className="field">
              <label htmlFor="batch-name">Name</label>
              <input
                id="batch-name"
                required
                value={batchName}
                onChange={(e) => setBatchName(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="batch-type">Type</label>
              <select
                id="batch-type"
                value={batchType}
                onChange={(e) => setBatchType(e.target.value as typeof batchType)}
              >
                <option value="annotate">annotate</option>
                <option value="review">review</option>
                <option value="auto_check">auto_check</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="batch-set">Evaluation set</label>
              <select
                id="batch-set"
                value={batchSetId}
                onChange={(e) =>
                  setBatchSetId(e.target.value === '' ? '' : Number(e.target.value))
                }
              >
                <option value="">—</option>
                {sets.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} (#{s.id})
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="batch-users">Assignee user IDs</label>
              <input
                id="batch-users"
                required
                value={batchUserIds}
                onChange={(e) => setBatchUserIds(e.target.value)}
                placeholder="2, 3"
              />
            </div>
          </div>
          <button className="btn btn-primary" type="submit">
            Create batch
          </button>
        </form>
        <table className="table" style={{ marginTop: '1rem' }}>
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Type</th>
              <th>Status</th>
              <th>Assignees</th>
            </tr>
          </thead>
          <tbody>
            {batches.map((b) => (
              <tr key={b.id}>
                <td>{b.id}</td>
                <td>{b.name}</td>
                <td>{b.batch_type}</td>
                <td>{b.status}</td>
                <td>{(b.assigned_user_ids || []).join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h2 className="section-title" style={{ fontSize: '1.1rem' }}>
          Run auto-checks
        </h2>
        <p className="muted">
          Runs number grounding, unsupported-sentence, reading-level, and field-accuracy checks over
          generations (optionally scoped to an evaluation set).
        </p>
        <div className="row">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() =>
              void wrap(async () => {
                const res = await api.runAutoChecks({})
                setMessage(`Auto-check run #${res.run_id} completed on ${res.count} generations.`)
              })
            }
          >
            Run on all generations
          </button>
          {sets.map((s) => (
            <button
              key={s.id}
              type="button"
              className="btn btn-ghost"
              onClick={() =>
                void wrap(async () => {
                  const res = await api.runAutoChecks({ evaluation_set_id: s.id })
                  setMessage(`Auto-check run #${res.run_id} for set “${s.name}” (${res.count}).`)
                })
              }
            >
              Run on {s.name}
            </button>
          ))}
        </div>
      </div>

      <div className="panel">
        <h2 className="section-title" style={{ fontSize: '1.1rem' }}>
          OCR benchmark
        </h2>
        <p className="muted">
          Prefer importing the committed real-scan benchmark (n=30, CER≈0.293 / WER≈0.456) so Results
          populates without live Tesseract. Live runs on Render free tier take minutes per page and
          can trip health checks — use only when regenerating. Facsimiles stay excluded. Public demo
          never accepts arbitrary uploads (PHI).
        </p>
        <div className="row">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() =>
              void wrap(async () => {
                const res = await api.importOcrBenchmark(false)
                setMessage(
                  `Imported OCR benchmark #${res.benchmark_id} · n_real_scans_scored=${
                    res.n_real_scans_scored ?? '—'
                  } (${res.seeded_from ?? 'ocr_benchmark_latest.json'}).`,
                )
              })
            }
          >
            Import committed benchmark
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() =>
              void wrap(async () => {
                const res = await api.runOcrBenchmark('tesseract')
                setMessage(
                  `OCR benchmark #${res.benchmark_id} (${res.engine}) on ${res.n_reports} reports.`,
                )
              })
            }
          >
            Run live OCR benchmark (slow)
          </button>
        </div>
        <p className="muted" style={{ fontSize: '0.85rem', marginTop: '0.75rem' }}>
          Live OCR for one report: <code>POST /api/admin/ocr/run?report_id=…&amp;force=true</code>.
          Admin-only test upload (de-identified / TCGA pages only):{' '}
          <code>POST /api/admin/ocr/upload-test</code> with <code>acknowledge_deidentified=true</code>
          . Image bytes are not stored. Default <code>OCR_MAX_PAGES=1</code> for live runs.
        </p>
      </div>
    </div>
  )
}
