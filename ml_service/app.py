from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import uuid
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

import joblib
import pypdf
from fastapi import Depends, FastAPI, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, MetaData, String, Table, create_engine, desc, func, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
import jwt
from jwt.exceptions import InvalidTokenError
from company_researcher import research_company

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
    'postgresql://postgres:FakeJobDetection%4010@db.kqfrmxbhmrvoghwgntnd.supabase.co:5432/postgres?sslmode=require',
)
if DATABASE_URL.startswith('postgresql://') and '+psycopg' not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://', 1)

JWT_SECRET = os.getenv('JWT_SECRET', 'change-me-in-env')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRE_MINUTES = int(os.getenv('JWT_EXPIRE_MINUTES', '1440'))
MODEL_DIR = Path(os.getenv('MODEL_DIR', 'artifacts'))
SUPABASE_URL = os.getenv('SUPABASE_URL', '').strip().rstrip('/')
SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY', '').strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '').strip()

LOCAL_MODEL_PATH = Path(os.getenv('LOCAL_MODEL_PATH', str(MODEL_DIR / 'personal_job_model.pkl')))
THRESHOLD_CONFIG_PATH = Path(os.getenv('FRAUD_THRESHOLD_CONFIG_PATH', str(MODEL_DIR / 'fraud_threshold.json')))
FRAUD_RISK_THRESHOLD = float(os.getenv('FRAUD_RISK_THRESHOLD', '35'))
LOCAL_MODEL_PROBABILITY_THRESHOLD = float(os.getenv('LOCAL_MODEL_PROBABILITY_THRESHOLD', '0.52'))

app = FastAPI(title='Truely ML API', version='2.0.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


def _create_engine_for_url(database_url: str) -> Engine:
    connect_args: dict[str, Any] = {}
    if database_url.startswith('postgresql') and 'connect_timeout=' not in database_url:
        connect_args['connect_timeout'] = 5
    return create_engine(database_url, pool_pre_ping=True, future=True, connect_args=connect_args)


def _ensure_job_analyses_schema_compatibility() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if 'job_analyses' not in existing_tables:
        return

    existing_columns = {column['name'] for column in inspector.get_columns('job_analyses')}
    is_postgres = engine.dialect.name == 'postgresql'
    column_types = {
        'input_payload': 'JSONB' if is_postgres else 'JSON',
        'prediction_payload': 'JSONB' if is_postgres else 'JSON',
        'risk_score': 'DOUBLE PRECISION' if is_postgres else 'REAL',
        'is_fake': 'BOOLEAN' if is_postgres else 'BOOLEAN',
        'created_at': 'TIMESTAMPTZ' if is_postgres else 'DATETIME',
    }
    missing_columns = [name for name in column_types.keys() if name not in existing_columns]
    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name in missing_columns:
            column_type = column_types[column_name]
            ddl = f'ALTER TABLE job_analyses ADD COLUMN {column_name} {column_type}'
            connection.execute(text(ddl))

    print(f'Added missing columns to job_analyses: {", ".join(missing_columns)}')


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
app_analyses_table = Table(
    'app_job_analyses',
    metadata,
    Column('id', Integer, primary_key=True),
    Column('user_id', Integer, nullable=False),
    Column('input_payload', JSON, nullable=False),
    Column('prediction_payload', JSON, nullable=False),
    Column('risk_score', Float, nullable=False),
    Column('is_fake', Boolean, nullable=False),
    Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
)

research_history_table = Table(
    'app_research_history',
    metadata,
    Column('id', Integer, primary_key=True),
    Column('user_id', Integer, nullable=False),
    Column('company', String(255), nullable=False),
    Column('role', String(255)),
    Column('location', String(255)),
    Column('result_payload', JSON),
    Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
)


def _refresh_analyses_table_binding() -> None:
    global analyses_table, JOB_ANALYSES_USER_ID_IS_UUID

    reflected = Table('job_analyses', MetaData(), autoload_with=engine)
    analyses_table = reflected
    JOB_ANALYSES_USER_ID_IS_UUID = 'uuid' in str(reflected.c.user_id.type).lower()


def _analysis_user_id_value(user_id: Any) -> Any:
    if JOB_ANALYSES_USER_ID_IS_UUID:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f'truely-user:{user_id}'))

    try:
        return int(user_id)
    except (TypeError, ValueError):
        return user_id


