import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { sendChip, sendFreetext, startSession } from '../api'
import { topicById } from '../topics'

function describeError(err) {
  const detail = err?.response?.data?.detail
  if (detail) return detail
  if (err?.response) return `The server returned ${err.response.status}.`
  return 'Could not reach the server. Is the Django backend running?'
}

export default function Chat({ topic }) {
  const navigate = useNavigate()
  const topicMeta = topicById(topic)

  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [current, setCurrent] = useState(null)
  // loading | ready | sending | done | error
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [typing, setTyping] = useState(false)
  const [draft, setDraft] = useState('')
  const [progress, setProgress] = useState({ answered: 0, limit: 0 })

  const bottomRef = useRef(null)
  // StrictMode runs effects twice in development. Without this guard every
  // page load would open two sessions and burn two LLM calls.
  const startedFor = useRef(null)

  useEffect(() => {
    if (startedFor.current === topic) return
    startedFor.current = topic

    setStatus('loading')
    startSession(topic)
      .then(({ data }) => {
        setSessionId(data.session_id)
        setProgress({ answered: 0, limit: data.turn_limit })
        setMessages([
          { kind: 'tutor', es: data.turn.ai_message, en: data.turn.ai_message_en },
        ])
        setCurrent(data.turn)
        setStatus('ready')
      })
      .catch((err) => {
        setError(describeError(err))
        setStatus('error')
      })
  }, [topic])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, status])

  const applyResult = (data) => {
    const grade = data.grade
    setMessages((prev) => [
      ...prev,
      {
        kind: 'feedback',
        graded: grade.graded,
        wasCorrect: grade.was_correct,
        feedbackEn: grade.feedback_en,
        correctedEs: grade.corrected_es,
        dueDate: grade.due_date,
        intervalDays: grade.interval_days,
      },
    ])
    setProgress((prev) => ({ ...prev, answered: prev.answered + 1 }))

    if (data.is_complete || !data.turn) {
      setCurrent(null)
      setStatus('done')
      return
    }
    setMessages((prev) => [
      ...prev,
      { kind: 'tutor', es: data.turn.ai_message, en: data.turn.ai_message_en },
    ])
    setCurrent(data.turn)
    setStatus('ready')
  }

  const submit = async (label, request) => {
    if (status !== 'ready') return
    setStatus('sending')
    setError('')
    setMessages((prev) => [...prev, { kind: 'learner', text: label }])
    try {
      const { data } = await request()
      applyResult(data)
    } catch (err) {
      setError(describeError(err))
      setStatus('ready') // let them try the same turn again
    }
  }

  const answerChip = (option) =>
    submit(option.es, () => sendChip(sessionId, option.id))

  const answerFreetext = () => {
    const text = draft.trim()
    if (!text) return
    setDraft('')
    setTyping(false)
    return submit(text, () => sendFreetext(sessionId, text))
  }

  if (status === 'loading') {
    return (
      <Shell topic={topicMeta}>
        <p className="py-16 text-center text-sm text-muted">Starting a session…</p>
      </Shell>
    )
  }

  if (status === 'error' && !sessionId) {
    return (
      <Shell topic={topicMeta}>
        <div className="rounded-xl border border-line bg-wrong-soft px-4 py-5">
          <p className="text-sm font-medium text-wrong">Could not start the session</p>
          <p className="mt-1 text-xs text-muted">{error}</p>
        </div>
        <Link to="/" className="mt-4 inline-block text-xs text-muted underline">
          Back to topics
        </Link>
      </Shell>
    )
  }

  return (
    <Shell topic={topicMeta} progress={progress}>
      <div className="flex-1 space-y-3 pb-4">
        {messages.map((message, index) => (
          <Message key={index} message={message} />
        ))}
        {status === 'sending' && (
          <p className="pl-1 text-xs text-muted">…</p>
        )}
        <div ref={bottomRef} />
      </div>

      {error && status === 'ready' && (
        <p className="mb-2 rounded-lg bg-wrong-soft px-3 py-2 text-xs text-wrong">
          {error} Try again.
        </p>
      )}

      {status === 'done' ? (
        <button
          type="button"
          onClick={() => navigate(`/recap/${sessionId}`)}
          className="w-full rounded-xl bg-ink px-4 py-3 text-sm font-medium text-white
                     transition hover:opacity-90"
        >
          See your recap
        </button>
      ) : (
        <Composer
          current={current}
          disabled={status !== 'ready'}
          typing={typing}
          setTyping={setTyping}
          draft={draft}
          setDraft={setDraft}
          onChip={answerChip}
          onSend={answerFreetext}
          onEnd={() => navigate(`/recap/${sessionId}`)}
        />
      )}
    </Shell>
  )
}

