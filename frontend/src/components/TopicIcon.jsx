// Small line icons, drawn inline rather than pulled from an icon package:
// three glyphs is not worth a dependency, and inline SVG inherits
// currentColor so each topic's accent applies for free.

const PATHS = {
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
    </>
  ),
  bowl: (
    <>
      <path d="M3 11h18" />
      <path d="M4 11a8 8 0 0 0 16 0" />
      <path d="M12 4v3M9 5.5v1.5M15 5.5v1.5" />
    </>
  ),
  plane: <path d="M3 13.5 21 4l-4.5 17-3.5-6.5L3 13.5Z" />,
}

export default function TopicIcon({ name, className = '' }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {PATHS[name] ?? PATHS.sun}
    </svg>
  )
}
