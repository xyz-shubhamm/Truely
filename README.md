# Fake Job Detection Platform

This workspace contains a Python-only backend with a React frontend:

- `client/` - React + Vite frontend (Google OAuth login, analysis UI, history)
- `ml_service/` - FastAPI backend (auth, prediction API, history persistence)
- `artifacts/` - trained model and vectorizer files

## Database and auth

- Database: Supabase Postgres
- Auth: Google OAuth via Supabase Auth + app-level JWT from FastAPI
- Saved data: every user prediction is stored in `job_analyses`

## Setup

1. Configure root `.env` for backend:

	- `DATABASE_URL`
	- `JWT_SECRET`
	- `JWT_EXPIRE_MINUTES`
	- `SUPABASE_URL`
	- `SUPABASE_ANON_KEY`
	- `MODEL_DIR`

2. Configure frontend Supabase env in `client/.env`:

	- `VITE_SUPABASE_URL`
	- `VITE_SUPABASE_ANON_KEY`

3. Enable Google provider in Supabase Auth settings:

	- Authentication -> Providers -> Google -> Enable
	- Add Google OAuth client credentials
	- Add redirect URL: `http://localhost:5173/auth/callback`

4. Run schema SQL in Supabase SQL Editor (create `app_users` and `job_analyses` tables).

5. Install backend dependencies:

	- `pip install -r ml_service/requirements.txt`

6. Start backend:

	- `python -m uvicorn ml_service.app:app --host 127.0.0.1 --port 8000`

7. Start frontend:

	- `cd client`
	- `npm install`
	- `npm run dev`

## Auth flow

- User clicks Continue with Google in frontend
- Supabase OAuth completes on `/auth/callback`
- Frontend sends Supabase access token to backend `/auth/google`
- Backend returns app JWT used for protected API routes
