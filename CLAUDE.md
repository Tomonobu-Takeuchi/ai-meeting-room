# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AI-PERSONA会議室** (AI-Persona Meeting Room) — A web app where users create AI personas that conduct real-time AI-powered discussions about user-specified topics, powered by Claude.

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server (http://localhost:8765)
python src/main.py

# Run production server
gunicorn src.main:app --bind 0.0.0.0:$PORT --timeout 300 --workers 1
```

## Required Environment Variables

```
ANTHROPIC_API_KEY     # Claude API (conversation generation, minutes)
OPENAI_API_KEY        # Whisper transcription (audio/video learning data)
DATABASE_URL          # PostgreSQL connection string (with pgvector extension)
SECRET_KEY            # Flask session secret
PORT                  # Default 8765 (dev) or set by Railway/Heroku
```

## Architecture

### Stack
- **Backend:** Python 3.12 + Flask, pg8000 (PostgreSQL), bcrypt sessions
- **Frontend:** Vanilla JS + HTML5, no build step, SSE for real-time streaming
- **Database:** PostgreSQL with pgvector extension (vector embeddings for RAG)
- **Deployment:** Railway via nixpacks (requires FFmpeg, libpq-dev)

### Key Files
| File | Purpose |
|------|---------|
| `src/main.py` | Flask app + all API routes (~766 lines) |
| `src/database.py` | PostgreSQL CRUD, connection management (~647 lines) |
| `src/persona/persona_manager.py` | Persona CRUD, AI prompts, growth tracking (~488 lines) |
| `src/meeting/meeting_room.py` | Session state, streaming generation (~187 lines) |
| `web/index.html` | Single-page UI (dark mode, purple/blue theme) |
| `web/app.js` | Frontend logic, SSE consumption, auth UI (~1493 lines) |

### Data Flow
1. User creates personas with personalities, backgrounds, and learning data
2. User starts a meeting with a topic + selected personas
3. Backend creates an in-memory session (`MeetingRoom.sessions` dict)
4. Frontend uses SSE to stream responses from `/api/stream/member|facilitator|auto/<session_id>`
5. Meeting persists to JSON in `data/meetings/`; logs written to DB on PDF export

### Streaming API Response Format (SSE)
```
data: {"type": "chunk", "text": "...", "persona_id": "..."}
data: {"type": "done", "message": {...}}
data: {"type": "error", "message": "..."}
```

### Database Tables
- `users` — auth (email, bcrypt password hash, plan)
- `personas` — persona definitions; `user_id=NULL` for system defaults, `role=facilitator|member`
- `persona_learn` — knowledge base with `vector(1536)` embeddings for semantic search
- `persona_patterns` — extracted conversation patterns
- `persona_growth` — maturity levels (0=初回, 1=見習い, 2=熟練, 3=達人) + scores
- `persona_meeting_stats` — meeting participation counts
- `feedback` — user ratings per persona response

### Important Implementation Details
- **Single worker:** `gunicorn --workers 1` because active sessions are stored in-memory
- **Japanese support:** `app.json.ensure_ascii = False`; PDF uses HeiseiKakuGo-W5 font
- **Session state:** Flask session stores `user_id`/`user_email`; meeting state in `MeetingRoom.sessions`
- **Context window:** Last 10 messages passed as history in each Claude API call
- **Learning data inputs:** manual text, URL scraping, YouTube transcripts, Whisper (audio/video via FFmpeg + yt-dlp)

## Utility Scripts (Untracked)
- `check_db.py` — Database inspection
- `add_growth_tables.py` — Migration for growth feature tables
