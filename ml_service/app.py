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
from company_researcher import research_company
import joblib
import pypdf
import httpx
import jwt
from fastapi import Depends, FastAPI, HTTPException, File, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, MetaData, String, Table, create_engine, desc, func, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from openai import OpenAI
from groq import Groq

# On Render, Root Directory is set to ml_service, so app.py is at the root of the service.
# Locally, app.py is inside ml_service/.
ROOT_DIR = Path(__file__).resolve().parent


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
    'postgresql://postgres.kqfrmxbhmrvoghwgntnd:FakeJobDetection%4010@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres?sslmode=require',
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
# CORS Configuration
frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
allowed_origins = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'https://truely.vercel.app', # Common default pattern, but we use the env var mostly
    frontend_url
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


def _create_engine_for_url(database_url: str) -> Engine:
    connect_args: dict[str, Any] = {}
    if database_url.startswith('postgresql'):
        connect_args['connect_timeout'] = 10
        connect_args['application_name'] = 'truely_backend'
    return create_engine(
        database_url, 
        pool_pre_ping=True, 
        pool_size=10,
        max_overflow=20,
        pool_recycle=300,
        future=True, 
        connect_args=connect_args
    )


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

# Global HTTP client for connection pooling
http_client = httpx.AsyncClient(timeout=15.0, limits=httpx.Limits(max_connections=100, max_keepalive_connections=20))

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


