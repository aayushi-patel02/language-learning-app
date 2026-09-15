import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { logIn } from '../api'
import { useAuth } from '../auth'
import AuthShell, { Field, SubmitButton } from './AuthShell'

export default function Login() {
  const navigate = useNavigate()
  const { adopt } = useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const { data } = await logIn(email, password)
      adopt(data)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Could not log you in.')
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Welcome back" subtitle="Pick up where you left off.">
      <form onSubmit={submit} noValidate>
        <Field
          label="Email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          autoComplete="email"
        />
        <Field
          label="Password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
        />

        {error && (
          <p className="mt-3 rounded-xl bg-error-soft px-3 py-2 text-xs text-error">
            {error}
          </p>
        )}

        <SubmitButton busy={busy}>Log in</SubmitButton>
      </form>

      <p className="mt-5 text-center text-xs text-muted">
        New here?{' '}
        <Link to="/signup" className="font-bold text-learner underline">
          Create an account
        </Link>
      </p>
    </AuthShell>
  )
}
