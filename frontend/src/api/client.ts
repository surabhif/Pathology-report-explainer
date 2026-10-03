/**
 * Thin fetch wrapper around the FastAPI backend.
 *
 * Auth: backend deps.py reads `X-Session-Token` (preferred) or the session cookie.
 * We store the session token in localStorage after /api/auth/redeem and send it
 * on every authenticated request.
 */

import type {
  AnnotationTaskOut,
  EvaluationSetOut,
  ExplainResponse,
  FactSpan,
  GlossaryTerm,
  ProgressOut,
  ReportDetail,
  ReportSummary,
  ResultsSummary,
  ReviewScores,
  ReviewTaskOut,
  SessionOut,
  TaskBatchOut,
  UserOut,
} from '../types'

const SESSION_KEY = 'pathexplain_session'
const USER_KEY = 'pathexplain_user'

/** Base URL: optional absolute origin, otherwise same-origin (Vite proxy /api). */
function apiBase(): string {
  const env = import.meta.env.VITE_API_BASE_URL as string | undefined
  if (env && env.trim()) return env.replace(/\/$/, '')
  return ''
}

export function getStoredSession(): string | null {
  return localStorage.getItem(SESSION_KEY)
}

export function getStoredUser(): UserOut | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as UserOut
  } catch {
    return null
  }
}

export function storeSession(session: SessionOut): void {
  localStorage.setItem(SESSION_KEY, session.session_token)
  localStorage.setItem(USER_KEY, JSON.stringify(session.user))
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY)
  localStorage.removeItem(USER_KEY)
}

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  auth = false,
): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && options.body) {
    headers.set('Content-Type', 'application/json')
  }
  if (auth) {
    const token = getStoredSession()
    if (token) {
      // Match backend: X-Session-Token (Cookie also works via redeem response).
      headers.set('X-Session-Token', token)
    }
  }

  const res = await fetch(`${apiBase()}${path}`, { ...options, headers })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* ignore parse errors */
    }
    throw new ApiError(res.status, detail)
  }

  // CSV / empty responses
  const ctype = res.headers.get('content-type') || ''
  if (ctype.includes('text/csv') || ctype.includes('text/plain')) {
    return (await res.text()) as T
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export const api = {
  redeemInvite(token: string) {
    return request<SessionOut>('/api/auth/redeem', {
      method: 'POST',
      body: JSON.stringify({ token }),
    })
  },

  me() {
    return request<UserOut>('/api/auth/me', {}, true)
  },

  logout() {
    return request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }, true)
  },

  // Public
  listReports(cancerType?: string) {
    const q = cancerType ? `?cancer_type=${encodeURIComponent(cancerType)}` : ''
    return request<ReportSummary[]>(`/api/public/reports${q}`)
  },

  getReport(reportId: number) {
    return request<ReportDetail>(`/api/public/reports/${reportId}`)
  },

  explainReport(reportId: number) {
    return request<ExplainResponse>(`/api/public/reports/${reportId}/explain`)
  },

  getGlossary() {
    return request<{ terms: GlossaryTerm[] }>('/api/public/glossary')
  },

  getAbout() {
    return request<{ title: string; body: string }>('/api/about')
  },

  // Admin
  listUsers() {
    return request<UserOut[]>('/api/admin/users', {}, true)
  },

  createInvite(body: { email: string; name: string; role: string; invite_token?: string }) {
    return request<UserOut>('/api/admin/invites', { method: 'POST', body: JSON.stringify(body) }, true)
  },

  getProgress() {
    return request<ProgressOut>('/api/admin/progress', {}, true)
  },

  listEvalSets() {
    return request<EvaluationSetOut[]>('/api/admin/evaluation-sets', {}, true)
  },

  createEvalSet(body: { name: string; cancer_types: string[]; report_ids: number[] }) {
    return request<EvaluationSetOut>(
      '/api/admin/evaluation-sets',
      { method: 'POST', body: JSON.stringify(body) },
      true,
    )
  },

  listBatches() {
    return request<TaskBatchOut[]>('/api/admin/batches', {}, true)
  },

  createBatch(body: {
    name: string
    batch_type: 'annotate' | 'review' | 'auto_check'
    evaluation_set_id?: number | null
    assigned_user_ids: number[]
  }) {
    return request<TaskBatchOut>('/api/admin/batches', { method: 'POST', body: JSON.stringify(body) }, true)
  },

  runAutoChecks(body: {
    generation_ids?: number[] | null
    batch_id?: number | null
    evaluation_set_id?: number | null
  } = {}) {
    return request<{ run_id: number; count: number; results: unknown }>(
      '/api/admin/runs/auto-checks',
      { method: 'POST', body: JSON.stringify(body) },
      true,
    )
  },

  // Annotate — never receives model generations from the API
  listAnnotateTasks() {
    return request<AnnotationTaskOut[]>('/api/annotate/tasks', {}, true)
  },

  getAnnotateTask(taskId: number) {
    return request<AnnotationTaskOut>(`/api/annotate/tasks/${taskId}`, {}, true)
  },

  submitGold(taskId: number, gold_labels: Record<string, FactSpan | null>) {
    return request<AnnotationTaskOut>(
      `/api/annotate/tasks/${taskId}`,
      {
        method: 'POST',
        body: JSON.stringify({ gold_labels, status: 'completed' }),
      },
      true,
    )
  },

  // Review
  listReviewTasks() {
    return request<ReviewTaskOut[]>('/api/review/tasks', {}, true)
  },

  getReviewTask(taskId: number) {
    return request<ReviewTaskOut>(`/api/review/tasks/${taskId}`, {}, true)
  },

  submitReview(
    taskId: number,
    body: { scores: ReviewScores; flagged_sentences: number[]; comments?: string | null },
  ) {
    return request<ReviewTaskOut>(
      `/api/review/tasks/${taskId}`,
      {
        method: 'POST',
        body: JSON.stringify({ ...body, status: 'completed' }),
      },
      true,
    )
  },

  // Results
  getResultsSummary() {
    return request<ResultsSummary>('/api/results/summary', {}, true)
  },

  async downloadResultsCsv(): Promise<Blob> {
    const token = getStoredSession()
    const headers = new Headers()
    if (token) headers.set('X-Session-Token', token)
    const res = await fetch(`${apiBase()}/api/results/export.csv`, { headers })
    if (!res.ok) throw new ApiError(res.status, 'CSV export failed')
    return res.blob()
  },
}
