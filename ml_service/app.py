from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, MetaData, String, Table, create_engine, desc, func, select
from sqlalchemy.engine import Engine
import jwt
from jwt.exceptions import InvalidTokenError

ROOT_DIR = Path(__file__).resolve().parents[1]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file(ROOT_DIR / '.env')

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://postgres:FakeJobDETECTION%4010@db.fqzlylidjcincqxtdgzu.supabase.co:5432/postgres',
)
if DATABASE_URL.startswith('postgresql://') and '+psycopg' not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://', 1)

JWT_SECRET = os.getenv('JWT_SECRET', 'change-me-in-env')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRE_MINUTES = int(os.getenv('JWT_EXPIRE_MINUTES', '1440'))

# Use pre-trained HuggingFace model
GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.1-8b-instant')
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '').strip()
GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'

app = FastAPI(title='Fake Job Detection ML API', version='2.0.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

metadata = MetaData()
users_table = Table(
    'app_users',
    metadata,
    Column('id', Integer, primary_key=True),
    Column('email', String(255), unique=True, nullable=False),
    Column('name', String(120), nullable=False),
    Column('password_hash', String(255), nullable=False),
    Column('email_verified', Boolean, nullable=False, server_default='false'),
    Column('email_verification_token', String(255)),
    Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column('verified_at', DateTime(timezone=True)),
)
analyses_table = Table(
    'job_analyses',
    metadata,
    Column('id', Integer, primary_key=True),
    Column('user_id', Integer, nullable=False),
    Column('input_payload', JSON, nullable=False),
    Column('prediction_payload', JSON, nullable=False),
    Column('risk_score', Float, nullable=False),
    Column('is_fake', Boolean, nullable=False),
    Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
)

engine: Engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
auth_scheme = HTTPBearer(auto_error=False)


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    iterations = 120000
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, digest_hex = stored_hash.split('$', 3)
        if algorithm != 'pbkdf2_sha256':
            return False
        calculated = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            int(iterations),
        ).hex()
        return hmac.compare_digest(calculated, digest_hex)
    except Exception:
        return False

groq_ready = bool(GROQ_API_KEY)


class JobPosting(BaseModel):
    title: str = ''
    company_profile: str = ''
    description: str = ''
    requirements: str = ''
    benefits: str = ''
    location: str = ''
    department: str = ''
    employment_type: str = ''
    required_experience: str = ''
    required_education: str = ''
    industry: str = ''
    function: str = ''


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


def _create_access_token(subject: str) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        'sub': subject,
        'iat': now,
        'exp': now + dt.timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _normalize_email(email: str) -> str:
    return (email or '').strip().lower()


def _serialize_user(user_row: Any) -> dict[str, Any]:
    return {
        'id': user_row.id,
        'email': user_row.email,
        'name': user_row.name,
        'created_at': user_row.created_at.isoformat() if user_row.created_at else None,
    }


def _get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(auth_scheme)) -> dict[str, Any]:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail='Missing authorization token')

    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get('sub', 0))
    except (InvalidTokenError, ValueError):
        raise HTTPException(status_code=401, detail='Invalid token') from None

    with engine.connect() as connection:
        row = connection.execute(select(users_table).where(users_table.c.id == user_id)).mappings().first()
        if row is None:
            raise HTTPException(status_code=401, detail='User not found')
        return dict(row)


def _build_posting_text(posting: JobPosting) -> str:
    parts = [
        f"Title: {posting.title}",
        f"Company: {posting.company_profile}",
        f"Description: {posting.description}",
        f"Requirements: {posting.requirements}",
        f"Benefits: {posting.benefits}",
        f"Location: {posting.location}",
        f"Department: {posting.department}",
        f"Employment type: {posting.employment_type}",
        f"Experience: {posting.required_experience}",
        f"Education: {posting.required_education}",
        f"Industry: {posting.industry}",
        f"Function: {posting.function}",
    ]
    return '\n'.join(part for part in parts if part.strip())


