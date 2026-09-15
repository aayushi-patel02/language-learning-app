import axios from 'axios'

// In development Vite proxies /api to Django (see vite.config.js), so the
// browser sees a single origin and CORS never applies. In production
// VITE_API_URL points at the deployed backend.
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Read on every request rather than set once at startup: signing in or out
// mid-session changes the token, and a captured copy would go stale.
api.interceptors.request.use((config) => {
  let token = null
  try {
    token = localStorage.getItem('charla.token')
  } catch {
    // Private browsing. Requests go out unauthenticated, which the backend
    // answers as the demo learner rather than rejecting.
  }
  if (token) config.headers.Authorization = `Token ${token}`
  return config
})

// --- accounts ---
export const startGuest = () => api.post('/auth/guest/')
export const signUp = (payload) => api.post('/auth/signup/', payload)
export const logIn = (email, password) =>
  api.post('/auth/login/', { email, password })
export const getMe = () => api.get('/auth/me/')
export const updateMe = (payload) => api.patch('/auth/me/', payload)
export const deleteAccount = () => api.delete('/auth/me/')

// Topic list with each one's review load, so the home screen can show what
// is actually due rather than three inert links.
export const getTopics = () => api.get('/topics/')

// Cumulative progress across every lesson, for the progress screen.
export const getProgress = () => api.get('/progress/')

// The vocabulary library, grouped by mastery, plus saved and recent cuts.
export const getVocabulary = () => api.get('/vocabulary/')
export const getWord = (id) => api.get(`/vocabulary/${id}/`)
export const setWordSaved = (id, isSaved) =>
  api.post(`/vocabulary/${id}/`, { is_saved: isSaved })

export const startSession = (topic) => api.post('/sessions/start/', { topic })

// Chips are identified by id, not by their text: the backend holds the answer
// key and decides whether the tap was right. Sending the text back would let
// the client pick its own grade.
export const sendChip = (sessionId, replyId) =>
  api.post(`/sessions/${sessionId}/next/`, { mode: 'chip', reply_id: replyId })

export const sendFreetext = (sessionId, text) =>
  api.post(`/sessions/${sessionId}/next/`, { mode: 'freetext', text })

export const getRecap = (sessionId) => api.get(`/sessions/${sessionId}/recap/`)

export default api
