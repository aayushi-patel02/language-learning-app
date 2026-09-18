import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

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

  // Set when the learner arrived from a word's own page, asking for that
  // word specifically. The backend echoes the word back so this screen can
  // name it, and so leaving goes back where they came from rather than home.
  const [searchParams] = useSearchParams()
  const focusWordId = searchParams.get('word')
  const [focusWord, setFocusWord] = useState(null)

  const leaveTo = focusWordId ? `/vocabulary/${focusWordId}` : '/'
  const recapPath = focusWordId
    ? `/recap/${sessionId}?word=${focusWordId}`
    : `/recap/${sessionId}`

  useEffect(() => {
    if (startedFor.current === topic) return
    startedFor.current = topic

    setStatus('loading')
    startSession(topic, focusWordId)
      .then(({ data }) => {
        setSessionId(data.session_id)
        setFocusWord(data.focus_word ?? null)
        setProgress({ answered: 0, limit: data.turn_limit })
        setMessages([
          { kind: 'tutor', text: data.turn.ai_message, en: data.turn.ai_message_en },
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

      // The verdict is a turn in the conversation, not a form below it, so it
      // goes into the transcript like anything else the tutor says.
      setMessages((prev) => [...prev, { kind: 'verdict', grade }])

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
    submit(option.text, () => sendChip(sessionId, option.id))

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
      { kind: 'tutor', text: pending.ai_message, en: pending.ai_message_en },
    ])
    setCurrent(pending)
    setPending(null)
    setStatus('ready')
  }

  if (status === 'loading') {
    return (
      <Shell topic={topicMeta} leaveTo={leaveTo}>
        <p className="py-16 text-center text-sm text-muted">Starting a lesson…</p>
      </Shell>
    )
  }

  if (status === 'error' && !sessionId) {
    return (
      <Shell topic={topicMeta} leaveTo={leaveTo}>
        <div className="rounded-xl border border-line bg-error-soft px-4 py-5">
          <p className="text-sm font-medium text-error">Could not start the lesson</p>
          <p className="mt-1 text-xs text-muted">{error}</p>
        </div>
        <Link
          to={leaveTo}
          className="mt-4 inline-flex min-h-11 items-center text-xs text-muted underline"
        >
          {focusWordId ? 'Back to the word' : 'Back to topics'}
        </Link>
      </Shell>
    )
  }

  return (
    <Shell topic={topicMeta} progress={progress} leaveTo={leaveTo}>
      {/* Says out loud why this lesson opened. Without it the screen is
          headed with the topic alone, so tapping "practise this word" on
          बिल and landing in Ordering Food reads as the app ignoring the
          request rather than answering it. */}
      {focusWord && (
        <div className="mb-3 flex items-baseline gap-2 rounded-2xl bg-learner-soft
                        px-3.5 py-2.5">
          <span className="text-[11px] font-bold tracking-wide text-learner uppercase">
            Starting with
          </span>
          <span className="min-w-0 flex-1 truncate text-sm font-bold">
            {focusWord.term}
          </span>
          <span className="shrink-0 truncate text-xs text-muted">
            {focusWord.english}
          </span>
        </div>
      )}

      {/* justify-end keeps a short conversation sitting above the controls
          instead of stranding two bubbles at the top of an empty screen. */}
      <div className="flex flex-1 flex-col justify-end space-y-2.5 pb-4">
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
        <button
          type="button"
          autoFocus
          onClick={advance}
          // One colour whatever the verdict was. The bubble directly above
          // already says whether the answer was right; recolouring the way
          // forward as well made the primary action change under the
          // learner turn by turn for no added information.
          className="btn min-h-12 w-full rounded-2xl bg-learner px-4 py-3 text-sm
                     font-extrabold tracking-wide text-white uppercase
                     hover:brightness-110"
        >
          {pending ? 'Continue' : 'Finish lesson'}
        </button>
      )}

      {status === 'done' && (
        <button
          type="button"
          onClick={() => navigate(recapPath)}
          className="btn min-h-12 w-full rounded-2xl bg-learner px-4 py-3 text-sm
                     font-extrabold tracking-wide text-white uppercase
                     hover:brightness-110"
        >
          See your results
        </button>
      )}

      {(status === 'ready' || status === 'sending') && (
        <Composer
          current={current}
          disabled={status !== 'ready'}
          typing={typing}
          draft={draft}
          setDraft={setDraft}
          onChip={answerChip}
          onSend={answerFreetext}
        />
      )}

      {/* One row, always in the same place. It lives outside the composer so
          "End lesson" survives the feedback state: the header's close button
          abandons the lesson, this one finishes it early and still shows the
          recap, which is a different intent. */}
      {status !== 'done' && (
        <div className="flex items-center justify-between">
          {status === 'feedback' ? (
            <span />
          ) : typing ? (
            <button
              type="button"
              onClick={() => setTyping(false)}
              className="inline-flex min-h-11 items-center pr-3 text-xs text-muted
                         underline"
            >
              Choose a reply instead
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setTyping(true)}
              disabled={status !== 'ready'}
              className="inline-flex min-h-11 items-center pr-3 text-xs text-muted
                         underline disabled:opacity-40"
            >
              Type your own instead
            </button>
          )}
          <button
            type="button"
            onClick={() => navigate(recapPath)}
            className="inline-flex min-h-11 items-center pl-3 text-xs text-muted
                       underline"
          >
            End lesson
          </button>
        </div>
      )}
    </Shell>
  )
}