def _extract_heuristics(posting: JobPosting, text: str) -> tuple[float, list[dict[str, str]]]:
    normalized_text = text.lower()
    normalized_company = (posting.company_profile or '').lower()

    signals: list[dict[str, str]] = []
    score = 0.0

    def add_signal(label: str, detail: str, weight: float, evidence: str) -> None:
        nonlocal score
        signals.append({'label': label, 'detail': detail, 'evidence': evidence})
        score = min(1.0, score + weight)

    if re.search(r'entry\s+fee|registration\s+fee|deposit\s+required|upfront\s+payment|pay\s+.*before|processing\s+fee', normalized_text):
        add_signal(
            'Upfront Payment Request',
            'The posting asks the candidate to pay before getting the job.',
            0.85,
            'entry fee / upfront payment',
        )

    if re.search(r'wire\s+money|send\s+money|payment\s+before|transfer\s+fee', normalized_text):
        add_signal(
            'Money Transfer Demand',
            'The posting mentions sending money or paying before onboarding.',
            0.80,
            'payment / wire transfer',
        )

    if re.search(r'gmail\.com|yahoo\.com|hotmail\.com|telegram|whatsapp', normalized_text) and not re.search(r'company|corporate|official|domain|\.com|\.io|\.org', normalized_company):
        add_signal(
            'Personal Contact Channel',
            'The posting relies on personal email or chat channels instead of a proper company domain.',
            0.45,
            'personal email / chat only',
        )

    if re.search(r'apply\s+now|urgent\s+hiring|join\s+immediately|limited\s+slots|start\s+today|no\s+experience\s+needed', normalized_text):
        add_signal(
            'Urgency Pressure',
            'The language pushes immediate action or unrealistic speed.',
            0.30,
            'urgent / apply now',
        )

    if re.search(r'quick\s+cash|easy\s+money|high\s+salary|30lpa|50lpa|70lpa', normalized_text):
        add_signal(
            'Suspicious Reward Language',
            'The compensation language looks unusually aggressive or too good to be true.',
            0.20,
            'high salary / easy money',
        )

    description_text = (posting.description or '').strip()
    short_description = len(description_text.split()) < 12
    missing_supporting_fields = not any([
        posting.requirements.strip(),
        posting.benefits.strip(),
        posting.company_profile.strip(),
    ])
    if short_description and missing_supporting_fields:
        add_signal(
            'Thin Job Detail',
            'The posting is too sparse to be a credible hiring listing.',
            0.15,
            'very short or incomplete posting',
        )

    return min(score, 1.0), signals


def _calibrate_risk_score(model_fake_probability: float, heuristic_probability: float, signals: list[dict[str, str]]) -> float:
    """
    Turn raw model output into a smoother 0-100 risk score.
    Keeps obvious scams high, but avoids fake 0/100 extremes.
    """
    combined_probability = (0.58 * model_fake_probability) + (0.42 * heuristic_probability)

    if signals:
        combined_probability = max(combined_probability, min(0.95, heuristic_probability + 0.12))

    risk_score = 100.0 * combined_probability

    if any(signal['label'] in {'Upfront Payment Request', 'Money Transfer Demand'} for signal in signals):
        risk_score = max(risk_score, 85.0)
    elif len(signals) >= 2:
        risk_score = max(risk_score, 78.0)
    elif signals:
        risk_score = max(risk_score, 62.0)

    risk_score = max(8.0, min(risk_score, 95.0))
    return round(risk_score, 2)


def _parse_probability(value: Any, default: float = 0.5) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(parsed, 1.0))


def _heuristic_fallback_result(posting: JobPosting, text: str, reason: str) -> dict[str, Any]:
    heuristic_probability, heuristic_signals = _extract_heuristics(posting, text)
    prediction = 'fake' if heuristic_probability >= 0.5 else 'real'
    confidence = max(heuristic_probability, 1.0 - heuristic_probability)

    return {
        'prediction': prediction,
        'threshold': 0.5,
        'real_probability': round(1.0 - heuristic_probability, 6),
        'fake_probability': round(heuristic_probability, 6),
        'confidence': round(confidence, 6),
        'input_length': len(text),
        'model_label': f'heuristic_fallback:{reason}',
        'model_fake_probability': round(heuristic_probability, 6),
        'heuristic_fake_probability': round(heuristic_probability, 6),
        'risk_score': None,
        'risk_signals': heuristic_signals,
    }


