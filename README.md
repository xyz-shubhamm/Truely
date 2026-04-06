# Fake Job Detection Platform

This workspace contains a Python-only backend with a React frontend:

- `client/` - React + Vite frontend (signup/login, analysis UI, history)
- `ml_service/` - FastAPI backend (auth, prediction API, history persistence)
- `artifacts/` - trained model and vectorizer files

## Database and auth

- Database: Supabase Postgres
- Auth: App-level JWT tokens from FastAPI
- Saved data: every user prediction is stored in `job_analyses`

## Setup

1. Configure root `.env`:

	- `DATABASE_URL`
	- `JWT_SECRET`
	- `JWT_EXPIRE_MINUTES`
	- `MODEL_DIR`

2. Run schema SQL in Supabase SQL Editor (create `app_users` and `job_analyses` tables).

3. Install backend dependencies:

	- `pip install -r ml_service/requirements.txt`

4. Start backend:

	- `python -m uvicorn ml_service.app:app --host 127.0.0.1 --port 8000`

5. Start frontend:

	- `cd client`
	- `npm install`
	- `npm run dev`