function Shell({ topic, progress, leaveTo = '/', children }) {
  const done = progress?.answered ?? 0
  const total = progress?.limit ?? 0
  const percent = total ? Math.round((done / total) * 100) : 0

  return (
    <div className="app-column mx-auto flex min-h-full max-w-md flex-col px-5 pt-5 pb-28">
      <header className="mb-4 flex items-center gap-3">
        {/* Abandoning a lesson returns where it was opened from: the word's
            page when that is where the learner came from, otherwise home. */}
        <Link
          to={leaveTo}
          aria-label="Leave this lesson"
          className="-ml-1 inline-flex h-11 w-11 shrink-0 items-center justify-center
                     rounded-full text-muted transition-colors hover:bg-surface
                     hover:text-ink"
        >
          <CloseIcon />
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
              className="h-full rounded-full bg-learner transition-[width] duration-500
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
  if (message.kind === 'verdict') return <Verdict grade={message.grade} />

  if (message.kind === 'tutor') {
    return (
      <div className="animate-rise max-w-[85%] rounded-2xl rounded-tl-sm bg-tutor px-4 py-2.5">
        <p className="text-sm">{message.text}</p>
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

/** The tutor's reaction, rendered as its own turn in the conversation. */
function Verdict({ grade }) {
  const ungraded = !grade.graded
  const right = grade.was_correct

  const tone = ungraded
    ? 'bg-surface'
    : right
      ? 'bg-success-soft'
      : 'bg-error-soft'
  const accent = ungraded ? 'text-muted' : right ? 'text-success' : 'text-error'

  return (
    <div
      className={`animate-rise max-w-[90%] rounded-2xl rounded-tl-sm px-4 py-3 ${tone}`}
    >
      {/* English, whatever is being learned. A verdict is the one thing the
          learner must never be unsure of, and a beginner does not yet know
          the target language's word for "correct" - which is also why the
          reason and the schedule note below it are in English. */}
      <p className={`text-sm font-extrabold ${accent}`}>
        {ungraded ? 'Skipped' : right ? 'Correct' : 'Not quite'}
      </p>

      {/* corrected means two different things: for a typed answer it is
          that sentence fixed, for a tapped chip it is the option that was
          right - which can be a different sentence entirely. Labelling it
          stops it reading as a contradiction of the reason below. */}
      {grade.corrected && (
        <>
          <p className="mt-2 text-[11px] font-bold tracking-wide text-muted uppercase">
            Correct answer
          </p>
          <p className="text-sm font-bold">{grade.corrected}</p>
        </>
      )}
      {grade.feedback_en && (
        <p className="mt-1.5 text-xs text-muted">{grade.feedback_en}</p>
      )}
      {grade.due_date && (
        <p className="mt-2 text-xs text-muted">
          You&rsquo;ll see this word again {formatDue(grade.due_date)}.
        </p>
      )}
    </div>
  )
}

function Composer({ current, disabled, typing, draft, setDraft, onChip, onSend }) {
  const inputRef = useRef(null)

  /** Prefill up to the blank so the learner carries straight on typing. */
  const applyStarter = (starter) => {
    // Everything before the first run of underscores. Stripping the blanks
    // in place would leave the trailing punctuation stranded, e.g.
    // "Quisiera ____." becoming "Quisiera ." instead of "Quisiera ".
    const prefix = starter.split(/_+/)[0]
    setDraft(prefix)
    // Focus regardless: when the blank comes first the prefix is empty, and
    // the tap should still put the learner in the field.
    requestAnimationFrame(() => {
      const input = inputRef.current
      if (!input) return
      input.focus()
      input.setSelectionRange(prefix.length, prefix.length)
    })
  }

  if (typing) {
    return (
      <div className="mb-1">
        {current?.sentence_starter && (
          <button
            type="button"
            onClick={() => applyStarter(current.sentence_starter)}
            className="mb-2 w-full rounded-xl border border-line bg-white px-3 py-2
                       text-left transition-colors hover:border-ink/20"
          >
            <span className="block text-[11px] font-bold tracking-wide text-muted
                             uppercase">
              Try starting with
            </span>
            <span className="mt-0.5 block text-sm font-semibold">
              {current.sentence_starter}
            </span>
          </button>
        )}
        <div className="flex gap-2">
          <input
            ref={inputRef}
            autoFocus
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => event.key === 'Enter' && onSend()}
            // English, like every other piece of chrome in the app. This
            // used to be Spanish, which was a leftover from when Spanish was
            // the only language: a Hindi lesson asked for a reply under
            // "Escribe tu respuesta".
            placeholder="Type your answer…"
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
            className="btn min-h-11 rounded-xl bg-learner px-4 py-2 text-sm
                       font-bold text-white hover:brightness-110
                       disabled:opacity-40"
          >
            Send
          </button>
        </div>
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
          className="btn w-full rounded-2xl border border-line bg-white px-4 py-3
                     text-left transition-colors hover:border-learner
                     disabled:opacity-40 focus:outline-none focus-visible:ring-2
                     focus-visible:ring-learner"
        >
          <span className="block text-sm font-medium">{option.text}</span>
          {option.en && (
            <span className="mt-0.5 block text-xs text-muted">{option.en}</span>
          )}
        </button>
      ))}

    </div>
  )
}


// A stroked cross rather than the × character, which renders thin, sits
// slightly high in its box and reads as punctuation next to the progress bar.
function CloseIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.25"
      strokeLinecap="round"
      aria-hidden="true"
      className="h-5 w-5"
    >
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  )
}