def _call_groq_classifier(posting: JobPosting, text: str) -> dict[str, Any]:
    if not GROQ_API_KEY:
        return _heuristic_fallback_result(posting, text, 'missing_api_key')

    prompt = {
        'title': posting.title,
        'company_profile': posting.company_profile,
        'description': posting.description,
        'requirements': posting.requirements,
        'benefits': posting.benefits,
        'location': posting.location,
        'department': posting.department,
        'employment_type': posting.employment_type,
        'required_experience': posting.required_experience,
        'required_education': posting.required_education,
        'industry': posting.industry,
        'function': posting.function,
    }

    system_message = (
        'You are a strict job-posting fraud classifier. '
        'Return only JSON with these keys: prediction, fake_probability, real_probability, confidence, model_label. '
        'prediction must be either "fake" or "real". '
        'fake_probability and real_probability must be numbers from 0 to 1 that sum to 1. '
        'confidence must be a number from 0 to 1. '
        'model_label should be a short label describing the strongest signal. '
        'Be conservative and base your answer only on the provided posting.'
    )
    user_message = json.dumps(prompt, ensure_ascii=True)

    request_body = json.dumps(
        {
            'model': GROQ_MODEL,
            'messages': [
                {'role': 'system', 'content': system_message},
                {'role': 'user', 'content': user_message},
            ],
            'temperature': 0,
            'max_tokens': 200,
        }
    ).encode('utf-8')

    request = urllib.request.Request(
        GROQ_API_URL,
        data=request_body,
        headers={
            'Authorization': f'Bearer {GROQ_API_KEY}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='ignore') if exc.fp else ''
        print(f'Groq inference failed ({exc.code}): {body[:200]}')
        return _heuristic_fallback_result(posting, text, f'http_{exc.code}')
    except Exception as exc:
        print(f'Groq inference failed: {exc}')
        return _heuristic_fallback_result(posting, text, 'request_error')

    choices = payload.get('choices') or []
    if not choices:
        return _heuristic_fallback_result(posting, text, 'no_choices')

    message = choices[0].get('message') or {}
    content = (message.get('content') or '').strip()
    if not content:
        return _heuristic_fallback_result(posting, text, 'empty_content')

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', content, re.S)
        if not match:
            print(f'Groq inference returned non-JSON content: {content[:200]}')
            return _heuristic_fallback_result(posting, text, 'invalid_json')
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            print(f'Groq inference returned malformed JSON block: {content[:200]}')
            return _heuristic_fallback_result(posting, text, 'malformed_json')

    fake_probability = _parse_probability(parsed.get('fake_probability'))
    real_probability = _parse_probability(parsed.get('real_probability'), default=1.0 - fake_probability)
    confidence = _parse_probability(parsed.get('confidence'), default=max(fake_probability, real_probability))
    prediction = str(parsed.get('prediction', '')).strip().lower()
    if prediction not in {'fake', 'real'}:
        prediction = 'fake' if fake_probability >= 0.5 else 'real'

    model_label = str(parsed.get('model_label', '')).strip() or ('fake' if prediction == 'fake' else 'real')

    if abs((fake_probability + real_probability) - 1.0) > 0.05:
        real_probability = max(0.0, min(1.0, 1.0 - fake_probability))

    return {
        'prediction': prediction,
        'threshold': 0.5,
        'real_probability': round(real_probability, 6),
        'fake_probability': round(fake_probability, 6),
        'confidence': round(confidence, 6),
        'input_length': len(text),
        'model_label': model_label,
        'model_fake_probability': round(fake_probability, 6),
        'heuristic_fake_probability': 0.0,
        'risk_score': None,
        'risk_signals': [],
    }


@app.on_event('startup')
def load_artifacts() -> None:
    metadata.create_all(engine)
    print(f'Groq model configured: {GROQ_MODEL}')
    print(f'Groq API key configured: {bool(GROQ_API_KEY)}')


@app.get('/health')
def health() -> dict[str, Any]:
    return {
        'status': 'ok',
        'service': 'python-backend-ml',
        'model_loaded': bool(GROQ_API_KEY),
        'model_type': 'groq_chat_completion',
        'model_id': GROQ_MODEL,
    }


@app.get('/api/info')
def api_info() -> dict[str, Any]:
    return {
        'service': 'python-backend-ml',
        'model_type': 'groq_chat_completion',
        'model_id': GROQ_MODEL,
        'ready': bool(GROQ_API_KEY),
    }


@app.post('/auth/signup')
def signup(payload: SignupRequest) -> dict[str, Any]:
    email = _normalize_email(payload.email)

    with engine.begin() as connection:
        existing = connection.execute(select(users_table).where(users_table.c.email == email)).mappings().first()
        if existing:
            raise HTTPException(status_code=409, detail='Email already registered')

        password_hash = _hash_password(payload.password)
        inserted = connection.execute(
            users_table.insert().values(
                email=email,
                name=payload.name.strip(),
                password_hash=password_hash,
                email_verified=True,
                email_verification_token=None,
                verified_at=dt.datetime.now(dt.timezone.utc),
            ).returning(users_table)
        ).mappings().first()

    auth_token = _create_access_token(str(inserted['id']))
    return {
        'message': 'Account created successfully.',
        'token': auth_token,
        'user': _serialize_user(inserted),
    }


@app.post('/auth/login')
def login(payload: LoginRequest) -> dict[str, Any]:
    email = _normalize_email(payload.email)

    with engine.connect() as connection:
        row = connection.execute(select(users_table).where(users_table.c.email == email)).mappings().first()

    if not row:
        raise HTTPException(status_code=401, detail='Invalid email or password')

    if not _verify_password(payload.password, row['password_hash']):
        raise HTTPException(status_code=401, detail='Invalid email or password')

    token = _create_access_token(str(row['id']))
    return {'token': token, 'user': _serialize_user(row)}



@app.get('/auth/me')
def me(current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
    return {'user': _serialize_user(current_user)}


def _predict_from_posting(posting: JobPosting) -> dict[str, Any]:
    text = _build_posting_text(posting).strip()
    if not text:
        raise HTTPException(status_code=400, detail='Empty job posting text')

    # Keep the semantic structure but stay within a safe token-sized window.
    text = text[:4000]

    groq_result = _call_groq_classifier(posting, text)
    confidence = float(groq_result['confidence'])
    model_fake_probability = float(groq_result['model_fake_probability'])

    heuristic_probability, heuristic_signals = _extract_heuristics(posting, text)

    risk_score = _calibrate_risk_score(model_fake_probability, heuristic_probability, heuristic_signals)
    fake_probability = risk_score / 100.0
    real_probability = 1.0 - fake_probability
    is_fake = risk_score >= 50.0

    prediction = 'fake' if is_fake else 'real'

    return {
        'prediction': prediction,
        'threshold': 0.5,
        'real_probability': round(real_probability, 6),
        'fake_probability': round(fake_probability, 6),
        'confidence': round(confidence, 6),
        'input_length': len(text),
        'model_label': groq_result['model_label'],
        'model_fake_probability': round(model_fake_probability, 6),
        'heuristic_fake_probability': round(heuristic_probability, 6),
        'risk_score': risk_score,
        'risk_signals': heuristic_signals,
    }


@app.post('/api/predict')
def api_predict(posting: JobPosting, current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
    result = _predict_from_posting(posting)
    risk_score = round(float(result.get('fake_probability', 0)) * 100, 2)

    with engine.begin() as connection:
        connection.execute(
            analyses_table.insert().values(
                user_id=current_user['id'],
                input_payload=posting.model_dump(),
                prediction_payload=result,
                risk_score=risk_score,
                is_fake=result['prediction'] == 'fake',
            )
        )

    return {'success': True, 'result': result}


@app.get('/api/history')
def api_history(limit: int = 20, current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 100))

    with engine.connect() as connection:
        rows = connection.execute(
            select(analyses_table)
            .where(analyses_table.c.user_id == current_user['id'])
            .order_by(desc(analyses_table.c.created_at))
            .limit(safe_limit)
        ).mappings().all()

    items = [
        {
            'id': row['id'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            'risk_score': row['risk_score'],
            'is_fake': row['is_fake'],
            'input_payload': row['input_payload'],
            'prediction_payload': row['prediction_payload'],
        }
        for row in rows
    ]
    return {'items': items}


@app.delete('/api/history')
def api_clear_history(current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
    with engine.begin() as connection:
        result = connection.execute(
            analyses_table.delete().where(analyses_table.c.user_id == current_user['id'])
        )

    return {'success': True, 'deleted_count': int(result.rowcount or 0)}


@app.delete('/api/history/{analysis_id}')
def api_delete_history_item(analysis_id: int, current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
    with engine.begin() as connection:
        result = connection.execute(
            analyses_table.delete().where(
                analyses_table.c.id == analysis_id,
                analyses_table.c.user_id == current_user['id'],
            )
        )

    deleted = int(result.rowcount or 0)
    if deleted == 0:
        raise HTTPException(status_code=404, detail='History item not found')

    return {'success': True, 'deleted_id': analysis_id}
