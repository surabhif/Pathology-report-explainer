import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { DEMO_TOKENS } from '../types'

/** Redeem invite token → session stored in localStorage. */
export function LoginPage() {
  const { login, user } = useAuth()
  const navigate = useNavigate()
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const session = await login(token.trim())
      const role = session.user.role
      if (role === 'admin') navigate('/admin')
      else if (role === 'annotator') navigate('/annotate')
      else if (role === 'clinician') navigate('/review')
      else navigate('/')
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.detail : 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page-enter" style={{ maxWidth: 480 }}>
      <h1 className="section-title">Login</h1>
      <p className="muted">
        Redeem an invite token. Session token is stored in localStorage and sent as{' '}
        <code>X-Session-Token</code>.
      </p>

      {user && (
        <p className="success-text">
          Signed in as {user.name} ({user.role}).
        </p>
      )}

      <form className="panel stack" onSubmit={(e) => void onSubmit(e)}>
        <div className="field">
          <label htmlFor="invite">Invite token</label>
          <input
            id="invite"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="DEMO_ADMIN_TOKEN"
            autoComplete="off"
            required
          />
        </div>
        {error && <p className="error-text">{error}</p>}
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {busy ? 'Redeeming…' : 'Redeem invite'}
        </button>
      </form>

      <div className="panel" style={{ marginTop: '1rem' }}>
        <h2 className="section-title" style={{ fontSize: '1.1rem' }}>
          Local demo tokens
        </h2>
        <p className="muted">
          Convenience defaults for local development only. Production must set{' '}
          <code>DEMO_ADMIN_TOKEN</code>, <code>DEMO_ANNOTATOR_TOKEN</code>, and{' '}
          <code>DEMO_CLINICIAN_TOKEN</code> (or invite users from Admin) — known defaults are never
          seeded when <code>APP_ENV=production</code>.
        </p>
        <div className="stack">
          {DEMO_TOKENS.map((d) => (
            <button
              key={d.token}
              type="button"
              className="btn btn-ghost"
              onClick={() => setToken(d.token)}
            >
              {d.label}: {d.token}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