def _build_analysis_insert_values(current_user_id: Any, posting: JobPosting, result: dict[str, Any], risk_score: float) -> dict[str, Any]:
    posting_payload = posting.model_dump()
    values: dict[str, Any] = {
        'user_id': _analysis_user_id_value(current_user_id),
        'input_payload': posting_payload,
        'prediction_payload': result,
        'risk_score': risk_score,
        'is_fake': result.get('prediction') == 'fake',
    }

    legacy_mappings = {
        'title': posting_payload.get('title', ''),
        'company_name': posting_payload.get('company_profile', ''),
        'company_profile': posting_payload.get('company_profile', ''),
        'description': posting_payload.get('description', ''),
        'requirements': posting_payload.get('requirements', ''),
        'benefits': posting_payload.get('benefits', ''),
        'location': posting_payload.get('location', ''),
        'department': posting_payload.get('department', ''),
        'employment_type': posting_payload.get('employment_type', ''),
        'required_experience': posting_payload.get('required_experience', ''),
        'required_education': posting_payload.get('required_education', ''),
        'industry': posting_payload.get('industry', ''),
        'function': posting_payload.get('function', ''),
        'rate': risk_score,
        'status': 'pending',
    }

    available_columns = {column.name for column in analyses_table.columns}
    for key, value in legacy_mappings.items():
        if key in available_columns and key not in values:
            values[key] = value

    for column in analyses_table.columns:
        name = column.name
        if name in values:
            continue
        if column.primary_key or column.autoincrement:
            continue
        if column.server_default is not None or column.nullable:
            continue

        column_type = str(column.type).lower()
        enum_values = getattr(column.type, 'enums', None)
        if enum_values:
            values[name] = 'pending' if 'pending' in enum_values else enum_values[0]
        elif any(token in column_type for token in ('char', 'text')):
            values[name] = ''
        elif 'bool' in column_type:
            values[name] = False
        elif any(token in column_type for token in ('int', 'numeric', 'real', 'double', 'float')):
            values[name] = 0
        elif 'json' in column_type:
            values[name] = {}
        elif 'uuid' in column_type:
            values[name] = str(uuid.uuid4())
        elif any(token in column_type for token in ('date', 'time')):
            values[name] = dt.datetime.now(dt.timezone.utc)

    return values


def _build_app_analysis_insert_values(current_user_id: Any, posting: JobPosting, result: dict[str, Any], risk_score: float) -> dict[str, Any]:
    try:
        user_id = int(current_user_id)
    except (TypeError, ValueError):
        user_id = 0

    return {
        'user_id': user_id,
        'input_payload': posting.model_dump(),
        'prediction_payload': result,
        'risk_score': risk_score,
        'is_fake': result.get('prediction') == 'fake',
    }

engine: Engine = _create_engine_for_url(DATABASE_URL)
auth_scheme = HTTPBearer(auto_error=False)
JOB_ANALYSES_USER_ID_IS_UUID = False
DATABASE_READY = True


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

local_model_ready = False
local_model_label = ''
local_model_artifact: Any = None


def _load_threshold_config() -> None:
    global FRAUD_RISK_THRESHOLD, LOCAL_MODEL_PROBABILITY_THRESHOLD

    if not THRESHOLD_CONFIG_PATH.exists():
        return

    try:
        payload = json.loads(THRESHOLD_CONFIG_PATH.read_text(encoding='utf-8'))
        configured = float(payload.get('fraud_risk_threshold_percent', FRAUD_RISK_THRESHOLD))
        FRAUD_RISK_THRESHOLD = max(5.0, min(99.0, configured))
        model_threshold = payload.get('selected_probability_threshold')
        if model_threshold is not None:
            try:
                LOCAL_MODEL_PROBABILITY_THRESHOLD = max(0.05, min(0.95, float(model_threshold)))
            except (TypeError, ValueError):
                pass
        print(f'Loaded fraud risk threshold from config: {FRAUD_RISK_THRESHOLD:.2f}%')
    except Exception as exc:
        print(f'Failed to load threshold config ({THRESHOLD_CONFIG_PATH}): {exc}')


