import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { getProgress } from '../api'
import { topicById } from '../topics'
import TopicIcon from './TopicIcon'

export default function Progress() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getProgress()
      .then((response) => setData(response.data))
      .catch(() => setError('Could not load your progress.'))
  }, [])

  return (
    <div className="app-column mx-auto flex min-h-full max-w-md flex-col px-5 pt-8 pb-12">
      <header className="mb-6 flex items-center gap-3">
        <Link
          to="/"
          aria-label="Back to topics"
          className="-ml-1 inline-flex min-h-11 min-w-11 items-center justify-center
                     text-lg text-muted transition hover:text-ink"
        >
          &lsaquo;
        </Link>
        <h1 className="text-2xl font-extrabold tracking-tight">Your progress</h1>
      </header>

      {error && (
        <p className="rounded-xl bg-error-soft px-3 py-2 text-sm text-error">{error}</p>
      )}

      {!data && !error && (
        <p className="py-16 text-center text-sm text-muted">Loading…</p>
      )}

      {data && <Body data={data} />}
    </div>
  )
}

function Body({ data }) {
  const accuracy =
    data.accuracy === null ? 'n/a' : `${Math.round(data.accuracy * 100)}%`

  if (data.words_started === 0) {
    return (
      <div className="rounded-2xl border border-line bg-white px-4 py-8 text-center">
        <p className="text-sm font-bold">Nothing to show yet</p>
        <p className="mt-1 text-xs text-muted">
          Finish a lesson and your progress will build up here.
        </p>
        <Link
          to="/"
          className="btn-3d mt-5 inline-flex min-h-12 items-center justify-center
                     rounded-2xl bg-learner px-5 py-3 text-sm font-extrabold
                     tracking-wide text-white uppercase hover:brightness-110"
        >
          Pick a topic
        </Link>
      </div>
    )
  }

  return (
    <>
      <div className="grid grid-cols-2 gap-3">
        <Stat
          value={data.words_started}
          suffix={`of ${data.vocabulary_total}`}
          label="Words started"
        />
        <Stat value={data.words_strong} label="Known well" tone="text-success" />
        <Stat value={accuracy} label="Accuracy all time" />
        <Stat value={data.lessons_completed} label="Lessons finished" />
      </div>

      <p className="mt-4 text-xs leading-relaxed text-muted">
        A word counts as known well once you have recalled it correctly three
        times in a row, the point where its review gap has grown past a
        fortnight.
      </p>

      <h2 className="mt-8 text-xs font-bold tracking-wide text-muted uppercase">
        By topic
      </h2>

      <ul className="mt-3 flex flex-col gap-3">
        {data.topics.map((topic) => (
          <TopicRow key={topic.id} topic={topic} />
        ))}
      </ul>

      <div className="mt-6 rounded-2xl bg-surface px-4 py-3.5">
        <p className="text-xs text-muted">
          <span className="font-bold text-ink">{data.total_reviews}</span> answers
          graded so far
          {data.total_lapses > 0 && (
            <>
              , <span className="font-bold text-ink">{data.total_lapses}</span> of
              them words you had known and forgotten
            </>
          )}
          .
        </p>
      </div>

      <Link
        to="/"
        className="btn-3d mt-8 flex min-h-12 items-center justify-center rounded-2xl
                   border-2 border-line bg-white px-4 py-3 text-sm font-extrabold
                   tracking-wide uppercase hover:bg-surface"
      >
        Back to topics
      </Link>
    </>
  )
}

function Stat({ value, suffix, label, tone = '' }) {
  return (
    <div className="rounded-2xl border border-line bg-white px-4 py-3.5">
      <p className={`text-2xl font-extrabold tabular-nums ${tone}`}>
        {value}
        {suffix && (
          <span className="ml-1 text-xs font-semibold text-muted">{suffix}</span>
        )}
      </p>
      <p className="mt-0.5 text-xs text-muted">{label}</p>
    </div>
  )
}

function TopicRow({ topic }) {
  const meta = topicById(topic.id)
  const percent = topic.total ? Math.round((topic.started / topic.total) * 100) : 0
  const strongPercent = topic.total
    ? Math.round((topic.strong / topic.total) * 100)
    : 0

  return (
    <li className="rounded-2xl border border-line bg-white px-4 py-3.5">
      <div className="flex items-center gap-3">
        <span
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg
                      ${meta?.tint ?? 'bg-surface'} ${meta?.accent ?? ''}`}
        >
          <TopicIcon name={meta?.icon} className="h-4.5 w-4.5" />
        </span>
        <span className="flex-1 text-sm font-bold">{topic.label}</span>
        <span className="text-xs tabular-nums text-muted">
          {topic.started}/{topic.total}
        </span>
      </div>

      {/* Two bands in one track: everything started, and the subset known
          well. Reading the gap between them is the point. */}
      <div className="relative mt-2.5 h-2 overflow-hidden rounded-full bg-line">
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-learner/30"
          style={{ width: `${percent}%` }}
        />
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-success"
          style={{ width: `${strongPercent}%` }}
        />
      </div>
      <p className="mt-1.5 text-xs text-muted">
        {topic.strong} known well
        {topic.started > topic.strong &&
          `, ${topic.started - topic.strong} still settling`}
      </p>
    </li>
  )
}
