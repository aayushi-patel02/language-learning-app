import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { sendChip, sendFreetext, startSession } from '../api'
import { formatDue } from '../dates'
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
  // loading | ready | sending | feedback | done | error
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [typing, setTyping] = useState(false)
  const [draft, setDraft] = useState('')
  const [progress, setProgress] = useState({ answered: 0, limit: 0 })

  // The answer just graded, and the turn waiting behind the Continue button.
  // Holding the next turn back is deliberate: if it appears immediately the
  // learner scrolls straight past the correction, which is the part that
  // actually teaches.
  const [feedback, setFeedback] = useState(null)
  const [pending, setPending] = useState(null)

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

  const submit = async (label, request) => {
    if (status !== 'ready') return
    setStatus('sending')
    setError('')
    setMessages((prev) => [...prev, { kind: 'learner', text: label }])
    try {
      const { data } = await request()
      const grade = data.grade

      // Tag the learner's bubble so the transcript keeps a quiet record of
      // how each answer went.
      setMessages((prev) => {
        const next = [...prev]
        const last = next[next.length - 1]
        if (last?.kind === 'learner') {
          next[next.length - 1] = {
            ...last,
            graded: grade.graded,
            wasCorrect: grade.was_correct,
          }
        }
        return next
      })

      setProgress((prev) => ({ ...prev, answered: prev.answered + 1 }))
      setFeedback(grade)
      setPending(data.is_complete ? null : data.turn)
      setStatus('feedback')
    } catch (err) {
      setError(describeError(err))
      setStatus('ready') // let them retry the same turn
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

  const advance = () => {
    setFeedback(null)
    if (!pending) {
      setCurrent(null)
      setStatus('done')
      return
    }
    setMessages((prev) => [
      ...prev,
      { kind: 'tutor', es: pending.ai_message, en: pending.ai_message_en },
    ])
    setCurrent(pending)
    setPending(null)
    setStatus('ready')
  }

  if (status === 'loading') {
    return (
      <Shell topic={topicMeta}>
        <p className="py-16 text-center text-sm text-muted">Starting a lesson…</p>
      </Shell>
    )
  }

  if (status === 'error' && !sessionId) {
    return (
      <Shell topic={topicMeta}>
        <div className="rounded-xl border border-line bg-error-soft px-4 py-5">
          <p className="text-sm font-medium text-error">Could not start the lesson</p>
          <p className="mt-1 text-xs text-muted">{error}</p>
        </div>
        <Link
          to="/"
          className="mt-4 inline-flex min-h-11 items-center text-xs text-muted underline"
        >
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
        {status === 'sending' && <Thinking />}
        <div ref={bottomRef} />
      </div>

      {error && status === 'ready' && (
        <p className="mb-2 rounded-lg bg-error-soft px-3 py-2 text-xs text-error">
          {error} Try again.
        </p>
      )}

      {status === 'feedback' && feedback && (
        <FeedbackPanel
          feedback={feedback}
          isLast={!pending}
          onContinue={advance}
        />
      )}

      {status === 'done' && (
        <button
          type="button"
          onClick={() => navigate(`/recap/${sessionId}`)}
          className="min-h-12 w-full rounded-xl bg-ink px-4 py-3 text-sm font-semibold
                     text-white transition hover:opacity-90"
        >
          See your results
        </button>
      )}

      {(status === 'ready' || status === 'sending') && (
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
  const done = progress?.answered ?? 0
  const total = progress?.limit ?? 0
  const percent = total ? Math.round((done / total) * 100) : 0

  return (
    <div className="mx-auto flex min-h-full max-w-md flex-col px-5 py-5">
      <header className="mb-4 flex items-center gap-3">
        <Link
          to="/"
          aria-label="Leave this lesson"
          className="-ml-1 inline-flex min-h-11 min-w-11 items-center justify-center
                     text-lg text-muted transition hover:text-ink"
        >
          &times;
        </Link>
        {total > 0 ? (
          <div
            role="progressbar"
            aria-valuenow={done}
            aria-valuemin={0}
            aria-valuemax={total}
            aria-label={`${done} of ${total} answered`}
            className="h-3 flex-1 overflow-hidden rounded-full bg-line"
          >
            <div
              className="h-full rounded-full bg-success transition-[width] duration-500
                         ease-out"
              style={{ width: `${percent}%` }}
            />
          </div>
        ) : (
          <span className="flex-1 text-sm font-medium text-muted">
            {topic?.label ?? 'Practice'}
          </span>
        )}
        {total > 0 && (
          <span className="w-10 shrink-0 text-right text-xs tabular-nums text-muted">
            {done}/{total}
          </span>
        )}
      </header>
      <div className="flex flex-1 flex-col">{children}</div>
    </div>
  )
}

function Thinking() {
  return (
    <div className="flex w-fit gap-1 rounded-2xl rounded-tl-sm bg-tutor px-4 py-3">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  )
}

function Message({ message }) {
  if (message.kind === 'tutor') {
    return (
      <div className="animate-rise max-w-[85%] rounded-2xl rounded-tl-sm bg-tutor px-4 py-2.5">
        <p className="text-sm">{message.es}</p>
        {message.en && <p className="mt-1 text-xs text-muted">{message.en}</p>}
      </div>
    )
  }

  // A quiet record in the transcript; the loud version is the feedback panel.
  const edge =
    message.graded === false
      ? ''
      : message.wasCorrect
        ? 'ring-2 ring-success/40'
        : message.wasCorrect === false
          ? 'ring-2 ring-error/40'
          : ''

  return (
    <div
      className={`animate-rise ml-auto w-fit max-w-[85%] rounded-2xl rounded-tr-sm
                  bg-learner px-4 py-2.5 ${edge}`}
    >
      <p className="text-sm text-white">{message.text}</p>
    </div>
  )
}

function FeedbackPanel({ feedback, isLast, onContinue }) {
  const ungraded = !feedback.graded
  const right = feedback.was_correct

  const tone = ungraded
    ? 'bg-surface'
    : right
      ? 'bg-success-soft'
      : 'bg-error-soft'
  const accent = ungraded ? 'text-muted' : right ? 'text-success' : 'text-error'
  const button = ungraded ? 'bg-ink' : right ? 'bg-success' : 'bg-error'

  return (
    <div className={`animate-rise -mx-5 -mb-5 mt-3 px-5 pt-4 pb-5 ${tone}`}>
      <p className={`text-base font-bold ${accent}`}>
        {ungraded ? 'Skipped' : right ? '¡Correcto!' : 'Not quite'}
      </p>

      {feedback.corrected_es && (
        <p className="mt-1 text-sm font-medium">{feedback.corrected_es}</p>
      )}
      {feedback.feedback_en && (
        <p className="mt-1 text-xs text-muted">{feedback.feedback_en}</p>
      )}
      {feedback.due_date && (
        <p className="mt-2 text-xs text-muted">
          You&rsquo;ll see this word again {formatDue(feedback.due_date)}.
        </p>
      )}

      <button
        type="button"
        autoFocus
        onClick={onContinue}
        className={`mt-4 min-h-12 w-full rounded-xl px-4 py-3 text-sm font-semibold
                    text-white transition hover:opacity-90 ${button}`}
      >
        {isLast ? 'Finish lesson' : 'Continue'}
      </button>
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
            // text-base, not text-sm: iOS Safari zooms the whole page when a
            // focused input is under 16px, which throws off the layout mid-demo.
            className="min-h-11 flex-1 rounded-lg border border-line px-3 py-2 text-base
                       focus:border-learner focus:outline-none disabled:opacity-50"
          />
          <button
            type="button"
            onClick={onSend}
            disabled={disabled || !draft.trim()}
            className="min-h-11 rounded-lg bg-learner px-4 py-2 text-sm font-semibold
                       text-white transition hover:opacity-90 disabled:opacity-40"
          >
            Send
          </button>
        </div>
        <button
          type="button"
          onClick={() => setTyping(false)}
          className="mt-1 inline-flex min-h-11 items-center text-xs text-muted underline"
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
          className="w-full rounded-xl border-2 border-line px-3 py-3 text-left
                     transition active:scale-[0.99] hover:border-learner/50
                     hover:bg-surface disabled:opacity-40 focus:outline-none
                     focus-visible:ring-2 focus-visible:ring-learner"
        >
          <span className="block text-sm font-medium">{option.es}</span>
          {option.en && (
            <span className="mt-0.5 block text-xs text-muted">{option.en}</span>
          )}
        </button>
      ))}

      {/* min-h-11 (44px) on both: they are small text links, but they still
          have to be thumb-sized targets on a phone. */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setTyping(true)}
          disabled={disabled}
          className="inline-flex min-h-11 items-center pr-3 text-xs text-muted
                     underline disabled:opacity-40"
        >
          Type your own instead
        </button>
        <button
          type="button"
          onClick={onEnd}
          className="inline-flex min-h-11 items-center pl-3 text-xs text-muted underline"
        >
          End lesson
        </button>
      </div>
    </div>
  )
}