def _ensure_local_model_loaded() -> bool:
    global local_model_artifact, local_model_ready, local_model_label

    if local_model_artifact is not None and local_model_ready:
        return True

    try:
        local_model_artifact = joblib.load(LOCAL_MODEL_PATH)
        local_model_ready = True
        local_model_label = f'local_pkl:{LOCAL_MODEL_PATH.name}'
        return True
    except Exception as exc:
        local_model_artifact = None
        local_model_ready = False
        local_model_label = ''
        print(f'Local model load failed ({LOCAL_MODEL_PATH}): {exc}')
        return False


class JobPosting(BaseModel):
    title: str = ''
    company_profile: str = ''
    description: str = ''
    hr_email: str = ''


class GoogleAuthRequest(BaseModel):
    access_token: str = Field(min_length=20, max_length=4096)


class EmailSignupRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=6, max_length=100)
    name: str = Field(min_length=1, max_length=120)


class EmailLoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1, max_length=100)


def _create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        'sub': subject,
        'iat': now,
        'exp': now + dt.timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _supabase_auth_get(path: str, access_token: str) -> dict[str, Any]:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(status_code=500, detail='Supabase auth is not configured')

    endpoint = f'{SUPABASE_URL}/auth/v1{path}'
    req = urlrequest.Request(
        endpoint,
        method='GET',
        headers={
            'apikey': SUPABASE_ANON_KEY,
            'Authorization': f'Bearer {access_token}',
        },
    )

    try:
        with urlrequest.urlopen(req, timeout=20) as response:
            raw = response.read().decode('utf-8').strip()
            return json.loads(raw) if raw else {}
    except urlerror.HTTPError:
        raise HTTPException(status_code=401, detail='Invalid Google session token') from None
    except urlerror.URLError:
        raise HTTPException(status_code=502, detail='Unable to reach Supabase auth service') from None


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

    fallback_user = {
        'id': user_id,
        'email': _normalize_email(str(payload.get('email', ''))),
        'name': str(payload.get('name', '')).strip() or 'User',
        'created_at': None,
    }

    if not DATABASE_READY:
        if fallback_user['email']:
            return fallback_user
        raise HTTPException(status_code=503, detail='Database not ready')

    try:
        with engine.connect() as connection:
            row = connection.execute(select(users_table).where(users_table.c.id == user_id)).mappings().first()
    except SQLAlchemyError:
        if fallback_user['email']:
            return fallback_user
        raise HTTPException(status_code=503, detail='Database unavailable') from None

    if row is None:
        if fallback_user['email']:
            return fallback_user
        raise HTTPException(status_code=401, detail='User not found')
    return dict(row)


def _build_posting_text(posting: JobPosting) -> str:
    parts = [
        f"Title: {posting.title}",
        f"Company: {posting.company_profile}",
        f"Description: {posting.description}",
    ]
    return '\n'.join(part for part in parts if part.strip())


