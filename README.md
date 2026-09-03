# Charla

A conversational Spanish tutor that decides what you practise using spaced repetition.

Flashcard apps drill words in isolation, and conversation apps don't track what
you're forgetting. Charla does both: it pulls the vocabulary you owe a review
into an actual conversation — you practise *la cuenta, por favor* by asking for
the bill, not by flipping a card — then grades how you handled it and schedules
the word's next appearance with SM-2.

Built for the Nerdy AI Hackathon Challenge.

## What it does

- **Three conversation topics** — daily routine, ordering food, travel basics.
  60 hand-checked vocabulary items with example sentences.
- **Two ways to answer.** Tap a suggested reply, or type your own and get it
  evaluated. Chips are the default because they're fast and predictable; free
  text is where the model actually reads your Spanish.
- **Real SM-2 scheduling.** Not a simplified stand-in — the full algorithm,
  including the ease-factor floor and the lapse reset. See below.
- **Session recap** showing what you practised and when each word is next due.

## Why the scheduler matters

The point of the app is that the conversation is driven by your review
schedule, so the scheduler has to be correct or the whole product is theatre.
[`tutor/sm2.py`](backend/tutor/sm2.py) implements Wozniak's SM-2:

```
if q >= 3:  I(1) = 1, I(2) = 6, I(n) = I(n-1) * EF ;  n += 1
else:       n = 0, I = 1                              # start the item over
            EF' = max(1.3, EF + (0.1 - (5-q) * (0.08 + (5-q) * 0.02)))
```

Two places implementations commonly go wrong, both covered by tests:

- **The repetition count must reset on a lapse.** If you track it with a
  "times seen" counter that only ever increments, a forgotten word skips the
  1-day/6-day relearning ramp and jumps straight back to a multiplied
  interval.
- **The interval uses the ease factor from _before_ the update**, matching the
  ordering of steps 3 and 5 in the original description.

Answers are graded on SM-2's 0–5 scale. A correct chip earns 4 rather than 5,
because picking a right answer off the screen is recognition, not recall; a
wrong chip earns 2 — "incorrect, but the answer looked familiar" — since the
correct option was visible. Typed answers are graded from the model's verdict.

## Architecture

| Layer | Choice |
| --- | --- |
| Backend | Django + Django REST Framework, SQLite |
| Frontend | React (Vite) + Tailwind CSS + react-router-dom |
| LLM | DeepSeek or Sarvam AI, selected by one env var |

The LLM sits behind an adapter in `tutor/llm.py` with a single `_call()` entry
point, so switching providers is a one-line config change rather than a
refactor. Every model call has a hand-written fallback response, and
`DEMO_MODE=true` serves pre-cached turns instead of calling out at all — a live
demo shouldn't depend on someone else's rate limit.

### Data model

- `VocabItem` — a word or phrase, scoped to a topic.
- `UserVocabState` — per-learner SM-2 state for one item: repetitions, ease
  factor, interval, due date, plus review counters for the recap.
- `ConversationSession` — one practice conversation on one topic.
- `Turn` — a tutor prompt and the learner's reply, graded in place.

## Running it locally

Requires Python 3.12+ and Node 18+.

```bash
git clone https://github.com/aayushi-patel02/language-learning-app.git
cd language-learning-app
```

**Backend**

```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then add your API key
python manage.py migrate
python manage.py seed_vocab
python manage.py runserver
```

The API is at `http://127.0.0.1:8000/api/`, the Django admin at `/admin/`
(run `python manage.py createsuperuser` first).

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/sessions/start/` | Start a session on a topic; returns the first tutor turn |
| `POST` | `/api/sessions/<id>/next/` | Submit a reply (chip or free text); returns the next turn |
| `GET` | `/api/sessions/<id>/recap/` | Session summary and upcoming review dates |

There is no signup flow. Practice runs against a seeded demo learner — an
auth system isn't what this project is demonstrating, and it would have cost a
day.

## Configuration

Copy `backend/.env.example` to `backend/.env`. The variables that matter:

| Variable | Default | Notes |
| --- | --- | --- |
| `LLM_PROVIDER` | `deepseek` | `deepseek` or `sarvam` |
| `DEEPSEEK_API_KEY` | — | required when the provider is DeepSeek |
| `SARVAM_API_KEY` | — | required when the provider is Sarvam |
| `DEMO_MODE` | `false` | serve cached turns, skip the model entirely |
| `SESSION_TURN_LIMIT` | `8` | exchanges before the recap screen |

## Tests

```bash
cd backend && python manage.py test tutor
```

Covers the ease-factor formula at every grade, the floor at 1.3, interval
progression, half-up rounding, lapse handling, and the session scheduler's
priority order.

## Project status

Working: data model, SM-2 scheduler and its tests, vocab seed, Django admin.

In progress: LLM adapter, session API, React frontend, deployment.

## Layout

```
backend/
  config/            Django settings, root URLconf
  tutor/
    models.py        vocab, review state, sessions, turns
    sm2.py           SM-2 algorithm and session scheduler
    tests.py         scheduler test suite
    llm.py           provider adapter and prompts
    views.py         API endpoints
    management/commands/seed_vocab.py
frontend/
  src/components/    Home, Chat, Recap
  src/api.js         backend client
```
