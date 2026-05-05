"""
company_researcher.py
Researches companies using free, no-API-key data sources:
  - Wikipedia REST API     (company info, founding year)
  - Reddit public JSON API  (community reviews, no key needed)
  - LeetCode GraphQL        (interview experiences)
  - AmbitionBox scraping    (India-focused ratings)
  - HuggingFace DistilBERT  (sentiment analysis, 67MB, cached locally)
"""
from __future__ import annotations

import datetime
import re
import time
import urllib.parse
from typing import Any

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Sentiment model (lazy-loaded, optional — falls back to keyword-based)
# ---------------------------------------------------------------------------
_sentiment_pipeline = None


def _get_sentiment_pipeline():
    global _sentiment_pipeline
    if _sentiment_pipeline is not None:
        return _sentiment_pipeline
    try:
        from transformers import pipeline as hf_pipeline
        _sentiment_pipeline = hf_pipeline(
            "sentiment-analysis",
            model="distilbert-base-uncased-finetuned-sst-2-english",
            truncation=True,
            max_length=512,
        )
        print("[company_researcher] DistilBERT sentiment model loaded.")
        return _sentiment_pipeline
    except Exception as exc:
        print(f"[company_researcher] HuggingFace model unavailable ({exc}), using keyword fallback.")
        return None


# ---------------------------------------------------------------------------
# Data Fetchers
# ---------------------------------------------------------------------------

def _safe_get(url: str, headers: dict | None = None, timeout: int = 10) -> requests.Response | None:
    """HTTP GET with a safe fallback."""
    try:
        h = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            **(headers or {}),
        }
        resp = requests.get(url, headers=h, timeout=timeout)
        return resp if resp.status_code == 200 else None
    except Exception:
        return None


def fetch_wikipedia_info(company: str) -> dict[str, Any]:
    """Fetch basic company info from Wikipedia with smart disambiguation."""
    variations = [
        urllib.parse.quote(company.replace(" ", "_") + "_(company)"),
        urllib.parse.quote(company.replace(" ", "_") + "_(corporation)"),
        urllib.parse.quote(company.replace(" ", "_") + "_(software)"),
        urllib.parse.quote(company.replace(" ", "_") + "_Inc."),
        urllib.parse.quote(company.replace(" ", "_")),
    ]
    
    for variant in variations:
        resp = _safe_get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{variant}")
        if resp is None: continue
        
        data = resp.json()
        extract = data.get("extract", "")
        title = data.get("title", "")
        
        # If it's a disambiguation page or mentions non-business entities primarily, skip to next variant
        blacklist = ["may refer to:", "is a fruit", "rainforest", "genus of", "species of", "is a song", "is a film", "is a book"]
        # Stricter company/tech validation
        company_indicators = ["company", "corporation", "inc.", "limited", "software", "technology", "services", "startup", "manufacturer", "firm", "business"]
        is_company_context = any(term in extract.lower() for term in company_indicators) or any(term in title.lower() for term in company_indicators)
        
        if any(term in extract.lower() for term in blacklist) and not is_company_context:
            continue
        
        # If the extract is very short and doesn't mention "company", it might be a weak match
        if len(extract) < 100 and not is_company_context:
            continue

        # Try to find a founding year
        founding_year: int | None = None
        year_match = re.search(r"(?:founded|incorporated|established|launched)\s+in\s+(\d{4})", extract, re.IGNORECASE)
        if year_match: founding_year = int(year_match.group(1))

        # Try to find founders
        founders: str | None = None
        founder_match = re.search(r"(?:founded|started|created|established)\s+by\s+([^.\n,]+(?:,\s+[^.\n,]+)*)", extract, re.IGNORECASE)
        if founder_match: founders = founder_match.group(1).strip()

        return {
            "found": True,
            "title": title,
            "description": extract[:500] if extract else "",
            "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
            "founding_year": founding_year,
            "founders": founders,
            "thumbnail": data.get("thumbnail", {}).get("source", ""),
        }

    return {"found": False, "title": company, "description": "", "url": "", "founding_year": None, "thumbnail": ""}


