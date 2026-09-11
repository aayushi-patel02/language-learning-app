import { useState } from 'react'
import { BrowserRouter, Route, Routes, useParams } from 'react-router-dom'

import Chat from './components/Chat'
import Home from './components/Home'
import Progress from './components/Progress'
import Recap from './components/Recap'
import Vocabulary from './components/Vocabulary'
import Welcome from './components/Welcome'
import WordDetail from './components/WordDetail'

const ONBOARDED_KEY = 'charla.onboarded'

function ChatRoute() {
  const { topic } = useParams()
  // Keyed on topic so switching topics remounts with fresh state rather than
  // leaving the previous conversation on screen.
  return <Chat key={topic} topic={topic} />
}

function Landing() {
  // Read synchronously in the initialiser so a returning learner never sees
  // the intro flash before the home screen replaces it.
  const [onboarded, setOnboarded] = useState(
    () => localStorage.getItem(ONBOARDED_KEY) === '1',
  )

  if (onboarded) return <Home />

  return (
    <Welcome
      onDone={() => {
        try {
          localStorage.setItem(ONBOARDED_KEY, '1')
        } catch {
          // Private browsing can refuse writes. Showing the intro again is a
          // far better failure than blocking the app.
        }
        setOnboarded(true)
      }}
    />
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/chat/:topic" element={<ChatRoute />} />
        <Route path="/recap/:sessionId" element={<Recap />} />
        <Route path="/progress" element={<Progress />} />
        <Route path="/vocabulary" element={<Vocabulary />} />
        <Route path="/vocabulary/:wordId" element={<WordDetail />} />
        <Route path="*" element={<Landing />} />
      </Routes>
    </BrowserRouter>
  )
}
