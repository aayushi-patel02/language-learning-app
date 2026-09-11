import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { getVocabulary } from '../api'
import { formatDue } from '../dates'
import { canSpeak, speak } from '../speech'

// Shelves are mutually exclusive so the tabs partition the collection.
// Saved and recent are cross-cuts over the same words, kept at the end.
const TABS = [
  { id: 'due', label: 'To review', tone: 'text-success' },
  { id: 'learning', label: 'Learning' },
  { id: 'mastered', label: 'Mastered', tone: 'text-success' },
  { id: 'new', label: 'Not started' },
  { id: 'saved', label: 'Saved' },
  { id: 'recent', label: 'Recent' },
]

export default function Vocabulary() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('due')

  useEffect(() => {
    getVocabulary()
      .then((response) => setData(response.data))
      .catch(() => setError('Could not load your vocabulary.'))
  }, [])

  const listFor = (id) =>
    id === 'saved' || id === 'recent' ? (data?.[id] ?? []) : (data?.shelves?.[id] ?? [])

  const countFor = (id) =>
    id === 'saved' || id === 'recent' ? (data?.[id]?.length ?? 0) : (data?.counts?.[id] ?? 0)

  const words = listFor(tab)

  return (
    <div className="app-column mx-auto flex min-h-full max-w-md flex-col px-5 pt-8 pb-12">
      <header className="mb-5 flex items-center gap-3">
        <Link
          to="/"
          aria-label="Back to topics"
          className="-ml-1 inline-flex min-h-11 min-w-11 items-center justify-center
                     text-lg text-muted transition hover:text-ink"
        >
          &lsaquo;
        </Link>
        <h1 className="flex-1 text-2xl font-extrabold tracking-tight">Vocabulary</h1>
        {data && (
          <span className="text-xs tabular-nums text-muted">{data.total} words</span>
        )}
      </header>

      {error && (
        <p className="rounded-xl bg-error-soft px-3 py-2 text-sm text-error">{error}</p>
      )}
      {!data && !error && (
        <p className="py-16 text-center text-sm text-muted">Loading…</p>
      )}

      {data && (
        <>
          {/* Horizontal scroll rather than wrapping: six tabs would otherwise
              take three lines on a narrow phone. */}
          <div className="-mx-5 mb-4 flex gap-2 overflow-x-auto px-5 pb-1">
            {TABS.map((entry) => {
              const active = entry.id === tab
              return (
                <button
                  key={entry.id}
                  type="button"
                  onClick={() => setTab(entry.id)}
                  className={`inline-flex min-h-11 shrink-0 items-center gap-1.5
                              rounded-full border px-3 text-xs font-bold
                              transition-colors ${
                                active
                                  ? 'border-learner bg-learner text-white'
                                  : 'border-line bg-white hover:border-ink/20'
                              }`}
                >
                  {entry.label}
                  <span
                    className={
                      active ? 'opacity-70' : (entry.tone ?? 'text-muted')
                    }
                  >
                    {countFor(entry.id)}
                  </span>
                </button>
              )
            })}
          </div>

          {words.length === 0 ? (
            <EmptyShelf tab={tab} />
          ) : (
            <ul className="flex flex-col gap-2">
              {words.map((word) => (
                <WordRow key={word.id} word={word} />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

function EmptyShelf({ tab }) {
  const message = {
    due: 'Nothing is due right now. Finish a lesson and words will appear here when they are ready for review.',
    learning: 'No words in progress yet.',
    mastered: 'None yet. A word lands here after three correct recalls in a row.',
    new: 'You have started every word in the collection.',
    saved: 'Tap the bookmark on any word to keep it here.',
    recent: 'Words you practise will show up here.',
  }[tab]

  return (
    <p className="rounded-2xl border border-line bg-white px-4 py-8 text-center
                  text-sm text-muted">
      {message}
    </p>
  )
}

function WordRow({ word }) {
  const speakable = canSpeak()

  return (
    <li className="rounded-2xl border border-line bg-white transition-colors
                   hover:border-ink/20">
      <div className="flex items-center gap-1 px-2 py-1">
        {speakable && (
          <button
            type="button"
            aria-label={`Hear ${word.spanish}`}
            onClick={() => speak(word.spanish)}
            className="inline-flex min-h-11 min-w-11 shrink-0 items-center
                       justify-center rounded-xl text-muted transition
                       hover:bg-surface hover:text-ink"
          >
            <SpeakerIcon />
          </button>
        )}

        <Link
          to={`/vocabulary/${word.id}`}
          className="flex min-w-0 flex-1 items-center gap-3 py-2 pr-2 focus:outline-none"
        >
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-bold">{word.spanish}</span>
            <span className="block truncate text-xs text-muted">{word.english}</span>
          </span>
          <span className="shrink-0 text-right">
            {word.due_date ? (
              <span className="block text-xs text-muted">
                {formatDue(word.due_date)}
              </span>
            ) : (
              <span className="block text-xs text-muted">not started</span>
            )}
            {word.is_saved && (
              <span className="block text-[11px] text-learner">saved</span>
            )}
          </span>
          <span aria-hidden="true" className="shrink-0 text-muted">
            &rsaquo;
          </span>
        </Link>
      </div>
    </li>
  )
}

function SpeakerIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="h-5 w-5"
    >
      <path d="M11 5 6 9H3v6h3l5 4V5Z" />
      <path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" />
    </svg>
  )
}