def _is_job_posting(text: str) -> bool:
    """Check if the text content is likely a job posting."""
    normalized = text.lower()
    
    # Core Job Description sections/headers (Higher weight)
    core_keywords = [
        'responsibilities', 'requirements', 'qualifications', 'experience',
        'salary', 'benefits', 'job description', 'duties', 'who you are',
        'what you will do', 'minimum qualifications', 'preferred qualifications',
        'about the role', 'what we offer', 'equal opportunity employer'
    ]
    
    # Contextual Job words (Lower weight)
    context_keywords = [
        'hiring', 'recruiting', 'candidate', 'opportunity', 'career',
        'intern', 'full-time', 'part-time', 'contract', 'engineer',
        'developer', 'manager', 'software', 'location', 'remote', 'apply'
    ]
    
    core_matches = sum(1 for word in core_keywords if word in normalized)
    context_matches = sum(1 for word in context_keywords if word in normalized)
    
    # Also check for structural patterns like "About [Company]" or "Apply now"
    structural_patterns = [
        r'about\s+(?:us|the\s+company|the\s+role)',
        r'apply\s+(?:now|here|online)',
        r'send\s+(?:your\s+)?cv|resume',
        r'looking\s+for\s+a',
        r'join\s+our\s+team'
    ]
    has_structural = any(re.search(pattern, normalized) for pattern in structural_patterns)
    
    # Heuristic scoring
    score = (core_matches * 2) + context_matches + (3 if has_structural else 0)
    
    # Require a decent score (at least 4) to be considered a job posting
    return score >= 4


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

    if re.search(r'starter\s+kit|buy\s+kit|recruit\s+others|downline|network\s+marketing|mlm|multi[-\s]?level\s+marketing', normalized_text):
        add_signal(
            'MLM Recruitment Pattern',
            'The posting resembles referral-chain or kit-purchase recruitment, which is high risk for scams.',
            0.65,
            'starter kit / recruit others',
        )

    if re.search(r'\b(penis|sexual|sex\s+chat|escort|adult\s+content|porn|nude|intimate\s+service)\b', normalized_text):
        add_signal(
            'Sexual or Inappropriate Content',
            'The posting includes explicit or inappropriate sexual wording and is likely unsafe or fraudulent.',
            0.90,
            'explicit sexual language',
        )

    if re.search(r'\b(daily\s+cash|cash\s+per\s+hour|rupees?\b|rs\.?\s*\d+)\b', normalized_text):
        add_signal(
            'Cash Lure Payment Pattern',
            'The compensation text uses informal cash-lure phrasing that is common in low-trust scam posts.',
            0.30,
            'daily cash / rupee cash phrasing',
        )

    if re.search(r'aadhaar|pan\s+card|bank\s+account|account\s+number|ifsc|otp|ssn|social\s+security', normalized_text):
        add_signal(
            'Sensitive Data Collection',
            'The posting requests sensitive personal or financial details too early in the hiring flow.',
            0.75,
            'personal document or bank detail request',
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

    if re.search(r'lorem\s+ipsum|dummy\s+text|sample\s+text', normalized_text):
        add_signal(
            'Placeholder Content',
            'The posting appears to contain filler text rather than a real job description.',
            0.85,
            'placeholder content detected',
        )

    if re.search(r'\b(pay\s+daily|\$\d+(\.\d+)?\s*(to|-)\s*\$?\d+\s*(plus\s+a\s+day|a\s+day)?|call\s+(us\s+)?today)\b', normalized_text):
        add_signal(
            'Aggressive Earnings Pitch',
            'The posting uses high-pressure earnings language common in scam campaigns.',
            0.70,
            'pay daily / call today pitch',
        )

    description_text = (posting.description or '').strip()
    short_description = len(description_text.split()) < 12
    missing_supporting_fields = not posting.company_profile.strip()
    if short_description and missing_supporting_fields:
        add_signal(
            'Thin Job Detail',
            'The posting is too sparse to be a credible hiring listing.',
            0.35,
            'very short or incomplete posting',
        )

    # Mild trust cues to avoid over-flagging structured, corporate-style listings.
    corporate_cues = 0
    if re.search(r'responsibilities|qualifications|requirements|benefits|full[-\s]?time|department', normalized_text):
        corporate_cues += 1
    if re.search(r'accounting|auditing|human resources|customer service|administrative assistant', normalized_text):
        corporate_cues += 1
    if corporate_cues >= 2 and score > 0:
        score = max(0.0, score - 0.18)

    return min(score, 1.0), signals


def _calibrate_risk_score(model_fake_probability: float, heuristic_probability: float, signals: list[dict[str, str]]) -> float:
    """
    Turn raw model output into a smoother 0-100 risk score.
    Keeps obvious scams high, but avoids fake 0/100 extremes.
    """
    combined_probability = (0.66 * model_fake_probability) + (0.34 * heuristic_probability)

    if signals:
        combined_probability = max(combined_probability, min(0.95, heuristic_probability + 0.08))

    risk_score = 100.0 * combined_probability

    strong_signal_labels = {
        'Upfront Payment Request',
        'Money Transfer Demand',
        'Sexual or Inappropriate Content',
        'Placeholder Content',
        'Aggressive Earnings Pitch',
    }
    weak_signal_labels = {
        'Urgency Pressure',
        'Suspicious Reward Language',
        'Thin Job Detail',
        'Personal Contact Channel',
    }

    strong_count = sum(1 for signal in signals if signal['label'] in strong_signal_labels)
    weak_count = sum(1 for signal in signals if signal['label'] in weak_signal_labels)

    if strong_count > 0:
        risk_score = max(risk_score, 85.0)
    elif weak_count >= 3:
        risk_score = max(risk_score, 78.0)
    elif weak_count >= 2:
        risk_score = max(risk_score, 58.0)

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


def _call_local_classifier(posting: JobPosting, text: str) -> dict[str, Any]:
    if not _ensure_local_model_loaded():
        return _heuristic_fallback_result(posting, text, 'local_model_not_loaded')

    try:
        fake_probability = 0.5

        if hasattr(local_model_artifact, 'predict_proba'):
            prob = local_model_artifact.predict_proba([text])[0]
            # Resolve probability using model class labels to avoid inverted fake/real mapping.
            classes = list(getattr(local_model_artifact, 'classes_', []))
            fake_index = None
            if classes:
                normalized = [str(cls).strip().lower() for cls in classes]
                for candidate in ('1', 'true', 'fake', 'fraud', 'fraudulent'):
                    if candidate in normalized:
                        fake_index = normalized.index(candidate)
                        break

            if fake_index is None:
                fake_index = 1 if len(prob) > 1 else 0

            fake_index = max(0, min(fake_index, len(prob) - 1))
            fake_probability = _parse_probability(prob[fake_index])
        elif isinstance(local_model_artifact, dict):
            model = local_model_artifact.get('model')
            vectorizer = local_model_artifact.get('vectorizer')
            if model is None or vectorizer is None:
                raise ValueError('Dict local model must contain "model" and "vectorizer" keys.')
            features = vectorizer.transform([text])
            prob = model.predict_proba(features)[0]
            classes = list(getattr(model, 'classes_', []))
            fake_index = None
            if classes:
                normalized = [str(cls).strip().lower() for cls in classes]
                for candidate in ('1', 'true', 'fake', 'fraud', 'fraudulent'):
                    if candidate in normalized:
                        fake_index = normalized.index(candidate)
                        break

            if fake_index is None:
                fake_index = 1 if len(prob) > 1 else 0

            fake_index = max(0, min(fake_index, len(prob) - 1))
            fake_probability = _parse_probability(prob[fake_index])
        else:
            raise ValueError(f'Unsupported local model artifact type: {type(local_model_artifact)}')
    except Exception as exc:
        print(f'Local model inference failed: {exc}')
        return _heuristic_fallback_result(posting, text, 'local_inference_error')

    real_probability = max(0.0, min(1.0, 1.0 - fake_probability))
    prediction = 'fake' if fake_probability >= LOCAL_MODEL_PROBABILITY_THRESHOLD else 'real'
    confidence = max(fake_probability, real_probability)

    return {
        'prediction': prediction,
        'threshold': round(LOCAL_MODEL_PROBABILITY_THRESHOLD, 4),
        'real_probability': round(real_probability, 6),
        'fake_probability': round(fake_probability, 6),
        'confidence': round(confidence, 6),
        'input_length': len(text),
        'model_label': local_model_label or 'local_pkl_model',
        'model_fake_probability': round(fake_probability, 6),
        'heuristic_fake_probability': 0.0,
        'risk_score': None,
        'risk_signals': [],
    }


def _active_model_summary() -> tuple[str, str, bool]:
    model_id = str(LOCAL_MODEL_PATH)
    return 'local_pickle', model_id, local_model_ready


@app.on_event('startup')
def load_artifacts() -> None:
    global local_model_artifact, local_model_ready, local_model_label, DATABASE_READY

    try:
        metadata.create_all(engine)
        _ensure_job_analyses_schema_compatibility()
        _refresh_analyses_table_binding()
        DATABASE_READY = True
    except SQLAlchemyError as exc:
        # Keep the API process alive so model-only endpoints can still be used.
        DATABASE_READY = False
        print(f'Database startup initialization skipped: {exc}')

    _load_threshold_config()

    _ensure_local_model_loaded()
    if local_model_ready:
        print(f'Local model loaded: {LOCAL_MODEL_PATH}')

    model_type, model_id, ready = _active_model_summary()
    print(f'Model type: {model_type}')
    print(f'Model id: {model_id}')
    print(f'Model ready: {ready}')
    print(f'Fraud risk threshold: {FRAUD_RISK_THRESHOLD:.2f}%')


@app.get('/health')
def health() -> dict[str, Any]:
    model_type, model_id, ready = _active_model_summary()
    return {
        'status': 'ok',
        'service': 'python-backend-ml',
        'database_ready': DATABASE_READY,
        'model_loaded': ready,
        'model_type': model_type,
        'model_id': model_id,
    }


@app.get('/api/info')
def api_info() -> dict[str, Any]:
    model_type, model_id, ready = _active_model_summary()
    return {
        'service': 'python-backend-ml',
        'model_type': model_type,
        'model_id': model_id,
        'ready': ready,
    }


@app.post('/auth/google')
@app.post('/api/auth/google')
def auth_google(payload: GoogleAuthRequest) -> dict[str, Any]:
    profile = _supabase_auth_get('/user', payload.access_token)
    email = _normalize_email(str(profile.get('email', '')))
    if not email:
        raise HTTPException(status_code=400, detail='Google account email is required')

    metadata = profile.get('user_metadata') or {}
    derived_name = str(metadata.get('full_name') or metadata.get('name') or email.split('@', 1)[0]).strip()
    safe_name = (derived_name or 'Google User')[:120]

    # Use a stable fallback identifier so login still works when the DB is unavailable.
    fallback_user_id = int(hashlib.sha256(email.encode('utf-8')).hexdigest()[:12], 16)

    if not DATABASE_READY:
        token = _create_access_token(
            str(fallback_user_id),
            {'email': email, 'name': safe_name},
        )
        return {
            'token': token,
            'user': {
                'id': fallback_user_id,
                'email': email,
                'name': safe_name,
                'created_at': None,
            },
        }

    with engine.begin() as connection:
        existing = connection.execute(select(users_table).where(users_table.c.email == email)).mappings().first()
        if existing:
            row = existing
        else:
            row = connection.execute(
                users_table.insert().values(
                    email=email,
                    name=safe_name,
                    password_hash=_hash_password(secrets.token_urlsafe(32)),
                    email_verified=True,
                    email_verification_token=None,
                    verified_at=dt.datetime.now(dt.timezone.utc),
                ).returning(users_table)
            ).mappings().first()

    token = _create_access_token(
        str(row['id']),
        {'email': email, 'name': row['name']},
    )
    return {'token': token, 'user': _serialize_user(row)}


@app.post('/auth/signup')
@app.post('/api/auth/signup')
def auth_signup(payload: EmailSignupRequest) -> dict[str, Any]:
    """Register a new user with email and password."""
    email = _normalize_email(payload.email)
    
    if not email or '@' not in email:
        raise HTTPException(status_code=400, detail='Valid email is required')
    
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail='Password must be at least 6 characters')
    
    if not DATABASE_READY:
        raise HTTPException(status_code=503, detail='Database not available')

    password_hash = _hash_password(payload.password)
    name = payload.name.strip()[:120] or email.split('@', 1)[0]

    try:
        with engine.begin() as connection:
            # Check if user already exists
            existing = connection.execute(
                select(users_table).where(users_table.c.email == email)
            ).mappings().first()
            
            if existing:
                raise HTTPException(status_code=400, detail='Email already registered')
            
            # Create new user
            row = connection.execute(
                users_table.insert().values(
                    email=email,
                    name=name,
                    password_hash=password_hash,
                    email_verified=True,  # Auto-verify for simple signup
                    email_verification_token=None,
                    verified_at=dt.datetime.now(dt.timezone.utc),
                ).returning(users_table)
            ).mappings().first()

        token = _create_access_token(
            str(row['id']),
            {'email': email, 'name': row['name']},
        )
        return {'token': token, 'user': _serialize_user(row)}
    
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail='Failed to create account') from exc


