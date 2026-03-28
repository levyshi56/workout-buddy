# Workout Buddy — iMessage AI Agent

AI workout coach you text with. No app — just iMessage. Built on Linq API.

## What it does

Text a phone number. Your coach guides you through real workouts in real time — one exercise at a time, rest timers and all. It remembers your history, injuries, goals, and PRs across every session.

## Architecture

```
User (iMessage) → Linq → Django Webhook → MongoDB (user context) → GPT-4o mini → Linq → User
                                                    ↘ Celery (rest timer) → Linq → User
```

## Stack

| Layer | Choice |
|---|---|
| Backend | Python / Django |
| Database | MongoDB via MongoEngine |
| Task Queue | Celery + Redis |
| Messaging | Linq API (iMessage / RCS / SMS) |
| LLM | GPT-4o mini (OpenAI) |
| Hosting | Railway |

## Local Setup

### Prerequisites
- Python 3.12+
- MongoDB running locally
- Redis running locally

### Install

```bash
git clone https://github.com/levyshi/workout-buddy.git
cd workout-buddy
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in .env with your API keys
```

### Run

```bash
# Django dev server
python manage.py runserver

# Celery worker (separate terminal)
celery -A workout_buddy worker --loglevel=info
```

### Health check

```
GET http://localhost:8000/api/health/
```

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/webhook/linq/` | POST | Receive inbound messages from Linq |
| `/api/health/` | GET | Health check |

## Environment Variables

See `.env.example` for all required variables:

- `SECRET_KEY` — Django secret key
- `MONGODB_URI` — MongoDB connection string
- `REDIS_URL` — Redis connection string
- `OPENAI_API_KEY` — OpenAI API key
- `LINQ_API_KEY` — Linq API key
- `LINQ_WEBHOOK_SECRET` — Linq webhook HMAC secret

## Key Links

- [Linq API Docs](https://apidocs.linqapp.com/)
- [Linq Sandbox Signup](https://dashboard.linqapp.com/sandbox-signup)