def fetch_company_logo(company: str, verified_title: str | None = None) -> str:
    """
    Fetches a company logo URL using Clearbit's autocomplete API.
    Uses verified_title (e.g. from Wikipedia) to improve accuracy.
    """
    search_term = verified_title or company
    try:
        # Step 1: Try Clearbit Autocomplete to get the official domain
        url = f"https://autocomplete.clearbit.com/v1/companies/suggest?query={urllib.parse.quote(search_term)}"
        resp = _safe_get(url, timeout=5)
        if resp:
            data = resp.json()
            if data and len(data) > 0:
                # Strategy: Find the best name match
                best_match = data[0]
                term_lower = search_term.lower()
                
                # 1. Exact match
                exact_matches = [item for item in data if item.get("name", "").lower() == term_lower]
                if exact_matches:
                    best_match = exact_matches[0]
                else:
                    # 2. Starts with search_term
                    starts_with = [item for item in data if item.get("name", "").lower().startswith(term_lower)]
                    if starts_with:
                        best_match = starts_with[0]
                
                domain = best_match.get("domain")
                if domain:
                    return f"https://logo.clearbit.com/{domain}"

        # Step 2: Fallback to guessing the domain for very common names
        clean_name = re.sub(r"[^a-z0-9]", "", company.lower())
        if clean_name in ["google", "apple", "microsoft", "meta", "netflix", "amazon"]:
            return f"https://logo.clearbit.com/{clean_name}.com"
            
        if clean_name:
            return f"https://logo.clearbit.com/{clean_name}.com"
    except Exception:
        pass
    return ""


def fetch_stackoverflow_mentions(company: str) -> list[dict[str, Any]]:
    """Fetch company-related questions from StackOverflow to see technical footprints."""
    try:
        url = f"https://api.stackexchange.com/2.3/search/advanced?order=desc&sort=relevance&q={urllib.parse.quote(company)}&site=stackoverflow"
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200: return []
        
        items = resp.json().get("items", [])
        posts = []
        for item in items[:8]:
            posts.append({
                "title":  item.get("title", ""),
                "text":   "Technical discussion or error report related to this company's services/APIs.",
                "score":  item.get("score", 0),
                "url":    item.get("link", ""),
                "source": "StackOverflow",
            })
        return posts
    except Exception:
        return []


def fetch_reddit_posts(company: str, role: str = "") -> list[dict[str, Any]]:
    """
    Fetch Reddit posts using the public unauthenticated JSON API.
    No API key required.
    """
    headers = {"User-Agent": "TruelyResearch/1.0 (educational, non-commercial)"}
    company_q = urllib.parse.quote(company)
    role_q = urllib.parse.quote(role) if role else ""
    broad_q = urllib.parse.quote(f"{company} {role} interview OR review OR experience OR culture OR scam".strip())

    urls = [
        f"https://www.reddit.com/r/cscareerquestions/search.json?q={company_q}&restrict_sr=1&sort=relevance&limit=12&t=all",
        f"https://www.reddit.com/r/recruitinghell/search.json?q={company_q}&restrict_sr=1&sort=relevance&limit=10&t=all",
        f"https://www.reddit.com/r/cscareerquestionsIN/search.json?q={company_q}&restrict_sr=1&sort=relevance&limit=10&t=all",
        f"https://www.reddit.com/r/india/search.json?q={company_q}+job&restrict_sr=1&sort=relevance&limit=8&t=all",
        f"https://www.reddit.com/search.json?q={broad_q}&sort=relevance&limit=15&t=year",
    ]

    posts: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    company_lower = company.lower()

    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code != 200:
                continue
            children = resp.json().get("data", {}).get("children", [])
            for child in children:
                d = child.get("data", {})
                title = d.get("title", "")
                body = d.get("selftext", "")[:350]
                permalink = d.get("permalink", "")
                post_url = f"https://reddit.com{permalink}"

                if post_url in seen_urls:
                    continue
                # Only posts that actually mention the company
                if company_lower not in title.lower() and company_lower not in body.lower():
                    continue

                seen_urls.add(post_url)
                posts.append({
                    "title": title,
                    "text": body,
                    "score": d.get("score", 0),
                    "subreddit": f"r/{d.get('subreddit', 'reddit')}",
                    "url": post_url,
                    "source": "Reddit",
                    "created": d.get("created_utc", 0),
                })
        except Exception:
            pass
        time.sleep(0.1)  # polite rate-limiting

    # Sort by Reddit score (upvotes) descending
    posts.sort(key=lambda x: x["score"], reverse=True)
    return posts[:20]


