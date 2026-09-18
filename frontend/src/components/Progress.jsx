import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { getProgress } from '../api'
import { topicById } from '../topics'
import Chevron from './Chevron'
import TopicIcon from './TopicIcon'

function formatMinutes(seconds) {
  if (!seconds) return '0 min'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours}h ${rest}m` : `${hours}h`
}

function percent(value) {
  return value === null || value === undefined
    ? null
    : Math.round(value * 100)
}

export default function Progress() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getProgress()
      .then((response) => setData(response.data))
      .catch(() => setError('Could not load your progress.'))
  }, [])

  return (
    <div className="app-column mx-auto flex min-h-full max-w-md flex-col px-5 pt-8 pb-28">
      <header className="mb-6 flex items-center gap-3">
        <Link
          to="/"
          aria-label="Back to topics"
          className="-ml-1 inline-flex min-h-11 min-w-11 items-center justify-center
                     text-lg text-muted transition hover:text-ink"
        >
          <Chevron direction="left" className="h-6 w-6" />
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

  const thisWeek = percent(data.accuracy_this_week)
  const lastWeek = percent(data.accuracy_last_week)
  const change = thisWeek !== null && lastWeek !== null ? thisWeek - lastWeek : null

  return (
    <>
      <Streak days={data.streak_days} practisedToday={data.practised_today} />

      <h2 className="mt-7 text-xs font-bold tracking-wide text-muted uppercase">
        This week
      </h2>
      <div className="mt-2.5 grid grid-cols-3 gap-2.5">
        <Stat value={formatMinutes(data.practice_seconds_this_week)} label="Practised" />
        <Stat value={data.answers_this_week} label="Answers" />
        <Stat
          value={thisWeek === null ? 'n/a' : `${thisWeek}%`}
          label="Accuracy"
          tone={change !== null && change > 0 ? 'text-success' : ''}
        />
      </div>
      {change !== null && (
        <p className="mt-2 text-xs text-muted">
          {change > 0
            ? `Up ${change} points on last week.`
            : change < 0
              ? `Down ${Math.abs(change)} points on last week.`
              : 'Level with last week.'}
        </p>
      )}

      <Calendar days={data.calendar} />

      <h2 className="mt-7 text-xs font-bold tracking-wide text-muted uppercase">
        All time
      </h2>
      <div className="mt-2.5 grid grid-cols-2 gap-2.5">
        <Stat
          value={data.words_started}
          suffix={`of ${data.vocabulary_total}`}
          label="Words started"
        />
        <Stat value={data.words_strong} label="Known well" tone="text-success" />
        <Stat
          value={percent(data.accuracy) === null ? 'n/a' : `${percent(data.accuracy)}%`}
          label="Accuracy"
        />
        <Stat value={data.lessons_completed} label="Conversations" />
      </div>
      <p className="mt-2.5 text-xs leading-relaxed text-muted">
        A word counts as known well once you have recalled it correctly three
        times in a row, the point where its review gap has grown past a
        fortnight.
      </p>

      {data.grammar.length > 0 && (
        <>
          <h2 className="mt-7 text-xs font-bold tracking-wide text-muted uppercase">
            Grammar
          </h2>
          <ul className="mt-2.5 flex flex-col gap-2">
            {data.grammar.map((area) => (
              <li
                key={area.area}
                className="flex items-center gap-3 rounded-2xl border border-line
                           bg-white px-4 py-3"
              >
                <span className="min-w-0 flex-1 text-sm font-bold">{area.area}</span>
                <span className="shrink-0 text-xs tabular-nums text-muted">
                  {area.errors} {area.errors === 1 ? 'slip' : 'slips'}
                </span>
                <Trend trend={area.trend} />
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs leading-relaxed text-muted">
            Grouped from the corrections you were given. An area needs at least
            three slips before it is given a direction.
          </p>
        </>
      )}

      {data.hardest_words.length > 0 && (
        <>
          <h2 className="mt-7 text-xs font-bold tracking-wide text-muted uppercase">
            Giving you trouble
          </h2>
          <ul className="mt-2.5 flex flex-col gap-2">
            {data.hardest_words.map((word) => (
              <li key={word.id}>
                <Link
                  to={`/vocabulary/${word.id}`}
                  className="flex items-center gap-3 rounded-2xl border border-line
                             bg-white px-4 py-3 transition-colors hover:border-ink/20"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-bold">
                      {word.term}
                    </span>
                    <span className="block truncate text-xs text-muted">
                      {word.english}
                    </span>
                  </span>
                  <span className="shrink-0 text-right text-xs text-muted">
                    {word.lapses > 0 && (
                      <span className="block">
                        forgotten {word.lapses}
                        {word.lapses === 1 ? ' time' : ' times'}
                      </span>
                    )}
                    {word.accuracy !== null && (
                      <span className="block">{Math.round(word.accuracy * 100)}% right</span>
                    )}
                  </span>
                  <span className="shrink-0 text-muted">
                    <Chevron className="h-[18px] w-[18px]" />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}

      <h2 className="mt-7 text-xs font-bold tracking-wide text-muted uppercase">
        By topic
      </h2>
      <ul className="mt-2.5 flex flex-col gap-2.5">
        {data.topics.map((topic) => (
          <TopicRow key={topic.id} topic={topic} />
        ))}
      </ul>

      <Link
        to="/vocabulary"
        className="btn-3d mt-8 flex min-h-12 items-center justify-center rounded-2xl
                   border-2 border-line bg-white px-4 py-3 text-sm font-extrabold
                   tracking-wide uppercase hover:bg-surface"
      >
        Browse all words
      </Link>
    </>
  )
}

function Streak({ days, practisedToday }) {
  return (
    <div
      className={`rounded-2xl px-4 py-4 ${
        days > 0 ? 'bg-topic-morning-soft' : 'bg-surface'
      }`}
    >
      <div className="flex items-baseline gap-2">
        <span
          className={`text-3xl font-extrabold tabular-nums ${
            days > 0 ? 'text-topic-morning' : 'text-muted'
          }`}
        >
          {days}
        </span>
        <span className="text-sm font-bold">
          {days === 1 ? 'day streak' : 'day streak'}
        </span>
      </div>
      <p className="mt-1 text-xs text-muted">
        {days === 0
          ? 'Practise today to start a streak.'
          : practisedToday
            ? 'Practised today. Come back tomorrow to keep it going.'
            : 'Practise today to keep your streak alive.'}
      </p>
    </div>
  )
}

function Calendar({ days }) {
  // Four weeks of squares. Intensity rather than exact counts: the useful
  // reading is "did I practise", not "how many answers exactly".
  const level = (answers) => {
    if (!answers) return 'bg-line'
    if (answers < 5) return 'bg-success/30'
    if (answers < 12) return 'bg-success/60'
    return 'bg-success'
  }

  return (
    <>
      <h2 className="mt-7 text-xs font-bold tracking-wide text-muted uppercase">
        Last four weeks
      </h2>
      <div className="mt-2.5 grid grid-cols-7 gap-1.5">
        {days.map((day) => (
          <div
            key={day.date}
            title={`${day.date}: ${day.answers} answers`}
            className={`aspect-square rounded-md ${level(day.answers)}`}
          />
        ))}
      </div>
    </>
  )
}

function Trend({ trend }) {
  const style = {
    improving: 'bg-success-soft text-success',
    'needs work': 'bg-error-soft text-error',
    steady: 'bg-surface text-muted',
    watching: 'bg-surface text-muted',
  }[trend]

  return (
    <span
      className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold ${style}`}
    >
      {trend}
    </span>
  )
}

function Stat({ value, suffix, label, tone = '' }) {
  return (
    <div className="rounded-2xl border border-line bg-white px-3.5 py-3">
      <p className={`text-xl font-extrabold tabular-nums ${tone}`}>
        {value}
        {suffix && (
          <span className="ml-1 text-xs font-semibold text-muted">{suffix}</span>
        )}
      </p>
      <p className="mt-0.5 text-[11px] text-muted">{label}</p>
    </div>
  )
}

function TopicRow({ topic }) {
  const meta = topicById(topic.id)
  const started = topic.total ? Math.round((topic.started / topic.total) * 100) : 0
  const strong = topic.total ? Math.round((topic.strong / topic.total) * 100) : 0

  return (
    <li className="rounded-2xl border border-line bg-white px-4 py-3.5">
      <div className="flex items-center gap-3">
        <span
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg
                      ${meta?.tint ?? 'bg-surface'} ${meta?.accent ?? ''}`}
        >
          <TopicIcon name={meta?.icon} className="h-4 w-4" />
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
          style={{ width: `${started}%` }}
        />
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-success"
          style={{ width: `${strong}%` }}
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
