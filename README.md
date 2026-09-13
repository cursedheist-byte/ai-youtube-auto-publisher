# AI YouTube Auto Publisher — Phase 1–8 Complete / Final Hardening Complete

**Phase 1:** project foundation — full DB schema, JWT auth, role-based
access, Admin Dashboard.

**Phase 2:** admin-only Google Drive source management (service account),
video discovery, safe re-scanning, error handling.

**Phase 3:** YouTube OAuth channel connection for normal users —
connect/disconnect a channel, automation on/off + daily upload count
settings, token encryption at rest, automatic token refresh with DB
write-back, and revoked-token detection.

**Phases 4–8:** upload history + race-safe duplicate prevention, AI SEO metadata, real manual Drive → YouTube uploads, daily APScheduler automation, deterministic retries, monitoring, and frontend status/error states.

The app never exposes OAuth tokens. Videos are staged only in short-lived temporary files and removed after each upload attempt.

---

## Prerequisites

- Python 3.11+, Node.js 20+, Docker

---

## 1. Start the database

```bash
docker compose up -d
```

## 2. Backend setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env` (see the variable table below), then:

```bash
alembic upgrade head
python create_admin.py admin@example.com "a-strong-password"
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

## 3. Frontend setup

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open http://localhost:5173.

---

## Environment variables (backend/.env)

| Variable | Required for | Notes |
|---|---|---|
| `DATABASE_URL` | Everything | Postgres connection string |
| `JWT_SECRET` | Everything | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ENCRYPTION_KEY` | Phase 3 | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — encrypts OAuth tokens at rest |
| `CORS_ORIGINS` | Everything | Default `http://localhost:5173` |
| `FRONTEND_URL` | Phase 3 | Where the browser is redirected after Google OAuth |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | Phase 3 | From Google Cloud Console OAuth client |
| `GOOGLE_OAUTH_REDIRECT_URI` | Phase 3 | Must exactly match the OAuth client's authorized redirect URI |
| `GOOGLE_SERVICE_ACCOUNT_JSON_PATH` | Phase 2 | Path to the Drive service account's JSON key file |
| `GEMINI_API_KEY` / `AI_PROVIDER` / `GEMINI_MODEL` | Phase 5 onward | Gemini metadata generation; required when AI_PROVIDER=gemini |
| `AI_REQUEST_TIMEOUT_SECONDS` | Phase 5 onward | AI request timeout |
| `YOUTUBE_PRIVACY_STATUS` / `YOUTUBE_DEFAULT_CATEGORY_ID` | Phase 6 onward | Upload metadata defaults |
| `YOUTUBE_UPLOAD_CHUNK_BYTES` | Phase 6 onward | Resumable upload chunk size |
| `RETRY_INTERVAL_MINUTES` / `MAX_UPLOAD_RETRIES` / `UPLOAD_STALE_AFTER_MINUTES` | Phase 8 onward | Retry and stale-upload policy |
| `OAUTH_STATE_TTL_SECONDS` / `OAUTH_STATE_COOKIE_NAME` / `OAUTH_STATE_COOKIE_SECURE` | OAuth | One-time browser-bound OAuth state |

---

## Google Cloud setup

One project provides both credentials below.

### Drive service account (Phase 2 — see Phase 2 docs if you skipped it)

Enable the Drive API → create a service account → download its JSON key →
set `GOOGLE_SERVICE_ACCOUNT_JSON_PATH` → share each Drive folder with its
email as Viewer.

### OAuth client for YouTube (Phase 3)

1. Enable the **YouTube Data API v3** on the same project.
2. APIs & Services → OAuth consent screen: **External**, fill required
   fields. While in **Testing** mode, add every Google account you'll test
   with under "Test users" — unverified apps are capped at 100 test users
   and show an "unverified app" warning (a real Google constraint, not
   something this code can bypass; full public use needs Google's
   verification review).
3. Credentials → Create Credentials → **OAuth client ID** → **Web
   application**.
4. Authorized redirect URI: `http://localhost:8000/api/channels/oauth/callback`
   (must exactly match `GOOGLE_OAUTH_REDIRECT_URI`).
5. Copy Client ID + Secret into `.env`.

---

## Testing Phase 3 locally

1. Complete the OAuth client setup above, including adding your test
   Google account under "Test users".
2. Log in as a normal user (register one if needed) → **Connect YouTube
   channel** → complete Google's consent screen.
3. You're redirected back to `http://localhost:5173/?channel_connected=1`
   with a green success banner, and the channel card appears showing its
   title, ID, and CONNECTED status.
4. Toggle **Automatic publishing** on/off and change the daily upload
   count — both persist (refresh the page to confirm).
5. Click **Disconnect** — the channel disappears from your dashboard.
   Reconnect the same channel via "Connect YouTube channel" again: it
   reappears with the same underlying identity (this matters once upload
   history exists in later phases — reconnecting never resets what's
   already been uploaded to that channel).
6. To see refresh/revocation handling: revoke the app's access directly
   from https://myaccount.google.com/permissions, then trigger any action
   that would use the channel's credentials in a later phase — the channel
   flips to `REVOKED`/`ERROR` status rather than failing silently.

## What to expect right now

- Admin Dashboard's "Connected YouTube channels" counter reflects real
  connections.
- Drive sources/scanning still work exactly as in Phase 2.
- The Phase 1–8 product loop is implemented. The hardening pass adds DB-backed OAuth state, stable Drive-ID duplicate protection, conservative uncertain-upload handling, validation, and monitoring.

