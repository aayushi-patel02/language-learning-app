import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { getTopics } from '../api'
import { useAuth } from '../auth'
import { TOPICS } from '../topics'
import TopicIcon from './TopicIcon'

export default function Home() {
  const { user } = useAuth()
  // Null until the request lands, so the cards can render immediately and the
  // counts fill in. Avoids a spinner on the very first screen.
  const [loads, setLoads] = useState(null)

  useEffect(() => {
    getTopics()
      .then(({ data }) => setLoads(data.topics))
      .catch(() => setLoads([])) // counts are a bonus, never a blocker
  }, [])

  const loadFor = (id) => loads?.find((topic) => topic.id === id)
  const totalDue = loads?.reduce((sum, topic) => sum + topic.due, 0) ?? 0

  return (
    <div className="app-column mx-auto flex min-h-full max-w-md flex-col px-5 pt-10 pb-28">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight">Charla</h1>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">
            Practise {user?.learning_language ?? 'a new language'} in
            conversation. What you get wrong comes back sooner.
          </p>
        </div>
        <Link
          to="/profile"
          aria-label="Your profile"
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl
                     border border-line bg-white text-2xl transition-colors
                     hover:border-ink/20"
        >
          {user?.avatar ?? '🦉'}
        </Link>
      </header>

      {loads !== null && (
        <div
          className={`mt-6 rounded-2xl px-4 py-3.5 ${
            totalDue > 0 ? 'bg-success-soft' : 'bg-surface'
          }`}
        >
          {totalDue > 0 ? (
            <p className="text-sm">
              <span className="text-base font-extrabold text-success">
                {totalDue}
              </span>
              <span className="font-semibold text-success"> words</span>
              <span className="text-muted"> ready to review today</span>
            </p>
          ) : (
            <p className="text-sm text-muted">
              Nothing due today. Pick a topic to learn new words.
            </p>
          )}
        </div>
      )}

      <nav className="mt-4 flex flex-col gap-3">
        {TOPICS.map((topic) => (
          <Link
            key={topic.id}
            to={`/chat/${topic.id}`}
            className="group flex items-center gap-4 rounded-2xl border border-line
                       bg-white px-4 py-4 transition-colors hover:border-ink/20
                       focus:outline-none focus-visible:ring-2
                       focus-visible:ring-learner"
          >
            <span
              className={`flex h-12 w-12 shrink-0 items-center justify-center
                          rounded-xl ${topic.tint} ${topic.accent}`}
            >
              <TopicIcon name={topic.icon} className="h-6 w-6" />
            </span>

            <span className="min-w-0 flex-1">
              <span className="block text-base font-bold">{topic.label}</span>
              <span className="mt-0.5 block text-xs text-muted">{topic.blurb}</span>
              <TopicLoad load={loadFor(topic.id)} accent={topic.accent} />
            </span>

            <span
              aria-hidden="true"
              className="shrink-0 text-muted transition group-hover:translate-x-0.5
                         group-hover:text-ink"
            >
              &rsaquo;
            </span>
          </Link>
        ))}
      </nav>

      <p className="mt-7 text-xs leading-relaxed text-muted">
        Each lesson picks the words you are due to review, using spaced
        repetition, and works them into the conversation.
      </p>
    </div>
  )
}

function TopicLoad({ load, accent }) {
  // Only the two counts a learner can act on. Words that are known but not
  // yet due used to show as "scheduled", which named an internal state and
  // gave nothing to do about it.
  if (!load) return null

  if (load.total === 0) {
    return <span className="mt-1.5 block text-xs text-muted">no vocabulary yet</span>
  }

  if (load.due === 0 && load.new === 0) {
    return (
      <span className="mt-1.5 block text-xs font-semibold text-success">
        All caught up
      </span>
    )
  }

  return (
    <span className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
      {load.due > 0 && (
        <span
          className={`rounded-full bg-surface px-2 py-0.5 font-bold ${accent}`}
        >
          {load.due} to review
        </span>
      )}
      {load.new > 0 && (
        <span className="font-medium text-muted">{load.new} new</span>
      )}
    </span>
  )
}
