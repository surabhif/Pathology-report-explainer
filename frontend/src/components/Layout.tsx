import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

/** Shared chrome: sticky research banner + nav + project-family footer. */
export function Layout() {
  const { user, logout } = useAuth()

  return (
    <div className="app-shell">
      <div className="site-top">
        <div className="research-banner" role="status">
          Research demo, not for clinical use
        </div>
        <header className="app-header">
          <div className="site-header-inner">
            <div className="brand-block">
              <NavLink to="/" className="brand-link" end>
                PathExplain
              </NavLink>
              <p className="brand-kicker">Surabhi · College research MVP</p>
            </div>
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
          </div>
        </header>
      </div>
      <main className="app-main">
        <Outlet />
      </main>
      <footer className="app-footer">
        <div className="footer-grid">
          <div>
            <p className="footer-brand">PathExplain</p>
            <p>
              College research MVP that turns de-identified pathology reports into grounded
              plain-language explanations. Sibling of Surabhi&apos;s Lymph Node Metastasis Detector.
            </p>
          </div>
          <div>
            <p className="footer-heading">Links</p>
            <ul className="footer-links">
              <li>
                <NavLink to="/about">About / model card</NavLink>
              </li>
              <li>
                <NavLink to="/results">Results</NavLink>
              </li>
              <li>
                <a
                  href="https://surabhif.github.io/Lymph-node-metastasis-detector/"
                  target="_blank"
                  rel="noreferrer"
                >
                  Lymph Node Detector
                </a>
              </li>
            </ul>
          </div>
        </div>
        <div className="project-family">
          <p className="footer-heading">Project family</p>
          <ul className="project-family-list">
            <li className="project-family-card is-current">
              <span className="project-family-swatch" style={{ background: '#F9EA8B' }} aria-hidden />
              <span>
                <strong>PathExplain</strong>
                <span className="project-family-blurb">You are here · Pathology reports</span>
              </span>
            </li>
            <li className="project-family-card">
              <span className="project-family-swatch" style={{ background: '#9B5654' }} aria-hidden />
              <a
                href="https://surabhif.github.io/Lymph-node-metastasis-detector/"
                target="_blank"
                rel="noreferrer"
              >
                <strong>Lymph-node metastasis detector</strong>
                <span className="project-family-blurb">PCam · In-browser ONNX</span>
              </a>
            </li>
            <li className="project-family-card">
              <span className="project-family-swatch" style={{ background: '#297373' }} aria-hidden />
              <span>
                <strong>BUS ultrasound</strong>
                <span className="project-family-blurb">Sibling brand · Teal #297373</span>
              </span>
            </li>
          </ul>
          <p className="project-family-note">
            Same research family: shared chrome, sharp corners, mono labels — each app keeps its own
            brand accent.
          </p>
        </div>
        <p className="footer-fine">
          Research only · Not for clinical use · De-identified public data
        </p>
      </footer>
    </div>
  )
}
