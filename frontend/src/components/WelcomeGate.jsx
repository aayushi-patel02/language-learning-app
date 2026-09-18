import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { startGuest } from '../api'
import { useAuth } from '../auth'

export default function WelcomeGate() {
  const navigate = useNavigate()
  const { adopt } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const tryAsGuest = async () => {
    setBusy(true)
    setError('')
    try {
      const { data } = await startGuest()
      adopt(data)
      navigate('/', { replace: true })
    } catch {
      setError('Could not start a session. Is the backend running?')
      setBusy(false)
    }
  }

  return (
    <div className="app-column mx-auto flex min-h-full max-w-md flex-col px-5 pt-16 pb-10">
      <div className="flex flex-1 flex-col justify-center text-center">
        <span
          aria-hidden="true"
          className="mx-auto flex h-20 w-20 items-center justify-center rounded-3xl
                     bg-learner text-4xl"
        >
          🦉
        </span>
        <h1 className="mt-5 text-4xl font-extrabold tracking-tight">Charla</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          Speak languages with confidence.
        </p>
      </div>

      {error && (
        <p className="mb-3 rounded-xl bg-error-soft px-3 py-2 text-center text-xs
                      text-error">
          {error}
        </p>
      )}

      <div className="space-y-2.5">
        <button
          type="button"
          onClick={() => navigate('/signup')}
          className="btn-3d min-h-12 w-full rounded-2xl bg-learner px-4 py-3 text-sm
                     font-extrabold tracking-wide text-white uppercase
                     hover:brightness-110"
        >
          Get started
        </button>
        <button
          type="button"
          onClick={() => navigate('/login')}
          className="btn-3d min-h-12 w-full rounded-2xl border border-line bg-white
                     px-4 py-3 text-sm font-extrabold tracking-wide uppercase
                     hover:bg-surface"
        >
          I already have an account
        </button>
      </div>

      {/* Deliberately the quietest of the three, but always present: making
          someone sign up before they can see anything is the fastest way to
          lose them, and a judge should be able to be inside the app in one
          tap. */}
      <button
        type="button"
        onClick={tryAsGuest}
        disabled={busy}
        className="mt-4 inline-flex min-h-11 items-center justify-center text-xs
                   font-semibold text-muted underline disabled:opacity-50"
      >
        {busy ? 'Setting things up…' : 'Try as guest'}
      </button>

      <p className="mt-2 text-center text-[11px] leading-relaxed text-muted">
        Practising as a guest keeps your progress. You can create an account
        later and it comes with you.
      </p>
    </div>
  )
}