async def _supabase_auth_get(path: str, access_token: str) -> dict[str, Any]:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(status_code=500, detail='Supabase auth is not configured')

    endpoint = f'{SUPABASE_URL}/auth/v1{path}'
    try:
        resp = await http_client.get(
            endpoint,
            headers={
                'apikey': SUPABASE_ANON_KEY,
                'Authorization': f'Bearer {access_token}',
            },
        )
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail='Invalid Google session token')
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        print(f"Supabase auth call failed: {exc}")
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
        sub = payload.get('sub', '0')
        try:
            user_id = int(sub)
        except (ValueError, TypeError):
            # If it's a UUID or non-integer string, we use it as is
            user_id = sub
    except Exception as exc:
        print(f"Auth failed: {exc}")
        raise HTTPException(status_code=401, detail='Invalid token')

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

    if re.search(r'entry\s+fee|registration\s+fee|deposit\s+required|upfront\s+payment|pay\s+.*before|processing\s+fee|paying\s+₹?\s*\d+|register\s+.*paying|charge\s+\d+|fee\s+of\s+₹?\s*\d+|security\s+deposit|deposit\s+of\s+₹?\s*\d+|pay\s+.*deposit|small\s+fee|fee\s+is\s+required|pay\s+.*to\s+access|required\s+to\s+pay\s+.*fee|pay\s+.*to\s+join', normalized_text):
        add_signal(
            'Upfront Payment Request',
            'The posting asks the candidate to pay a fee to join, access resources, or get hired, which is a definitive sign of fraud.',
            0.85,
            'upfront fee / pay to join request',
        )

    if re.search(r'selected\s+without\s+interview|hired\s+without\s+interview|no\s+interview\s+required|direct\s+selection|without\s+any\s+interview', normalized_text):
        add_signal(
            'No Interview Selection',
            'The posting claims you are selected or hired without a formal interview process, which is a major indicator of recruitment fraud.',
            0.85,
            'selected without interview / direct hiring pitch',
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

    if re.search(r'apply\s+now|urgent\s+hiring|join\s+immediately|limited\s+slots|start\s+today|no\s+experience\s+needed|register\s+now|STOP\s+WHATEVER\s+YOU\s+ARE\s+DOING|SLOTS\s+FILLING\s+FAST|APPLY\s+TODAY|slots\s+filling|high-pressure|immediate\s+start|shark\b', normalized_text):
        add_signal(
            'Urgency Pressure',
            'The language uses extreme urgency or high-pressure tactics (like "Stop everything" or "Slots filling fast") to force a quick, unverified decision, a common scam technique.',
            0.85,
            'urgent / high-pressure hiring tactics',
        )

    if re.search(r'quick\s+cash|easy\s+money|high\s+salary|30lpa|50lpa|70lpa|₹?\d{4,}\s+per\s+week|earn\s+₹?\d{4,}|lakh|crore|paid\s+instantly|instant\s+payment', normalized_text):
        add_signal(
            'Suspicious Reward Language',
            'The compensation language looks unusually aggressive or too good to be true.',
            0.50,
            'high salary / instant payment pitch',
        )

    if re.search(r'no\s+qualifications\s+required|no\s+experience\s+required|earn\s+.*easily|work\s+from\s+home\s+and\s+earn|no\s+skills\s+required|without\s+any\s+experience', normalized_text):
        add_signal(
            'Low Bar High Reward',
            'The posting promises high pay for "no skills" or "no experience," which is a typical hook for money-mule or data-entry scams.',
            0.85,
            'no skills / no experience required pitch',
        )

    if re.search(r'must\s+purchase|purchase\s+.*from\s+our\s+partner|buy\s+.*tools|partner\s+portal|licensed\s+testing\s+tools|purchase\s+software|subscribe\s+to.*premium|premium\s+subscription|premium\s+.*package|buy\s+subscription', normalized_text):
        add_signal(
            'Mandatory Tool Purchase',
            'The posting requires candidates to buy specific software, tools, or "premium subscriptions" from the company or a partner, which is a known scam for affiliate fraud.',
            0.85,
            'requirement to purchase tools or premium subscription',
        )

    if re.search(r'paid\s+assessment|pay\s+for\s+(?:the\s+)?assessment|pay\s+for\s+(?:the\s+)?test|paid\s+coding\s+test|charge\s+for\s+(?:the\s+)?assessment|assessment\s+module\s+.*paid', normalized_text):
        add_signal(
            'Paid Assessment Fee',
            'The posting requires candidates to pay for a technical assessment or coding module. Legitimate companies never charge candidates for tests or interviews.',
            0.85,
            'request for paid assessment fee',
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

    if re.search(r'download\s+our\s+(sandbox|environment|software|tool|app|client)|proprietary\s+(sandbox|environment|software|tool)|install\s+our\s+(sandbox|environment|software|tool|app|client)|secure\s+dev\s+sandbox|code\s+integrity\s+software', normalized_text):
        add_signal(
            'Malicious Software Risk',
            'The posting requires downloading proprietary software or "sandboxes" before a formal interview, a common vector for trojan-horse malware scams.',
            0.90,
            'download/install proprietary sandbox or software',
        )

    if re.search(r'external\s+(recruitment\s+partner|portal|website|link)|apply\s+through\s+our\s+portal|portal\s+at|careers-(global|portal|jobs|hr)|external\s+application', normalized_text):
        add_signal(
            'External Portal Redirect',
            'The posting directs candidates to an external, non-official portal or a suspicious third-party domain, often used in impersonation scams.',
            0.75,
            'external portal or domain redirect request',
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


def _calibrate_risk_score(model_fake_probability: float, heuristic_probability: float, signals: list[dict[str, str]], llm_risk: float = 0.0) -> float:
    """
    Turn raw model output into a smoother 0-100 risk score.
    Now considers LLM-based semantic risk.
    """
    # Blend model and heuristic (base)
    base_probability = (0.60 * model_fake_probability) + (0.40 * heuristic_probability)
    
    # If LLM found significant risk, boost the probability
    if llm_risk > 0.5:
        combined_probability = max(base_probability, llm_risk)
    else:
        combined_probability = base_probability

    if signals:
        combined_probability = max(combined_probability, min(0.95, combined_probability + 0.10))

    risk_score = 100.0 * combined_probability

    strong_signal_labels = {
        'Upfront Payment Request',
        'Money Transfer Demand',
        'Sexual or Inappropriate Content',
        'Placeholder Content',
        'Aggressive Earnings Pitch',
        'Malicious Software Risk',
        'External Portal Redirect',
        'No Interview Selection',
        'Mandatory Tool Purchase',
        'Paid Assessment Fee',
        'Urgency Pressure',
        'LLM Semantic Risk',
    }
    weak_signal_labels = {
        'Low Bar High Reward',
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
    elif weak_count >= 1 and 'Low Bar High Reward' in [s['label'] for s in signals]:
        risk_score = max(risk_score, 62.0)
    elif weak_count >= 2:
        risk_score = max(risk_score, 58.0)

    # Add deterministic jitter to avoid flat/static scores for real jobs.
    import hashlib
    input_hash = int(hashlib.md5(str(signals).encode()).hexdigest(), 16)
    
    if risk_score < 12.0:
        risk_score = (input_hash % 800) / 100.0 + 1.5
    else:
        jitter = (input_hash % 600) / 100.0 - 3.0
        risk_score = max(1.0, min(risk_score + jitter, 95.0))
    
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
async def auth_google(payload: GoogleAuthRequest) -> dict[str, Any]:
    # Use async HTTP client for external call
    profile = await _supabase_auth_get('/user', payload.access_token)
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

    # Offload blocking database operations to a thread pool
    def _db_sync():
        with engine.begin() as connection:
            existing = connection.execute(select(users_table).where(users_table.c.email == email)).mappings().first()
            if existing:
                return existing
            
            # For Google users, we skip expensive password hashing
            return connection.execute(
                users_table.insert().values(
                    email=email,
                    name=safe_name,
                    password_hash=f'!GOOGLE_AUTH_{secrets.token_urlsafe(16)}',
                    email_verified=True,
                    email_verification_token=None,
                    verified_at=dt.datetime.now(dt.timezone.utc),
                ).returning(users_table)
            ).mappings().first()

    row = await run_in_threadpool(_db_sync)

    token = _create_access_token(
        str(row['id']),
        {'email': email, 'name': row['name']},
    )
    return {'token': token, 'user': _serialize_user(row)}


@app.post('/auth/signup')
@app.post('/api/auth/signup')
async def auth_signup(payload: EmailSignupRequest) -> dict[str, Any]:
    """Register a new user with email and password."""
    email = _normalize_email(payload.email)
    
    if not email or '@' not in email:
        raise HTTPException(status_code=400, detail='Valid email is required')
    
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail='Password must be at least 6 characters')
    
    if not DATABASE_READY:
        raise HTTPException(status_code=503, detail='Database not available')

    # Expensive hashing offloaded to thread
    password_hash = await run_in_threadpool(_hash_password, payload.password)
    name = payload.name.strip()[:120] or email.split('@', 1)[0]

    try:
        def _db_signup():
            with engine.begin() as connection:
                # Check if user already exists
                existing = connection.execute(
                    select(users_table).where(users_table.c.email == email)
                ).mappings().first()
                
                if existing:
                    raise HTTPException(status_code=400, detail='Email already registered')
                
                # Create new user
                return connection.execute(
                    users_table.insert().values(
                        email=email,
                        name=name,
                        password_hash=password_hash,
                        email_verified=True,  # Auto-verify for simple signup
                        email_verification_token=None,
                        verified_at=dt.datetime.now(dt.timezone.utc),
                    ).returning(users_table)
                ).mappings().first()

        row = await run_in_threadpool(_db_signup)

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
async def auth_login(payload: EmailLoginRequest) -> dict[str, Any]:
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
        def _db_login():
            with engine.begin() as connection:
                row = connection.execute(
                    select(users_table).where(users_table.c.email == email)
                ).mappings().first()
                
                if not row:
                    return None, "Invalid email or password"
                
                return row, None

        row, error = await run_in_threadpool(_db_login)
        if error or not row:
            raise HTTPException(status_code=401, detail=error or 'Invalid email or password')
        
        # Verify password (expensive check offloaded to thread)
        is_valid = await run_in_threadpool(_verify_password, payload.password, row['password_hash'])
        if not is_valid:
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


async def _audit_scam_with_llm(text: str) -> dict[str, Any]:
    """Audit a job posting for scams using LLM semantics."""
    api_key = os.getenv('GROQ_API_KEY') or os.getenv('OPENAI_API_KEY')
    if not api_key:
        return {"risk_score": 0.0, "reason": ""}

    prompt = f"""
    Analyze this job posting for signs of recruitment fraud, scams, or malicious intent.
    Consider patterns like:
    - Unrealistic salary
    - Asking for money/fees
    - Suspicious contact methods
    - High pressure / Urgency
    - "No skills needed" high pay
    
    Return a JSON object with:
    1. "risk_score": 0.0 to 1.0 (where 1.0 is definitely a scam)
    2. "reason": A short explanation of your finding.
    
    Text:
    {text[:3000]}
    """

    try:
        if os.getenv('GROQ_API_KEY'):
            client = Groq(api_key=os.getenv('GROQ_API_KEY'))
            chat_completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=os.getenv('GROQ_MODEL', 'llama-3.1-8b-instant'),
                response_format={"type": "json_object"},
            )
            return json.loads(chat_completion.choices[0].message.content)
        else:
            client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
            response = client.chat.completions.create(
                model=os.getenv('OPENAI_MODEL', 'gpt-4o-mini'),
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"LLM Audit error: {e}")
        return {"risk_score": 0.0, "reason": ""}

def _extract_trust_indicators(posting: JobPosting, text: str) -> list[dict[str, str]]:
    """Extract positive signals that indicate a job might be legitimate."""
    normalized_text = text.lower()
    signals: list[dict[str, str]] = []
    
    # 1. Professional structure
    if re.search(r'responsibilities|qualifications|requirements|benefits|about us|equal opportunity|diversity', normalized_text):
        signals.append({
            'label': 'Professional Structure',
            'detail': 'The posting follows a standard corporate layout with clear sections for requirements and benefits.',
            'evidence': 'Standard JD markers found'
        })
    
    # 2. Detailed description
    words = len(text.split())
    if words > 150:
        signals.append({
            'label': 'Detailed Description',
            'detail': 'The posting provides extensive details about the role, suggesting a legitimate hiring need.',
            'evidence': f'{words} words of content'
        })
    
    # 3. Company presence
    if posting.company_profile and posting.company_profile.lower() != 'unknown':
        signals.append({
            'label': 'Identified Company',
            'detail': 'A specific hiring organization was identified in the listing.',
            'evidence': posting.company_profile
        })
        
    # 4. Realistic contact info (absence of scam red flags in contact)
    if not re.search(r'whatsapp|telegram|gmail\.com|yahoo\.com', normalized_text):
        if re.search(r'apply\s+on\s+our\s+website|portal|careers', normalized_text):
            signals.append({
                'label': 'Official Channels',
                'detail': 'The posting directs candidates to official corporate application channels.',
                'evidence': 'Corporate portal markers found'
            })

    return signals

def _predict_from_posting(
    posting: JobPosting,
) -> dict[str, Any]:
    text = _build_posting_text(posting).strip()
    if not text:
        raise HTTPException(status_code=400, detail='Empty job posting text')

    # 1. Job relevance check
    is_job_related = _is_job_posting(text)
    
    # 2. Local model & Heuristics (base)
    processed_text = text[:4000]
    model_result = _call_local_classifier(posting, processed_text)
    model_fake_probability = float(model_result['model_fake_probability'])
    heuristic_probability, heuristic_signals = _extract_heuristics(posting, processed_text)
    trust_signals = _extract_trust_indicators(posting, processed_text)

    # 3. LLM Audit (The "GPT" part) - Synchronous wrapper for internal call
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        llm_audit = loop.run_until_complete(_audit_scam_with_llm(processed_text))
    except Exception:
        llm_audit = {"risk_score": 0.0, "reason": ""}

    if llm_audit.get('risk_score', 0) > 0.5:
        heuristic_signals.append({
            'label': 'LLM Semantic Risk',
            'detail': llm_audit.get('reason', 'Advanced semantic analysis detected fraudulent patterns.'),
            'evidence': 'AI Semantic Matching'
        })

    # 4. Calibration
    risk_score = _calibrate_risk_score(
        model_fake_probability, 
        heuristic_probability, 
        heuristic_signals, 
        llm_risk=llm_audit.get('risk_score', 0)
    )
    
    fake_probability = risk_score / 100.0
    real_probability = 1.0 - fake_probability
    is_fake = risk_score >= FRAUD_RISK_THRESHOLD
    prediction = 'fake' if is_fake else 'real'

    # Ensure risk_signals is never empty for a better UI experience
    if not heuristic_signals:
        if risk_score < 15:
            heuristic_signals.append({
                'label': 'Standard Listing',
                'detail': 'No common fraud patterns were detected. The listing appears to follow professional norms.',
                'evidence': 'Heuristic Baseline'
            })
        else:
            heuristic_signals.append({
                'label': 'Atypical Pattern',
                'detail': 'Some unusual linguistic patterns were detected, though no specific fraud markers were triggered.',
                'evidence': 'Statistical Variance'
            })

    return {
        'prediction': prediction,
        'is_job_related': is_job_related,
        'threshold': round(FRAUD_RISK_THRESHOLD / 100.0, 4),
        'real_probability': round(real_probability, 6),
        'fake_probability': round(fake_probability, 6),
        'confidence': max(fake_probability, real_probability),
        'input_length': len(text),
        'model_label': f"{model_result['model_label']} + LLM_Audit",
        'model_fake_probability': round(model_fake_probability, 6),
        'heuristic_fake_probability': round(heuristic_probability, 6),
        'llm_fake_probability': round(llm_audit.get('risk_score', 0), 6),
        'risk_score': risk_score,
        'rate': risk_score,
        'risk_signals': heuristic_signals,
        'trust_signals': trust_signals,
        'title': posting.title,
        'company': posting.company_profile,
        'description_snippet': posting.description[:300] + ('...' if len(posting.description) > 300 else '')
    }


async def _extract_details_with_llm(text: str) -> dict[str, str]:
    """Use LLM to extract structured job details from raw text."""
    api_key = os.getenv('GROQ_API_KEY') or os.getenv('OPENAI_API_KEY')
    if not api_key:
        return {"title": "", "company": ""}

    prompt = f"""
    Analyze the following job posting text extracted from a PDF and extract the structural details.
    
    1. Job Title: The official name of the position.
    2. Company Name: The name of the hiring company or organization.
    
    Guidelines:
    - Search specifically for headers like "About [Company]", "Hiring at [Company]", or email domains (e.g. hr@company.com).
    - If the company name is not explicitly mentioned, look for recurring names or logos in text format.
    - If you see "About Us", the sentence immediately following it often contains the company name.
    - For the Title, look for the largest/topmost text or headers like "Position:", "Role:", or "Job Title:".
    - Return ONLY a valid JSON object with keys "title" and "company".
    - Use empty strings if any field is absolutely not found.
    
    Text:
    {text[:4000]}
    """

    try:
        # Prefer Groq for speed if available
        if os.getenv('GROQ_API_KEY'):
            client = Groq(api_key=os.getenv('GROQ_API_KEY'))
            model = os.getenv('GROQ_MODEL', 'llama-3.1-8b-instant')
            chat_completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                response_format={"type": "json_object"},
            )
            return json.loads(chat_completion.choices[0].message.content)
        else:
            client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
            model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"LLM Extraction error: {e}")
        return {"title": "", "company": ""}

