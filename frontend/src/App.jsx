import { useEffect, useState } from 'react'
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useParams,
} from 'react-router-dom'

import { AuthProvider, useAuth } from './auth'
import Chat from './components/Chat'
import Home from './components/Home'
import Login from './components/Login'
import Profile from './components/Profile'
import Progress from './components/Progress'
import Recap from './components/Recap'
import SignUp from './components/SignUp'
import Splash from './components/Splash'
import Vocabulary from './components/Vocabulary'
import Welcome from './components/Welcome'
import WelcomeGate from './components/WelcomeGate'
import WordDetail from './components/WordDetail'

const ONBOARDED_KEY = 'charla.onboarded'

// The splash is held for a moment even when the session resolves instantly,
// so it reads as a deliberate opening rather than a flicker on the way past.
const SPLASH_MS = 1100

function ChatRoute() {
  const { topic } = useParams()
  // Keyed on topic so switching topics remounts with fresh state rather than
  // leaving the previous conversation on screen.
  return <Chat key={topic} topic={topic} />
}

/** Everything inside the app proper requires a learner, guest or otherwise. */
function RequireLearner({ children }) {
  const { user, ready } = useAuth()
  if (!ready) return <Splash />
  if (!user) return <Navigate to="/welcome" replace />
  return children
}

function Landing() {
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

function Shell() {
  const { ready } = useAuth()
  const [splashDone, setSplashDone] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setSplashDone(true), SPLASH_MS)
    return () => clearTimeout(timer)
  }, [])

  if (!ready || !splashDone) return <Splash />

  return (
    <Routes>
      <Route path="/welcome" element={<WelcomeGate />} />
      <Route path="/signup" element={<SignUp />} />
      <Route path="/login" element={<Login />} />

      <Route
        path="/"
        element={
          <RequireLearner>
            <Landing />
          </RequireLearner>
        }
      />
      <Route
        path="/chat/:topic"
        element={
          <RequireLearner>
            <ChatRoute />
          </RequireLearner>
        }
      />
      <Route
        path="/recap/:sessionId"
        element={
          <RequireLearner>
            <Recap />
          </RequireLearner>
        }
      />
      <Route
        path="/progress"
        element={
          <RequireLearner>
            <Progress />
          </RequireLearner>
        }
      />
      <Route
        path="/vocabulary"
        element={
          <RequireLearner>
            <Vocabulary />
          </RequireLearner>
        }
      />
      <Route
        path="/vocabulary/:wordId"
        element={
          <RequireLearner>
            <WordDetail />
          </RequireLearner>
        }
      />
      <Route
        path="/profile"
        element={
          <RequireLearner>
            <Profile />
          </RequireLearner>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
    </AuthProvider>
  )
}
