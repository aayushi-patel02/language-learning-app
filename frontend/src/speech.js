// Pronunciation through the browser's own speech synthesis. No API, no audio
// files to host, no extra provider to run out of credit, and it works with the
// network down. Voice quality depends on the OS; macOS and iOS ship good
// Spanish voices, which is what matters for the demo.

const LANG = 'es-ES'

export const canSpeak = () =>
  typeof window !== 'undefined' && 'speechSynthesis' in window

/** Prefer a real Spanish voice when the platform offers one. */
function spanishVoice() {
  const voices = window.speechSynthesis.getVoices() || []
  return (
    voices.find((v) => v.lang === LANG) ??
    voices.find((v) => v.lang?.startsWith('es')) ??
    null
  )
}

export function speak(text) {
  if (!canSpeak() || !text) return false

  // Cancel first: tapping several words quickly would otherwise queue them
  // and play a backlog after the learner has moved on.
  window.speechSynthesis.cancel()

  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = LANG
  // Slightly under natural pace; this is a pronunciation model, not speech.
  utterance.rate = 0.85
  const voice = spanishVoice()
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
