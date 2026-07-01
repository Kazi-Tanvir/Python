"""
Data Breach Lookup Module
==========================
Checks if a phone number appears in known data breaches,
paste dumps, or leaked databases. Uses public search interfaces
and URL generation for manual verification.
"""

import urllib.parse
import requests
import phonenumbers

from osint.report import ModuleResult

_TIMEOUT = 10
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


def _check_haveibeenpwned_phone(e164: str) -> dict:
    """
    Check HaveIBeenPwned for the phone number.
    Note: HIBP primarily indexes emails, but some breaches contain phone numbers.
    The search URL allows checking if the number appears in any breach.
    """
    encoded = urllib.parse.quote(e164)
    return {
        "Service": "Have I Been Pwned",
        "Search URL": f"https://haveibeenpwned.com/unifiedsearch/{encoded}",
        "Note": "HIBP indexes emails primarily; phone breaches are limited",
        "Status": "🔗 Manual check required",
    }


def _check_intelligence_x(e164: str) -> dict:
    """
    Intelligence X — Powerful search engine for leaked data.
    Has a public search interface.
    """
    encoded = urllib.parse.quote(e164)
    return {
        "Service": "Intelligence X",
        "Search URL": f"https://intelx.io/?s={encoded}",
        "Note": "Searches breaches, paste sites, darknet, and public records",
        "Status": "🔗 Manual check required (free account available)",
    }


def _check_dehashed(e164: str) -> dict:
    """
    Dehashed — Search engine for leaked credentials.
    Supports phone number searches.
    """
    clean = e164.lstrip("+")
    return {
        "Service": "Dehashed",
        "Search URL": f"https://www.dehashed.com/search?query={clean}",
        "Note": "Requires free account for full results",
        "Status": "🔗 Manual check required",
    }


def _check_leakcheck(e164: str) -> dict:
    """
    LeakCheck — Data breach search engine.
    """
    clean = e164.lstrip("+")
    return {
        "Service": "LeakCheck",
        "Search URL": f"https://leakcheck.io/search?query={clean}&type=phone",
        "Note": "Free tier available with limited results",
        "Status": "🔗 Manual check required",
    }


def _check_snusbase(e164: str) -> dict:
    """
    Snusbase — Database search engine.
    """
    return {
        "Service": "Snusbase",
        "Search URL": f"https://snusbase.com/search?q={urllib.parse.quote(e164)}",
        "Note": "Paid service, but shows if results exist for free",
        "Status": "🔗 Manual check required",
    }


def _check_breachdirectory(e164: str) -> dict:
    """
    BreachDirectory — Free breach search.
    """
    clean = e164.lstrip("+")
    return {
        "Service": "BreachDirectory",
        "Search URL": f"https://breachdirectory.org/search?q={clean}",
        "Note": "Free search with partial result preview",
        "Status": "🔗 Manual check required",
    }


def _check_hudsonrock(e164: str) -> dict:
    """
    Hudson Rock Cavalier — Free cybercrime intelligence tool.
    Checks if the phone number appears in infostealer malware logs.
    """
    info = {
        "Service": "Hudson Rock (Cavalier)",
        "Status": "🔗 Checking...",
    }

    try:
        url = f"https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-phone"
        params = {"phone": e164.lstrip("+")}
        resp = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)

        if resp.status_code == 200:
            data = resp.json()
            if data and (isinstance(data, list) and len(data) > 0):
                info["Status"] = "⚠️ Phone found in infostealer logs!"
                info["Records Found"] = str(len(data))
                # Extract key info from first few records
                for i, record in enumerate(data[:3]):
                    if isinstance(record, dict):
                        info[f"Record {i+1} - Source"] = record.get("source", "Unknown")
                        info[f"Record {i+1} - Date"] = record.get("date_compromised", "Unknown")
            else:
                info["Status"] = "✅ Not found in infostealer logs"
        else:
            info["Status"] = "🔗 Manual check required"
            info["Search URL"] = "https://cavalier.hudsonrock.com/osint"

    except Exception:
        info["Status"] = "🔗 Manual check required"
        info["Search URL"] = "https://cavalier.hudsonrock.com/osint"

    return info


def _check_pasted_sites(e164: str) -> list[dict]:
    """
    Generate search URLs for paste sites that may contain the phone number.
    """
    sites = [
        ("Pastebin", f"https://www.google.com/search?q=site:pastebin.com+\"{e164}\""),
        ("GitHub Gists", f"https://gist.github.com/search?q={urllib.parse.quote(e164)}"),
        ("JustPaste.it", f"https://www.google.com/search?q=site:justpaste.it+\"{e164}\""),
        ("Paste.ee", f"https://www.google.com/search?q=site:paste.ee+\"{e164}\""),
        ("Ghostbin", f"https://www.google.com/search?q=site:ghostbin.com+\"{e164}\""),
    ]

    return [
        {"Service": name, "Search URL": url, "Status": "🔗 Manual check"}
        for name, url in sites
    ]


def lookup(phone_raw: str, parsed: phonenumbers.PhoneNumber) -> ModuleResult:
    """
    Check data breach databases and paste sites for the phone number.
    """
    result = ModuleResult(module_name="data_breaches")

    try:
        e164 = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.E164
        )

        # Run all breach checks
        breach_checks = [
            _check_haveibeenpwned_phone(e164),
            _check_intelligence_x(e164),
            _check_dehashed(e164),
            _check_leakcheck(e164),
            _check_snusbase(e164),
            _check_breachdirectory(e164),
            _check_hudsonrock(e164),
        ]

        for check in breach_checks:
            service = check.get("Service", "Unknown")
            result.data[service] = check
            # Collect URLs
            if "Search URL" in check:
                result.urls.append(check["Search URL"])

        # Paste site checks
        paste_checks = _check_pasted_sites(e164)
        paste_results = {}
        for paste in paste_checks:
            paste_results[paste["Service"]] = paste["Search URL"]
            result.urls.append(paste["Search URL"])

        result.data["Paste Sites"] = paste_results

        result.success = True

    except Exception as e:
        result.errors.append(f"Data breach lookup failed: {e}")

    return result
