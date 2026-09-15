import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { deleteAccount, updateMe } from '../api'
import { useAuth } from '../auth'

const AVATARS = ['🦉', '🐙', '🦊', '🐢', '🦜', '🐝', '🌵', '🍋']
const LANGUAGES = ['English', 'Spanish', 'Hindi', 'Gujarati', 'French', 'German', 'Portuguese']

export default function Profile() {
  const navigate = useNavigate()
  const { user, setUser, signOut } = useAuth()

  const [draft, setDraft] = useState(null)
  const [saved, setSaved] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  useEffect(() => {
    if (user) {
      setDraft({
        display_name: user.name === 'Guest' ? '' : user.name,
        avatar: user.avatar,
        native_language: user.native_language,
        learning_language: user.learning_language,
      })
    }
  }, [user])

  if (!user || !draft) {
    return (
      <Shell>
        <p className="py-16 text-center text-sm text-muted">Loading…</p>
      </Shell>
    )
  }

  const change = (key, value) => {
    const next = { ...draft, [key]: value }
    setDraft(next)
    setSaved(false)
    // Saved on change rather than behind a button: there is no destructive
    // edit here, and a Save button people forget to press is worse.
    updateMe({ [key]: value })
      .then(({ data }) => {
        setUser(data)
        setSaved(true)
      })
      .catch(() => setSaved(false))
  }

  const remove = async () => {
    try {
      await deleteAccount()
    } finally {
      await signOut()
      navigate('/welcome', { replace: true })
    }
  }

  return (
    <Shell>
      <div className="flex items-center gap-4">
        <span
          aria-hidden="true"
          className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl
                     bg-surface text-3xl"
        >
          {draft.avatar}
        </span>
        <div className="min-w-0">
          <p className="truncate text-xl font-extrabold">{user.name}</p>
          <p className="truncate text-xs text-muted">
            {user.is_guest ? 'Practising as a guest' : user.email}
          </p>
        </div>
      </div>

      {user.is_guest && (
        <div className="mt-5 rounded-2xl bg-topic-morning-soft px-4 py-3.5">
          <p className="text-sm font-bold">Your progress is not saved anywhere</p>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            Create an account and everything you have practised comes with you.
            Clear this browser first and it is gone.
          </p>
          <Link
            to="/signup"
            className="btn-3d mt-3 flex min-h-11 items-center justify-center rounded-xl
                       bg-topic-morning px-4 py-2 text-xs font-extrabold tracking-wide
                       text-white uppercase hover:brightness-110"
          >
            Create an account
          </Link>
        </div>
      )}

      <h2 className="mt-7 text-xs font-bold tracking-wide text-muted uppercase">
        Avatar
      </h2>
      <div className="mt-2.5 flex flex-wrap gap-2">
        {AVATARS.map((emoji) => (
          <button
            key={emoji}
            type="button"
            onClick={() => change('avatar', emoji)}
            aria-label={`Choose ${emoji}`}
            aria-pressed={draft.avatar === emoji}
            className={`flex h-12 w-12 items-center justify-center rounded-xl border-2
                        text-2xl transition-colors ${
                          draft.avatar === emoji
                            ? 'border-learner bg-surface'
                            : 'border-line bg-white hover:border-ink/20'
                        }`}
          >
            {emoji}
          </button>
        ))}
      </div>

      {!user.is_guest && (
        <>
          <h2 className="mt-7 text-xs font-bold tracking-wide text-muted uppercase">
            Name
          </h2>
          <input
            value={draft.display_name}
            onChange={(event) => change('display_name', event.target.value)}
            placeholder="Your name"
            className="mt-2.5 min-h-12 w-full rounded-xl border-2 border-line bg-white
                       px-3.5 py-2.5 text-base focus:border-learner focus:outline-none"
          />
        </>
      )}

      <Picker
        label="I speak"
        value={draft.native_language}
        onChange={(value) => change('native_language', value)}
      />
      <Picker
        label="I am learning"
        value={draft.learning_language}
        onChange={(value) => change('learning_language', value)}
        note="Charla currently teaches Spanish. Other languages are a matter of
              seeding vocabulary, not changing the app."
      />

      {saved && <p className="mt-4 text-xs text-success">Saved.</p>}

      <div className="mt-8 space-y-2">
        <button
          type="button"
          onClick={async () => {
            await signOut()
            navigate('/welcome', { replace: true })
          }}
          className="btn-3d flex min-h-12 w-full items-center justify-center rounded-2xl
                     border-2 border-line bg-white px-4 py-3 text-sm font-extrabold
                     tracking-wide uppercase hover:bg-surface"
        >
          Log out
        </button>

        {confirmingDelete ? (
          <div className="rounded-2xl border-2 border-error bg-error-soft px-4 py-3.5">
            <p className="text-sm font-bold text-error">Delete this account?</p>
            <p className="mt-1 text-xs leading-relaxed text-muted">
              Every word you have learned and every conversation goes with it.
              This cannot be undone.
            </p>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={remove}
                className="btn-3d min-h-11 flex-1 rounded-xl bg-error px-3 py-2 text-xs
                           font-extrabold tracking-wide text-white uppercase
                           hover:brightness-110"
              >
                Yes, delete
              </button>
              <button
                type="button"
                onClick={() => setConfirmingDelete(false)}
                className="btn-3d min-h-11 flex-1 rounded-xl border-2 border-line
                           bg-white px-3 py-2 text-xs font-extrabold tracking-wide
                           uppercase"
              >
                Keep it
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirmingDelete(true)}
            className="inline-flex min-h-11 w-full items-center justify-center text-xs
                       text-muted underline"
          >
            Delete account
          </button>
        )}
      </div>
    </Shell>
  )
}

function Picker({ label, value, onChange, note }) {
  return (
    <>
      <h2 className="mt-7 text-xs font-bold tracking-wide text-muted uppercase">
        {label}
      </h2>
      <div className="mt-2.5 flex flex-wrap gap-2">
        {LANGUAGES.map((language) => (
          <button
            key={language}
            type="button"
            onClick={() => onChange(language)}
            className={`inline-flex min-h-11 items-center rounded-full border px-3.5
                        text-xs font-bold transition-colors ${
                          value === language
                            ? 'border-learner bg-learner text-white'
                            : 'border-line bg-white hover:border-ink/20'
                        }`}
          >
            {language}
          </button>
        ))}
      </div>
      {note && <p className="mt-2 text-[11px] leading-relaxed text-muted">{note}</p>}
    </>
  )
}

function Shell({ children }) {
  return (
    <div className="app-column mx-auto min-h-full max-w-md px-5 pt-8 pb-12">
      <header className="mb-6 flex items-center gap-3">
        <Link
          to="/"
          aria-label="Back to topics"
          className="-ml-1 inline-flex min-h-11 min-w-11 items-center justify-center
                     text-lg text-muted transition hover:text-ink"
        >
          &lsaquo;
        </Link>
        <h1 className="text-2xl font-extrabold tracking-tight">Profile</h1>
      </header>
      {children}
    </div>
  )
}
