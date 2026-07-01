"""
Reputation & Risk Scoring Module
==================================
Checks spam/scam databases, robocall registries, and regulatory
complaint databases. Produces an aggregate risk score.
"""

import re
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


def _build_spam_urls(e164: str, region: str) -> list[dict]:
    """Build URLs for spam/scam checking services."""
    clean = re.sub(r"\D", "", e164)
    digits10 = clean[-10:] if len(clean) >= 10 else clean
    encoded = urllib.parse.quote(e164)

    urls = [
        # International spam checkers
        {
            "service": "ShouldIAnswer",
            "url": f"https://www.shouldianswer.com/phone-number/{clean}",
            "type": "Spam Database",
        },
        {
            "service": "CallerComplaints",
            "url": f"https://www.callercomplaint.com/phone-number/{digits10}",
            "type": "Complaint Database",
        },
        {
            "service": "WhoCalledMe",
            "url": f"https://www.whocalledme.com/phone-number/{digits10}",
            "type": "Caller Reports",
        },
        {
            "service": "CallerID Test (Google)",
            "url": f"https://www.google.com/search?q=\"{e164}\"+spam+OR+scam+OR+fraud+OR+robocall",
            "type": "Google Spam Check",
        },
    ]

    # US-specific
    if region in ("US", "CA", ""):
        urls.extend([
            {
                "service": "FTC Complaint Search",
                "url": f"https://www.google.com/search?q=site:ftc.gov+\"{e164}\"",
                "type": "FTC Complaints",
            },
            {
                "service": "FCC Robocall Search",
                "url": f"https://www.google.com/search?q=site:fcc.gov+\"{e164}\"+robocall",
                "type": "FCC Reports",
            },
            {
                "service": "DoNotCall Registry Check",
                "url": "https://www.donotcall.gov/verify.html",
                "type": "DNC Registry",
            },
            {
                "service": "800Notes",
                "url": f"https://800notes.com/Phone.aspx/{digits10}",
                "type": "Caller Reports",
            },
            {
                "service": "RoboKiller",
                "url": f"https://lookup.robokiller.com/p/{digits10}",
                "type": "Robocall Database",
            },
            {
                "service": "Nomorobo",
                "url": f"https://www.nomorobo.com/lookup/{digits10}",
                "type": "Robocall Database",
            },
        ])

    # UK-specific
    if region in ("GB", "UK"):
        urls.extend([
            {
                "service": "Ofcom Nuisance Calls (UK)",
                "url": f"https://www.google.com/search?q=site:ofcom.org.uk+\"{e164}\"",
                "type": "Ofcom Reports",
            },
        ])

    return urls


def _calculate_risk_score(data: dict) -> dict:
    """
    Calculate a heuristic risk score based on gathered data.
    Score: 0 (safe) to 100 (high risk).
    """
    score = 0
    factors = []

    # Check for VoIP (higher risk for spam/scam)
    for key, val in data.items():
        val_str = str(val).lower()
        if "voip" in val_str:
            score += 15
            factors.append("VoIP number detected (+15)")
            break

    # Check for prepaid
    for key, val in data.items():
        val_str = str(val).lower()
        if "prepaid" in val_str and ("yes" in val_str or "true" in val_str):
            score += 10
            factors.append("Prepaid number (+10)")
            break

    # Check for fraud/spam mentions
    for key, val in data.items():
        val_str = str(val).lower()
        if any(w in val_str for w in ["spam", "scam", "fraud", "abuse"]):
            if any(w in val_str for w in ["yes", "found", "reported", "⚠️"]):
                score += 25
                factors.append(f"Spam/scam indicator in {key} (+25)")

    # If no concerning signals, it's likely clean
    if score == 0:
        factors.append("No risk indicators found")

    # Cap at 100
    score = min(score, 100)

    # Classify
    if score >= 70:
        risk_level = "🔴 HIGH RISK"
    elif score >= 40:
        risk_level = "🟡 MODERATE RISK"
    elif score >= 15:
        risk_level = "🟠 LOW RISK"
    else:
        risk_level = "🟢 CLEAN"

    return {
        "Risk Score": f"{score}/100",
        "Risk Level": risk_level,
        "Risk Factors": "\n".join(f"  • {f}" for f in factors) if factors else "None",
    }


def lookup(phone_raw: str, parsed: phonenumbers.PhoneNumber) -> ModuleResult:
    """
    Check spam/scam databases and calculate risk score.
    """
    result = ModuleResult(module_name="reputation")

    try:
        e164 = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.E164
        )
        region = phonenumbers.region_code_for_number(parsed) or ""

        # Build spam check URLs
        spam_urls = _build_spam_urls(e164, region)

        # Organize by type
        by_type = {}
        for entry in spam_urls:
            dtype = entry["type"]
            if dtype not in by_type:
                by_type[dtype] = {}
            by_type[dtype][entry["service"]] = entry["url"]
            result.urls.append(entry["url"])

        # Try ShouldIAnswer for automated check
        try:
            clean = re.sub(r"\D", "", e164)
            resp = requests.get(
                f"https://www.shouldianswer.com/phone-number/{clean}",
                headers=_HEADERS,
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                page = resp.text.lower()
                if "negative" in page or "spam" in page or "scam" in page:
                    result.data["ShouldIAnswer"] = "⚠️ Negative reports found"
                elif "positive" in page or "safe" in page:
                    result.data["ShouldIAnswer"] = "✅ Positive reputation"
                else:
                    result.data["ShouldIAnswer"] = "ℹ️ No reports found"
        except Exception:
            result.data["ShouldIAnswer"] = "🔗 Manual check required"

        # Add categorized URLs
        for dtype, services in by_type.items():
            result.data[dtype] = services

        # Calculate risk score (will be enhanced by data from other modules)
        risk = _calculate_risk_score(result.data)
        # Insert risk score at the top
        risk_data = dict(risk)
        risk_data.update(result.data)
        result.data = risk_data

        result.success = True

    except Exception as e:
        result.errors.append(f"Reputation lookup failed: {e}")

    return result
