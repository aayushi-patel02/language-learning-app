// Pronunciation through the browser's own speech synthesis. No API, no audio
// files to host, no extra provider to run out of credit, and it works with the
// network down. Voice quality depends on the OS; macOS and iOS ship good
// voices for all four languages, which is what matters for the demo.

// BCP-47 tags, because a SpeechSynthesisUtterance with the wrong one reads
// the text with English phonetics - "Guten Morgen" in an American accent is
// worse than no audio at all, since the whole point is a pronunciation model.
const TAGS = {
  Spanish: 'es-ES',
  French: 'fr-FR',
  German: 'de-DE',
  Hindi: 'hi-IN',
}

const DEFAULT_LANGUAGE = 'Spanish'

const tagFor = (language) => TAGS[language] ?? TAGS[DEFAULT_LANGUAGE]

export const canSpeak = () =>
  typeof window !== 'undefined' && 'speechSynthesis' in window

/** Prefer an exact regional voice, then any voice for the same language. */
function voiceFor(tag) {
  const voices = window.speechSynthesis.getVoices() || []
  const prefix = tag.split('-')[0]
  return (
    voices.find((v) => v.lang === tag) ??
    voices.find((v) => v.lang?.replace('_', '-').startsWith(prefix)) ??
    null
  )
}

/** True when the platform actually has a voice for this language. */
export function canSpeakLanguage(language) {
  if (!canSpeak()) return false
  return voiceFor(tagFor(language)) !== null
}

export function speak(text, language = DEFAULT_LANGUAGE) {
  if (!canSpeak() || !text) return false

  // Cancel first: tapping several words quickly would otherwise queue them
  // and play a backlog after the learner has moved on.
  window.speechSynthesis.cancel()

  const tag = tagFor(language)
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = tag
  // Slightly under natural pace; this is a pronunciation model, not speech.
  utterance.rate = 0.85
  const voice = voiceFor(tag)
  if (voice) utterance.voice = voice
  window.speechSynthesis.speak(utterance)
  return true
}

// Chrome populates the voice list asynchronously, so the first call can see an
// empty array. Touching it early means a voice is ready by the time a learner
// taps one.
if (canSpeak()) {
  window.speechSynthesis.getVoices()
}
