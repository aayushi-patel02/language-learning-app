// Plain-English wording for SM-2 state. The algorithm thinks in intervals and
// repetition counts; a learner should never have to.

export function formatDue(dueDate) {
  if (!dueDate) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const due = new Date(`${dueDate}T00:00:00`)
  const days = Math.round((due - today) / 86400000)

  if (days <= 0) return 'today'
  if (days === 1) return 'tomorrow'
  if (days < 7) return `in ${days} days`
  if (days < 14) return 'in a week'
  if (days < 30) return `in ${Math.round(days / 7)} weeks`
  if (days < 60) return 'in a month'
  return `in ${Math.round(days / 30)} months`
}

/** What the learner's streak on this word is, in words rather than numbers. */
export function formatStreak({ graded, repetitions }) {
  if (!graded) return 'not graded'
  if (repetitions === 0) return 'starting over'
  if (repetitions === 1) return 'first time right'
  return `${repetitions} in a row`
}
