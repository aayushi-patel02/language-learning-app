import axios from 'axios'

// In development Vite proxies /api to Django (see vite.config.js), so the
// browser sees a single origin and CORS never applies. In production
// VITE_API_URL points at the deployed backend.
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Topic list with each one's review load, so the home screen can show what
// is actually due rather than three inert links.
export const getTopics = () => api.get('/topics/')

// Cumulative progress across every lesson, for the progress screen.
export const getProgress = () => api.get('/progress/')

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
