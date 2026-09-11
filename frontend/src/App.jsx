import { BrowserRouter, Route, Routes, useParams } from 'react-router-dom'

import Chat from './components/Chat'
import Home from './components/Home'
import Recap from './components/Recap'

function ChatRoute() {
  const { topic } = useParams()
  // Keyed on topic so switching topics remounts with fresh state rather than
  // leaving the previous conversation on screen.
  return <Chat key={topic} topic={topic} />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/chat/:topic" element={<ChatRoute />} />
        <Route path="/recap/:sessionId" element={<Recap />} />
        <Route path="*" element={<Home />} />
      </Routes>
    </BrowserRouter>
  )
}
