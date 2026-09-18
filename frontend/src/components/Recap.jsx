import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getRecap } from '../api'
import { formatDue, formatStreak } from '../dates'

export default function Recap() {
  const { sessionId } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getRecap(sessionId)
      .then((response) => setData(response.data))
      .catch((err) =>
        setError(err?.response?.data?.detail ?? 'Could not load this recap.'),
      )
  }, [sessionId])

  if (error) {
    return (
      <Shell>
        <p className="rounded-lg bg-error-soft px-3 py-2 text-sm text-error">{error}</p>
      </Shell>
    )
  }

  if (!data) {
    return (
      <Shell>
        <p className="py-16 text-center text-sm text-muted">Loading…</p>
      </Shell>
    )
  }

  const accuracy =
    data.accuracy === null ? 'n/a' : `${Math.round(data.accuracy * 100)}%`

  return (
    <Shell>
      <div className="animate-pop py-4 text-center">
        <div
          aria-hidden="true"
          className="mx-auto flex h-16 w-16 items-center justify-center rounded-full
                     bg-success-soft text-3xl text-success"
        >
          ✓
        </div>
        <h1 className="mt-4 text-2xl font-bold tracking-tight">
          Lesson complete
        </h1>
        <p className="mt-1 text-sm text-muted">{data.topic_label}</p>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3">
        <Stat label="Words" value={data.words_practiced} />
        <Stat label="Correct" value={`${data.turns_correct}/${data.turns_graded}`} />
        <Stat label="Accuracy" value={accuracy} />
      </div>

      <h2 className="mt-8 text-xs font-medium tracking-wide text-muted uppercase">
        When you&rsquo;ll see these again
      </h2>

      {data.words.length === 0 ? (
        <p className="mt-3 text-sm text-muted">
          No words were practised in this session.
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-line">
          {data.words.map((word) => (
            <li key={word.term} className="flex items-center gap-3 py-2.5">
              <span
                aria-hidden="true"
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                  !word.graded
                    ? 'bg-muted'
                    : word.was_correct
                      ? 'bg-success'
                      : 'bg-error'
                }`}
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">{word.term}</span>
                {word.romanisation && (
                  <span className="block truncate text-xs text-muted italic">
                    {word.romanisation}
                  </span>
                )}
                <span className="block truncate text-xs text-muted">
                  {word.english}
                </span>
              </span>
              <span className="shrink-0 text-right">
                <span className="block text-xs">
                  {word.graded ? formatDue(word.due_date) : 'not graded'}
                </span>
                <span className="block text-[11px] text-muted">
                  {formatStreak(word)}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-6 text-xs leading-relaxed text-muted">
        Review dates come from SM-2. A word you got wrong resets to a one-day
        interval; each correct answer pushes it further out.
      </p>

      <div className="mt-8 space-y-2 pb-4">
        <Link
          to={`/chat/${data.topic}`}
          className="btn-3d flex min-h-12 items-center justify-center rounded-2xl
                     bg-success px-4 py-3 text-sm font-extrabold tracking-wide
                     text-white uppercase hover:brightness-110"
        >
          Next lesson
        </Link>
        <Link
          to="/"
          className="btn-3d flex min-h-12 items-center justify-center rounded-2xl
                     border-2 border-line bg-white px-4 py-3 text-sm font-extrabold
                     tracking-wide uppercase hover:bg-surface"
        >
          Back to topics
        </Link>
      </div>
    </Shell>
  )
}

function Shell({ children }) {
  return (
    <div className="app-column mx-auto min-h-full max-w-md px-5 pt-8 pb-28">{children}</div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="rounded-xl bg-surface px-3 py-3 text-center">
      <p className="text-lg font-bold tabular-nums">{value}</p>
      <p className="mt-0.5 text-xs text-muted">{label}</p>
    </div>
  )
}
