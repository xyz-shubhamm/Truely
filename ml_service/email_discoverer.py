"""
email_discoverer.py
Peak-accuracy HR email discovery using all free, no-credit-card methods:
  1. Company website scraping (requests + bs4)
  2. GitHub public commit API (60 req/hr free, no key)
  3. Reddit public JSON API (no key)
  4. SMTP RCPT TO probing (smtplib) — only when catch-all is NOT detected
Principle: Never show an email unless it was FOUND somewhere real or SMTP-confirmed.
"""
from __future__ import annotations

import re
import smtplib
import socket
import time
import urllib.parse
import urllib.request
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests
from bs4 import BeautifulSoup
import dns.resolver

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COMMON_HR_PATTERNS = [
    'hr', 'hiring', 'talent', 'careers', 'jobs', 'recruitment',
    'recruiter', 'people', 'humanresources', 'apply', 'joinus',
]

FREE_DOMAINS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
    'protonmail.com', 'proton.me', 'icloud.com',
}

SCRAPE_PATHS = ['/', '/contact', '/contact-us', '/about', '/about-us',
                '/team', '/our-team', '/careers', '/jobs', '/work-with-us',
                '/join-us', '/hiring']

SENIORITY_SENIOR = re.compile(
    r'\b(senior|sr\.?|lead|head|principal|director|vp|vice\s+president|manager|chief)\b',
    re.IGNORECASE,
)
SENIORITY_JUNIOR = re.compile(
    r'\b(junior|jr\.?|associate|coordinator|assistant|trainee|intern|graduate)\b',
    re.IGNORECASE,
)

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_get(url: str, timeout: int = 8) -> requests.Response | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        return r if r.status_code == 200 else None
    except Exception:
        return None


def _extract_emails_from_text(text: str, domain: str) -> list[str]:
    pattern = rf'[a-zA-Z0-9._%+\-]+@{re.escape(domain)}'
    return list({m.lower() for m in re.findall(pattern, text)})


def _get_mx_host(domain: str) -> str | None:
    try:
        records = dns.resolver.resolve(domain, 'MX', lifetime=5)
        return str(sorted(records, key=lambda r: r.preference)[0].exchange).rstrip('.')
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Phase 1 — Catch-All Detection
# ---------------------------------------------------------------------------

def detect_catch_all(domain: str, mx_host: str | None = None) -> bool:
    """
    Send RCPT TO with a guaranteed-fake address.
    If MX accepts it → catch-all server → SMTP probing unreliable.
    """
    if mx_host is None:
        mx_host = _get_mx_host(domain)
    if not mx_host:
        return True  # can't connect anyway → treat as catch-all

    fake_email = f'truely_fake_xyz_91827364@{domain}'
    try:
        with smtplib.SMTP(timeout=8) as smtp:
            smtp.connect(mx_host, 25)
            smtp.helo('truely.verify')
            smtp.mail('verify@truely.app')
            code, _ = smtp.rcpt(fake_email)
            return code == 250  # accepts fake → catch-all
    except Exception:
        return True  # can't probe → treat as catch-all (safe default)

# ---------------------------------------------------------------------------
# Phase 2 — Company Website Scraping
# ---------------------------------------------------------------------------

def scrape_website_emails(domain: str) -> list[dict[str, Any]]:
    """Scrape company website pages for real email addresses."""
    found: dict[str, dict] = {}

    for path in SCRAPE_PATHS:
        url = f'https://{domain}{path}'
        resp = _safe_get(url, timeout=8)
        if resp is None:
            continue

        emails = _extract_emails_from_text(resp.text, domain)
        # Also get surrounding context for role classification
        soup = BeautifulSoup(resp.text, 'html.parser')
        page_text = soup.get_text(separator=' ', strip=True)

        for email in emails:
            if email not in found:
                # Extract context: 200 chars around email occurrence
                idx = page_text.lower().find(email.lower())
                context = page_text[max(0, idx - 100): idx + 100] if idx != -1 else ''
                found[email] = {
                    'email': email,
                    'source': 'website',
                    'page': path,
                    'context': context,
                    'confidence': 50,
                }
        time.sleep(0.4)  # polite

    return list(found.values())

# ---------------------------------------------------------------------------
# Phase 3 — GitHub Commit Email Search
# ---------------------------------------------------------------------------

