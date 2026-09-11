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
| LLM | Groq, Gemini, DeepSeek or Sarvam, selected by one env var |

The LLM sits behind an adapter in [`tutor/llm.py`](backend/tutor/llm.py) with a
single `_call()` entry point, so switching providers is a one-line config
change rather than a refactor. That paid off repeatedly: the build started on
DeepSeek, and each move after it — to Gemini, then to Groq — cost one function
and one dictionary entry. DeepSeek and Groq share a single OpenAI-protocol code
path; Gemini and Sarvam have their own.

Responses are hardened before use — markdown fences stripped, prose wrappers
tolerated, then normalised into a guaranteed shape. Every call has a
hand-written fallback turn, and `DEMO_MODE=true` skips the network entirely and
replays a fixed script, because a live demo shouldn't depend on someone else's
rate limit.

One rule the API layer relies on: if grading a typed answer fails, the result
comes back `graded=False` and **no** SM-2 update runs. A provider outage must
never record a wrong answer the learner didn't give.

To check the live path at any time:

```bash
cd backend && python manage.py check_llm
```

It prints the active provider, confirms the key is present without printing it,
makes one real request, and exits non-zero if anything fell back. Add
`--list-models` to see which models your key can actually reach.

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
| `LLM_PROVIDER` | `groq` | `groq`, `gemini`, `deepseek` or `sarvam` |
| `GROQ_API_KEY` | — | required when the provider is Groq |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | model access varies by account; `check_llm --list-models` is authoritative |
| `GEMINI_API_KEY` | — | required when the provider is Gemini |
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

Working end to end: data model, SM-2 scheduler, LLM adapter with fallbacks, all
three API endpoints, vocab seed, Django admin, and the React frontend. 150
tests, none of which touch the network.

In progress: deployment.

Currently running on `DEMO_MODE=true`. The three providers wired up all refuse
new free-tier projects at the moment, so the app serves its hand-written turn
bank. Chip practice, SM-2 scheduling and the recap are fully real either way;
what demo mode costs is free-text evaluation and conversational variety. Any
provider with credit switches it back on through `LLM_PROVIDER`.

## Deployment

Backend on Render, frontend on Vercel, from the same repo.

**Backend.** At [dashboard.render.com/blueprints](https://dashboard.render.com/blueprints),
import this repo — Render reads [`render.yaml`](render.yaml) instead of you
filling in a web form. It prompts for the values marked `sync: false`
(`GROQ_API_KEY`, and the two origin lists once the frontend URL exists) and
generates `DJANGO_SECRET_KEY` itself. [`backend/build.sh`](backend/build.sh)
installs, collects static files, migrates and seeds on every deploy.

The blueprint ships with `DEMO_MODE=true`. That is intentional: a live demo
should not depend on someone else's rate limit. Set it to `false` in the Render
dashboard when you want to show the model working.

Render's free disk is ephemeral, so on SQLite the review history is wiped on
every restart. Attach a Postgres instance and set `DATABASE_URL` to make the
schedule persist — `settings.py` picks it up automatically.

**Frontend.** Import the same repo at Vercel with root directory `frontend`,
and set `VITE_API_URL` to the Render URL plus `/api`.
[`frontend/vercel.json`](frontend/vercel.json) rewrites all paths to
`index.html`; without it, opening `/recap/5` directly returns a 404, because
routing happens client-side.

Then set `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` on Render to the
Vercel URL, with no trailing slash.

**Before relying on it:** hit the live URL several times, including after
fifteen minutes of inactivity. Render's free tier sleeps, and the first request
back can take close to a minute.

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
