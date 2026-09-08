// Slugs must match tutor/models.py TOPIC_CHOICES exactly - the backend
// rejects anything else with a 400.
export const TOPICS = [
  {
    id: 'daily_routine',
    label: 'Daily routine',
    blurb: 'Waking up, meals, getting to work',
  },
  {
    id: 'ordering_food',
    label: 'Ordering food',
    blurb: 'Tables, menus, asking for the bill',
  },
  {
    id: 'travel_basics',
    label: 'Travel basics',
    blurb: 'Tickets, directions, checking in',
  },
]

export const topicById = (id) => TOPICS.find((topic) => topic.id === id)