def search_github_emails(domain: str) -> list[dict[str, Any]]:
    """Search GitHub public commits for company-domain emails."""
    results = []
    seen: set[str] = set()

    queries = [
        f'author-email:{domain}',
        f'committer-email:{domain}',
    ]

    for q in queries:
        try:
            url = f'https://api.github.com/search/commits?q={urllib.parse.quote(q)}&per_page=30'
            req = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'TruelyApp/1.0',
                    'Accept': 'application/vnd.github.v3+json',
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                for item in data.get('items', []):
                    commit = item.get('commit', {})
                    for role_key in ('author', 'committer'):
                        entry = commit.get(role_key, {})
                        email = (entry.get('email') or '').lower()
                        if not email or domain not in email or email in seen:
                            continue
                        if any(free in email for free in FREE_DOMAINS):
                            continue
                        seen.add(email)
                        name = entry.get('name', '')
                        # Try to get github profile
                        gh_user = item.get(role_key, {}) or {}
                        gh_login = gh_user.get('login', '')
                        gh_profile = f'https://github.com/{gh_login}' if gh_login else ''
                        # Infer role from commit message context
                        msg = commit.get('message', '')
                        results.append({
                            'email': email,
                            'source': 'github',
                            'name': name,
                            'github_profile': gh_profile,
                            'context': msg[:200],
                            'confidence': 40,
                        })
        except Exception:
            pass
        time.sleep(0.3)

    return results

# ---------------------------------------------------------------------------
# Phase 4 — Reddit / Web Mentions
# ---------------------------------------------------------------------------

def search_reddit_mentions(domain: str) -> list[dict[str, Any]]:
    """Search Reddit for posts mentioning company domain emails."""
    results = []
    seen: set[str] = set()

    urls = [
        f'https://www.reddit.com/search.json?q=%40{urllib.parse.quote(domain)}&sort=relevance&limit=25&t=all',
        f'https://www.reddit.com/r/cscareerquestions/search.json?q=%40{urllib.parse.quote(domain)}&sort=relevance&limit=10&restrict_sr=1&t=all',
    ]

    for url in urls:
        try:
            resp = requests.get(url, headers={'User-Agent': 'TruelyApp/1.0 (educational)'}, timeout=8)
            if resp.status_code != 200:
                continue
            children = resp.json().get('data', {}).get('children', [])
            for child in children:
                d = child.get('data', {})
                text = f"{d.get('title', '')} {d.get('selftext', '')}"
                emails = _extract_emails_from_text(text, domain)
                for email in emails:
                    if email in seen:
                        continue
                    seen.add(email)
                    results.append({
                        'email': email,
                        'source': 'reddit',
                        'context': text[:200],
                        'confidence': 25,
                        'reddit_url': f"https://reddit.com{d.get('permalink', '')}",
                    })
        except Exception:
            pass
        time.sleep(0.25)

    return results

# ---------------------------------------------------------------------------
# Phase 5 — SMTP Pattern Probing (only if NOT catch-all)
# ---------------------------------------------------------------------------

def smtp_probe_single(email: str, mx_host: str, timeout: int = 7) -> bool:
    """Returns True if SMTP RCPT TO responds with 250 (mailbox likely exists)."""
    try:
        with smtplib.SMTP(timeout=timeout) as smtp:
            smtp.connect(mx_host, 25)
            smtp.helo('truely.verify')
            smtp.mail('verify@truely.app')
            code, _ = smtp.rcpt(email)
            return code == 250
    except Exception:
        return False


def smtp_probe_patterns(domain: str, mx_host: str, is_catch_all: bool) -> list[dict[str, Any]]:
    """Probe common HR email patterns via SMTP. Only meaningful if not catch-all."""
    if is_catch_all:
        return []

    results = []
    patterns = [f'{p}@{domain}' for p in COMMON_HR_PATTERNS]

    def probe(email: str) -> dict | None:
        if smtp_probe_single(email, mx_host):
            return {
                'email': email,
                'source': 'smtp_probe',
                'context': '',
                'confidence': 20,
                'smtp_verified': True,
            }
        return None

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(probe, e): e for e in patterns}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    return results

# ---------------------------------------------------------------------------
# Role Classification
# ---------------------------------------------------------------------------

_ROLE_MAP = {
    'hr': 'HR Department',
    'humanresources': 'HR Department',
    'people': 'People Team',
    'talent': 'Talent Acquisition',
    'ta': 'Talent Acquisition',
    'recruit': 'Recruiter',
    'recruitment': 'Recruiter',
    'recruiter': 'Recruiter',
    'hiring': 'Careers Team',
    'jobs': 'Careers Team',
    'careers': 'Careers Team',
    'apply': 'Careers Team',
    'joinus': 'Careers Team',
}


