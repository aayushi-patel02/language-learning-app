import { Link } from 'react-router-dom'

import { TOPICS } from '../topics'

export default function Home() {
  return (
    <div className="mx-auto flex min-h-full max-w-md flex-col px-5 py-10">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Charla</h1>
        <p className="mt-1 text-sm text-muted">
          Practise Spanish in conversation. What you get wrong comes back sooner.
        </p>
      </header>

      <nav className="flex flex-col gap-3">
        {TOPICS.map((topic) => (
          <Link
            key={topic.id}
            to={`/chat/${topic.id}`}
            className="group flex items-center justify-between rounded-xl border border-line
                       px-4 py-4 transition hover:border-ink/25 hover:bg-surface
                       focus:outline-none focus-visible:ring-2 focus-visible:ring-learner"
          >
            <span>
              <span className="block text-sm font-medium">{topic.label}</span>
              <span className="mt-0.5 block text-xs text-muted">{topic.blurb}</span>
            </span>
            <span
              aria-hidden="true"
              className="text-muted transition group-hover:translate-x-0.5 group-hover:text-ink"
            >
              &rarr;
            </span>
          </Link>
        ))}
      </nav>

      <p className="mt-8 text-xs leading-relaxed text-muted">
        Each session picks the words you are due to review, using spaced
        repetition, and works them into the conversation.
      </p>
    </div>
  )
}
