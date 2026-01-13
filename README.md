# GhostReply 👻

AI-powered X/Twitter engagement assistant for AI, Web3, and crypto spaces.

## Features

- 🔍 **Tweet Discovery** — Monitors X for high-visibility tweets about AI, crypto, Web3
- 🤖 **AI Reply Generation** — Uses OpenRouter (free models) to draft short, insightful replies
- ✍️ **Manual Review** — Review and approve drafts before posting
- 📊 **Analytics** — Track engagement and performance

## Quick Start

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and add your OpenRouter API key
```

### 3. Login to X (First Time)

```bash
python browser.py
# Browser opens — log in manually, session is saved
```

### 4. Start Backend

```bash
python main.py
# API runs on http://localhost:8000
```

### 5. Start Frontend

```bash
cd frontend
npm install
npm run dev
# Dashboard on http://localhost:3000
```

## Architecture

```
├── main.py           # FastAPI server + control endpoints
├── browser.py        # Playwright X automation
├── monitor.py        # Tweet discovery & AI generation loop
├── openrouter.py     # OpenRouter AI client
├── routes.py         # REST API routes
├── database.py       # SQLite models
├── config.py         # Settings
└── frontend/         # Next.js dashboard
    ├── app/          # Pages (dashboard, tweets, drafts, analytics)
    ├── components/   # UI components
    └── lib/          # API client
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Health check |
| `POST /control/start` | Start tweet monitor |
| `POST /control/stop` | Stop monitor |
| `GET /control/status` | Monitor status |
| `GET /api/tweets` | List discovered tweets |
| `GET /api/replies` | List reply drafts |
| `POST /api/replies/{id}/approve` | Approve a draft |
| `POST /api/replies/{id}/reject` | Reject a draft |
| `POST /control/post/{id}` | Post a reply |

## Rate Limits

- Max 15 replies per hour
- 30-180 second random delay between actions
- 24-hour cooldown per account (no replying twice to same person)

## Tech Stack

- **Backend**: Python, FastAPI, Playwright, SQLite
- **Frontend**: Next.js 14, TypeScript, Tailwind CSS
- **AI**: OpenRouter (Llama, Mistral, Qwen free models)
