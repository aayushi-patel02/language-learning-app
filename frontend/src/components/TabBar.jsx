import { NavLink } from 'react-router-dom'

// Drawn inline for the same reason as TopicIcon: four glyphs is not worth a
// dependency, and currentColor means the active state is one class change.
const ICONS = {
  home: (
    <>
      <path d="M3.5 10.6 12 3.5l8.5 7.1" />
      <path d="M5.8 9.4V20h12.4V9.4" />
      <path d="M9.8 20v-5.2h4.4V20" />
    </>
  ),
  book: (
    <>
      <path d="M4 4.8A1.8 1.8 0 0 1 5.8 3H19v15.6H5.8A1.8 1.8 0 0 0 4 20.4Z" />
      <path d="M8 7.4h7M8 10.8h5" />
    </>
  ),
  chart: (
    <>
      <path d="M4 20.2h16" />
      <path d="M7.5 20.2v-4.6M12 20.2V7.6M16.5 20.2v-8.4" />
    </>
  ),
  person: (
    <>
      <circle cx="12" cy="8" r="3.6" />
      <path d="M4.9 20a7.1 7.1 0 0 1 14.2 0" />
    </>
  ),
}

const TABS = [
  { to: '/', label: 'Learn', icon: 'home' },
  { to: '/vocabulary', label: 'Words', icon: 'book' },
  { to: '/progress', label: 'Progress', icon: 'chart' },
  { to: '/profile', label: 'Profile', icon: 'person' },
]

export default function TabBar() {
  // `inset-x-0` with `mx-auto max-w-md` centres the bar at the width of the
  // readable column instead of stretching it across the viewport. On a wide
  // screen the column has visible edges, so a full-width bar would float free
  // of the app it belongs to. `app-column` gives it the same opaque
  // background and side edges as the content above it.
  return (
    <nav
      aria-label="Sections"
      className="app-column fixed inset-x-0 bottom-0 z-30 mx-auto max-w-md
                 border-t border-line"
      // The iPhone home indicator sits over the bottom of the viewport, so the
      // row is lifted clear of it rather than tucked underneath.
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <ul className="flex">
        {TABS.map(({ to, label, icon }) => (
          <li key={to} className="flex-1">
            <NavLink
              to={to}
              // Without `end`, "/" would count as active on every route,
              // because every path starts with it.
              end={to === '/'}
              className={({ isActive }) =>
                `flex min-h-14 flex-col items-center justify-center gap-0.5 py-1.5
                 transition-colors ${
                   isActive ? 'text-learner' : 'text-muted hover:text-ink'
                 }`
              }
            >
              {({ isActive }) => (
                <>
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={isActive ? 2.2 : 1.7}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                    className="h-6 w-6"
                  >
                    {ICONS[icon]}
                  </svg>
                  <span
                    className={`text-[10px] tracking-wide ${
                      isActive ? 'font-extrabold' : 'font-bold'
                    }`}
                  >
                    {label}
                  </span>
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
