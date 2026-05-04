"""
email_verifier.py
HR email verification using:
  - email-validator  (syntax + MX deliverability)
  - dnspython        (SPF, DMARC, DKIM)
  - Clearbit Autocomplete (company -> official domain, no API key)
  - python-whois     (domain age, optional)
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

import dns.resolver
from email_validator import validate_email, EmailNotValidError

# ---------------------------------------------------------------------------
# Company domain database
# ---------------------------------------------------------------------------
KNOWN_COMPANY_DOMAINS: dict[str, list[str]] = {
    'google': ['google.com', 'alphabet.com'],
    'microsoft': ['microsoft.com'],
    'amazon': ['amazon.com'],
    'apple': ['apple.com'],
    'meta': ['meta.com', 'fb.com', 'facebook.com'],
    'netflix': ['netflix.com'],
    'stripe': ['stripe.com'],
    'airbnb': ['airbnb.com'],
    'uber': ['uber.com'],
    'linkedin': ['linkedin.com'],
    'twitter': ['twitter.com', 'x.com'],
    'salesforce': ['salesforce.com'],
    'adobe': ['adobe.com'],
    'oracle': ['oracle.com'],
    'ibm': ['ibm.com'],
    'intel': ['intel.com'],
    'nvidia': ['nvidia.com'],
    'cisco': ['cisco.com'],
    'sap': ['sap.com'],
    'infosys': ['infosys.com'],
    'tcs': ['tcs.com'],
    'wipro': ['wipro.com'],
    'hcl': ['hcl.com', 'hcltech.com'],
    'accenture': ['accenture.com'],
    'deloitte': ['deloitte.com'],
    'pwc': ['pwc.com'],
    'kpmg': ['kpmg.com'],
    'ey': ['ey.com'],
    'capgemini': ['capgemini.com'],
    'cognizant': ['cognizant.com'],
    'zoho': ['zoho.com'],
    'flipkart': ['flipkart.com'],
    'swiggy': ['swiggy.com'],
    'zomato': ['zomato.com'],
    'paytm': ['paytm.com'],
    'ola': ['olacabs.com'],
    'razorpay': ['razorpay.com'],
    'freshworks': ['freshworks.com'],
    'atlassian': ['atlassian.com'],
    'github': ['github.com'],
    'gitlab': ['gitlab.com'],
    'slack': ['slack.com'],
    'zoom': ['zoom.us'],
    'shopify': ['shopify.com'],
    'twilio': ['twilio.com'],
    'dropbox': ['dropbox.com'],
    'spotify': ['spotify.com'],
    'tesla': ['tesla.com'],
    'samsung': ['samsung.com'],
    'dell': ['dell.com'],
    'hp': ['hp.com'],
    'lenovo': ['lenovo.com'],
    'qualcomm': ['qualcomm.com'],
    'amd': ['amd.com'],
    'paypal': ['paypal.com'],
    'visa': ['visa.com'],
    'mastercard': ['mastercard.com'],
}

FREE_EMAIL_DOMAINS: set[str] = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.com',
    'aol.com', 'proton.me', 'protonmail.com', 'icloud.com', 'me.com',
    'mail.com', 'yandex.com', 'rediffmail.com', 'inbox.com', 'msn.com',
    'yopmail.com', 'guerrillamail.com', 'tempmail.com', 'mailinator.com',
    'throwam.com', 'trashmail.com', 'sharklasers.com',
}

# Most common DKIM selectors
DKIM_SELECTORS: list[str] = ['google', 'selector1', 'selector2', 'default', 'mail']


# ---------------------------------------------------------------------------
# DNS Checks
# ---------------------------------------------------------------------------

def _check_spf(domain: str) -> bool:
    try:
        answers = dns.resolver.resolve(domain, 'TXT', lifetime=5)
        for rdata in answers:
            txt = b''.join(rdata.strings).decode('utf-8', errors='ignore')
            if txt.startswith('v=spf1'):
                return True
    except Exception:
        pass
    return False


def _check_dmarc(domain: str) -> bool:
    try:
        answers = dns.resolver.resolve(f'_dmarc.{domain}', 'TXT', lifetime=5)
        for rdata in answers:
            txt = b''.join(rdata.strings).decode('utf-8', errors='ignore')
            if txt.startswith('v=DMARC1'):
                return True
    except Exception:
        pass
    return False


def _check_dkim(domain: str) -> bool:
    """Try the most common DKIM selectors."""
    for selector in DKIM_SELECTORS:
        try:
            answers = dns.resolver.resolve(
                f'{selector}._domainkey.{domain}', 'TXT', lifetime=2
            )
            for rdata in answers:
                txt = b''.join(rdata.strings).decode('utf-8', errors='ignore')
                if 'v=DKIM1' in txt or 'p=' in txt:
                    return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------------------
# Clearbit Autocomplete (free, no API key)
# ---------------------------------------------------------------------------

def _clearbit_lookup(company_name: str) -> list[str]:
    """Returns list of official domains for a company via Clearbit's free autocomplete."""
    if not company_name or len(company_name.strip()) < 2:
        return []
    try:
        encoded = urllib.parse.quote(company_name.strip()[:80])
        url = f'https://autocomplete.clearbit.com/v1/companies/suggest?query={encoded}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return [item['domain'] for item in data if item.get('domain')]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Domain Age (optional — requires python-whois)
