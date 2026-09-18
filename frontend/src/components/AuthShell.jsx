import { useNavigate } from 'react-router-dom'

import Chevron from './Chevron'

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
          <Chevron direction="left" className="h-6 w-6" />
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
        className={`min-h-12 w-full rounded-xl border px-3.5 py-2.5 text-base
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
      className="btn mt-5 min-h-12 w-full rounded-2xl bg-learner px-4 py-3 text-sm
                 font-extrabold tracking-wide text-white uppercase
                 hover:brightness-110 disabled:opacity-60"
    >
      {busy ? 'One moment…' : children}
    </button>
  )
}
