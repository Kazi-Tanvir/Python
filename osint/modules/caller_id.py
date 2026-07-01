"""
Caller ID & Phone Directory Module
====================================
Queries public phone directories, reverse lookup services,
and caller identification databases.
"""

import re
import urllib.parse
import requests
import phonenumbers
from phonenumbers import geocoder

from osint.report import ModuleResult

_TIMEOUT = 10
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


def _build_directory_urls(e164: str, national: str, region: str) -> list[dict]:
    """
    Build reverse phone lookup URLs for major directories.
    Covers US/international directories and caller ID services.
    """
    clean = re.sub(r"\D", "", e164)
    digits10 = clean[-10:] if len(clean) >= 10 else clean
    encoded = urllib.parse.quote(e164)

    directories = []

    # ── International / General ──
    directories.extend([
        {
            "service": "Truecaller",
            "url": f"https://www.truecaller.com/search/{region.lower()}/{digits10}",
            "region": "Global",
            "type": "Caller ID",
        },
        {
            "service": "Sync.me",
            "url": f"https://sync.me/search/?number={encoded}",
            "region": "Global",
            "type": "Caller ID",
        },
        {
            "service": "Whocalledme.com",
            "url": f"https://whocalledme.com/phone-number/{digits10}",
            "region": "Global",
            "type": "Caller ID / Spam",
        },
        {
            "service": "SpyDialer",
            "url": f"https://www.spydialer.com/results.aspx?type=phone&q={digits10}",
            "region": "US/Global",
            "type": "Reverse Lookup",
        },
        {
            "service": "NumLookup",
            "url": f"https://www.numlookup.com/phone/{encoded}",
            "region": "Global",
            "type": "Carrier Lookup",
        },
        {
            "service": "FreeCarrierLookup",
            "url": f"https://freecarrierlookup.com/?phone={digits10}",
            "region": "US",
            "type": "Carrier Lookup",
        },
    ])

    # ── US-specific directories ──
    if region in ("US", "CA", ""):
        directories.extend([
            {
                "service": "WhitePages",
                "url": f"https://www.whitepages.com/phone/{digits10}",
                "region": "US",
                "type": "Reverse Lookup",
            },
            {
                "service": "AnyWho",
                "url": f"https://www.anywho.com/phone/{digits10}",
                "region": "US",
                "type": "Reverse Lookup",
            },
            {
                "service": "ThatsThem",
                "url": f"https://thatsthem.com/phone/{digits10}",
                "region": "US",
                "type": "People Search",
            },
            {
                "service": "FastPeopleSearch",
                "url": f"https://www.fastpeoplesearch.com/{digits10}",
                "region": "US",
                "type": "People Search",
            },
            {
                "service": "USPhonebook",
                "url": f"https://www.usphonebook.com/{digits10}",
                "region": "US",
                "type": "People Search",
            },
            {
                "service": "ZabaSearch",
                "url": f"https://www.zabasearch.com/phone/{digits10}",
                "region": "US",
                "type": "People Search",
            },
            {
                "service": "411.com",
                "url": f"https://www.411.com/phone/{digits10}",
                "region": "US",
                "type": "Reverse Lookup",
            },
            {
                "service": "Spokeo",
                "url": f"https://www.spokeo.com/phone-lookup/{digits10}",
                "region": "US",
                "type": "People Search",
            },
            {
                "service": "BeenVerified",
                "url": f"https://www.beenverified.com/phone/{digits10}/",
                "region": "US",
                "type": "Background Check",
            },
            {
                "service": "Intelius",
                "url": f"https://www.intelius.com/phone/{digits10}/",
                "region": "US",
                "type": "Background Check",
            },
        ])

    # ── UK directories ──
    if region in ("GB", "UK", ""):
        directories.extend([
            {
                "service": "TheTelephoneBook (UK)",
                "url": f"https://www.thephonebook.bt.com/result?page_num=1&search_type=reverse&search_text={digits10}",
                "region": "UK",
                "type": "Reverse Lookup",
            },
        ])

    # ── India directories ──
    if region in ("IN", ""):
        directories.extend([
            {
                "service": "IndiaPhoneNumber",
                "url": f"https://www.google.com/search?q=\"{e164}\"+india+phone+directory",
                "region": "IN",
                "type": "Directory Search",
            },
        ])

    return directories


def _check_truecaller_web(e164: str, region: str) -> dict:
    """
    Attempt to probe Truecaller web for basic info.
    Full results require auth, but we can check if the page loads.
    """
    clean = re.sub(r"\D", "", e164)
    digits10 = clean[-10:] if len(clean) >= 10 else clean
    url = f"https://www.truecaller.com/search/{region.lower()}/{digits10}"

    info = {
        "Service": "Truecaller",
        "Lookup URL": url,
        "Status": "🔗 Manual check required (sign in for full details)",
    }

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)
        if resp.status_code == 200:
            if "truecaller" in resp.text.lower():
                info["Status"] = "✅ Truecaller page exists — sign in for name/details"
        elif resp.status_code == 404:
            info["Status"] = "❌ Not found on Truecaller"
    except Exception:
        pass

    return info


def lookup(phone_raw: str, parsed: phonenumbers.PhoneNumber) -> ModuleResult:
    """
    Query phone directories and caller ID services.
    """
    result = ModuleResult(module_name="caller_id")

    try:
        e164 = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.E164
        )
        national = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.NATIONAL
        )
        region = phonenumbers.region_code_for_number(parsed) or ""

        # Build directory URLs
        directories = _build_directory_urls(e164, national, region)

        # Truecaller check
        truecaller = _check_truecaller_web(e164, region)
        result.data["Truecaller"] = truecaller

        # Organize by type
        by_type = {}
        for d in directories:
            dtype = d["type"]
            if dtype not in by_type:
                by_type[dtype] = {}
            by_type[dtype][d["service"]] = d["url"]
            result.urls.append(d["url"])

        for dtype, services in by_type.items():
            result.data[dtype] = services

        result.data["Region Detected"] = region or "Unknown"
        result.data["Total Directories"] = str(len(directories))

        result.success = True

    except Exception as e:
        result.errors.append(f"Caller ID lookup failed: {e}")

    return result