# ---------------------------------------------------------------------------

def _get_domain_age_days(domain: str) -> int | None:
    try:
        import whois
        import datetime
        w = whois.whois(domain)
        creation = w.creation_date
        if isinstance(creation, list):
            creation = creation[0]
        if creation:
            return (datetime.datetime.now() - creation).days
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Company Domain Matching
# ---------------------------------------------------------------------------

def _match_company_domain(
    domain: str, company_name: str, clearbit_domains: list[str]
) -> tuple[bool, str]:
    """Returns (matched, method)."""
    if not company_name:
        return True, 'no_company_provided'

    domain_lower = domain.lower()

    # 1. Clearbit (most reliable)
    if domain_lower in clearbit_domains:
        return True, 'clearbit'

    # 2. Known database
    company_norm = re.sub(r'[^a-z0-9]', '', company_name.lower())
    for known_name, known_domains in KNOWN_COMPANY_DOMAINS.items():
        known_norm = re.sub(r'[^a-z0-9]', '', known_name)
        if known_norm in company_norm or company_norm in known_norm:
            if domain_lower in known_domains:
                return True, 'known_database'

    # 3. Fuzzy: domain base vs company name
    domain_base = domain_lower.split('.')[0]
    if domain_base in company_norm or company_norm in domain_base:
        return True, 'fuzzy'

    return False, 'no_match'


# ---------------------------------------------------------------------------
# Trust Score
# ---------------------------------------------------------------------------

def _compute_trust(result: dict) -> tuple[int, str, list[str]]:
    score = 40
    flags: list[str] = []

    if result['valid_syntax']:
        score += 10
    else:
        flags.append('Invalid email syntax')

    if result['deliverable']:
        score += 15
    else:
        score -= 15
        flags.append('No MX records — domain cannot receive email')

    if result['is_free_email']:
        score -= 25
        flags.append('Free/personal email provider (not a corporate address)')

    if result['has_spf']:
        score += 10
    else:
        flags.append('Missing SPF record')

    if result['has_dmarc']:
        score += 10
    else:
        flags.append('Missing DMARC record')

    if result['has_dkim']:
        score += 5

    if result['domain_match']:
        score += 15
    else:
        flags.append('Email domain does not match the stated company name')

    age = result.get('domain_age_days')
    if age is not None:
        if age < 180:
            score -= 20
            flags.append(f'Domain registered only {age} days ago — very new')
        elif age < 365:
            score -= 10
            flags.append(f'Domain is less than 1 year old ({age} days)')

    score = max(5, min(95, score))

    if score >= 70:
        verdict = 'Likely Legitimate'
    elif score >= 45:
        verdict = 'Uncertain'
    else:
        verdict = 'Suspicious'

    return score, verdict, flags


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def verify_hr_email(email: str, company_name: str = '') -> dict[str, Any]:
    result: dict[str, Any] = {
        'valid_syntax': False,
        'deliverable': False,
        'has_spf': False,
        'has_dmarc': False,
        'has_dkim': False,
        'is_free_email': False,
        'domain_match': False,
        'domain_match_method': '',
        'domain': None,
        'domain_age_days': None,
        'clearbit_domains': [],
        'trust_score': 0,
        'verdict': 'Unknown',
        'flags': [],
        'error': None,
    }

    if not email or not email.strip():
        result['verdict'] = 'No Email Provided'
        return result

    try:
        valid = validate_email(email.strip(), check_deliverability=True)
        result['valid_syntax'] = True
        result['deliverable'] = True
        domain = valid.domain
        result['domain'] = domain

        result['is_free_email'] = domain in FREE_EMAIL_DOMAINS
        result['has_spf'] = _check_spf(domain)
        result['has_dmarc'] = _check_dmarc(domain)
        result['has_dkim'] = _check_dkim(domain)

        clearbit_domains = _clearbit_lookup(company_name) if company_name else []
        result['clearbit_domains'] = clearbit_domains

        matched, method = _match_company_domain(domain, company_name, clearbit_domains)
        result['domain_match'] = matched
        result['domain_match_method'] = method

        result['domain_age_days'] = _get_domain_age_days(domain)

    except EmailNotValidError as exc:
        result['error'] = str(exc)
    except Exception:
        result['error'] = 'Verification encountered an internal error.'

    score, verdict, flags = _compute_trust(result)
    result['trust_score'] = score
    result['verdict'] = verdict
    result['flags'] = flags

    return result
