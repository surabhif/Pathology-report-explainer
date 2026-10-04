import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

/** Shared chrome: research banner + nav + role chip when logged in. */
export function Layout() {
  const { user, logout } = useAuth()

  return (
    <>
      <div className="research-banner" role="status">
        Research demo, not for clinical use
      </div>
      <header className="app-header">
        <NavLink to="/" className="brand-link" end>
          PathExplain
        </NavLink>
        <nav className="nav-links" aria-label="Main">
          <NavLink to="/" end>
            Demo
          </NavLink>
          <NavLink to="/about">About</NavLink>
          <NavLink to="/results">Results</NavLink>
          {user?.role === 'admin' && <NavLink to="/admin">Admin</NavLink>}
          {(user?.role === 'annotator' || user?.role === 'admin') && (
            <NavLink to="/annotate">Annotate</NavLink>
          )}
          {(user?.role === 'clinician' || user?.role === 'admin') && (
            <NavLink to="/review">Review</NavLink>
          )}
          {user ? (
            <>
              <span className="role-chip" title={user.email}>
                {user.role}
              </span>
              <button type="button" className="btn btn-ghost" onClick={() => void logout()}>
                Log out
              </button>
            </>
          ) : (
            <NavLink to="/login">Login</NavLink>
          )}
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
      <footer className="app-footer">
        PathExplain · college research MVP · grounded plain-language pathology explanations
      </footer>
    </>
  )
}
