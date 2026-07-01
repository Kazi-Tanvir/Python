"""
Social Media Lookup Module
===========================
Checks if a phone number is associated with accounts on major social
media platforms. Constructs search URLs and performs availability probes
where possible.
"""

import re
import hashlib
import requests
import phonenumbers

from osint.report import ModuleResult

_TIMEOUT = 8
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _check_url(url: str, success_indicators: list[str] = None) -> bool | None:
    """
    Probe a URL to see if it resolves to a valid profile.
    Returns True if profile found, False if 404, None if uncertain.
    """
    try:
        resp = requests.get(
            url,
            headers=_HEADERS,
            timeout=_TIMEOUT,
            allow_redirects=True,
        )
        if resp.status_code == 404:
            return False
        if resp.status_code == 200:
            if success_indicators:
                page = resp.text.lower()
                return any(ind.lower() in page for ind in success_indicators)
            return True
        return None
    except Exception:
        return None


def _phone_variants(e164: str, national: str) -> list[str]:
    """Generate multiple format variants for searching."""
    variants = set()

    # E.164 format: +1234567890
    variants.add(e164)

    # Without plus: 1234567890
    variants.add(e164.lstrip("+"))

    # National format (may have spaces/dashes)
    variants.add(national)

    # No spaces/dashes
    clean = re.sub(r"[\s\-\(\)]+", "", national)
    variants.add(clean)

    # With dashes (US-style): 123-456-7890
    digits = re.sub(r"\D", "", e164)
    if len(digits) >= 10:
        last10 = digits[-10:]
        variants.add(f"{last10[:3]}-{last10[3:6]}-{last10[6:]}")
        variants.add(f"({last10[:3]}) {last10[3:6]}-{last10[6:]}")

    # URL-encoded variants
    variants.add(e164.replace("+", "%2B"))

    return list(variants)


def _build_social_urls(e164: str, national: str) -> dict[str, list[dict]]:
    """
    Build search/lookup URLs for every major social media platform.
    Returns a dict of platform -> list of {url, type, description}.
    """
    clean = re.sub(r"\D", "", e164)
    variants = _phone_variants(e164, national)
    primary_query = e164

    platforms = {}

    # ── Facebook ──
    platforms["Facebook"] = [
        {
            "url": f"https://www.facebook.com/search/people/?q={primary_query}",
            "type": "search",
            "desc": "Facebook People Search",
        },
        {
            "url": f"https://www.facebook.com/login/identify/?ctx=recover&lwv=110&phone={clean}",
            "type": "recovery",
            "desc": "Facebook Account Recovery (may reveal partial name)",
        },
        {
            "url": f"https://m.facebook.com/search/people/?q={primary_query}",
            "type": "search",
            "desc": "Facebook Mobile Search",
        },
    ]

    # ── Instagram ──
    platforms["Instagram"] = [
        {
            "url": f"https://www.instagram.com/accounts/account_recovery_send_ajax/",
            "type": "recovery",
            "desc": "Instagram Recovery Endpoint (POST with phone)",
        },
        {
            "url": f"https://www.google.com/search?q=site:instagram.com+\"{primary_query}\"",
            "type": "google_dork",
            "desc": "Google → Instagram phone mention",
        },
    ]

    # ── Twitter / X ──
    platforms["Twitter / X"] = [
        {
            "url": f"https://twitter.com/search?q=\"{primary_query}\"&f=user",
            "type": "search",
            "desc": "Twitter/X User Search",
        },
        {
            "url": f"https://x.com/search?q=\"{primary_query}\"&f=user",
            "type": "search",
            "desc": "X.com User Search",
        },
    ]

    # ── LinkedIn ──
    platforms["LinkedIn"] = [
        {
            "url": f"https://www.google.com/search?q=site:linkedin.com/in+\"{primary_query}\"",
            "type": "google_dork",
            "desc": "Google → LinkedIn profile with phone",
        },
        {
            "url": f"https://www.linkedin.com/search/results/people/?keywords={primary_query}",
            "type": "search",
            "desc": "LinkedIn People Search",
        },
    ]

    # ── TikTok ──
    platforms["TikTok"] = [
        {
            "url": f"https://www.google.com/search?q=site:tiktok.com+\"{primary_query}\"",
            "type": "google_dork",
            "desc": "Google → TikTok profile with phone",
        },
    ]

    # ── Snapchat ──
    platforms["Snapchat"] = [
        {
            "url": f"https://www.google.com/search?q=site:snapchat.com+\"{primary_query}\"",
            "type": "google_dork",
            "desc": "Google → Snapchat with phone",
        },
    ]

    # ── Pinterest ──
    platforms["Pinterest"] = [
        {
            "url": f"https://www.google.com/search?q=site:pinterest.com+\"{primary_query}\"",
            "type": "google_dork",
            "desc": "Google → Pinterest with phone",
        },
    ]

    # ── Reddit ──
    platforms["Reddit"] = [
        {
            "url": f"https://www.google.com/search?q=site:reddit.com+\"{primary_query}\"",
            "type": "google_dork",
            "desc": "Google → Reddit mentions",
        },
        {
            "url": f"https://www.reddit.com/search/?q=\"{primary_query}\"",
            "type": "search",
            "desc": "Reddit Search",
        },
    ]

    # ── GitHub ──
    platforms["GitHub"] = [
        {
            "url": f"https://github.com/search?q=\"{primary_query}\"&type=code",
            "type": "search",
            "desc": "GitHub Code Search (leaked in repos?)",
        },
    ]

    # ── Gravatar ──
    # Check if phone-derived patterns exist
    for variant in [e164, clean]:
        email_guess = f"{variant}@gmail.com"
        md5 = hashlib.md5(email_guess.lower().encode()).hexdigest()
        platforms.setdefault("Gravatar", []).append({
            "url": f"https://www.gravatar.com/avatar/{md5}?d=404",
            "type": "probe",
            "desc": f"Gravatar check for {email_guess}",
        })

    return platforms


def lookup(phone_raw: str, parsed: phonenumbers.PhoneNumber) -> ModuleResult:
    """
    Check social media platforms for the phone number.
    Constructs search URLs and probes where possible.
    """
    result = ModuleResult(module_name="social_media")

    try:
        e164 = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.E164
        )
        national = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.NATIONAL
        )

        platforms = _build_social_urls(e164, national)

        found = {}
        all_urls = []

        for platform, entries in platforms.items():
            platform_urls = []
            for entry in entries:
                url = entry["url"]
                desc = entry["desc"]
                platform_urls.append(f"{desc}: {url}")
                all_urls.append(url)

                # Attempt automated probe for certain types
                if entry["type"] == "probe":
                    status = _check_url(url)
                    if status is True:
                        found[platform] = f"✅ Possible match found"
                    elif status is False:
                        found[platform] = f"❌ Not found"

            if platform not in found:
                found[platform] = "🔗 Manual verification needed"

        result.data = found
        result.data["_search_urls"] = {
            platform: [e["url"] for e in entries]
            for platform, entries in platforms.items()
        }

        # Flatten all URLs for the report
        for platform, entries in platforms.items():
            for entry in entries:
                result.urls.append(entry["url"])

        result.success = True

    except Exception as e:
        result.errors.append(f"Social media lookup failed: {e}")

    return result