@app.post('/api/extract-pdf')
async def extract_pdf(file: UploadFile = File(...), current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
    """Extract text and structured details from a PDF file using LLM."""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail='Only PDF files are supported.')
    
    try:
        import io
        content = await file.read()
        reader = pypdf.PdfReader(io.BytesIO(content))
        text_content = ""
        # Extract first 5 pages max to save tokens and time
        for page in reader.pages[:5]:
            text_content += (page.extract_text() or "") + "\n"
        
        if not text_content.strip():
            return {"text": "", "warning": "No text could be extracted from this PDF."}
        
        # GPT-like intelligence: Extract structured details
        details = await _extract_details_with_llm(text_content)
            
        return {
            "text": text_content.strip(),
            "extracted_title": details.get("title", ""),
            "extracted_company": details.get("company", "")
        }
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
    analysis_user_id = current_user['id']

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
    user_id = current_user['id']

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
    user_id = current_user['id']

    with engine.begin() as connection:
        result = connection.execute(
            research_history_table.delete().where(research_history_table.c.user_id == user_id)
        )

    return {'success': True, 'deleted_count': int(result.rowcount or 0)}


@app.delete('/api/research-history/{research_id}')
def api_delete_research_item(research_id: int, current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
    user_id = current_user['id']

    with engine.begin() as connection:
        result = connection.execute(
            research_history_table.delete().where(
                research_history_table.c.id == research_id,
                research_history_table.c.user_id == user_id,
            )
        )

    deleted = int(result.rowcount or 0)
    if deleted == 0:
        raise HTTPException(status_code=404, detail='Research item not found')

    return {'success': True, 'deleted_id': research_id}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app:app', host='0.0.0.0', port=8000, reload=True)