---

## Project structure

```
ai-youtube-auto-publisher/
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py, config.py, database.py, models.py, schemas.py, security.py, deps.py
│   │   ├── services/
│   │   │   ├── drive_service.py
│   │   │   ├── token_crypto.py          # Fernet encryption for OAuth tokens
│   │   │   └── youtube_oauth_service.py # OAuth flow, refresh, revoke
│   │   └── routers/
│   │       ├── auth.py, admin.py, drive.py
│   │       └── channels.py               # connect/list/disconnect/settings
│   ├── alembic/  # 0001 initial, 0002 scan errors, 0003 duration, 0004 final hardening
│   └── create_admin.py
└── frontend/src/
    ├── api/ (client.js, driveSources.js, channels.js)
    ├── context/AuthContext.jsx
    ├── components/ (ProtectedRoute, Layout)
    └── pages/ (Login, Register, AdminDashboard, DriveSources, UserDashboard)
```

---


## Phases 4–8 implementation

The Phase 3 codebase has now been extended without changing the FastAPI + SQLAlchemy + PostgreSQL + APScheduler + React/Vite architecture.

### Upload lifecycle
- `UploadHistory` is created before any external upload call and uses the existing `UNIQUE(drive_video_id, channel_id)` constraint as the final duplicate guard.
- Statuses are `pending`, `uploading`, `success`, and `failed`. Successful rows retain the returned YouTube video ID.
- Failed uploads are recorded in `FailedUploads`; deterministic failures may be retried, while uncertain YouTube outcomes are marked `UNCERTAIN:` and are never blindly retried.
- Disconnect/reconnect never deletes channel rows or upload history.

### AI metadata
- `AI_PROVIDER=gemini` selects the provider-neutral Gemini implementation.
- Metadata is generated only from known Drive/file context; prompts explicitly prevent invented claims about unseen video content.
- AI failures become failed upload records instead of crashing the automation batch.

### Manual upload
- `POST /api/uploads/channels/{channel_id}/upload-now` performs the real Drive download, AI metadata generation, OAuth refresh, and YouTube resumable upload.
- Videos are staged only in a short-lived temporary file and deleted in `finally`; no permanent video storage is introduced.

### Automation
- APScheduler runs a 60-second watchdog tick (plus a retry-interval job) in the single FastAPI process.
- Daily publishing is driven from the DB, not the process: the admin sets exactly two anchor
  times (default 09:00 / 18:00, Asia/Kolkata) and each user's `daily_upload_count` is
  distributed around those anchors — 1/day picks one anchor, 2/day uses both, 3+/day splits
  ceil/floor between the anchors with randomized minute offsets.
- Each slot is claimed via `UNIQUE(channel_id, run_date, slot_index)`; the watchdog recomputes
  due-but-unclaimed slots every tick, so restarts catch up today's missed slots exactly once.
  If the instance sleeps through an entire calendar day, that day's slots are not recovered.
- One channel/video failure does not abort other work.

### Production migrations (Render)
Render does not run Alembic automatically. Either run `alembic upgrade head` against the
production `DATABASE_URL` after each deploy that adds a migration, or set the service start
command to `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

### User/admin API additions
- Users can view eligible videos, upload history, and automation runs.
- Admins can view recent automation runs and a health summary.
- Existing admin Drive-source deletion now refuses to remove sources with upload history, preserving foreign keys and historical duplicate protection; disabling a source is the safe alternative.

### Configuration added
- `GEMINI_MODEL` (default `gemini-2.5-flash`)
- `AI_REQUEST_TIMEOUT_SECONDS`
- `YOUTUBE_PRIVACY_STATUS` (default `public`)
- `YOUTUBE_DEFAULT_CATEGORY_ID` (default `22`)
- `YOUTUBE_UPLOAD_CHUNK_BYTES`

Final hardening adds Alembic migration `0004_final_hardening` for the server-side OAuth state table, upload attempt/status fields, the `uncertain` upload state, BIGINT Drive file sizes, and the PostgreSQL stable-Drive-ID duplicate guard. Existing records are preserved; no tables are dropped or recreated.


## Final hardening

**Phase 1–8: COMPLETE. Final hardening pass: COMPLETE.**

- OAuth state is unpredictable, server-side, one-time, expiring, and browser-bound.
- OAuth access/refresh tokens remain encrypted at rest and are never returned to the frontend.
- Duplicate protection uses the stable Google Drive file ID plus the YouTube channel, with a PostgreSQL trigger/advisory lock as the cross-source database guarantee.
- Upload states include `pending`, `uploading`, `success`, `failed`, and `uncertain`. An uncertain outcome is never blindly retried.
- Temporary Drive video files are deleted in `finally` blocks.
- Gemini output is validated before YouTube submission; provider failures are not treated as successful uploads.
- APScheduler is explicit about timezone and uses PostgreSQL advisory locks to prevent duplicate daily/retry execution across accidental multiple processes.
- YouTube processing/privacy status is recorded on a best-effort basis after a confirmed upload. Requested `public` visibility is not a guarantee when Google's unverified-project restrictions apply.

### Testing

Run from `backend/`:

```bash
pytest -q
python -m compileall -q app tests alembic
alembic check
```

Run from `frontend/`:

```bash
npm install
npm run build
```

The PostgreSQL concurrency test requires a real PostgreSQL database and must not be represented as passing when PostgreSQL is unavailable.
