import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { getWord, setWordSaved } from '../api'
import { formatDue } from '../dates'
import { canSpeak, speak } from '../speech'
import Chevron from './Chevron'

const SHELF_LABEL = {
  due: 'Ready to review',
  learning: 'Learning',
  mastered: 'Mastered',
  new: 'Not started yet',
}

export default function WordDetail() {
  const { wordId } = useParams()
  const navigate = useNavigate()
  const [word, setWord] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getWord(wordId)
      .then((response) => setWord(response.data))
      .catch(() => setError('Could not load this word.'))
  }, [wordId])

  const toggleSaved = () => {
    if (!word) return
    const next = !word.is_saved
    // Optimistic: the bookmark should feel instant, and a failed request
    // simply puts it back.
    setWord({ ...word, is_saved: next })
    setWordSaved(word.id, next).catch(() =>
      setWord((prev) => (prev ? { ...prev, is_saved: !next } : prev)),
    )
  }

  if (error) {
    return (
      <Shell onBack={() => navigate(-1)}>
        <p className="rounded-xl bg-error-soft px-3 py-2 text-sm text-error">{error}</p>
      </Shell>
    )
  }

  if (!word) {
    return (
      <Shell onBack={() => navigate(-1)}>
        <p className="py-16 text-center text-sm text-muted">Loading…</p>
      </Shell>
    )
  }

  return (
    <Shell onBack={() => navigate(-1)} saved={word.is_saved} onSave={toggleSaved}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-3xl font-extrabold tracking-tight break-words">
            {word.term}
          </h1>
          {word.romanisation && (
            <p className="mt-1 text-base text-muted italic">{word.romanisation}</p>
          )}
          <p className="mt-1 text-base text-muted">{word.english}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-full bg-surface px-2 py-0.5 font-bold text-muted">
              {word.topic_label}
            </span>
            {word.part_of_speech && (
              <span className="text-muted">{word.part_of_speech}</span>
            )}
          </div>
        </div>
        {canSpeak() && (
          <button
            type="button"
            aria-label={`Hear ${word.term}`}
            onClick={() => speak(word.term, word.language)}
            className="btn-3d inline-flex min-h-12 min-w-12 shrink-0 items-center
                       justify-center rounded-2xl bg-learner text-white
                       hover:brightness-110"
          >
            <SpeakerIcon />
          </button>
        )}
      </div>

      {word.example && (
        <div className="mt-6 rounded-2xl border border-line bg-white px-4 py-3.5">
          <p className="text-[11px] font-bold tracking-wide text-muted uppercase">
            In a sentence
          </p>
          <div className="mt-1.5 flex items-start gap-2">
            <p className="flex-1 text-sm font-semibold">{word.example}</p>
            {canSpeak() && (
              <button
                type="button"
                aria-label="Hear the example sentence"
                onClick={() => speak(word.example, word.language)}
                className="inline-flex min-h-11 min-w-11 shrink-0 items-center
                           justify-center rounded-xl text-muted transition
                           hover:bg-surface hover:text-ink"
              >
                <SpeakerIcon small />
              </button>
            )}
          </div>
          <p className="mt-0.5 text-xs text-muted">{word.example_en}</p>
        </div>
      )}

      <h2 className="mt-7 text-xs font-bold tracking-wide text-muted uppercase">
        Your schedule
      </h2>
      <div className="mt-2.5 grid grid-cols-2 gap-2.5">
        <Fact
          value={SHELF_LABEL[word.shelf] ?? word.shelf}
          label="Mastery level"
          tone={word.shelf === 'mastered' ? 'text-success' : ''}
        />
        <Fact
          value={word.due_date ? formatDue(word.due_date) : 'not scheduled'}
          label="Next review"
        />
        <Fact
          value={word.repetitions === 0 ? 'none' : `${word.repetitions} in a row`}
          label="Correct streak"
        />
        <Fact
          value={
            word.accuracy === null
              ? 'n/a'
              : `${Math.round(word.accuracy * 100)}%`
          }
          label={`Accuracy over ${word.total_reviews} ${
            word.total_reviews === 1 ? 'try' : 'tries'
          }`}
        />
      </div>

      {word.lapses > 0 && (
        <p className="mt-2.5 text-xs text-muted">
          You have known and then forgotten this word {word.lapses}{' '}
          {word.lapses === 1 ? 'time' : 'times'}, which is why it comes back
          sooner than the rest.
        </p>
      )}

      {/* Named here rather than on the recap: this is the screen someone
          opens when they want to know why a date is what it is, and the
          numbers it explains are right above it. */}
      <p className="mt-2.5 text-xs leading-relaxed text-muted">
        These dates come from SM-2, a spaced repetition algorithm. Each
        correct answer multiplies the gap before you see this word again;
        getting it wrong sends the gap back to one day.
      </p>

      <h2 className="mt-7 text-xs font-bold tracking-wide text-muted uppercase">
        Where you met it
      </h2>
      {word.appearances.length === 0 ? (
        <p className="mt-2.5 rounded-2xl border border-line bg-white px-4 py-6
                      text-center text-sm text-muted">
          You have not practised this word in a conversation yet.
        </p>
      ) : (
        <ul className="mt-2.5 flex flex-col gap-2.5">
          {word.appearances.map((turn, index) => (
            <li
              key={index}
              className="rounded-2xl border border-line bg-white px-4 py-3.5"
            >
              <p className="text-sm">{turn.tutor_message}</p>
              {turn.tutor_message_en && (
                <p className="mt-0.5 text-xs text-muted">{turn.tutor_message_en}</p>
              )}
              {turn.user_reply && (
                <p
                  className={`mt-2.5 rounded-xl px-3 py-2 text-sm ${
                    turn.was_correct
                      ? 'bg-success-soft text-ink'
                      : 'bg-error-soft text-ink'
                  }`}
                >
                  <span className="mr-1.5 text-[11px] font-bold tracking-wide uppercase">
                    {turn.was_correct === null
                      ? 'You said'
                      : turn.was_correct
                        ? 'You got it'
                        : 'You missed it'}
                  </span>
                  <br />
                  {turn.user_reply}
                </p>
              )}
              {turn.feedback_en && (
                <p className="mt-1.5 text-xs text-muted">{turn.feedback_en}</p>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* Carries the word id, so the lesson opens on this word rather than
          wherever the scheduler would have reached on its own. A hard word
          sorts behind every easier one, so without this the learner could
          never get to the word they just asked for. */}
      <Link
        to={`/chat/${word.topic}?word=${word.id}`}
        className="btn-3d mt-8 flex min-h-12 items-center justify-center rounded-2xl
                   bg-learner px-4 py-3 text-sm font-extrabold tracking-wide
                   text-white uppercase hover:brightness-110"
      >
        Practise this word
      </Link>
    </Shell>
  )
}

function Shell({ onBack, saved, onSave, children }) {
  return (
    <div className="app-column mx-auto min-h-full max-w-md px-5 pt-8 pb-28">
      <header className="mb-5 flex items-center justify-between">
        <button
          type="button"
          onClick={onBack}
          aria-label="Back"
          className="-ml-1 inline-flex min-h-11 min-w-11 items-center justify-center
                     text-lg text-muted transition hover:text-ink"
        >
          <Chevron direction="left" className="h-6 w-6" />
        </button>
        {onSave && (
          <button
            type="button"
            onClick={onSave}
            aria-pressed={saved}
            className={`inline-flex min-h-11 items-center gap-1.5 rounded-full border
                        px-3 text-xs font-bold transition-colors ${
                          saved
                            ? 'border-learner bg-learner text-white'
                            : 'border-line bg-white text-muted hover:border-ink/20'
                        }`}
          >
            <BookmarkIcon filled={saved} />
            {saved ? 'Saved' : 'Save'}
          </button>
        )}
      </header>
      {children}
    </div>
  )
}

function Fact({ value, label, tone = '' }) {
  return (
    <div className="rounded-2xl border border-line bg-white px-3.5 py-3">
      <p className={`text-sm font-extrabold ${tone}`}>{value}</p>
      <p className="mt-0.5 text-[11px] text-muted">{label}</p>
    </div>
  )
}

function SpeakerIcon({ small }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={small ? 'h-5 w-5' : 'h-6 w-6'}
    >
      <path d="M11 5 6 9H3v6h3l5 4V5Z" />
      <path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" />
    </svg>
  )
}

function BookmarkIcon({ filled }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="h-4 w-4"
    >
      {/* Rounded corners and a shallower notch. The old path was a bare
          rectangle with a deep V cut out of it, which at 14px read as an
          arrow pointing down rather than a bookmark. */}
      <path
        d="M6.75 3.75h10.5a.9.9 0 0 1 .9.9v14.9a.7.7 0 0 1-1.11.57L12 16.4
           l-5.04 3.72a.7.7 0 0 1-1.11-.57V4.65a.9.9 0 0 1 .9-.9Z"
      />
    </svg>
  )
}
