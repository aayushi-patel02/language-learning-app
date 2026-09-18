import { useState } from 'react'

import TopicIcon from './TopicIcon'

// Three panels, because the one thing a newcomer cannot guess is *why* some
// words say "to review". Explaining the loop before the first lesson is what
// makes the home screen legible.
const STEPS = [
  {
    icon: 'bowl',
    tint: 'bg-topic-food-soft',
    accent: 'text-topic-food',
    title: 'Learn by talking',
    body: 'You practise inside a real conversation, ordering food or asking directions, instead of flipping flashcards.',
  },
  {
    icon: 'sun',
    tint: 'bg-topic-morning-soft',
    accent: 'text-topic-morning',
    title: 'Get it wrong, see it sooner',
    body: 'Every answer is graded. A word you miss comes back tomorrow. A word you know moves further away: 6 days, then 15, then a month.',
  },
  {
    icon: 'plane',
    tint: 'bg-topic-travel-soft',
    accent: 'text-topic-travel',
    title: 'Each lesson is chosen for you',
    body: 'Charla works out which words you are about to forget and builds the next conversation around them.',
  },
]

export default function Welcome({ onDone }) {
  const [step, setStep] = useState(0)
  const isLast = step === STEPS.length - 1
  const panel = STEPS[step]

  return (
    <div className="app-column mx-auto flex min-h-full max-w-md flex-col px-5 pt-10 pb-8">
      <header>
        <h1 className="text-3xl font-extrabold tracking-tight">Charla</h1>
        <p className="mt-1 text-sm text-muted">
          From first words to real conversations
        </p>
      </header>

      <div className="flex flex-1 flex-col justify-center py-8">
        <div key={step} className="animate-rise">
          <span
            className={`flex h-16 w-16 items-center justify-center rounded-2xl
                        ${panel.tint} ${panel.accent}`}
          >
            <TopicIcon name={panel.icon} className="h-8 w-8" />
          </span>
          <h2 className="mt-5 text-2xl font-extrabold tracking-tight">
            {panel.title}
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">{panel.body}</p>
        </div>
      </div>

      <div className="mb-5 flex items-center gap-1.5" aria-hidden="true">
        {STEPS.map((_, index) => (
          <span
            key={index}
            className={`h-1.5 rounded-full transition-all ${
              index === step ? 'w-6 bg-learner' : 'w-1.5 bg-line'
            }`}
          />
        ))}
      </div>

      <button
        type="button"
        onClick={() => (isLast ? onDone() : setStep(step + 1))}
        className="btn min-h-12 w-full rounded-2xl bg-learner px-4 py-3 text-sm
                   font-extrabold tracking-wide text-white uppercase
                   hover:brightness-110"
      >
        {isLast ? 'Start learning' : 'Next'}
      </button>

      <button
        type="button"
        onClick={onDone}
        className="mt-2 inline-flex min-h-11 items-center justify-center text-xs
                   text-muted underline"
      >
        Skip
      </button>
    </div>
  )
}