@app.post('/auth/login')
@app.post('/api/auth/login')
def auth_login(payload: EmailLoginRequest) -> dict[str, Any]:
    """Login with email and password."""
    email = _normalize_email(payload.email)
    
    if not email or '@' not in email:
        raise HTTPException(status_code=400, detail='Valid email is required')
    
    if not payload.password:
        raise HTTPException(status_code=400, detail='Password is required')
    
    # Fallback for when DB is unavailable
    fallback_user_id = int(hashlib.sha256(email.encode('utf-8')).hexdigest()[:12], 16)
    
    if not DATABASE_READY:
        token = _create_access_token(
            str(fallback_user_id),
            {'email': email, 'name': email.split('@', 1)[0]},
        )
        return {
            'token': token,
            'user': {
                'id': fallback_user_id,
                'email': email,
                'name': email.split('@', 1)[0],
                'created_at': None,
            },
        }

    try:
        with engine.begin() as connection:
            row = connection.execute(
                select(users_table).where(users_table.c.email == email)
            ).mappings().first()
            
            if not row:
                raise HTTPException(status_code=401, detail='Invalid email or password')
            
            # Verify password
            if not _verify_password(payload.password, row['password_hash']):
                raise HTTPException(status_code=401, detail='Invalid email or password')
            
            token = _create_access_token(
                str(row['id']),
                {'email': email, 'name': row['name']},
            )
            return {'token': token, 'user': _serialize_user(row)}
    
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail='Login failed') from exc



