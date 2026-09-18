import { useEffect, useRef, useState } from 'react'

import { getLanguages, updateMe } from '../api'
import { useAuth } from '../auth'
import Chevron from './Chevron'

/** Switch what you are learning without going to the profile screen.
 *
 * The list comes from /api/languages/ rather than a constant here, so it can
 * only ever offer a language that has vocabulary seeded behind it.
 */
export default function LanguagePicker() {
  const { user, setUser } = useAuth()
  const [languages, setLanguages] = useState([])
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const box = useRef(null)

  useEffect(() => {
    getLanguages()
      .then(({ data }) => setLanguages(data.languages))
      .catch(() => setLanguages([]))
  }, [])

  // A menu that only closes by choosing something is a trap, so a click
  // anywhere else and the escape key both dismiss it.
  useEffect(() => {
    if (!open) return undefined

    const onPointerDown = (event) => {
      if (!box.current?.contains(event.target)) setOpen(false)
    }
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const current = user?.learning_language

  const choose = async (code) => {
    if (code === current) {
      setOpen(false)
      return
    }
    setBusy(true)
    try {
      const { data } = await updateMe({ learning_language: code })
      // Updating the shared user is what makes the rest of the screen
      // refetch: the topic counts are keyed on the language.
      setUser(data)
      setOpen(false)
    } catch {
      // Leaving the menu open with the old language still selected is a
      // truthful failure; a silent close would look like it had worked.
    } finally {
      setBusy(false)
    }
  }

  if (!current) return null

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        onClick={() => setOpen((was) => !was)}
        disabled={busy}
        aria-expanded={open}
        aria-haspopup="listbox"
        className="inline-flex min-h-11 items-center gap-2 rounded-full border
                   border-line bg-white py-1.5 pr-3 pl-3.5 transition-colors
                   hover:border-ink/20 disabled:opacity-60"
      >
        <span className="text-[11px] font-bold tracking-wide text-muted uppercase">
          Learning
        </span>
        <span className="text-sm font-extrabold">{current}</span>
        <span
          className={`text-muted transition-transform ${open ? '-rotate-90' : 'rotate-90'}`}
        >
          <Chevron className="h-4 w-4" />
        </span>
      </button>

      {open && (
        <ul
          role="listbox"
          aria-label="Language to learn"
          className="absolute top-full left-0 z-20 mt-2 w-60 overflow-hidden
                     rounded-2xl border border-line bg-white py-1"
        >
          {languages.map(({ code, label, word_count: words }) => (
            <li key={code}>
              <button
                type="button"
                role="option"
                aria-selected={code === current}
                onClick={() => choose(code)}
                className={`flex min-h-11 w-full items-center justify-between gap-3
                            px-3.5 text-left transition-colors hover:bg-surface ${
                              code === current ? 'text-learner' : ''
                            }`}
              >
                <span className="text-sm font-bold">{label}</span>
                <span className="text-[11px] text-muted">{words} words</span>
              </button>
            </li>
          ))}

          <li className="border-t border-line px-3.5 pt-2 pb-1.5">
            <p className="text-[11px] leading-relaxed text-muted">
              Each language keeps its own schedule, so switching costs you
              nothing.
            </p>
          </li>
        </ul>
      )}
    </div>
  )
}
