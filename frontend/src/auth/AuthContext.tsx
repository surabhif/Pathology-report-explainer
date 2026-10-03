import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  api,
  clearSession,
  getStoredSession,
  getStoredUser,
  storeSession,
} from '../api/client'
import type { SessionOut, UserOut } from '../types'

interface AuthState {
  user: UserOut | null
  sessionToken: string | null
  login: (inviteToken: string) => Promise<SessionOut>
  logout: () => Promise<void>
  refreshMe: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(() => getStoredUser())
  const [sessionToken, setSessionToken] = useState<string | null>(() => getStoredSession())

  const login = useCallback(async (inviteToken: string) => {
    const session = await api.redeemInvite(inviteToken)
    storeSession(session)
    setUser(session.user)
    setSessionToken(session.session_token)
    return session
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } catch {
      /* ignore network errors on logout */
    }
    clearSession()
    setUser(null)
    setSessionToken(null)
  }, [])

  const refreshMe = useCallback(async () => {
    if (!getStoredSession()) return
    try {
      const me = await api.me()
      setUser(me)
      localStorage.setItem('pathexplain_user', JSON.stringify(me))
    } catch {
      clearSession()
      setUser(null)
      setSessionToken(null)
    }
  }, [])

  const value = useMemo(
    () => ({ user, sessionToken, login, logout, refreshMe }),
    [user, sessionToken, login, logout, refreshMe],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