@app.get('/auth/me')
def me(current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
    return {'user': _serialize_user(current_user)}


def _predict_from_posting(
    posting: JobPosting,
) -> dict[str, Any]:
    text = _build_posting_text(posting).strip()
    if not text:
        raise HTTPException(status_code=400, detail='Empty job posting text')

    # Check for job relevance
    is_job_related = _is_job_posting(text)
    
    # Keep the semantic structure but stay within a safe token-sized window.
    text = text[:4000]

    model_result = _call_local_classifier(posting, text)

    confidence = float(model_result['confidence'])
    model_fake_probability = float(model_result['model_fake_probability'])

    heuristic_probability, heuristic_signals = _extract_heuristics(posting, text)

    risk_score = _calibrate_risk_score(model_fake_probability, heuristic_probability, heuristic_signals)
    fake_probability = risk_score / 100.0
    real_probability = 1.0 - fake_probability
    is_fake = risk_score >= FRAUD_RISK_THRESHOLD

    prediction = 'fake' if is_fake else 'real'

    return {
        'prediction': prediction,
        'is_job_related': is_job_related,
        'threshold': round(FRAUD_RISK_THRESHOLD / 100.0, 4),
        'real_probability': round(real_probability, 6),
        'fake_probability': round(fake_probability, 6),
        'confidence': round(confidence, 6),
        'input_length': len(text),
        'model_label': model_result['model_label'],
        'model_fake_probability': round(model_fake_probability, 6),
        'heuristic_fake_probability': round(heuristic_probability, 6),
        'risk_score': risk_score,
        'rate': risk_score,
        'risk_signals': heuristic_signals,
    }


@app.post('/api/extract-pdf')
async def extract_pdf(file: UploadFile = File(...), current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
    """Extract text from a PDF file for analysis."""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail='Only PDF files are supported.')
    
    try:
        import io
        content = await file.read()
        reader = pypdf.PdfReader(io.BytesIO(content))
        text_content = ""
        for page in reader.pages:
            text_content += (page.extract_text() or "") + "\n"
        
        if not text_content.strip():
            return {"text": "", "warning": "No text could be extracted from this PDF."}
            
        return {"text": text_content.strip()}
    except Exception as e:
        print(f"PDF Extraction error: {e}")
        raise HTTPException(status_code=500, detail='Failed to extract text from PDF.')

@app.post('/api/predict')
def api_predict(
    posting: JobPosting,
    current_user: dict[str, Any] = Depends(_get_current_user),
) -> dict[str, Any]:
    result = _predict_from_posting(posting)
    risk_score = round(float(result.get('fake_probability', 0)) * 100, 2)
    insert_values = _build_app_analysis_insert_values(current_user['id'], posting, result, risk_score)

    try:
        with engine.begin() as connection:
            connection.execute(app_analyses_table.insert().values(**insert_values))
    except Exception as exc:
        # Keep prediction API available even if persistence temporarily fails.
        print(f'Prediction persistence skipped: {exc}')

    return {'success': True, 'result': result}


@app.get('/api/history')
def api_history(limit: int = 20, current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 100))
    analysis_user_id = int(current_user['id'])

    try:
        with engine.connect() as connection:
            rows = connection.execute(
                select(app_analyses_table)
                .where(app_analyses_table.c.user_id == analysis_user_id)
                .order_by(desc(app_analyses_table.c.created_at))
                .limit(safe_limit)
            ).mappings().all()
    except Exception as exc:
        print(f'History query skipped: {exc}')
        return {'items': []}

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
    analysis_user_id = int(current_user['id'])

    with engine.begin() as connection:
        result = connection.execute(
            app_analyses_table.delete().where(app_analyses_table.c.user_id == analysis_user_id)
        )

    return {'success': True, 'deleted_count': int(result.rowcount or 0)}


