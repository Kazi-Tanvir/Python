"""
Messaging Apps Lookup Module
=============================
Checks if a phone number is registered on messaging platforms:
WhatsApp, Telegram, Viber, Signal, Skype.
Uses public-facing endpoints and URL probing.
"""

import re
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
}


def _check_whatsapp(e164: str) -> dict:
    """
    Check WhatsApp presence via wa.me redirect.
    wa.me/<number> redirects to the WhatsApp web/app if the number exists.
    """
    clean = e164.lstrip("+")
    info = {
        "Platform": "WhatsApp",
        "Status": "Unknown",
        "Direct Link": f"https://wa.me/{clean}",
        "API Link": f"https://api.whatsapp.com/send?phone={clean}",
    }

    try:
        # wa.me will redirect — if the number exists, it goes to a valid page
        resp = requests.head(
            f"https://wa.me/{clean}",
            headers=_HEADERS,
            timeout=_TIMEOUT,
            allow_redirects=False,
        )

        if resp.status_code in (301, 302):
            location = resp.headers.get("Location", "")
            if "send" in location or "api.whatsapp" in location:
                info["Status"] = "✅ Number registered on WhatsApp"
            else:
                info["Status"] = "🔗 Redirect detected — likely registered"
        elif resp.status_code == 200:
            info["Status"] = "✅ Likely registered on WhatsApp"
        elif resp.status_code == 404:
            info["Status"] = "❌ Not found on WhatsApp"
        else:
            info["Status"] = f"⚠️ Uncertain (HTTP {resp.status_code})"

    except requests.exceptions.Timeout:
        info["Status"] = "⏱️ Request timed out"
    except Exception as e:
        info["Status"] = f"⚠️ Check failed: {str(e)[:60]}"

    return info


def _check_telegram(e164: str) -> dict:
    """
    Check Telegram presence.
    Uses t.me phone lookup patterns and the public resolver.
    """
    clean = e164.lstrip("+")
    info = {
        "Platform": "Telegram",
        "Status": "🔗 Manual verification required",
        "Resolve Link": f"https://t.me/+{clean}",
        "Search Method": "Open Telegram app → Contacts → Add by phone number",
    }

    try:
        # Try the t.me link to see if it resolves
        resp = requests.head(
            f"https://t.me/+{clean}",
            headers=_HEADERS,
            timeout=_TIMEOUT,
            allow_redirects=False,
        )

        if resp.status_code in (200, 301, 302):
            location = resp.headers.get("Location", "")
            if resp.status_code == 200:
                info["Status"] = "🔗 Link is active (may be invite or profile)"
            elif "tg://" in location:
                info["Status"] = "✅ Telegram account detected (deep link redirect)"
        elif resp.status_code == 404:
            info["Status"] = "❌ No public Telegram link found"

    except Exception as e:
        info["Status"] = f"⚠️ Check failed: {str(e)[:60]}"

    return info


def _check_viber(e164: str) -> dict:
    """Check Viber presence via public directory."""
    clean = e164.lstrip("+")
    info = {
        "Platform": "Viber",
        "Status": "🔗 Manual verification required",
        "Lookup Link": f"viber://add?number={clean}",
        "Search Method": "Open Viber → Search → Enter phone number",
    }

    try:
        resp = requests.get(
            f"https://www.viber.com/api/lookup?phone={clean}",
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            info["Status"] = "✅ Viber account may exist"
        elif resp.status_code == 404:
            info["Status"] = "❌ Not found on Viber"
    except Exception:
        pass

    return info


def _check_signal(e164: str) -> dict:
    """Check Signal — limited to URL generation since Signal is privacy-focused."""
    return {
        "Platform": "Signal",
        "Status": "🔗 Manual verification required",
        "Lookup Method": "Open Signal → New Message → Enter phone number",
        "Note": "Signal does not expose a public lookup API (privacy by design)",
    }


def _check_skype(e164: str) -> dict:
    """Check Skype via web search."""
    clean = e164.lstrip("+")
    return {
        "Platform": "Skype",
        "Status": "🔗 Manual verification required",
        "Search Link": f"https://www.google.com/search?q=site:join.skype.com+\"{e164}\"",
        "Web Search": f"https://web.skype.com/search?q={clean}",
        "Lookup Method": "Open Skype → People → Search by phone number",
    }


def _check_line(e164: str) -> dict:
    """Check LINE messenger."""
    return {
        "Platform": "LINE",
        "Status": "🔗 Manual verification required",
        "Lookup Method": "Open LINE → Add Friends → Search by Phone",
        "Google Dork": f"https://www.google.com/search?q=site:line.me+\"{e164}\"",
    }


def _check_wechat(e164: str) -> dict:
    """Check WeChat."""
    return {
        "Platform": "WeChat",
        "Status": "🔗 Manual verification required",
        "Lookup Method": "Open WeChat → Contacts → Add → Search by Phone",
        "Google Dork": f"https://www.google.com/search?q=\"{e164}\"+wechat",
    }


def lookup(phone_raw: str, parsed: phonenumbers.PhoneNumber) -> ModuleResult:
    """
    Check all messaging platforms for the phone number.
    """
    result = ModuleResult(module_name="messaging_apps")

    try:
        e164 = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.E164
        )

        checks = [
            _check_whatsapp(e164),
            _check_telegram(e164),
            _check_viber(e164),
            _check_signal(e164),
            _check_skype(e164),
            _check_line(e164),
            _check_wechat(e164),
        ]

        for check in checks:
            platform = check.pop("Platform", "Unknown")
            result.data[platform] = check

            # Collect clickable URLs
            for key, val in check.items():
                if isinstance(val, str) and (
                    val.startswith("http")
                    or val.startswith("viber://")
                ):
                    result.urls.append(val)

        result.success = True

    except Exception as e:
        result.errors.append(f"Messaging apps lookup failed: {e}")

    return result
