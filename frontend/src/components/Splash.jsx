export default function Splash() {
  return (
    <div className="app-column mx-auto flex min-h-full max-w-md flex-col items-center
                    justify-center px-5">
      <div className="animate-pop text-center">
        <span
          aria-hidden="true"
          className="mx-auto flex h-20 w-20 items-center justify-center rounded-3xl
                     bg-learner text-4xl"
        >
          🦉
        </span>
        <h1 className="mt-5 text-4xl font-extrabold tracking-tight">Charla</h1>
        <p className="mt-2 text-sm text-muted">
          Speak languages with confidence.
        </p>
      </div>

      {/* Three dots rather than a spinner: a spinner implies something might
          fail, and this wait is always short. */}
      <div className="mt-10 flex gap-1.5" aria-label="Loading">
        {[0, 160, 320].map((delay) => (
          <span
            key={delay}
            className="h-2 w-2 animate-bounce rounded-full bg-learner/50"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </div>
    </div>
  )
}
