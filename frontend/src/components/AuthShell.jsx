import { useNavigate } from 'react-router-dom'

/** Shared chrome for the sign-up and log-in screens. */
export default function AuthShell({ title, subtitle, children }) {
  const navigate = useNavigate()

  return (
    <div className="app-column mx-auto min-h-full max-w-md px-5 pt-8 pb-12">
      <header className="mb-6 flex items-center gap-2">
        <button
          type="button"
          onClick={() => navigate('/welcome')}
          aria-label="Back"
          className="-ml-1 inline-flex min-h-11 min-w-11 items-center justify-center
                     text-lg text-muted transition hover:text-ink"
        >
          &lsaquo;
        </button>
      </header>

      <h1 className="text-2xl font-extrabold tracking-tight">{title}</h1>
      {subtitle && <p className="mt-1.5 text-sm text-muted">{subtitle}</p>}

      <div className="mt-6">{children}</div>
    </div>
  )
}

export function Field({ label, hint, invalid, ...props }) {
  return (
    <label className="mt-4 block first:mt-0">
      <span className="mb-1.5 block text-xs font-bold tracking-wide text-muted uppercase">
        {label}
      </span>
      <input
        // text-base, not text-sm: iOS Safari zooms the whole page when a
        // focused input is under 16px.
        className={`min-h-12 w-full rounded-xl border-2 px-3.5 py-2.5 text-base
                    focus:outline-none ${
                      invalid
                        ? 'border-error bg-error-soft'
                        : 'border-line bg-white focus:border-learner'
                    }`}
        {...props}
      />
      {hint && <span className="mt-1 block text-[11px] text-muted">{hint}</span>}
    </label>
  )
}

export function SubmitButton({ busy, children }) {
  return (
    <button
      type="submit"
      disabled={busy}
      className="btn-3d mt-5 min-h-12 w-full rounded-2xl bg-learner px-4 py-3 text-sm
                 font-extrabold tracking-wide text-white uppercase
                 hover:brightness-110 disabled:opacity-60"
    >
      {busy ? 'One moment…' : children}
    </button>
  )
}

/**
 * Google sign-in needs an OAuth client id from the project's Google Cloud
 * console. Until VITE_GOOGLE_CLIENT_ID is set the button explains that rather
 * than failing on tap: a dead control that looks live is worse than one that
 * says what it is waiting for.
 */
export function GoogleButton({ label }) {
  const configured = Boolean(import.meta.env.VITE_GOOGLE_CLIENT_ID)

  if (!configured) return null

  return (
    <button
      type="button"
      onClick={() => {
        // Wired up once the client id exists; see README.
      }}
      className="btn-3d flex min-h-12 w-full items-center justify-center gap-2.5
                 rounded-2xl border-2 border-line bg-white px-4 py-3 text-sm
                 font-bold hover:bg-surface"
    >
      <GoogleMark />
      {label}
    </button>
  )
}

function GoogleMark() {
  return (
    <svg viewBox="0 0 18 18" aria-hidden="true" className="h-4 w-4">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18Z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33Z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.59C13.46.9 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58Z"
      />
    </svg>
  )
}