@app.delete('/api/history/{analysis_id}')
def api_delete_history_item(analysis_id: int, current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
    analysis_user_id = int(current_user['id'])

    with engine.begin() as connection:
        result = connection.execute(
            app_analyses_table.delete().where(
                app_analyses_table.c.id == analysis_id,
                app_analyses_table.c.user_id == analysis_user_id,
            )
        )

    deleted = int(result.rowcount or 0)
    if deleted == 0:
        raise HTTPException(status_code=404, detail='History item not found')

    return {'success': True, 'deleted_id': analysis_id}


class ResearchRequest(BaseModel):
    company: str
    role: str = ''
    location: str = ''


@app.post('/api/research')
def api_research(
    payload: ResearchRequest,
    current_user: dict[str, Any] = Depends(_get_current_user),
) -> dict[str, Any]:
    """Research a company using multiple public data sources."""
    if not payload.company.strip():
        raise HTTPException(status_code=400, detail='Company name is required')

    try:
        # Calls the research_company function from company_researcher.py
        result = research_company(
            payload.company.strip(),
            payload.role.strip(),
            payload.location.strip(),
        )

        # Save to research history
        try:
            with engine.begin() as connection:
                connection.execute(
                    research_history_table.insert().values(
                        user_id=int(current_user['id']),
                        company=payload.company.strip(),
                        role=payload.role.strip(),
                        location=payload.location.strip(),
                        result_payload=result
                    )
                )
        except Exception as db_exc:
            print(f"Failed to save research history: {db_exc}")

        return {'success': True, 'data': result}
    except Exception as exc:
        print(f'Research failed for {payload.company}: {exc}')
        raise HTTPException(status_code=500, detail=f'Research failed: {str(exc)}')


@app.get('/api/research-history')
def api_get_research_history(
    limit: int = 50,
    current_user: dict[str, Any] = Depends(_get_current_user),
) -> dict[str, Any]:
    user_id = int(current_user['id'])

    with engine.connect() as connection:
        query = (
            select(research_history_table)
            .where(research_history_table.c.user_id == user_id)
            .order_by(desc(research_history_table.c.created_at))
            .limit(limit)
        )
        rows = connection.execute(query).mappings().all()

    items = [
        {
            'id': row.id,
            'company': row.company,
            'role': row.role,
            'location': row.location,
            'result_payload': row.result_payload,
            'created_at': row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
    return {'items': items}
    
@app.delete('/api/research-history')
def api_clear_research_history(current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
    user_id = int(current_user['id'])

    with engine.begin() as connection:
        result = connection.execute(
            research_history_table.delete().where(research_history_table.c.user_id == user_id)
        )

    return {'success': True, 'deleted_count': int(result.rowcount or 0)}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app:app', host='0.0.0.0', port=8000, reload=True)
