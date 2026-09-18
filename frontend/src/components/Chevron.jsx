// A stroked chevron, replacing the ‹ and › typographic glyphs these used to
// be. Those are punctuation: they render hairline-thin, ignore any weight you
// set, and sit slightly off the optical centre of a button, so a back control
// read as a stray character rather than something to press.
//
// Same idiom as TopicIcon and the tab bar: inline SVG inheriting currentColor,
// no icon dependency for what is two line segments.
export default function Chevron({ direction = 'right', className = 'h-5 w-5' }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.25"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      <path d={direction === 'left' ? 'M15 5 8 12l7 7' : 'M9 5l7 7-7 7'} />
    </svg>
  )
}