def fetch_leetcode_discussions(company: str) -> list[dict[str, Any]]:
    """Fetch LeetCode Discuss posts about a company via the public GraphQL endpoint."""
    gql = """
    query discussionList($first: Int, $query: String) {
      discussQuestionList(first: $first, query: $query, orderBy: MOST_VIEWED) {
        edges {
          node {
            id title viewCount commentCount slug
            post { content creationDate }
          }
        }
      }
    }
    """
    try:
        resp = requests.post(
            "https://leetcode.com/graphql/",
            json={"query": gql, "variables": {"first": 15, "query": f"{company} interview experience"}},
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://leetcode.com/discuss/",
            },
            timeout=12,
        )
        if resp.status_code != 200:
            return []

        edges = resp.json().get("data", {}).get("discussQuestionList", {}).get("edges", [])
        company_lower = company.lower()
        posts = []

        for edge in edges:
            node = edge.get("node", {})
            title = node.get("title", "")
            if company_lower not in title.lower():
                continue
            content = re.sub(r"<[^>]+>", "", node.get("post", {}).get("content", ""))[:350]
            posts.append({
                "title": title,
                "text": content,
                "views": node.get("viewCount", 0),
                "comments": node.get("commentCount", 0),
                "url": f"https://leetcode.com/discuss/interview-experience/{node.get('slug', '')}",
                "source": "LeetCode Discuss",
            })

        return posts
    except Exception:
        return []


def fetch_hn_discussions(company: str) -> list[dict[str, Any]]:
    """Fetch discussions from Hacker News using the Algolia public API."""
    try:
        # Search for company mentions in stories and comments
        url = f"https://hn.algolia.com/api/v1/search?query={urllib.parse.quote(company)}&tags=story&hitsPerPage=10"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return []
        
        hits = resp.json().get("hits", [])
        posts = []
        for hit in hits:
            posts.append({
                "title":  hit.get("title", "HN Thread"),
                "text":   hit.get("text", "")[:350],
                "score":  hit.get("points", 0),
                "url":    f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                "source": "Hacker News",
            })
        return posts
    except Exception:
        return []


def fetch_ambitionbox_data(company: str) -> dict[str, Any]:
    """Scrape AmbitionBox for India-focused company ratings."""
    slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")
    url = f"https://www.ambitionbox.com/overview/{slug}-overview"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")

            # Look for rating number
            rating: float | None = None
            for tag in soup.find_all(string=re.compile(r"^\d\.\d$")):
                try:
                    v = float(tag.strip())
                    if 1.0 <= v <= 5.0:
                        rating = v
                        break
                except ValueError:
                    pass

            # Review count
            review_count: int | None = None
            m = re.search(r"(\d[\d,]+)\s+reviews?", resp.text, re.IGNORECASE)
            if m:
                review_count = int(m.group(1).replace(",", ""))

            return {
                "found": True,
                "rating": rating,
                "review_count": review_count,
                "url": url,
                "source": "AmbitionBox",
            }
    except Exception:
        pass
    return {"found": False, "rating": None, "review_count": None, "url": url, "source": "AmbitionBox"}


# ---------------------------------------------------------------------------
# Sentiment Analysis
# ---------------------------------------------------------------------------

