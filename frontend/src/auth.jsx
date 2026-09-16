import { createContext, useCallback, useContext, useEffect, useState } from 'react'

import api, { getMe } from './api'

const TOKEN_KEY = 'charla.token'

// localStorage rather than a cookie: the frontend and backend live on
// different origins in production, where a session cookie is a third-party
// cookie and Safari blocks those. An Authorization header is untouched by
// any browser.
export function readToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function writeToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // Private browsing can refuse writes. The session still works for as long
    // as the tab is open; it just will not be remembered.
  }
}

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // Distinguishes "no account yet" from "we have not asked yet", so the app
  // never flashes the welcome screen at someone who is already signed in.
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const token = readToken()
    if (!token) {
      setReady(true)
      return
    }
    getMe()
      .then(({ data }) => setUser(data))
      .catch(() => {
        // A token the server no longer honours is worse than none: it would
        // leave the app stuck believing it is signed in.
        writeToken(null)
      })
      .finally(() => setReady(true))
  }, [])

  const adopt = useCallback((payload) => {
    writeToken(payload.token)
    setUser(payload.user)
    return payload.user
  }, [])

  const signOut = useCallback(async () => {
    try {
      await api.post('/auth/logout/')
    } catch {
      // Even if the server cannot be reached, dropping the local token is
      // what the learner asked for.
    }
    writeToken(null)
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, ready, adopt, signOut, setUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