function Shell({ topic, progress, children }) {
  return (
    <div className="mx-auto flex min-h-full max-w-md flex-col px-5 py-6">
      <header className="mb-5 flex items-baseline justify-between">
        <Link to="/" className="text-sm text-muted hover:text-ink">
          &larr; <span className="font-medium">{topic?.label ?? 'Practice'}</span>
        </Link>
        {progress?.limit > 0 && (
          <span className="text-xs text-muted">
            {Math.min(progress.answered + 1, progress.limit)} / {progress.limit}
          </span>
        )}
      </header>
      <div className="flex flex-1 flex-col">{children}</div>
    </div>
  )
}

function Message({ message }) {
  if (message.kind === 'tutor') {
    return (
      <div className="max-w-[85%] rounded-2xl rounded-tl-sm bg-tutor px-4 py-2.5">
        <p className="text-sm">{message.es}</p>
        {message.en && (
          <p className="mt-1 text-xs text-muted">{message.en}</p>
        )}
      </div>
    )
  }

  if (message.kind === 'learner') {
    return (
      <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-tr-sm bg-learner px-4 py-2.5">
        <p className="text-sm text-white">{message.text}</p>
      </div>
    )
  }

  // feedback
  if (!message.graded) {
    return (
      <p className="ml-auto w-fit max-w-[85%] text-right text-xs text-muted">
        {message.feedbackEn}
      </p>
    )
  }

  const tone = message.wasCorrect
    ? 'bg-right-soft text-right'
    : 'bg-wrong-soft text-wrong'

  return (
    <div className={`ml-auto w-fit max-w-[85%] rounded-lg px-3 py-2 text-right ${tone}`}>
      <p className="text-xs font-medium">
        {message.wasCorrect ? 'Correct' : 'Not quite'}
      </p>
      {message.feedbackEn && (
        <p className="mt-0.5 text-xs opacity-90">{message.feedbackEn}</p>
      )}
      {message.correctedEs && (
        <p className="mt-1 text-xs font-medium">{message.correctedEs}</p>
      )}
      {message.dueDate && (
        <p className="mt-1 text-[11px] text-muted">
          Next review {message.dueDate}
        </p>
      )}
    </div>
  )
}

function Composer({
  current,
  disabled,
  typing,
  setTyping,
  draft,
  setDraft,
  onChip,
  onSend,
  onEnd,
}) {
  if (typing) {
    return (
      <div>
        <div className="flex gap-2">
          <input
            autoFocus
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => event.key === 'Enter' && onSend()}
            placeholder="Escribe tu respuesta…"
            disabled={disabled}
            className="flex-1 rounded-lg border border-line px-3 py-2 text-sm
                       focus:border-learner focus:outline-none disabled:opacity-50"
          />
          <button
            type="button"
            onClick={onSend}
            disabled={disabled || !draft.trim()}
            className="rounded-lg bg-learner px-4 py-2 text-sm font-medium text-white
                       transition hover:opacity-90 disabled:opacity-40"
          >
            Send
          </button>
        </div>
        <button
          type="button"
          onClick={() => setTyping(false)}
          className="mt-2 text-xs text-muted underline"
        >
          Choose a reply instead
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {(current?.reply_options ?? []).map((option) => (
        <button
          key={option.id}
          type="button"
          onClick={() => onChip(option)}
          disabled={disabled}
          className="w-full rounded-lg border border-line px-3 py-2.5 text-left transition
                     hover:border-ink/25 hover:bg-surface disabled:opacity-40
                     focus:outline-none focus-visible:ring-2 focus-visible:ring-learner"
        >
          <span className="block text-sm">{option.es}</span>
          {option.en && (
            <span className="mt-0.5 block text-xs text-muted">{option.en}</span>
          )}
        </button>
      ))}

      <div className="flex items-center justify-between pt-1">
        <button
          type="button"
          onClick={() => setTyping(true)}
          disabled={disabled}
          className="text-xs text-muted underline disabled:opacity-40"
        >
          Type your own instead
        </button>
        <button type="button" onClick={onEnd} className="text-xs text-muted underline">
          End session
        </button>
      </div>
    </div>
  )
}
