// Slugs must match tutor/models.py TOPIC_CHOICES exactly - the backend
// rejects anything else with a 400.
//
// `accent` / `tint` are Tailwind colour names from the @theme block in
// index.css, so each topic card reads as its own thing rather than three
// identical grey boxes.
export const TOPICS = [
  {
    id: 'daily_routine',
    label: 'Daily routine',
    blurb: 'Waking up, meals, getting to work',
    accent: 'text-topic-morning',
    tint: 'bg-topic-morning-soft',
    icon: 'sun',
  },
  {
    id: 'ordering_food',
    label: 'Ordering food',
    blurb: 'Tables, menus, asking for the bill',
    accent: 'text-topic-food',
    tint: 'bg-topic-food-soft',
    icon: 'bowl',
  },
  {
    id: 'travel_basics',
    label: 'Travel basics',
    blurb: 'Tickets, directions, checking in',
    accent: 'text-topic-travel',
    tint: 'bg-topic-travel-soft',
    icon: 'plane',
  },
]

export const topicById = (id) => TOPICS.find((topic) => topic.id === id)
