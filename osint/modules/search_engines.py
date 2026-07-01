"""
Search Engine Intelligence Module
===================================
Performs advanced Google dorking and DuckDuckGo searches
to find mentions of the phone number across the web.
Supports Google Custom Search API for automated results.
"""

import re
import json
import urllib.parse
import requests
import phonenumbers
from bs4 import BeautifulSoup

from shared.config import get_env
from osint.report import ModuleResult

_TIMEOUT = 10
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _build_google_dorks(e164: str, national: str) -> list[dict]:
    """
    Build an extensive set of Google dork queries for the phone number.
    Each dork targets a specific type of intelligence.
    """
    clean = re.sub(r"\D", "", e164)
    digits10 = clean[-10:] if len(clean) >= 10 else clean

    # Build format variants for query
    formats = list({
        e164,
        clean,
        national,
        re.sub(r"[\s\-\(\)]+", "", national),
    })

    dorks = []

    for phone in formats[:2]:  # Use top 2 formats to avoid too many dorks
        escaped = f'"{phone}"'

        # General web mentions
        dorks.append({
            "query": escaped,
            "category": "General Web Mentions",
            "url": f"https://www.google.com/search?q={urllib.parse.quote(escaped)}",
        })

        # Social media sites
        for site, name in [
            ("facebook.com", "Facebook"),
            ("linkedin.com", "LinkedIn"),
            ("twitter.com", "Twitter"),
            ("instagram.com", "Instagram"),
            ("tiktok.com", "TikTok"),
            ("vk.com", "VKontakte"),
        ]:
            q = f'{escaped} site:{site}'
            dorks.append({
                "query": q,
                "category": f"{name} Mentions",
                "url": f"https://www.google.com/search?q={urllib.parse.quote(q)}",
            })

    # Special dorks (only with primary format)
    primary = f'"{e164}"'

    # Leaked documents
    for ftype in ["pdf", "doc", "xls", "csv"]:
        q = f'{primary} filetype:{ftype}'
        dorks.append({
            "query": q,
            "category": f"Leaked {ftype.upper()} Documents",
            "url": f"https://www.google.com/search?q={urllib.parse.quote(q)}",
        })

    # Contact pages / directories
    for term in ["contact", "directory", "staff", "about", "team"]:
        q = f'{primary} inurl:{term}'
        dorks.append({
            "query": q,
            "category": f"Contact/Directory Pages ({term})",
            "url": f"https://www.google.com/search?q={urllib.parse.quote(q)}",
        })

    # Paste sites (potential leaks)
    for site in ["pastebin.com", "ghostbin.com", "paste.ee", "justpaste.it"]:
        q = f'{primary} site:{site}'
        dorks.append({
            "query": q,
            "category": f"Paste Site ({site})",
            "url": f"https://www.google.com/search?q={urllib.parse.quote(q)}",
        })

    # Classifieds / marketplaces
    for site in ["craigslist.org", "olx.com", "gumtree.com", "ebay.com"]:
        q = f'{primary} site:{site}'
        dorks.append({
            "query": q,
            "category": f"Marketplace ({site})",
            "url": f"https://www.google.com/search?q={urllib.parse.quote(q)}",
        })

    # Court / public records
    q = f'{primary} ("court" OR "case" OR "arrest" OR "warrant" OR "docket")'
    dorks.append({
        "query": q,
        "category": "Court / Legal Records",
        "url": f"https://www.google.com/search?q={urllib.parse.quote(q)}",
    })

    # Job / business listings
    q = f'{primary} ("resume" OR "CV" OR "job" OR "hiring" OR "employee")'
    dorks.append({
        "query": q,
        "category": "Resume / Job Listings",
        "url": f"https://www.google.com/search?q={urllib.parse.quote(q)}",
    })

    return dorks


def _google_custom_search(query: str) -> list[dict]:
    """
    Use Google Custom Search API for automated results.
    Free tier: 100 queries/day.
    """
    api_key = get_env("GOOGLE_API_KEY")
    cse_id = get_env("GOOGLE_CSE_ID")

    if not api_key or not cse_id:
        return []

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cse_id,
        "q": query,
        "num": 10,
    }

    try:
        resp = requests.get(url, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("items", []):
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            })
        return results
    except Exception:
        return []


def _duckduckgo_search(query: str) -> list[dict]:
    """
    Use DuckDuckGo HTML search (no API key needed).
    Scrapes the lite/html version for results.
    """
    results = []

    try:
        url = "https://html.duckduckgo.com/html/"
        resp = requests.post(
            url,
            data={"q": query},
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        for result_div in soup.select(".result"):
            title_tag = result_div.select_one(".result__title a")
            snippet_tag = result_div.select_one(".result__snippet")

            if title_tag:
                link = title_tag.get("href", "")
                # DuckDuckGo wraps links — extract the actual URL
                if "uddg=" in link:
                    link = urllib.parse.unquote(
                        link.split("uddg=")[1].split("&")[0]
                    )

                results.append({
                    "title": title_tag.get_text(strip=True),
                    "link": link,
                    "snippet": snippet_tag.get_text(strip=True) if snippet_tag else "",
                })

        return results[:10]

    except Exception:
        return []


def lookup(phone_raw: str, parsed: phonenumbers.PhoneNumber) -> ModuleResult:
    """
    Run search engine intelligence gathering.
    Builds Google dorks, queries DuckDuckGo, and optionally uses Google CSE API.
    """
    result = ModuleResult(module_name="search_engines")

    try:
        e164 = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.E164
        )
        national = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.NATIONAL
        )

        # Build all Google dorks
        dorks = _build_google_dorks(e164, national)

        # Organize dorks by category
        dork_categories = {}
        for dork in dorks:
            cat = dork["category"]
            dork_categories.setdefault(cat, []).append(dork["url"])
            result.urls.append(dork["url"])

        result.data["Google Dorks Generated"] = f"{len(dorks)} search queries"
        result.data["Categories Covered"] = ", ".join(sorted(set(
            d["category"].split(" (")[0] for d in dorks
        )))

        # DuckDuckGo automated search
        ddg_results = _duckduckgo_search(f'"{e164}"')
        if ddg_results:
            result.data["DuckDuckGo Results Found"] = str(len(ddg_results))
            for i, r in enumerate(ddg_results[:5]):
                result.data[f"DDG Result #{i+1}"] = (
                    f"{r['title']}\n  → {r['link']}\n  {r['snippet'][:120]}"
                )
                result.urls.append(r["link"])
        else:
            result.data["DuckDuckGo Results"] = "No direct results found"

        # Google Custom Search API (if configured)
        cse_results = _google_custom_search(f'"{e164}"')
        if cse_results:
            result.data["Google CSE Results Found"] = str(len(cse_results))
            for i, r in enumerate(cse_results[:5]):
                result.data[f"CSE Result #{i+1}"] = (
                    f"{r['title']}\n  → {r['link']}\n  {r['snippet'][:120]}"
                )
                result.urls.append(r["link"])
        elif get_env("GOOGLE_API_KEY"):
            result.data["Google CSE Results"] = "No results found"

        result.success = True

    except Exception as e:
        result.errors.append(f"Search engine lookup failed: {e}")

    return result
