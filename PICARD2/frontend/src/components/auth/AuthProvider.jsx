import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { apiRequest, buildApiUrl } from '../../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [user, setUser] = useState(null)
  const [authError, setAuthError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')

  async function refreshSession({ silent = false } = {}) {
    if (!silent) {
      setIsLoading(true)
    }

    try {
      const data = await apiRequest('/auth/session/')
      setIsAuthenticated(Boolean(data.authenticated))
      setUser(data.user || null)
      setCsrfToken(data.csrfToken || '')

      if (data.authenticated) {
        setAuthError('')
      }
    } catch {
      setIsAuthenticated(false)
      setUser(null)
      setCsrfToken('')
      setAuthError('Unable to reach the backend authentication service.')
    } finally {
      if (!silent) {
        setIsLoading(false)
      }
    }
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const authStatus = params.get('auth')
    const reason = params.get('reason')

    if (authStatus === 'error') {
      setAuthError(reason ? `GitHub login failed: ${reason}` : 'GitHub login failed.')
    } else if (authStatus === 'success') {
      setAuthError('')
    }

    if (authStatus) {
      params.delete('auth')
      params.delete('reason')
      const nextSearch = params.toString()
      const nextUrl = `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ''}${window.location.hash}`
      window.history.replaceState({}, '', nextUrl)
    }

    refreshSession().catch(() => undefined)
  }, [])

  function login() {
    setAuthError('')
    const loginUrl = new URL(buildApiUrl('/auth/github/login/'), window.location.origin)
    loginUrl.searchParams.set('origin', window.location.origin)
    window.location.assign(loginUrl.toString())
  }

  async function logout() {
    try {
      await apiRequest('/auth/logout/', {
        method: 'POST',
        csrfToken,
      })
    } finally {
      setAuthError('')
      setIsAuthenticated(false)
      setUser(null)
      setCsrfToken('')
    }
  }

  const value = useMemo(() => {
    return {
      authError,
      csrfToken,
      isAuthenticated,
      isLoading,
      login,
      logout,
      refreshSession,
      user,
    }
  }, [authError, csrfToken, isAuthenticated, isLoading, user])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used inside AuthProvider')
  }
  return ctx
}
