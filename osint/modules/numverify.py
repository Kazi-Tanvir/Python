"""
API Validation Module (NumVerify, AbstractAPI, IPQualityScore)
==============================================================
Queries external phone validation APIs for carrier data,
fraud scoring, line type, and active status.
All APIs have free tiers — keys are optional but recommended.
"""

import requests
import phonenumbers

from shared.config import get_env
from osint.report import ModuleResult

# Timeout for all API requests (seconds)
_TIMEOUT = 10


def _query_numverify(e164: str) -> dict | None:
    """
    Query NumVerify API.
    Free tier: 100 requests/month.
    Docs: https://numverify.com/documentation
    """
    api_key = get_env("NUMVERIFY_API_KEY")
    if not api_key:
        return None

    # NumVerify free tier requires HTTP (not HTTPS)
    url = "http://apilayer.net/api/validate"
    params = {
        "access_key": api_key,
        "number": e164.lstrip("+"),
        "format": 1,
    }

    try:
        resp = requests.get(url, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if data.get("valid") is not None:
            return {
                "Valid": "✅ Yes" if data.get("valid") else "❌ No",
                "Local Format": data.get("local_format", "—"),
                "International Format": data.get("international_format", "—"),
                "Country": f"{data.get('country_name', '?')} ({data.get('country_code', '?')})",
                "Location": data.get("location", "—"),
                "Carrier": data.get("carrier", "—"),
                "Line Type": data.get("line_type", "—"),
            }
    except Exception:
        pass

    return None


def _query_abstract_api(e164: str) -> dict | None:
    """
    Query AbstractAPI Phone Validation.
    Free tier: 100 requests/month.
    Docs: https://www.abstractapi.com/api/phone-validation-api
    """
    api_key = get_env("ABSTRACT_API_KEY")
    if not api_key:
        return None

    url = "https://phonevalidation.abstractapi.com/v1/"
    params = {
        "api_key": api_key,
        "phone": e164,
    }

    try:
        resp = requests.get(url, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if data.get("phone"):
            return {
                "Valid": "✅ Yes" if data.get("valid") else "❌ No",
                "Phone": data.get("phone", "—"),
                "Country": f"{data.get('country', {}).get('name', '?')} ({data.get('country', {}).get('code', '?')})",
                "Location": data.get("location", "—"),
                "Carrier": data.get("carrier", "—"),
                "Type": data.get("type", "—"),
            }
    except Exception:
        pass

    return None


def _query_ipqualityscore(e164: str) -> dict | None:
    """
    Query IPQualityScore Phone Reputation API.
    Free tier: 200 requests/month.
    Provides fraud scoring, spam risk, active status, and more.
    Docs: https://www.ipqualityscore.com/documentation/phone-number-validation-api
    """
    api_key = get_env("IPQUALITYSCORE_API_KEY")
    if not api_key:
        return None

    clean_number = e164.lstrip("+")
    url = f"https://ipqualityscore.com/api/json/phone/{api_key}/{clean_number}"

    try:
        resp = requests.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if data.get("success"):
            result = {
                "Valid": "✅ Yes" if data.get("valid") else "❌ No",
                "Active": "✅ Yes" if data.get("active") else "❌ No / Unknown",
                "Fraud Score": f"{data.get('fraud_score', '?')}/100",
                "Recent Abuse": "⚠️ Yes" if data.get("recent_abuse") else "✅ No",
                "VOIP": "📡 Yes" if data.get("VOIP") else "No",
                "Prepaid": "Yes" if data.get("prepaid") else "No",
                "Risky": "⚠️ Yes" if data.get("risky") else "✅ No",
                "Carrier": data.get("carrier", "—"),
                "Line Type": data.get("line_type", "—"),
                "Country": data.get("country", "—"),
                "Region": data.get("region", "—"),
                "City": data.get("city", "—"),
                "Zip Code": data.get("zip_code", "—"),
                "Dialing Code": data.get("dialing_code", "—"),
                "Do Not Call": "📵 Yes" if data.get("do_not_call") else "No",
            }
            return result
    except Exception:
        pass

    return None


def lookup(phone_raw: str, parsed: phonenumbers.PhoneNumber) -> ModuleResult:
    """
    Query all available phone validation APIs.

    Tries NumVerify → AbstractAPI → IPQualityScore.
    Results from all available APIs are merged into the output.
    """
    result = ModuleResult(module_name="numverify")
    e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

    apis_tried = 0
    apis_succeeded = 0

    # NumVerify
    numverify_data = _query_numverify(e164)
    if numverify_data:
        result.data["numverify"] = numverify_data
        apis_succeeded += 1
    apis_tried += 1 if get_env("NUMVERIFY_API_KEY") else 0

    # AbstractAPI
    abstract_data = _query_abstract_api(e164)
    if abstract_data:
        result.data["abstract_api"] = abstract_data
        apis_succeeded += 1
    apis_tried += 1 if get_env("ABSTRACT_API_KEY") else 0

    # IPQualityScore
    ipqs_data = _query_ipqualityscore(e164)
    if ipqs_data:
        result.data["ipqualityscore"] = ipqs_data
        apis_succeeded += 1
    apis_tried += 1 if get_env("IPQUALITYSCORE_API_KEY") else 0

    if apis_tried == 0:
        result.data["Status"] = "No API keys configured"
        result.data["Help"] = (
            "Add any of these to your .env file for enhanced lookups:\n"
            "  NUMVERIFY_API_KEY      — numverify.com (free: 100/mo)\n"
            "  ABSTRACT_API_KEY       — abstractapi.com (free: 100/mo)\n"
            "  IPQUALITYSCORE_API_KEY — ipqualityscore.com (free: 200/mo)"
        )
        result.success = True  # Not a failure, just no keys
    elif apis_succeeded > 0:
        result.success = True
    else:
        result.errors.append("All API queries failed. Check your API keys and network.")

    return result