_POSITIVE_KW = [
    "good", "great", "excellent", "amazing", "awesome", "best", "love", "fantastic",
    "helpful", "supportive", "growth", "learning", "friendly", "professional",
    "work life balance", "benefits", "collaborative", "innovative", "recommend",
    "positive", "happy", "satisfied", "impressed", "legitimate", "genuine",
]
_NEGATIVE_KW = [
    "bad", "terrible", "awful", "worst", "horrible", "scam", "fraud", "fake",
    "toxic", "unprofessional", "avoid", "warning", "ghosted", "never responded",
    "no offer", "wasted time", "rejected", "disappointed", "misleading", "lied",
    "overwork", "underpaid", "no work life balance", "management issues", "burnout",
    "beware", "stay away", "trap", "not legitimate", "not real",
]


def _keyword_sentiment(texts: list[str]) -> dict[str, int]:
    pos = neg = 0
    for t in texts:
        tl = t.lower()
        p = sum(1 for kw in _POSITIVE_KW if kw in tl)
        n = sum(1 for kw in _NEGATIVE_KW if kw in tl)
        if p > n:
            pos += 1
        elif n > p:
            neg += 1
    total = len(texts)
    neutral = total - pos - neg
    return {
        "positive": round(pos / total * 100) if total else 0,
        "negative": round(neg / total * 100) if total else 0,
        "neutral": round(neutral / total * 100) if total else 0,
        "total": total,
        "method": "keyword",
    }


def analyze_sentiment(texts: list[str]) -> dict[str, int]:
    if not texts:
        return {"positive": 0, "negative": 0, "neutral": 0, "total": 0, "method": "none"}

    pipe = _get_sentiment_pipeline()
    if pipe is None:
        return _keyword_sentiment(texts)

    try:
        truncated = [t[:450] for t in texts if t.strip()]
        results = pipe(truncated, batch_size=8)
        pos = sum(1 for r in results if r["label"] == "POSITIVE")
        neg = sum(1 for r in results if r["label"] == "NEGATIVE")
        total = len(results)
        return {
            "positive": round(pos / total * 100) if total else 0,
            "negative": round(neg / total * 100) if total else 0,
            "neutral": round((total - pos - neg) / total * 100) if total else 0,
            "total": total,
            "method": "distilbert",
        }
    except Exception:
        return _keyword_sentiment(texts)


# ---------------------------------------------------------------------------
# Red Flag Detection
# ---------------------------------------------------------------------------

_SCAM_KW = [
    "scam", "fraud", "fake", "never pay", "beware", "trap", "stay away",
    "blacklist", "con", "cheat", "cheated", "ghosted me", "lied", "misled",
    "false promises", "not legitimate", "fake company",
]


def detect_red_flags(
    wiki: dict, reddit: list, sentiment: dict, company: str
) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []

    if not wiki.get("found"):
        flags.append({
            "flag": "No verifiable online presence",
            "detail": (
                f'Could not find "{company}" on Wikipedia. Legitimate companies '
                "typically have verifiable public records."
            ),
            "severity": "high",
        })

    if wiki.get("founding_year"):
        age = datetime.datetime.now().year - wiki["founding_year"]
        if age < 2:
            flags.append({
                "flag": "Very new company",
                "detail": (
                    f'Company founded in {wiki["founding_year"]} — only {age} year(s) old. '
                    "New companies carry higher risk."
                ),
                "severity": "medium",
            })

    neg_pct = sentiment.get("negative", 0)
    if neg_pct > 60:
        flags.append({
            "flag": "High negative sentiment online",
            "detail": f"{neg_pct}% of online discussions are negative — possible systemic issues.",
            "severity": "high",
        })
    elif neg_pct > 40:
        flags.append({
            "flag": "Mixed online reputation",
            "detail": f"{neg_pct}% of online discussions contain negative feedback.",
            "severity": "medium",
        })

    scam_hits = sum(
        1 for p in reddit
        if any(kw in (p.get("title", "") + p.get("text", "")).lower() for kw in _SCAM_KW)
    )
    if scam_hits >= 3:
        flags.append({
            "flag": "Multiple scam reports found",
            "detail": f"{scam_hits} Reddit posts contain scam/fraud keywords about this company.",
            "severity": "high",
        })
    elif scam_hits == 1 or scam_hits == 2:
        flags.append({
            "flag": "Scam concerns reported",
            "detail": f"{scam_hits} online post(s) mention potential fraud or scam activity.",
            "severity": "medium",
        })

    return flags


