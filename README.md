# LearnTogether

A small internal tool where people post what they want to learn and add a +1 to topics suggested by others.

- **Backend:** FastAPI, SQLAlchemy 2, SQLite
- **Frontend:** plain HTML, CSS and JavaScript served by the same app
- **Auth:** Google OAuth 2.0 / OpenID Connect (Authlib), with an optional development-only sign-in
- **Tests:** pytest

## Setup

Requires Python 3.12+.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
```

Edit `.env` and set at least `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Run

```bash
python init_db.py                                   # optional, tables are also created on startup
uvicorn app.main:create_app --factory --reload
```

Open http://localhost:8000. Signed-out visitors are sent to `/login`.

## Configuration

All settings come from environment variables (loaded from `.env` if present).

| Variable | Required | Description |
| --- | --- | --- |
| `APP_ENV` | no | `development` (default) or `production`. |
| `SECRET_KEY` | yes | Signs the session cookie. At least 32 characters in production. |
| `DATABASE_URL` | no | Defaults to `sqlite:///./learntogether.db`. |
| `GOOGLE_CLIENT_ID` | in production | OAuth client ID from Google Cloud. |
| `GOOGLE_CLIENT_SECRET` | in production | OAuth client secret. |
| `OAUTH_REDIRECT_URI` | no | Override the callback URL (useful behind a reverse proxy). Defaults to `<host>/auth/callback`. |
| `DEV_AUTH_ENABLED` | no | `true` enables development sign-in. Only honoured when `APP_ENV=development`. |

The app refuses to start if the configuration is unsafe: missing `SECRET_KEY`, an unknown `APP_ENV`, or in production a short secret, missing Google credentials, or `DEV_AUTH_ENABLED=true`.

## Google sign-in

1. In [Google Cloud Console](https://console.cloud.google.com/apis/credentials), configure the OAuth consent screen (scopes: `openid`, `email`, `profile`).
2. Create credentials → **OAuth client ID** → application type **Web application**.
3. Add an authorised redirect URI for every place the app runs, e.g.
   - `http://localhost:8000/auth/callback`
   - `https://learn.example.com/auth/callback`
4. Put the client ID and secret in `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, then restart.

How the flow is protected:

- Authlib generates `state`, `nonce` and a PKCE (S256) verifier, keeps them in the signed session, and checks them on the callback. A callback with a missing or unknown `state` is rejected.
- The ID token is verified with Google's published keys (discovered from Google's OpenID configuration), including the nonce.
- Accounts whose email isn't verified by Google are refused.
- On sign-in the session is cleared and reissued, so nothing from before sign-in carries over.

## Development-only sign-in

If you don't have Google credentials yet, set both:

```env
APP_ENV=development
DEV_AUTH_ENABLED=true
```

The login page then shows a clearly labelled "Development sign-in" form where you type a display name. It creates a real user row (`subject = dev:<name>`), so topics and votes work exactly as they do for Google users. This is meant for local testing only:

- the `/auth/dev-login` route is not registered unless both settings are present;
- the app will not start with `APP_ENV=production` and `DEV_AUTH_ENABLED=true`.

## Security notes

- Sessions use a signed, `HttpOnly`, `SameSite=Lax` cookie. With `APP_ENV=production` it's also `Secure`, so serve the app over HTTPS.
- Every state-changing request (`POST /api/topics`, votes, logout, dev sign-in) must send the session's CSRF token in an `X-CSRF-Token` header.
- Responses carry a strict Content-Security-Policy (`default-src 'self'`, no inline scripts), `X-Frame-Options: DENY` and `nosniff`.
- `.env` and `*.db` files are git-ignored. Never commit real credentials.

## API

All errors return JSON as `{"detail": "<message>"}`.

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/api/topics` | optional | Topics with `vote_count`, sorted by count (desc), then oldest first. `has_voted` is set for the signed-in user. |
| `POST` | `/api/topics` | required + CSRF | Body `{"name": "..."}`. `201`, `409` duplicate, `422` invalid. |
| `POST` | `/api/topics/{id}/vote` | required + CSRF | `201`, `404` unknown topic, `409` already voted. |
| `GET` | `/api/me` | required | Current user and the session's CSRF token. `401` when signed out. |
| `GET` | `/auth/options` | none | Which sign-in methods are available, plus a CSRF token for the login page. |
| `GET` | `/auth/google`, `/auth/callback` | none | Google OAuth flow. |
| `POST` | `/auth/logout` | CSRF | Ends the session. |

Topic rules: whitespace is trimmed and collapsed, 1–100 characters, at least one letter or number. Duplicates are detected case-insensitively on the cleaned name (`normalized_name`, unique in the database). Adding a topic doesn't add a vote; the creator can +1 it like anyone else.

## Database

Three tables, created automatically on startup or with `python init_db.py`:

- `users`: `id`, `subject` (unique; Google `sub` or `dev:<name>`), `email`, `name`, `created_at`
- `topics`: `id`, `name`, `normalized_name` (unique), `created_by` → `users.id` (indexed), `created_at`
- `topic_votes`: `id`, `topic_id` → `topics.id` (cascade delete), `user_id` → `users.id` (indexed), `created_at`, unique on `(topic_id, user_id)`

Vote counts are always computed from `topic_votes`. SQLite foreign keys are switched on for every connection.

There are no migrations. If you change the models, delete `learntogether.db` (local data only) or add Alembic.

## Tests

```bash
pytest -q
```

Each test gets its own temporary SQLite database. The suite covers topic creation and validation, duplicate detection, list ordering and counts, one-vote-per-user (both through the API and against the database constraint), unknown topic IDs, unauthenticated and CSRF-less writes, the configuration safety checks, and the Google flow: authorisation redirect parameters, state rejection, unverified email, and successful sign-in. Google's discovery document and token exchange are stubbed in tests, so no network access is needed.

## Project layout

```
app/
  main.py            app factory: middleware, routers, static files
  config.py          settings and startup safety checks
  database.py        engine, session dependency, table creation
  models.py          SQLAlchemy models
  schemas.py         Pydantic request/response models and topic validation
  security.py        current-user and CSRF dependencies
  routers/auth.py    login page, Google OAuth, dev sign-in, logout
  routers/topics.py  topics, votes, /api/me
  static/            index.html, login.html, styles.css, app.js, login.js
tests/
init_db.py
```