def classify_role(email: str, context: str = '', name: str = '') -> str:
    local = email.split('@')[0].lower().replace('.', '').replace('-', '').replace('_', '')
    combined_context = f'{context} {name}'.lower()

    # 1. Direct local-part match
    for key, role in _ROLE_MAP.items():
        if key in local:
            # Try to determine seniority from context
            if role in ('Recruiter', 'Talent Acquisition', 'HR Department'):
                if SENIORITY_SENIOR.search(combined_context):
                    return f'Senior {role}'
                if SENIORITY_JUNIOR.search(combined_context):
                    return f'Junior {role}'
            return role

    # 2. Personal email (firstname.lastname pattern) — check context for seniority
    if re.match(r'^[a-z]+[.\-_][a-z]+$', local) or re.match(r'^[a-z]{2,}\d*$', local):
        if SENIORITY_SENIOR.search(combined_context):
            return 'Senior Recruiter'
        if SENIORITY_JUNIOR.search(combined_context):
            return 'Junior Recruiter'
        return 'People (Unclassified)'

    return 'People (Unclassified)'

# ---------------------------------------------------------------------------
# Confidence Scoring & Deduplication
# ---------------------------------------------------------------------------

def _source_priority(sources: list[str]) -> int:
    score = 0
    if 'website' in sources:
        score += 50
    if 'github' in sources:
        score += 40
    if 'reddit' in sources:
        score += 25
    if 'smtp_probe' in sources:
        score += 20
    return min(score, 100)


def merge_and_score(all_results: list[dict], is_catch_all: bool) -> list[dict]:
    """Merge results from all sources, deduplicate, compute final confidence."""
    merged: dict[str, dict] = {}

    for item in all_results:
        email = item['email'].lower().strip()
        if email in merged:
            existing = merged[email]
            existing['sources'].add(item['source'])
            if item.get('name') and not existing.get('name'):
                existing['name'] = item['name']
            if item.get('github_profile') and not existing.get('github_profile'):
                existing['github_profile'] = item['github_profile']
            if item.get('context') and not existing.get('context'):
                existing['context'] = item['context']
        else:
            merged[email] = {
                'email': email,
                'sources': {item['source']},
                'name': item.get('name', ''),
                'github_profile': item.get('github_profile', ''),
                'context': item.get('context', ''),
                'reddit_url': item.get('reddit_url', ''),
                'smtp_verified': item.get('smtp_verified', False),
            }

    results = []
    for email, data in merged.items():
        sources_list = list(data['sources'])
        confidence = _source_priority(sources_list)

        # Penalize if catch-all and only SMTP source
        if is_catch_all and sources_list == ['smtp_probe']:
            continue  # Skip — unreliable

        role = classify_role(email, data.get('context', ''), data.get('name', ''))

        results.append({
            'email': email,
            'confidence': confidence,
            'sources': sources_list,
            'role': role,
            'name': data.get('name') or None,
            'github_profile': data.get('github_profile') or None,
            'context': (data.get('context') or '')[:200],
            'smtp_verified': data.get('smtp_verified', False),
            'reddit_url': data.get('reddit_url') or None,
            'catch_all_warning': is_catch_all,
        })

    # Only show emails with confidence >= 25 (at least one real source)
    results = [r for r in results if r['confidence'] >= 25]
    return sorted(results, key=lambda x: x['confidence'], reverse=True)

# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def discover_hr_emails(company: str, domain: str) -> dict[str, Any]:
    """
    Full pipeline: catch-all detection → multi-source discovery → scoring → role classification.
    """
    mx_host = _get_mx_host(domain)
    is_catch_all = detect_catch_all(domain, mx_host)

    # Run all discovery sources
    all_results: list[dict] = []
    sources_used: list[str] = []

    def run_website():
        r = scrape_website_emails(domain)
        if r:
            sources_used.append('website')
        return r

    def run_github():
        r = search_github_emails(domain)
        if r:
            sources_used.append('github')
        return r

    def run_reddit():
        r = search_reddit_mentions(domain)
        if r:
            sources_used.append('reddit')
        return r

    def run_smtp():
        if mx_host and not is_catch_all:
            r = smtp_probe_patterns(domain, mx_host, is_catch_all)
            if r:
                sources_used.append('smtp_probe')
            return r
        return []

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(run_website),
            executor.submit(run_github),
            executor.submit(run_reddit),
            executor.submit(run_smtp),
        ]
        for future in as_completed(futures):
            try:
                all_results.extend(future.result())
            except Exception:
                pass

    emails = merge_and_score(all_results, is_catch_all)

    return {
        'company': company,
        'domain': domain,
        'catch_all': is_catch_all,
        'mx_host': mx_host or '',
        'sources_used': list(set(sources_used)),
        'total_found': len(emails),
        'emails': emails,
    }