# ---------------------------------------------------------------------------
# Trust Score
# ---------------------------------------------------------------------------

def calculate_trust_score(wiki: dict, sentiment: dict, flags: list, reddit_n: int, lc_n: int) -> int:
    score = 50

    if wiki.get("found"):
        score += 15
        if wiki.get("founding_year"):
            age = datetime.datetime.now().year - wiki["founding_year"]
            if age >= 20:
                score += 15
            elif age >= 10:
                score += 10
            elif age >= 5:
                score += 5
            elif age < 2:
                score -= 15
    else:
        score -= 15

    pos = sentiment.get("positive", 0)
    neg = sentiment.get("negative", 0)
    if pos > 60:
        score += 15
    elif pos > 40:
        score += 8
    if neg > 60:
        score -= 20
    elif neg > 40:
        score -= 10

    for f in flags:
        score -= 15 if f["severity"] == "high" else 8

    if reddit_n > 10:
        score += 5   # well-known company
    if lc_n > 0:
        score += 5   # developer-community recognition

    return max(5, min(95, score))


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def research_company(company: str, role: str = "", location: str = "") -> dict[str, Any]:
    """
    Orchestrates all data fetching and analysis for a company.
    Returns a structured dict ready to be JSON-serialised.
    """
    wiki      = fetch_wikipedia_info(company)
    reddit    = fetch_reddit_posts(company, role)
    leetcode  = fetch_leetcode_discussions(company)
    hn        = fetch_hn_discussions(company)
    so        = fetch_stackoverflow_mentions(company)
    ambition  = fetch_ambitionbox_data(company)
    logo_url  = fetch_company_logo(company, wiki.get("title") if wiki.get("found") else None)

    # Build text corpus for sentiment
    corpus = []
    for p in reddit:
        t = f"{p.get('title','')} {p.get('text','')}".strip()
        if t:
            corpus.append(t)
    for p in leetcode:
        t = f"{p.get('title','')} {p.get('text','')}".strip()
        if t:
            corpus.append(t)
    for p in hn:
        t = f"{p.get('title','')} {p.get('text','')}".strip()
        if t:
            corpus.append(t)
    for p in so:
        t = f"{p.get('title','')} {p.get('text','')}".strip()
        if t:
            corpus.append(t)

    sentiment  = analyze_sentiment(corpus)
    flags      = detect_red_flags(wiki, reddit, sentiment, company)
    trust      = calculate_trust_score(wiki, sentiment, flags, len(reddit), len(leetcode))

    # Build unified review list for the frontend
    reviews = []
    for p in reddit[:10]:
        reviews.append({
            "title":     p["title"],
            "text":      p.get("text", "")[:220],
            "source":    p["source"],
            "sub":       p.get("subreddit", ""),
            "url":       p["url"],
            "score":     p.get("score", 0),
        })
    for p in leetcode[:5]:
        reviews.append({
            "title":  p["title"],
            "text":   p.get("text", "")[:220],
            "source": p["source"],
            "url":    p["url"],
            "views":  p.get("views", 0),
        })
    for p in hn[:5]:
        reviews.append({
            "title":  p["title"],
            "text":   p.get("text", "")[:220],
            "source": p["source"],
            "url":    p["url"],
            "score":  p.get("score", 0),
        })
    for p in so[:5]:
        reviews.append({
            "title":  p["title"],
            "text":   p.get("text", "")[:220],
            "source": p["source"],
            "url":    p["url"],
            "score":  p.get("score", 0),
        })

    return {
        "company":     company,
        "role":        role,
        "location":    location,
        "trust_score": trust,
        "trust_level": "High" if trust >= 65 else "Medium" if trust >= 40 else "Low",
        "wikipedia":   wiki,
        "sentiment":   sentiment,
        "red_flags":   flags,
        "reviews":     reviews,
        "ambitionbox": ambition,
        "logo_url":    logo_url,
        "sources": {
            "reddit":   len(reddit),
            "leetcode": len(leetcode),
            "hn":       len(hn),
            "so":       len(so),
        },
    }
