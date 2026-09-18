import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { getRecap } from '../api'
import { formatDue, formatStreak } from '../dates'

export default function Recap() {
  const { sessionId } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  // Carried through the lesson from a word's own page. A lesson opened for
  // one word should end back at that word, showing what practising it did
  // to its schedule, not at the topic list.
  const [searchParams] = useSearchParams()
  const focusWordId = Number(searchParams.get('word')) || null

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

  // Only when the word was actually reached. Ending a lesson on turn one
  // leaves the rest of the plan ungraded, and offering to go back to a word
  // whose numbers did not move would be a lie.
  const focusWord = focusWordId
    ? data.words.find((word) => word.id === focusWordId)
    : null

  return (
    <Shell>
      <div className="animate-pop py-4 text-center">
        <div
          aria-hidden="true"
          className="mx-auto flex h-16 w-16 items-center justify-center rounded-full
                     bg-learner-soft text-3xl text-learner"
        >
          ✓
        </div>
        <h1 className="mt-4 text-2xl font-bold tracking-tight">
          Lesson complete
        </h1>
        {/* Same words as the banner on the lesson screen, so the two agree
            about why this lesson happened. */}
        <p className="mt-1 text-sm text-muted">
          {focusWord
            ? `${data.topic_label}, starting with ${focusWord.term}`
            : data.topic_label}
        </p>
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
            <li key={word.id ?? word.term} className="flex items-center gap-3 py-2.5">
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

      {/* The mechanic, not the algorithm's name. This is the moment right
          after finishing a lesson; someone who wants the detail finds it on
          a word's own page, next to that word's actual numbers. */}
      <p className="mt-6 text-xs leading-relaxed text-muted">
        Get a word right and it comes back a little later each time. Get one
        wrong and it comes back tomorrow.
      </p>

      <div className="mt-8 space-y-2 pb-4">
        <Link
          to={`/chat/${data.topic}`}
          className="btn flex min-h-12 items-center justify-center rounded-2xl
                     bg-learner px-4 py-3 text-sm font-extrabold tracking-wide
                     text-white uppercase hover:brightness-110"
        >
          Next lesson
        </Link>
        {/* A lesson opened from a word ends back at that word, where its new
            review date and streak are waiting. Sending it home instead
            dropped the learner one screen away from the only thing they
            came to see. */}
        <Link
          to={focusWord ? `/vocabulary/${focusWord.id}` : '/'}
          className="btn flex min-h-12 items-center justify-center rounded-2xl
                     border border-line bg-white px-4 py-3 text-sm font-extrabold
                     tracking-wide uppercase transition-colors hover:border-learner"
        >
          <span className="truncate">
            {focusWord ? `Back to ${focusWord.term}` : 'Back to topics'}
          </span>
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
