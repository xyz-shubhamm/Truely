# Truely - Intelligent Job Scam Detection Platform

Truely is a premium career protection platform that uses AI forensics and LLM semantics to detect recruitment fraud.

## Key Improvements (v2.0)

- **🚀 Instant Login**: Optimized Google OAuth sync and added a "Verifying Session" loading state to eliminate redirect delays.
- **🧠 GPT-Powered PDF Parsing**: Replaced regex-based extraction with LLM-based intelligence (Groq/OpenAI) for 99% accuracy in company/title extraction.
- **🛡️ Semantic Scam Audit**: Every job analysis now includes a deep-semantic audit by an LLM to catch sophisticated fraud patterns that traditional models miss.
- **💎 Premium UI**: Unified dark mode with smooth transitions and glassmorphism.

## Setup & Running

### 1. Environment Configuration
The platform uses a unified `.env` file in the root directory. Ensure it contains:
- `DATABASE_URL`: Supabase Postgres connection string.
- `GROQ_API_KEY`: Required for fast LLM features (Free tier available).
- `OPENAI_API_KEY`: Fallback for LLM features.
- `SUPABASE_URL` & `SUPABASE_ANON_KEY`: From your Supabase project.

### 2. Backend Installation (Python 3.9+)
```bash
# Navigate to root
pip install -r ml_service/requirements.txt
```

### 3. Frontend Installation
```bash
cd client
npm install
```

### 4. Running the Platform
Open two terminal windows:

**Terminal 1: Backend**
```bash
# From root
python -m uvicorn ml_service.app:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2: Frontend**
```bash
cd client
npm run dev
```

## Technology Stack
- **Frontend**: React, Vite, TailwindCSS (Vanilla CSS customized), Supabase Auth.
- **Backend**: FastAPI, SQLAlchemy, PyPDF, Scikit-learn.
- **AI**: Groq (Llama-3.1), OpenAI (GPT-4o-mini), DistilBERT (Local).
