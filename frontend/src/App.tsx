import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { Layout } from './components/Layout'
import { AboutPage } from './pages/AboutPage'
import { AdminPage } from './pages/AdminPage'
import { AnnotatePage } from './pages/AnnotatePage'
import { HomePage } from './pages/HomePage'
import { LoginPage } from './pages/LoginPage'
import { ResultsPage } from './pages/ResultsPage'
import { ReviewPage } from './pages/ReviewPage'

/**
 * PathExplain SPA routes.
 * Public: /, /about, /login
 * Authenticated role tools: /admin, /annotate, /review, /results
 */
export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<HomePage />} />
            <Route path="about" element={<AboutPage />} />
            <Route path="login" element={<LoginPage />} />
            <Route path="admin" element={<AdminPage />} />
            <Route path="annotate" element={<AnnotatePage />} />
            <Route path="review" element={<ReviewPage />} />
            <Route path="results" element={<ResultsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
