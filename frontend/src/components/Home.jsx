import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { getTopics } from '../api'
import { TOPICS } from '../topics'

export default function Home() {
  // Seeded from the static list so the cards render immediately; the counts
  // fill in when the request lands. Avoids a spinner on the first screen.
  const [loads, setLoads] = useState(null)

  useEffect(() => {
    getTopics()
      .then(({ data }) => setLoads(data.topics))
      .catch(() => setLoads([])) // counts are a bonus, never a blocker
  }, [])

  const loadFor = (id) => loads?.find((topic) => topic.id === id)
  const totalDue = loads?.reduce((sum, topic) => sum + topic.due, 0) ?? 0

  return (
    <div className="mx-auto flex min-h-full max-w-md flex-col px-5 py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Charla</h1>
        <p className="mt-1 text-sm text-muted">
          Practise Spanish in conversation. What you get wrong comes back sooner.
        </p>
      </header>

      {loads !== null && (
        <p className="mb-5 text-sm">
          {totalDue > 0 ? (
            <>
              <span className="font-semibold text-right">{totalDue} words</span>
              <span className="text-muted"> ready to review today.</span>
            </>
          ) : (
            <span className="text-muted">
              Nothing due today — starting a topic introduces new words.
            </span>
          )}
        </p>
      )}

      <nav className="flex flex-col gap-3">
        {TOPICS.map((topic) => {
          const load = loadFor(topic.id)
          return (
            <Link
              key={topic.id}
              to={`/chat/${topic.id}`}
              className="group flex items-center justify-between gap-3 rounded-xl border
                         border-line px-4 py-4 transition hover:border-ink/25
                         hover:bg-surface focus:outline-none
                         focus-visible:ring-2 focus-visible:ring-learner"
            >
              <span className="min-w-0">
                <span className="block text-sm font-medium">{topic.label}</span>
                <span className="mt-0.5 block text-xs text-muted">{topic.blurb}</span>
                {load && <TopicLoad load={load} />}
              </span>
              <span
                aria-hidden="true"
                className="shrink-0 text-muted transition group-hover:translate-x-0.5
                           group-hover:text-ink"
              >
                &rarr;
              </span>
            </Link>
          )
        })}
      </nav>

      <p className="mt-8 text-xs leading-relaxed text-muted">
        Each session picks the words you are due to review, using spaced
        repetition, and works them into the conversation.
      </p>
    </div>
  )
}

function TopicLoad({ load }) {
  return (
    <span className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      {load.due > 0 && (
        <span className="font-medium text-right">{load.due} due</span>
      )}
      {load.new > 0 && <span className="text-muted">{load.new} new</span>}
      {load.scheduled > 0 && (
        <span className="text-muted">{load.scheduled} scheduled</span>
      )}
      {load.due === 0 && load.new === 0 && load.scheduled === 0 && (
        <span className="text-muted">no vocabulary seeded</span>
      )}
    </span>
  )
}
