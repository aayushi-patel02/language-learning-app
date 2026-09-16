import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { signUp } from '../api'
import { useAuth } from '../auth'
import AuthShell, { Field, SubmitButton } from './AuthShell'

export default function SignUp() {
  const navigate = useNavigate()
  const { adopt, user } = useAuth()

  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [accepted, setAccepted] = useState(false)
  const [error, setError] = useState('')
  const [field, setField] = useState('')
  const [busy, setBusy] = useState(false)

  const set = (key) => (event) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }))

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    setField('')
    try {
      // The interceptor sends the guest token if there is one, which is what
      // lets the backend convert that guest into this account rather than
      // starting a second empty one.
      const { data } = await signUp({ ...form, accepted_terms: accepted })
      adopt(data)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Could not create your account.')
      setField(err?.response?.data?.field ?? '')
      setBusy(false)
    }
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle={
        user?.is_guest
          ? 'Your progress so far comes with you.'
          : 'It takes a moment and keeps your progress safe.'
      }
    >
      <form onSubmit={submit} noValidate>
        <Field
          label="Name"
          value={form.name}
          onChange={set('name')}
          autoComplete="name"
          invalid={field === 'name'}
        />
        <Field
          label="Email"
          type="email"
          value={form.email}
          onChange={set('email')}
          autoComplete="email"
          invalid={field === 'email'}
        />
        <Field
          label="Password"
          type="password"
          value={form.password}
          onChange={set('password')}
          autoComplete="new-password"
          invalid={field === 'password'}
          hint="At least 8 characters, and not a common one."
        />

        <label className="mt-4 flex cursor-pointer items-start gap-2.5">
          <input
            type="checkbox"
            checked={accepted}
            onChange={(event) => setAccepted(event.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 accent-learner"
          />
          <span
            className={`text-xs leading-relaxed ${
              field === 'accepted_terms' ? 'text-error' : 'text-muted'
            }`}
          >
            I accept the terms of use and the privacy policy.
          </span>
        </label>

        {error && (
          <p className="mt-3 rounded-xl bg-error-soft px-3 py-2 text-xs text-error">
            {error}
          </p>
        )}

        <SubmitButton busy={busy}>Create account</SubmitButton>
      </form>

      <p className="mt-5 text-center text-xs text-muted">
        Already have an account?{' '}
        <Link to="/login" className="font-bold text-learner underline">
          Log in
        </Link>
      </p>
    </AuthShell>
  )
}
